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

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from contextlib import asynccontextmanager
import json
import asyncio
import bcrypt
import time
from datetime import datetime, timedelta

from logger import logger

# 导入本地模块
from database import init_db, get_db, User, Strategy, StrategyResult, SubscriptionPackage, UserSubscription  # 数据库模型和工具
from stock_service import get_stock_list, run_strategy, get_kline_data, get_realtime_quote  # 股票数据服务
from redis_client import init_redis, close_redis, get_redis, make_cache_key, make_running_key, get_ttl_seconds
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
    - 初始化Redis连接
    - 启动定时任务调度器

    在应用关闭时执行清理操作：
    - 关闭Redis连接
    """
    try:
        await init_redis()
        logger.info("Redis连接成功")
    except Exception as e:
        logger.warning(f"Redis连接失败，策略缓存将不可用: {e}")
    start_scheduler()
    yield
    await close_redis()


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


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        body = b""
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()

        logger.info(f">>> {request.method} {request.url.path} query={dict(request.query_params)} body={body.decode('utf-8', errors='replace')[:2000]}")

        response = await call_next(request)
        duration = round((time.time() - start) * 1000, 1)
        logger.info(f"<<< {request.method} {request.url.path} status={response.status_code} {duration}ms")
        return response


app.add_middleware(RequestLoggingMiddleware)

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


class UserRegister(BaseModel):
    phone: str
    password: str
    nickname: Optional[str] = ""


class UserLogin(BaseModel):
    phone: str
    password: str


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


class CreateOrderRequest(BaseModel):
    """创建订阅订单请求"""
    package_id: int


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


@app.post("/api/register")
def register_user(user: UserRegister, db: Session = Depends(get_db)):
    """注册新用户（手机号+密码）"""
    if not user.phone or len(user.phone) != 11:
        return {"code": 1, "message": "请输入正确的11位手机号"}
    if not user.password or len(user.password) < 6:
        return {"code": 1, "message": "密码至少6位"}

    existing = db.query(User).filter(User.phone == user.phone).first()
    if existing:
        return {"code": 1, "message": "该手机号已注册"}

    hashed = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt())
    db_user = User(
        openid=f"phone_{user.phone}",
        phone=user.phone,
        nickname=user.nickname or f"用户{user.phone[-4:]}",
        password_hash=hashed.decode('utf-8')
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"code": 0, "data": {"id": db_user.id, "phone": db_user.phone, "nickname": db_user.nickname}}


@app.post("/api/login")
def login_user(user: UserLogin, db: Session = Depends(get_db)):
    """用户登录（手机号+密码）"""
    db_user = db.query(User).filter(User.phone == user.phone).first()
    if not db_user or not db_user.password_hash:
        return {"code": 1, "message": "手机号或密码错误"}

    if not bcrypt.checkpw(user.password.encode('utf-8'), db_user.password_hash.encode('utf-8')):
        return {"code": 1, "message": "手机号或密码错误"}

    return {"code": 0, "data": {"id": db_user.id, "phone": db_user.phone, "nickname": db_user.nickname}}


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
async def create_custom_strategy(
    user_id: int,
    strategy: CustomStrategyCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    生成自定义策略

    调用AI大模型生成Python脚本，保存到数据库后立即返回，
    同时异步推送通知给管理员。
    """
    from notify import notify_admins_new_strategy

    try:
        # 订阅检查
        _, pkg = get_user_active_subscription(db, user_id)
        if not pkg:
            return {"code": 2, "message": "请先订阅套餐后再创建自定义策略"}

        # 配额检查
        custom_count = db.query(Strategy).filter(
            Strategy.user_id == user_id,
            Strategy.conditions.like('%"type": "custom"%')
        ).count()
        if custom_count >= pkg.strategy_limit:
            return {"code": 3, "message": f"当前套餐最多创建{pkg.strategy_limit}个自定义策略，已达上限"}

        # 保存策略到数据库（不调用AI生成脚本，由管理员后续处理）
        db_strategy = Strategy(
            user_id=user_id,
            name=strategy.name,
            description=strategy.description,
            conditions=json.dumps({"type": "custom", "description": strategy.description})
        )
        db.add(db_strategy)
        db.commit()
        db.refresh(db_strategy)

        # 获取用户昵称
        user = db.query(User).filter(User.id == user_id).first()
        user_nickname = user.nickname if user else f"用户{user_id}"

        # 异步通知管理员
        background_tasks.add_task(
            notify_admins_new_strategy, user_id, db_strategy.id, strategy.name, user_nickname
        )

        return {"code": 0, "data": {"id": db_strategy.id}}
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
async def run_strategy_by_id(
    strategy_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    force: bool = False,
):
    """
    执行指定策略（异步执行 + Redis缓存）

    - 缓存命中：直接返回结果
    - 缓存未命中：触发后台异步执行，立即返回执行中状态
    - force=true：强制刷新缓存
    """
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")

    cache_key = make_cache_key("saved", str(strategy_id))
    running_key = make_running_key(cache_key)
    redis = get_redis()

    # Redis可用时检查缓存
    if redis and not force:
        try:
            cached = await redis.get(cache_key)
            if cached:
                result_data = json.loads(cached)
                result_data["status"] = "completed"
                result_data["from_cache"] = True
                return {"code": 0, "data": result_data}
        except Exception as e:
            logger.warning(f"Redis读取失败: {e}")

    # 分布式锁：SET NX 原子操作防止重复执行
    if redis:
        try:
            acquired = await redis.set(running_key, "1", nx=True, ex=300)
            if not acquired:
                return {"code": 0, "data": {"status": "running", "message": "策略正在执行中，请稍后查询"}}
        except Exception as e:
            logger.warning(f"Redis锁获取失败: {e}")

    background_tasks.add_task(
        _execute_saved_strategy_background, strategy_id, cache_key, running_key
    )
    return {"code": 0, "data": {"status": "running", "message": "策略已开始执行，请稍后查询"}}


