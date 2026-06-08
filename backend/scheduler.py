"""
定时任务调度模块。

调度器：APScheduler BackgroundScheduler，在 FastAPI lifespan 中启动。

注册的任务：
1. daily_strategy_run            —— 每天 08:30，跑全部启用的用户策略
2. warmup_builtin_strategies     —— 每天 16:00，预热全部 6 个内置策略并回填缓存
3. check_expired_subscriptions   —— 每天 00:05，把到期订阅置 expired

环境变量：
    SCHEDULE_HOUR / SCHEDULE_MINUTE              用户策略执行时间，默认 08:30
    BUILTIN_WARMUP_HOUR / BUILTIN_WARMUP_MINUTE  内置策略预热时间，默认 16:00
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import asyncio
import json
import os
from dotenv import load_dotenv

from logger import logger

load_dotenv()


# ============================================================
# 配置参数
# ============================================================

SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "8"))
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "30"))

BUILTIN_WARMUP_HOUR = int(os.getenv("BUILTIN_WARMUP_HOUR", "14"))
BUILTIN_WARMUP_MINUTE = int(os.getenv("BUILTIN_WARMUP_MINUTE", "20"))

scheduler = BackgroundScheduler()


# ============================================================
# 定时任务函数
# ============================================================

def daily_strategy_run():
    """
    每天定时执行全部启用的用户策略。

    流程：查询 is_active=True 的策略 → 获取全量股票 → 逐策略筛选 → 写库。
    单个策略异常不影响其他策略；裸异常已禁用，所有失败都会写日志。
    """
    from database import SessionLocal, Strategy, StrategyResult
    from stock_service import get_stock_list, get_realtime_quote
    from strategies.builtin import STRATEGIES as all_builtin

    logger.info(f"开始执行用户策略定时任务: {datetime.now()}")

    db = SessionLocal()
    try:
        strategies = db.query(Strategy).filter(Strategy.is_active == True).all()
        if not strategies:
            logger.info("没有启用的用户策略，跳过")
            return

        stock_list = get_stock_list()
        today = datetime.now().strftime("%Y-%m-%d")

        for strategy in strategies:
            try:
                logger.info(f"执行策略: {strategy.name} (ID: {strategy.id})")

                conditions = json.loads(strategy.conditions) if strategy.conditions else {}
                strategy_type = conditions.get("type", "")

                if strategy_type == "custom" and strategy.script_code:
                    # AI/人工自定义策略：动态执行脚本拿 check_stock
                    namespace = {}
                    exec(
                        "from stock_service import get_kline_data, get_realtime_quote\n" + strategy.script_code,
                        namespace,
                    )
                    check_func = namespace.get('check_stock')
                elif strategy_type in all_builtin:
                    # 内置策略：用 func + 默认参数 + 用户覆盖参数
                    builtin = all_builtin[strategy_type]
                    params = {k: v.get("default") for k, v in builtin["params"].items()}
                    params.update(conditions.get("params", {}))
                    check_func = lambda stock, func=builtin["func"], p=params: func(stock, **p)
                else:
                    logger.warning(f"未知策略类型 {strategy_type}，跳过 (策略 {strategy.id})")
                    continue

                results = []
                for stock in stock_list:
                    try:
                        if check_func(stock):
                            quote = get_realtime_quote(stock['code'], stock['market'])
                            stock['quote'] = quote
                            results.append(stock)
                    except Exception as e:
                        logger.debug(f"股票 {stock.get('code')} 筛选异常: {e}")
                        continue

                db.add(StrategyResult(
                    strategy_id=strategy.id,
                    user_id=strategy.user_id,
                    run_date=today,
                    stocks_json=json.dumps(results, ensure_ascii=False),
                ))
                logger.info(f"策略 {strategy.name} 完成，命中 {len(results)} 只")
            except Exception as e:
                logger.error(f"策略 {strategy.name} 执行失败: {e}")
                continue

        db.commit()
        logger.info("用户策略定时任务执行完成")
    except Exception as e:
        logger.error(f"用户策略定时任务异常: {e}")
    finally:
        db.close()


def warmup_builtin_strategies():
    """
    每天 16:00 预跑全部 6 个内置策略。
    结果写入 strategy_results（strategy_id=0、stocks_json 含 _strategy_key），
    并回填 Redis 缓存（TTL 到当日 24 点），便于用户当日访问命中。
    """
    from database import SessionLocal, StrategyResult
    from stock_service import get_stock_list
    from strategies.builtin import STRATEGIES as all_builtin
    from main import _run_strategy_sync
    from redis_client import get_redis, make_cache_key, get_ttl_seconds, invalidate_results_cache

    logger.info(f"开始预热内置策略，共 {len(all_builtin)} 个")

    stock_list = get_stock_list()
    today = datetime.now().strftime("%Y-%m-%d")
    redis = get_redis()

    db = SessionLocal()
    try:
        for key, meta in all_builtin.items():
            try:
                params = {k: v.get("default") for k, v in meta["params"].items()}
                check_func = lambda stock, func=meta["func"], p=params: func(stock, **p)

                logger.info(f"[预热] 执行 {key} ({meta['name']})")
                results = _run_strategy_sync(check_func, stock_list)

                db_data = {
                    "_strategy_key": key,
                    "stocks": results,
                    "params": params,
                }
                db.add(StrategyResult(
                    strategy_id=0,
                    user_id=0,
                    run_date=today,
                    stocks_json=json.dumps(db_data, ensure_ascii=False),
                ))
                db.commit()

                # 失效"当天结果"聚合缓存，让结果页立刻能读到这条新数据
                try:
                    asyncio.run(invalidate_results_cache())
                except Exception as e:
                    logger.warning(f"[预热] 失效 results 缓存失败 {key}: {e}")

                if redis:
                    cache_key = make_cache_key("builtin", key, params)
                    result_data = {
                        "count": len(results),
                        "stocks": results,
                        "params": params,
                        "cached_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    try:
                        ttl = get_ttl_seconds()
                        asyncio.run(redis.set(
                            cache_key, json.dumps(result_data, ensure_ascii=False), ex=ttl,
                        ))
                    except Exception as e:
                        logger.warning(f"[预热] Redis 回填失败 {key}: {e}")

                logger.info(f"[预热] {key} 完成，命中 {len(results)} 只")
            except Exception as e:
                logger.error(f"[预热] {key} 失败: {e}")
                continue
    finally:
        db.close()
    logger.info("内置策略预热完成")


def check_expired_subscriptions():
    """每天 00:05 把 status=paid 且已过期的订阅标记为 expired。"""
    from database import SessionLocal, UserSubscription

    db = SessionLocal()
    try:
        expired = db.query(UserSubscription).filter(
            UserSubscription.status == "paid",
            UserSubscription.expired_at <= datetime.now(),
        ).all()
        for sub in expired:
            sub.status = "expired"
        if expired:
            db.commit()
            logger.info(f"标记 {len(expired)} 个过期订阅")
    except Exception as e:
        logger.error(f"检查过期订阅异常: {e}")
    finally:
        db.close()


# ============================================================
# 调度器管理
# ============================================================

def start_scheduler():
    """启动定时任务，注册三个 cron job。FastAPI lifespan 启动时调用。"""
    scheduler.add_job(
        daily_strategy_run,
        CronTrigger(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE),
        id="daily_strategy",
        name="每日用户策略执行",
        replace_existing=True,
    )
    scheduler.add_job(
        warmup_builtin_strategies,
        CronTrigger(hour=BUILTIN_WARMUP_HOUR, minute=BUILTIN_WARMUP_MINUTE),
        id="warmup_builtin",
        name="内置策略预热",
        replace_existing=True,
    )
    scheduler.add_job(
        check_expired_subscriptions,
        CronTrigger(hour=0, minute=5),
        id="check_expired_subs",
        name="检查过期订阅",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        f"定时任务已启动："
        f"每天 {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d} 执行用户策略，"
        f"{BUILTIN_WARMUP_HOUR:02d}:{BUILTIN_WARMUP_MINUTE:02d} 预热内置策略，"
        f"00:05 检查过期订阅"
    )