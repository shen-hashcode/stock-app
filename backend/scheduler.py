from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import json
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "8"))
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "30"))

scheduler = BackgroundScheduler()


def daily_strategy_run():
    """每天定时执行所有活跃策略"""
    from database import SessionLocal, Strategy, StrategyResult
    from stock_service import get_stock_list, get_realtime_quote
    from strategies.builtin import STRATEGIES
    
    logger.info(f"开始执行定时任务: {datetime.now()}")
    
    db = SessionLocal()
    try:
        strategies = db.query(Strategy).filter(Strategy.is_active == True).all()
        
        if not strategies:
            logger.info("没有活跃策略")
            return
        
        stock_list = get_stock_list()
        today = datetime.now().strftime("%Y-%m-%d")
        
        for strategy in strategies:
            try:
                logger.info(f"执行策略: {strategy.name} (ID: {strategy.id})")
                
                conditions = json.loads(strategy.conditions) if strategy.conditions else {}
                strategy_type = conditions.get("type", "")
                
                if strategy_type == "custom" and strategy.script_code:
                    namespace = {}
                    exec(
                        "from stock_service import get_kline_data, get_realtime_quote\n" + strategy.script_code,
                        namespace
                    )
                    check_func = namespace.get('check_stock')
                elif strategy_type in STRATEGIES:
                    builtin = STRATEGIES[strategy_type]
                    params = {k: v.get("default") for k, v in builtin["params"].items()}
                    params.update(conditions.get("params", {}))
                    check_func = lambda stock, func=builtin["func"], p=params: func(stock, **p)
                else:
                    continue
                
                results = []
                for stock in stock_list:
                    try:
                        if check_func(stock):
                            quote = get_realtime_quote(stock['code'], stock['market'])
                            stock['quote'] = quote
                            results.append(stock)
                    except:
                        continue
                
                result_record = StrategyResult(
                    strategy_id=strategy.id,
                    run_date=today,
                    stocks_json=json.dumps(results, ensure_ascii=False)
                )
                db.add(result_record)
                
                logger.info(f"策略 {strategy.name} 执行完成，找到 {len(results)} 只股票")
                
            except Exception as e:
                logger.error(f"策略 {strategy.name} 执行失败: {e}")
                continue
        
        db.commit()
        logger.info("定时任务执行完成")
        
    except Exception as e:
        logger.error(f"定时任务执行异常: {e}")
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(
        daily_strategy_run,
        CronTrigger(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE),
        id="daily_strategy",
        name="每日策略执行",
        replace_existing=True
    )
    scheduler.start()
    logger.info(f"定时任务已启动，每天 {SCHEDULE_HOUR}:{SCHEDULE_MINUTE} 执行")


def stop_scheduler():
    scheduler.shutdown()