@app.post("/api/strategies/builtin/{strategy_key}/run")
async def run_builtin_strategy(
    strategy_key: str,
    request: Request,
    background_tasks: BackgroundTasks,
    params: Optional[dict] = None,
    force: bool = False,
    db: Session = Depends(get_db),
):
    """
    直接运行内置策略（三级缓存：Redis → 数据库 → 异步执行）

    1. Redis缓存命中：直接返回
    2. 数据库当天结果命中：返回并回填Redis
    3. 都没有：触发后台异步执行，结果先存数据库再缓存Redis
    """
    if strategy_key not in STRATEGIES:
        raise HTTPException(status_code=404, detail="策略不存在")

    builtin_strategy = STRATEGIES[strategy_key]
    strategy_params = {k: v.get("default") for k, v in builtin_strategy["params"].items()}
    if params:
        strategy_params.update(params)

    cache_key = make_cache_key("builtin", strategy_key, strategy_params)
    running_key = make_running_key(cache_key)
    redis = get_redis()

    # 第一级：Redis缓存
    if redis and not force:
        try:
            cached = await redis.get(cache_key)
            if cached:
                result_data = json.loads(cached)
                result_data["status"] = "completed"
                result_data["from_cache"] = True
                return {"code": 0, "data": result_data}
        except Exception as e:
            logger.warning(f"Redis读取失败: {e}")

    # 第二级：数据库查询当天结果（内置策略结果strategy_id=0）
    if not force:
        today = datetime.now().strftime("%Y-%m-%d")
        db_result = db.query(StrategyResult).filter(
            StrategyResult.run_date == today,
            StrategyResult.strategy_id == 0,
        ).all()
        for r in db_result:
            try:
                meta = json.loads(r.stocks_json) if r.stocks_json else {}
                if isinstance(meta, dict) and meta.get("_strategy_key") == strategy_key:
                    stocks = meta.get("stocks", [])
                    result_data = {
                        "count": len(stocks),
                        "stocks": stocks,
                        "params": strategy_params,
                        "status": "completed",
                        "from_cache": False,
                        "from_db": True,
                        "cached_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
                    }
                    # 回填Redis
                    if redis:
                        try:
                            ttl = get_ttl_seconds()
                            await redis.set(cache_key, json.dumps(result_data, ensure_ascii=False), ex=ttl)
                        except Exception:
                            pass
                    return {"code": 0, "data": result_data}
            except (json.JSONDecodeError, AttributeError):
                continue

    # 第三级：异步执行
    if redis:
        try:
            acquired = await redis.set(running_key, "1", nx=True, ex=300)
            if not acquired:
                return {"code": 0, "data": {"status": "running", "message": "策略正在执行中，请稍后查询"}}
        except Exception as e:
            logger.warning(f"Redis锁获取失败: {e}")

    # 记录用户维度的执行中状态
    user_id = request.headers.get("X-User-Id", "")
    user_running_key = ""
    if redis and user_id:
        user_running_key = f"running:user:{user_id}:{strategy_key}"
        try:
            strategy_name = STRATEGIES[strategy_key]["name"]
            await redis.set(user_running_key, strategy_name, ex=300)
        except Exception:
            pass

    background_tasks.add_task(
        _execute_builtin_strategy_background, strategy_key, strategy_params, cache_key, running_key, user_running_key
    )
    return {"code": 0, "data": {"status": "running", "message": "策略已开始执行，请稍后查询"}}


