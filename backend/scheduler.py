"""
智能选股助手 - 定时任务调度模块

本模块负责：
1. 配置定时任务执行时间
2. 定时执行所有活跃策略
3. 保存策略执行结果到数据库

定时任务执行流程：
1. 从数据库读取所有启用的策略
2. 获取全量股票列表
3. 遍历执行每个策略
4. 保存筛选结果到strategy_results表

配置项（.env文件）：
- SCHEDULE_HOUR: 执行小时（0-23），默认8
- SCHEDULE_MINUTE: 执行分钟（0-59），默认30

使用方式：
    from scheduler import start_scheduler, stop_scheduler
    
    # 启动定时任务
    start_scheduler()
    
    # 停止定时任务
    stop_scheduler()
"""

# ============================================================
# 第一部分：导入依赖
# ============================================================

from apscheduler.schedulers.background import BackgroundScheduler  # 后台调度器
from apscheduler.triggers.cron import CronTrigger  # Cron触发器
from datetime import datetime
import json
import logging
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 创建日志记录器
logger = logging.getLogger(__name__)


# ============================================================
# 第二部分：配置参数
# ============================================================

# 从环境变量读取定时任务执行时间
# 默认每天8:30执行
SCHEDULE_HOUR = int(os.getenv("SCHEDULE_HOUR", "8"))
SCHEDULE_MINUTE = int(os.getenv("SCHEDULE_MINUTE", "30"))

# 创建后台调度器实例
# BackgroundScheduler: 在后台线程运行，不阻塞主进程
scheduler = BackgroundScheduler()


# ============================================================
# 第三部分：定时任务函数
# ============================================================

def daily_strategy_run():
    """
    每天定时执行所有活跃策略
    
    这是定时任务的核心函数，负责：
    1. 查询所有is_active=True的策略
    2. 获取全量股票列表
    3. 遍历执行每个策略
    4. 保存筛选结果到数据库
    
    执行逻辑：
    - 对于内置策略：从STRATEGIES字典获取函数和参数
    - 对于AI自定义策略：动态执行Python脚本
    
    异常处理：
    - 单个策略执行失败不影响其他策略
    - 所有异常都会记录到日志
    
    调用链:
        APScheduler定时触发 -> daily_strategy_run()
        -> 查询活跃策略 -> 获取股票列表 -> 执行策略 -> 保存结果
    """
    # 导入本地模块（避免循环导入）
    from database import SessionLocal, Strategy, StrategyResult
    from stock_service import get_stock_list, get_realtime_quote
    from strategies.builtin import STRATEGIES
    
    logger.info(f"开始执行定时任务: {datetime.now()}")
    
    # 创建数据库会话
    db = SessionLocal()
    try:
        # 查询所有启用的策略
        strategies = db.query(Strategy).filter(Strategy.is_active == True).all()
        
        if not strategies:
            logger.info("没有活跃策略")
            return
        
        # 获取全量股票列表（约5000只）
        stock_list = get_stock_list()
        today = datetime.now().strftime("%Y-%m-%d")
        
        # 遍历执行每个策略
        for strategy in strategies:
            try:
                logger.info(f"执行策略: {strategy.name} (ID: {strategy.id})")
                
                # 解析策略条件
                conditions = json.loads(strategy.conditions) if strategy.conditions else {}
                strategy_type = conditions.get("type", "")
                
                # 根据策略类型构建检查函数
                if strategy_type == "custom" and strategy.script_code:
                    # AI自定义策略：动态执行脚本
                    namespace = {}
                    exec(
                        "from stock_service import get_kline_data, get_realtime_quote\n" + strategy.script_code,
                        namespace
                    )
                    check_func = namespace.get('check_stock')
                elif strategy_type in STRATEGIES:
                    # 内置策略：获取函数和参数
                    builtin = STRATEGIES[strategy_type]
                    params = {k: v.get("default") for k, v in builtin["params"].items()}
                    params.update(conditions.get("params", {}))
                    check_func = lambda stock, func=builtin["func"], p=params: func(stock, **p)
                else:
                    continue  # 未知策略类型，跳过
                
                # 遍历股票执行筛选
                results = []
                for stock in stock_list:
                    try:
                        if check_func(stock):
                            # 符合条件，获取实时行情
                            quote = get_realtime_quote(stock['code'], stock['market'])
                            stock['quote'] = quote
                            results.append(stock)
                    except:
                        continue  # 跳过异常股票
                
                # 保存筛选结果
                result_record = StrategyResult(
                    strategy_id=strategy.id,
                    run_date=today,
                    stocks_json=json.dumps(results, ensure_ascii=False)
                )
                db.add(result_record)
                
                logger.info(f"策略 {strategy.name} 执行完成，找到 {len(results)} 只股票")
                
            except Exception as e:
                logger.error(f"策略 {strategy.name} 执行失败: {e}")
                continue  # 单个策略失败不影响其他策略
        
        # 提交所有结果到数据库
        db.commit()
        logger.info("定时任务执行完成")
        
    except Exception as e:
        logger.error(f"定时任务执行异常: {e}")
    finally:
        db.close()  # 确保关闭数据库连接


# ============================================================
# 第四部分：调度器管理
# ============================================================

def start_scheduler():
    """
    启动定时任务调度器
    
    添加daily_strategy_run任务到调度器，并启动调度器
    任务会按照SCHEDULE_HOUR:SCHEDULE_MINUTE配置的时间每天执行
    
    调用时机:
        FastAPI应用启动时（main.py的lifespan函数中）
    
    调用链:
        main.py -> lifespan() -> start_scheduler()
    """
    # 添加定时任务
    scheduler.add_job(
        daily_strategy_run,
        CronTrigger(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE),  # Cron表达式
        id="daily_strategy",
        name="每日策略执行",
        replace_existing=True  # 替换已存在的同名任务
    )
    
    # 启动调度器
    scheduler.start()
    logger.info(f"定时任务已启动，每天 {SCHEDULE_HOUR}:{SCHEDULE_MINUTE} 执行")


def stop_scheduler():
    """
    停止定时任务调度器
    
    关闭调度器，停止所有定时任务
    
    调用时机:
        应用关闭时（可选）
    """
    scheduler.shutdown()
