"""
智能选股助手 - FastAPI后端主应用

本模块是整个后端服务的入口，负责：
1. 定义所有API接口
2. 初始化数据库和定时任务
3. 处理用户、策略、结果的CRUD操作
4. 调用策略引擎执行选股

启动方式: python main.py
服务地址: http://localhost:8000
"""

# ============================================================
# 第一部分：导入依赖
# ============================================================

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from contextlib import asynccontextmanager
import json
import asyncio
from datetime import datetime

# 导入本地模块
from database import init_db, get_db, User, Strategy, StrategyResult  # 数据库模型和工具
from stock_service import get_stock_list, get_stock_list_quick, run_strategy, get_kline_data, get_realtime_quote  # 股票数据服务
from strategies.builtin import STRATEGIES as BUILTIN_STRATEGIES  # 内置策略
from strategies.steady_rise import STRATEGIES as STEADY_RISE_STRATEGIES  # 稳步上涨策略

# 合并所有内置策略到一个字典中，方便统一调用
STRATEGIES = {**BUILTIN_STRATEGIES, **STEADY_RISE_STRATEGIES}
from scheduler import start_scheduler  # 定时任务调度器


# ============================================================
# 第二部分：应用初始化
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理器
    
    在FastAPI应用启动时执行初始化操作：
    - 启动定时任务调度器
    
    在应用关闭时执行清理操作（目前为空）
    """
    start_scheduler()  # 启动定时任务
    yield  # 应用运行中...


# 创建FastAPI应用实例
app = FastAPI(title="智能选股助手", lifespan=lifespan)

# 添加CORS中间件，允许微信开发者工具的请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化数据库，创建所有表结构
init_db()


# ============================================================
# 第三部分：Pydantic数据模型（请求/响应结构定义）
# ============================================================

class UserCreate(BaseModel):
    """
    用户创建请求模型
    
    用于微信登录时创建或获取用户信息
    
    属性:
        openid: 微信用户唯一标识（由wx.login获取）
        nickname: 用户昵称（可选）
        phone: 手机号码（可选）
    """
    openid: str
    nickname: Optional[str] = ""
    phone: Optional[str] = ""


class StrategyCreate(BaseModel):
    """
    策略创建请求模型
    
    用于创建内置策略的实例（用户选择内置策略并配置参数）
    
    属性:
        name: 策略名称
        description: 策略描述
        conditions: 策略条件配置（JSON格式），包含type和params
    """
    name: str
    description: str
    conditions: Optional[str] = "{}"


class CustomStrategyCreate(BaseModel):
    """
    自定义策略创建请求模型
    
    用于AI生成自定义策略（用户用自然语言描述选股条件）
    
    属性:
        name: 策略名称
        description: 用自然语言描述的选股条件
    """
    name: str
    description: str


class StrategyResponse(BaseModel):
    """
    策略响应模型
    
    用于返回策略详细信息
    
    属性:
        id: 策略ID
        name: 策略名称
        description: 策略描述
        conditions: 策略条件（JSON字符串）
        script_code: AI生成的Python脚本代码（仅自定义策略）
        is_active: 是否启用
        created_at: 创建时间
    """
    id: int
    name: str
    description: str
    conditions: str
    script_code: Optional[str]
    is_active: bool
    created_at: datetime
    
    model_config = {"from_attributes": True}  # 允许从ORM对象创建


# ============================================================
# 第四部分：用户管理接口
# ============================================================

@app.post("/api/users")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    """
    创建或获取用户
    
    工作流程：
    1. 根据openid查询用户是否已存在
    2. 如果存在，直接返回用户信息
    3. 如果不存在，创建新用户并返回
    
    请求参数:
        user: UserCreate - 用户信息
        db: Session - 数据库会话（自动注入）
    
    返回:
        {"code": 0, "data": {"id": 用户ID, "openid": 微信openid}}
    
    调用链:
        小程序wx.login -> 获取code -> 调用此接口 -> 返回用户ID
    """
    # 查询用户是否已存在
    db_user = db.query(User).filter(User.openid == user.openid).first()
    if db_user:
        # 用户已存在，直接返回
        return {"code": 0, "data": {"id": db_user.id, "openid": db_user.openid}}
    
    # 创建新用户
    db_user = User(openid=user.openid, nickname=user.nickname, phone=user.phone)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)  # 刷新以获取自增ID
    return {"code": 0, "data": {"id": db_user.id, "openid": db_user.openid}}


# ============================================================
# 第五部分：策略管理接口
# ============================================================

@app.get("/api/strategies/builtin")
def get_builtin_strategies():
    """
    获取所有内置策略列表
    
    返回系统预置的所有选股策略及其参数配置
    
    返回:
        {
            "code": 0,
            "data": [
                {
                    "key": "rise_pullback",  // 策略唯一标识
                    "name": "涨幅回调",      // 策略名称
                    "description": "...",    // 策略描述
                    "params": {...}          // 参数配置
                },
                ...
            ]
        }
    
    调用链:
        小程序首页 -> 加载策略列表 -> 调用此接口 -> 展示热门策略
    """
    strategies = []
    for key, value in STRATEGIES.items():
        strategies.append({
            "key": key,
            "name": value["name"],
            "description": value["description"],
            "params": value["params"]
        })
    return {"code": 0, "data": strategies}


@app.post("/api/strategies")
def create_strategy(user_id: int, strategy: StrategyCreate, db: Session = Depends(get_db)):
    """
    创建用户策略
    
    用户选择内置策略后，保存策略配置到数据库
    
    参数:
        user_id: 用户ID（查询参数）
        strategy: 策略信息（请求体）
        db: 数据库会话
    
    请求体:
        {
            "name": "我的涨幅回调策略",
            "description": "前3日涨幅超过13%时回调买入",
            "conditions": "{\"type\": \"rise_pullback\", \"params\": {\"days\": 3}}"
        }
    
    返回:
        {"code": 0, "data": {"id": 策略ID}}
    
    调用链:
        小程序策略页 -> 选择内置策略 -> 配置参数 -> 调用此接口 -> 保存到数据库
    """
    db_strategy = Strategy(
        user_id=user_id,
        name=strategy.name,
        description=strategy.description,
        conditions=strategy.conditions  # JSON格式存储策略类型和参数
    )
    db.add(db_strategy)
    db.commit()
    db.refresh(db_strategy)
    return {"code": 0, "data": {"id": db_strategy.id}}


@app.post("/api/strategies/custom")
async def create_custom_strategy(user_id: int, strategy: CustomStrategyCreate, db: Session = Depends(get_db)):
    """
    创建AI自定义策略
    
    用户用自然语言描述选股条件，系统调用AI大模型生成Python脚本
    
    参数:
        user_id: 用户ID
        strategy: 包含策略名称和自然语言描述
        db: 数据库会话
    
    请求体:
        {
            "name": "我的自定义策略",
            "description": "前3天累计涨幅超过15%，第4天回调，市值大于100亿"
        }
    
    返回:
        {
            "code": 0,
            "data": {
                "id": 策略ID,
                "script": "生成的Python脚本代码"
            }
        }
    
    调用链:
        小程序首页 -> 输入选股描述 -> 点击"AI生成策略" -> 调用此接口
        -> 调用AI API生成代码 -> 保存策略和脚本到数据库
    """
    from stock_service import generate_strategy_script, extract_strategy_name
    
    try:
        # 调用AI大模型生成策略脚本
        script_code = await generate_strategy_script(strategy.description)
        
        # 从描述中提取策略名称
        name = extract_strategy_name(strategy.name)
        
        # 保存策略到数据库
        db_strategy = Strategy(
            user_id=user_id,
            name=name,
            description=strategy.description,
            script_code=script_code,  # AI生成的Python代码
            conditions=json.dumps({"type": "custom", "description": strategy.description})
        )
        db.add(db_strategy)
        db.commit()
        db.refresh(db_strategy)
        
        return {"code": 0, "data": {"id": db_strategy.id, "script": script_code}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/strategies/{user_id}")
def get_user_strategies(user_id: int, db: Session = Depends(get_db)):
    """
    获取用户的所有策略列表
    
    查询指定用户创建的所有策略（包括内置策略实例和AI自定义策略）
    
    参数:
        user_id: 用户ID
        db: 数据库会话
    
    返回:
        {
            "code": 0,
            "data": [
                {
                    "id": 1,
                    "name": "涨幅回调策略",
                    "description": "...",
                    "conditions": "{...}",
                    "is_active": true,
                    ...
                }
            ]
        }
    
    调用链:
        小程序策略tab -> 加载策略列表 -> 调用此接口 -> 展示用户策略
    """
    strategies = db.query(Strategy).filter(Strategy.user_id == user_id).all()
    return {"code": 0, "data": strategies}


# ============================================================
# 第六部分：策略执行接口
# ============================================================

@app.post("/api/strategies/{strategy_id}/run")
async def run_strategy_by_id(strategy_id: int, db: Session = Depends(get_db)):
    """
    执行指定策略
    
    根据策略ID执行策略，遍历股票池筛选符合条件的股票
    
    执行流程：
    1. 从数据库读取策略配置
    2. 解析策略类型和参数
    3. 获取全量股票列表
    4. 遍历执行策略函数
    5. 保存筛选结果到数据库
    
    参数:
        strategy_id: 策略ID
        db: 数据库会话
    
    返回:
        {
            "code": 0,
            "data": {
                "count": 符合条件的股票数量,
                "stocks": [股票列表]
            }
        }
    
    调用链:
        小程序策略页 -> 点击"立即执行" -> 调用此接口
        -> 获取股票池 -> 执行策略筛选 -> 保存结果 -> 返回结果
    """
    # 查询策略
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")
    
    try:
        # 解析策略条件（JSON格式）
        conditions = json.loads(strategy.conditions) if strategy.conditions else {}
        strategy_type = conditions.get("type", "")
        
        # 根据策略类型构建检查函数
        if strategy_type == "custom" and strategy.script_code:
            # AI自定义策略：动态执行Python脚本
            script_code = strategy.script_code
            namespace = {}
            # 在隔离的命名空间中执行脚本
            exec(
                "from stock_service import get_kline_data, get_realtime_quote\n" + script_code,
                namespace
            )
            check_func = namespace.get('check_stock')  # 获取脚本中定义的check_stock函数
        elif strategy_type in STRATEGIES:
            # 内置策略：从字典获取策略函数和默认参数
            builtin_strategy = STRATEGIES[strategy_type]
            params = {k: v.get("default") for k, v in builtin_strategy["params"].items()}
            params.update(conditions.get("params", {}))  # 用用户自定义参数覆盖默认值
            # 创建lambda函数封装策略调用
            check_func = lambda stock, func=builtin_strategy["func"], p=params: func(stock, **p)
        else:
            raise HTTPException(status_code=400, detail="未知策略类型")
        
        # 获取股票列表（限制200只，加快响应）
        stock_list = get_stock_list_quick(200)
        
        # 使用线程池并发执行筛选
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = []

        def process_stock(stock):
            try:
                if check_func(stock):
                    quote = get_realtime_quote(stock['code'], stock['market'])
                    stock['quote'] = quote
                    return stock
            except:
                pass
            return None

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_stock, s): s for s in stock_list}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
        
        # 保存筛选结果到数据库
        today = datetime.now().strftime("%Y-%m-%d")
        result_record = StrategyResult(
            strategy_id=strategy_id,
            run_date=today,
            stocks_json=json.dumps(results, ensure_ascii=False)  # JSON格式存储
        )
        db.add(result_record)
        db.commit()
        
        return {"code": 0, "data": {"count": len(results), "stocks": results}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/strategies/builtin/{strategy_key}/run")
async def run_builtin_strategy(
    strategy_key: str,
    params: Optional[dict] = None,
    stock_limit: int = 0
):
    """
    直接运行内置策略（无需先创建策略）
    
    这是一个快捷接口，可以直接调用内置策略并传入自定义参数
    
    参数:
        strategy_key: 策略key（如 "rise_pullback", "steady_rise"）
        params: 自定义参数（可选，覆盖默认值）
        stock_limit: 限制扫描股票数量（0表示全部）
    
    请求示例:
        POST /api/strategies/builtin/steady_rise/run?stock_limit=1000
        Body: {"days": 5, "min_pct": 0, "max_pct": 3, "market_cap_min": 0}
    
    返回:
        {
            "code": 0,
            "data": {
                "count": 符合条件的数量,
                "stocks": [股票列表],
                "params": 实际使用的参数
            }
        }
    
    调用链:
        API调用/测试 -> 直接指定策略key和参数 -> 获取股票池 -> 执行筛选 -> 返回结果
    """
    # 验证策略是否存在
    if strategy_key not in STRATEGIES:
        raise HTTPException(status_code=404, detail="策略不存在")

    try:
        # 获取策略配置
        builtin_strategy = STRATEGIES[strategy_key]
        
        # 构建参数：先用默认值，再用用户传入的参数覆盖
        strategy_params = {k: v.get("default") for k, v in builtin_strategy["params"].items()}
        if params:
            strategy_params.update(params)

        # 创建检查函数
        check_func = lambda stock, func=builtin_strategy["func"], p=strategy_params: func(stock, **p)

        # 获取股票列表（默认限制200只，加快响应）
        stock_list = get_stock_list_quick(stock_limit if stock_limit > 0 else 200)

        # 使用线程池并发执行筛选
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = []

        def process_stock(stock):
            try:
                if check_func(stock):
                    quote = get_realtime_quote(stock['code'], stock['market'])
                    stock['quote'] = quote
                    return stock
            except:
                pass
            return None

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_stock, s): s for s in stock_list}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        return {"code": 0, "data": {"count": len(results), "stocks": results, "params": strategy_params}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 第七部分：结果查询接口
# ============================================================

@app.get("/api/results/{strategy_id}")
def get_strategy_results(strategy_id: int, limit: int = 10, db: Session = Depends(get_db)):
    """
    获取策略的历史执行结果
    
    查询指定策略的所有执行记录，按时间倒序排列
    
    参数:
        strategy_id: 策略ID
        limit: 返回记录数量限制（默认10条）
        db: 数据库会话
    
    返回:
        {
            "code": 0,
            "data": [
                {
                    "id": 结果ID,
                    "strategy_id": 策略ID,
                    "run_date": "2024-01-15",
                    "stocks_json": "[...]",  // 筛选结果JSON
                    "created_at": "2024-01-15T08:30:00"
                }
            ]
        }
    
    调用链:
        小程序结果tab -> 选择策略 -> 调用此接口 -> 展示历史结果
    """
    results = db.query(StrategyResult)\
        .filter(StrategyResult.strategy_id == strategy_id)\
        .order_by(StrategyResult.created_at.desc())\
        .limit(limit)\
        .all()
    return {"code": 0, "data": results}


# ============================================================
# 第八部分：股票信息接口
# ============================================================

@app.get("/api/stock/{code}")
def get_stock_info(code: str, market: str):
    """
    获取单只股票的详细信息
    
    返回股票的实时行情和最近10天的K线数据
    
    参数:
        code: 股票代码（如 "000001"）
        market: 市场（"sh"=上海, "sz"=深圳）
    
    返回:
        {
            "code": 0,
            "data": {
                "quote": {
                    "price": 10.96,        // 现价
                    "change_pct": 0.27,    // 涨跌幅(%)
                    "volume": 766628,      // 成交量
                    "market_cap": 2126.89  // 总市值(亿)
                },
                "kline": [                  // 最近10天K线
                    {
                        "day": "2024-01-15",
                        "open": 10.83,
                        "close": 10.86,
                        "high": 10.92,
                        "low": 10.83,
                        "volume": 793529
                    },
                    ...
                ]
            }
        }
    
    调用链:
        小程序结果页 -> 点击股票 -> 调用此接口 -> 展示股票详情
    """
    # 获取实时行情
    quote = get_realtime_quote(code, market)
    
    # 获取K线数据
    kline = get_kline_data(code, market)
    
    # 只返回最近10天的K线
    kline_data = []
    if kline is not None:
        kline_data = kline[-10:] if len(kline) > 10 else kline
    
    return {
        "code": 0,
        "data": {
            "quote": quote,
            "kline": kline_data
        }
    }


# ============================================================
# 第九部分：应用启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    # 启动uvicorn服务器，监听所有网络接口的8000端口
    uvicorn.run(app, host="0.0.0.0", port=8000)