# ============================================================
# 策略后台执行函数
# ============================================================

def _run_strategy_sync(check_func, stock_list):
    """同步执行策略筛选（供asyncio.to_thread调用）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    total = len(stock_list)
    checked = [0]

    logger.info(f"开始筛选，共{total}只股票")

    def process_stock(stock):
        try:
            passed = check_func(stock)
            checked[0] += 1
            if checked[0] % 500 == 0:
                logger.info(f"筛选进度: {checked[0]}/{total}，已命中{len(results)}只")
            if passed:
                quote = None
                for attempt in range(3):
                    quote = get_realtime_quote(stock['code'], stock['market'])
                    if quote:
                        break
                    time.sleep(0.5 * (attempt + 1))
                if not quote:
                    quote = {'price': 0, 'change_pct': 0, 'volume': 0, 'market_cap': 0}
                stock_copy = dict(stock)
                stock_copy['quote'] = quote
                logger.info(f"命中: {stock['code']} {stock['name']}")
                return stock_copy
        except Exception as e:
            logger.debug(f"股票{stock['code']}筛选异常: {e}")
        return None

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(process_stock, s): s for s in stock_list}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    logger.info(f"筛选完成，共检查{total}只，命中{len(results)}只")
    return results


async def _execute_builtin_strategy_background(
    strategy_key: str, strategy_params: dict, cache_key: str, running_key: str, user_running_key: str = ""
):
    """后台执行内置策略，先存数据库再缓存Redis"""
    from database import SessionLocal

    db = SessionLocal()
    try:
        builtin_strategy = STRATEGIES[strategy_key]
        check_func = lambda stock, func=builtin_strategy["func"], p=strategy_params: func(stock, **p)

        stock_list = get_stock_list()
        results = await asyncio.to_thread(_run_strategy_sync, check_func, stock_list)

        result_data = {
            "count": len(results),
            "stocks": results,
            "params": strategy_params,
            "cached_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # 先存入数据库
        today = datetime.now().strftime("%Y-%m-%d")
        db_data = {
            "_strategy_key": strategy_key,
            "stocks": results,
            "params": strategy_params,
        }
        result_record = StrategyResult(
            strategy_id=0,
            user_id=0,
            run_date=today,
            stocks_json=json.dumps(db_data, ensure_ascii=False),
        )
        db.add(result_record)
        db.commit()

        # 再缓存到Redis
        redis = get_redis()
        if redis:
            ttl = get_ttl_seconds()
            await redis.set(cache_key, json.dumps(result_data, ensure_ascii=False), ex=ttl)
            logger.info(f"策略[{strategy_key}]执行完成，结果已存库并缓存，筛选出{len(results)}只股票")
    except Exception as e:
        logger.error(f"后台执行策略失败[{strategy_key}]: {e}")
    finally:
        db.close()
        redis = get_redis()
        if redis:
            try:
                await redis.delete(running_key)
            except Exception:
                pass
            if user_running_key:
                try:
                    await redis.delete(user_running_key)
                except Exception:
                    pass


async def _execute_saved_strategy_background(
    strategy_id: int, cache_key: str, running_key: str
):
    """后台执行已保存策略并缓存结果"""
    from database import SessionLocal

    db = SessionLocal()
    try:
        strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
        if not strategy:
            return

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
            builtin_strategy = STRATEGIES[strategy_type]
            params = {k: v.get("default") for k, v in builtin_strategy["params"].items()}
            params.update(conditions.get("params", {}))
            check_func = lambda stock, func=builtin_strategy["func"], p=params: func(stock, **p)
        else:
            return

        stock_list = get_stock_list()
        results = await asyncio.to_thread(_run_strategy_sync, check_func, stock_list)

        # 保存到数据库
        today = datetime.now().strftime("%Y-%m-%d")
        result_record = StrategyResult(
            strategy_id=strategy_id,
            user_id=strategy.user_id,
            run_date=today,
            stocks_json=json.dumps(results, ensure_ascii=False),
        )
        db.add(result_record)
        db.commit()

        # 缓存结果
        result_data = {
            "count": len(results),
            "stocks": results,
            "cached_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        redis = get_redis()
        if redis:
            ttl = get_ttl_seconds()
            await redis.set(cache_key, json.dumps(result_data, ensure_ascii=False), ex=ttl)
            logger.info(f"策略[ID:{strategy_id}]执行完成，结果已缓存，筛选出{len(results)}只股票")
    except Exception as e:
        logger.error(f"后台执行策略失败[ID:{strategy_id}]: {e}")
    finally:
        db.close()
        redis = get_redis()
        if redis:
            try:
                await redis.delete(running_key)
            except Exception:
                pass


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


@app.get("/api/results/user/{user_id}")
def get_user_results(user_id: int, limit: int = 20, db: Session = Depends(get_db)):
    """获取用户的所有策略执行结果"""
    results = db.query(StrategyResult)\
        .filter(StrategyResult.user_id == user_id)\
        .order_by(StrategyResult.created_at.desc())\
        .limit(limit)\
        .all()
    return {"code": 0, "data": results}


@app.get("/api/strategies/running/{user_id}")
async def get_running_strategies(user_id: int):
    """查询指定用户是否有策略正在执行中"""
    redis = get_redis()
    running_list = []
    if redis:
        try:
            async for key in redis.scan_iter(match=f"running:user:{user_id}:*"):
                strategy_key = key.split(":")[-1]
                name = await redis.get(key)
                running_list.append({"key": strategy_key, "name": name or strategy_key})
        except Exception as e:
            logger.warning(f"查询用户running策略失败: {e}")
    return {"code": 0, "data": running_list}


@app.get("/api/results/today/{user_id}")
async def get_user_today_results(user_id: int, db: Session = Depends(get_db)):
    """
    获取用户当天所有策略执行结果（Redis优先，fallback到MySQL）

    返回当天该用户所有跑出来的结果，包含内置策略和自定义策略。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    redis = get_redis()

    # 先从Redis查询用户当天结果缓存
    redis_cache_key = f"results:today:{user_id}:{today}"
    if redis:
        try:
            cached = await redis.get(redis_cache_key)
            if cached:
                return {"code": 0, "data": json.loads(cached), "from_cache": True}
        except Exception as e:
            logger.warning(f"Redis读取用户当天结果失败: {e}")

    # Redis没有，查MySQL
    # 1. 查用户自定义策略的结果
    user_results = db.query(StrategyResult).filter(
        StrategyResult.user_id == user_id,
        StrategyResult.run_date == today,
    ).order_by(StrategyResult.created_at.desc()).all()

    # 2. 查内置策略的结果（strategy_id=0的公共结果）
    builtin_results = db.query(StrategyResult).filter(
        StrategyResult.run_date == today,
        StrategyResult.strategy_id == 0,
    ).order_by(StrategyResult.created_at.desc()).all()

    # 组装返回数据
    result_list = []

    # 内置策略结果
    for r in builtin_results:
        try:
            meta = json.loads(r.stocks_json) if r.stocks_json else {}
            if isinstance(meta, dict) and "_strategy_key" in meta:
                strategy_key = meta["_strategy_key"]
                strategy_info = STRATEGIES.get(strategy_key, {})
                result_list.append({
                    "id": r.id,
                    "type": "builtin",
                    "strategy_key": strategy_key,
                    "strategy_name": strategy_info.get("name", strategy_key),
                    "run_date": r.run_date,
                    "stocks": meta.get("stocks", []),
                    "count": len(meta.get("stocks", [])),
                    "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
                })
        except (json.JSONDecodeError, AttributeError):
            continue

    # 用户自定义策略结果
    for r in user_results:
        try:
            stocks = json.loads(r.stocks_json) if r.stocks_json else []
            # 跳过内置策略格式的记录（已在上面处理）
            if isinstance(stocks, dict) and "_strategy_key" in stocks:
                continue
            # 获取策略名称
            strategy = db.query(Strategy).filter(Strategy.id == r.strategy_id).first()
            strategy_name = strategy.name if strategy else f"策略{r.strategy_id}"
            result_list.append({
                "id": r.id,
                "type": "custom",
                "strategy_id": r.strategy_id,
                "strategy_name": strategy_name,
                "run_date": r.run_date,
                "stocks": stocks if isinstance(stocks, list) else [],
                "count": len(stocks) if isinstance(stocks, list) else 0,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            })
        except (json.JSONDecodeError, AttributeError):
            continue

    # 缓存到Redis（TTL到当天24点）
    if redis and result_list:
        try:
            ttl = get_ttl_seconds()
            await redis.set(redis_cache_key, json.dumps(result_list, ensure_ascii=False), ex=ttl)
        except Exception:
            pass

    return {"code": 0, "data": result_list, "from_cache": False}


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
# 第九部分：订阅与支付接口
# ============================================================

def get_user_active_subscription(db: Session, user_id: int):
    """获取用户当前有效订阅，返回 (subscription, package) 或 (None, None)"""
    sub = db.query(UserSubscription).filter(
        UserSubscription.user_id == user_id,
        UserSubscription.status == "paid",
        UserSubscription.expired_at > datetime.now()
    ).order_by(UserSubscription.expired_at.desc()).first()

    if sub:
        pkg = db.query(SubscriptionPackage).filter(
            SubscriptionPackage.id == sub.package_id
        ).first()
        return sub, pkg
    return None, None


@app.get("/api/subscription/packages")
def list_subscription_packages(db: Session = Depends(get_db)):
    """获取所有上架的订阅套餐"""
    packages = db.query(SubscriptionPackage).filter(
        SubscriptionPackage.is_active == True
    ).order_by(SubscriptionPackage.sort_order).all()

    return {
        "code": 0,
        "data": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price_cents": p.price_cents,
                "duration_days": p.duration_days,
                "strategy_limit": p.strategy_limit
            }
            for p in packages
        ]
    }


@app.get("/api/subscription/status")
def get_subscription_status(user_id: int, db: Session = Depends(get_db)):
    """查询用户订阅状态和剩余策略配额"""
    sub, pkg = get_user_active_subscription(db, user_id)

    if not sub or not pkg:
        return {
            "code": 0,
            "data": {
                "has_subscription": False,
                "package_name": None,
                "strategy_limit": 0,
                "strategies_used": 0,
                "strategies_remaining": 0,
                "expired_at": None
            }
        }

    custom_count = db.query(Strategy).filter(
        Strategy.user_id == user_id,
        Strategy.conditions.like('%"type": "custom"%')
    ).count()

    return {
        "code": 0,
        "data": {
            "has_subscription": True,
            "package_name": pkg.name,
            "strategy_limit": pkg.strategy_limit,
            "strategies_used": custom_count,
            "strategies_remaining": max(0, pkg.strategy_limit - custom_count),
            "expired_at": sub.expired_at.strftime("%Y-%m-%d %H:%M:%S") if sub.expired_at else None
        }
    }


@app.post("/api/subscription/create_order")
def create_subscription_order(
    user_id: int,
    req: CreateOrderRequest,
    db: Session = Depends(get_db)
):
    """创建订阅支付订单，返回前端支付参数"""
    # 验证套餐存在
    pkg = db.query(SubscriptionPackage).filter(
        SubscriptionPackage.id == req.package_id,
        SubscriptionPackage.is_active == True
    ).first()
    if not pkg:
        return {"code": 1, "message": "套餐不存在或已下架"}

    # 获取用户openid
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"code": 1, "message": "用户不存在"}
    if not user.openid or user.openid.startswith("phone_"):
        return {"code": 1, "message": "微信支付需要微信授权登录"}

    # 生成订单
    from wechat_pay import generate_order_no, create_prepay_order, build_payment_params
    order_no = generate_order_no()
    subscription = UserSubscription(
        user_id=user_id,
        package_id=req.package_id,
        order_no=order_no,
        amount_cents=pkg.price_cents,
        status="pending"
    )
    db.add(subscription)
    db.commit()

    # 调用微信统一下单
    result = create_prepay_order(
        order_no=order_no,
        amount_cents=pkg.price_cents,
        description=f"智能选股助手-{pkg.name}",
        openid=user.openid
    )

    if "error" in result:
        return {"code": 1, "message": result["error"]}

    # 生成前端支付参数
    payment_params = build_payment_params(result["prepay_id"])

    return {
        "code": 0,
        "data": {
            "order_no": order_no,
            "payment_params": payment_params
        }
    }


@app.get("/api/subscription/order/{order_no}")
def query_order_status(order_no: str, user_id: int, db: Session = Depends(get_db)):
    """查询订单状态（前端支付后轮询）"""
    sub = db.query(UserSubscription).filter(
        UserSubscription.order_no == order_no,
        UserSubscription.user_id == user_id
    ).first()

    if not sub:
        return {"code": 1, "message": "订单不存在"}

    return {
        "code": 0,
        "data": {
            "status": sub.status,
            "expired_at": sub.expired_at.strftime("%Y-%m-%d %H:%M:%S") if sub.expired_at else None
        }
    }


@app.post("/api/pay/callback")
async def wechat_pay_callback(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """微信支付回调通知"""
    body = await request.body()
    headers = dict(request.headers)

    # 验证签名
    from wechat_pay import verify_callback_signature, decrypt_callback_data
    if not verify_callback_signature(headers, body):
        return {"code": "FAIL", "message": "签名验证失败"}

    # 解析回调数据
    try:
        callback_data = json.loads(body)
    except Exception:
        return {"code": "FAIL", "message": "数据格式错误"}

    if callback_data.get("event_type") != "TRANSACTION.SUCCESS":
        return {"code": "SUCCESS", "message": ""}

    # 解密通知内容
    resource = callback_data.get("resource", {})
    order_data = decrypt_callback_data(resource)
    if not order_data:
        return {"code": "FAIL", "message": "解密失败"}

    order_no = order_data.get("out_trade_no")
    transaction_id = order_data.get("transaction_id")

    # 查找订单
    sub = db.query(UserSubscription).filter(
        UserSubscription.order_no == order_no
    ).first()
    if not sub:
        logger.warning(f"回调找不到订单: {order_no}")
        return {"code": "SUCCESS", "message": ""}

    # 幂等：已支付则直接返回成功
    if sub.status == "paid":
        return {"code": "SUCCESS", "message": ""}

    # 激活订阅
    pkg = db.query(SubscriptionPackage).filter(
        SubscriptionPackage.id == sub.package_id
    ).first()

    now = datetime.now()
    sub.status = "paid"
    sub.transaction_id = transaction_id
    sub.paid_at = now
    sub.started_at = now
    sub.expired_at = now + timedelta(days=pkg.duration_days if pkg else 30)
    db.commit()

    # 异步通知管理员
    user = db.query(User).filter(User.id == sub.user_id).first()
    nickname = user.nickname if user else f"用户{sub.user_id}"
    pkg_name = pkg.name if pkg else "未知套餐"

    from notify import notify_admins_new_subscription
    background_tasks.add_task(
        notify_admins_new_subscription,
        sub.user_id, nickname, pkg_name, sub.amount_cents
    )

    logger.info(f"订阅激活成功: 用户{sub.user_id}, 套餐{pkg_name}, 订单{order_no}")
    return {"code": "SUCCESS", "message": ""}


# ============================================================
# 第十部分：应用启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    # 启动uvicorn服务器，监听所有网络接口的8000端口
    uvicorn.run(app, host="0.0.0.0", port=8000)
