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
from typing import Optional
from contextlib import asynccontextmanager
import json
import asyncio
import bcrypt
import time
import os
import requests
from datetime import datetime, timedelta

from logger import logger

# 导入本地模块
from database import init_db, get_db, User, Strategy, StrategyResult, SubscriptionPackage, UserSubscription
from stock_service import get_stock_list, get_kline_data, get_realtime_quote
from redis_client import init_redis, close_redis, get_redis, make_cache_key, make_running_key, get_ttl_seconds, invalidate_results_cache
from strategies.builtin import STRATEGIES  # 内置策略（6 个）
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

class UserRegister(BaseModel):
    """手机号 + 密码 注册请求体。"""
    phone: str
    password: str
    nickname: Optional[str] = ""


class UserLogin(BaseModel):
    phone: str
    password: str


class WxLoginRequest(BaseModel):
    """微信小程序登录请求：前端 wx.login 拿到的 code"""
    code: str
    nickname: Optional[str] = ""


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


# ============================================================
# 第四部分：用户管理接口
# ============================================================

@app.post("/api/wx_login")
def wx_login(req: WxLoginRequest, db: Session = Depends(get_db)):
    """
    微信小程序登录：用 wx.login 拿到的 code 换 openid，按 openid upsert 用户。

    前端流程：wx.login -> code -> POST /api/wx_login -> 拿到 userId
    """
    appid = os.getenv("WECHAT_APPID", "")
    secret = os.getenv("WECHAT_SECRET", "")
    if not appid or not secret:
        return {"code": 1, "message": "服务端未配置微信 AppID / Secret"}

    try:
        resp = requests.get(
            "https://api.weixin.qq.com/sns/jscode2session",
            params={
                "appid": appid,
                "secret": secret,
                "js_code": req.code,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        data = resp.json()
    except Exception as e:
        logger.error(f"调用 jscode2session 异常: {e}")
        return {"code": 1, "message": f"微信登录服务异常: {e}"}

    openid = data.get("openid")
    if not openid:
        logger.warning(f"jscode2session 未返回 openid: {data}")
        return {"code": 1, "message": data.get("errmsg") or "换取 openid 失败"}

    db_user = db.query(User).filter(User.openid == openid).first()
    if not db_user:
        db_user = User(openid=openid, nickname=req.nickname or "")
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
    elif req.nickname and not db_user.nickname:
        db_user.nickname = req.nickname
        db.commit()

    return {
        "code": 0,
        "data": {
            "id": db_user.id,
            "openid": db_user.openid,
            "nickname": db_user.nickname or "",
        },
    }


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


@app.post("/api/strategies/custom")
async def create_custom_strategy(
    user_id: int,
    strategy: CustomStrategyCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    用户提交自然语言描述的自定义策略。

    流程：
    - 已有有效定制订阅且配额充足：直接创建策略，一对一关联到该订阅。
    - 否则：创建订阅订单 + 策略（一对一），返回支付参数，由前端拉起支付。
    - 定制订阅配额已满：返回 code 3。

    策略脚本（script_code）由管理员后续人工编写，此处不自动调用 LLM。
    """
    from notify import notify_admins_new_strategy
    from wechat_pay import generate_order_no, create_prepay_order, build_payment_params

    try:
        # 定制套餐（可创建自定义策略的套餐：strategy_limit > 0）
        custom_pkg = db.query(SubscriptionPackage).filter(
            SubscriptionPackage.strategy_limit > 0,
            SubscriptionPackage.is_active == True
        ).order_by(SubscriptionPackage.sort_order).first()

        sub, pkg = get_user_active_subscription(db, user_id)
        custom_count = db.query(Strategy).filter(
            Strategy.user_id == user_id
        ).count()

        has_custom_sub = bool(sub and pkg and pkg.strategy_limit > 0)
        quota_available = has_custom_sub and custom_count < pkg.strategy_limit

        user = db.query(User).filter(User.id == user_id).first()
        user_nickname = user.nickname if user else f"用户{user_id}"

        # 情况1：已有有效定制订阅且配额充足，直接建策略并关联到现有订阅
        if quota_available:
            db_strategy = Strategy(
                user_id=user_id,
                name=strategy.name,
                description=strategy.description,
                subscription_id=sub.id,
            )
            db.add(db_strategy)
            db.commit()
            db.refresh(db_strategy)

            background_tasks.add_task(
                notify_admins_new_strategy, user_id, db_strategy.id, strategy.name, user_nickname
            )
            return {"code": 0, "data": {"id": db_strategy.id}}

        # 情况2：定制订阅配额已满
        if has_custom_sub and not quota_available:
            return {"code": 3, "message": f"当前套餐最多创建{pkg.strategy_limit}个自定义策略，已达上限"}

        # 情况3：无定制订阅，创建订单 + 策略（一对一），返回支付参数
        if not custom_pkg:
            return {"code": 1, "message": "定制策略套餐不存在或已下架"}

        if not user:
            return {"code": 1, "message": "用户不存在"}
        if not user.openid or user.openid.startswith("phone_"):
            return {"code": 1, "message": "微信支付需要微信授权登录"}

        # 创建订阅订单（pending）
        order_no = generate_order_no()
        subscription = UserSubscription(
            user_id=user_id,
            package_id=custom_pkg.id,
            order_no=order_no,
            amount_cents=custom_pkg.price_cents,
            status="pending",
        )
        db.add(subscription)
        db.commit()
        db.refresh(subscription)

        # 创建策略，一对一关联到该订阅
        db_strategy = Strategy(
            user_id=user_id,
            name=strategy.name,
            description=strategy.description,
            subscription_id=subscription.id,
        )
        db.add(db_strategy)
        db.commit()
        db.refresh(db_strategy)

        # 调微信统一下单
        result = create_prepay_order(
            order_no=order_no,
            amount_cents=custom_pkg.price_cents,
            description=f"智能选股助手-{custom_pkg.name}",
            openid=user.openid,
        )
        if "error" in result:
            return {"code": 1, "message": result["error"]}

        subscription.prepay_id = result["prepay_id"]
        db.commit()

        payment_params = build_payment_params(result["prepay_id"])

        background_tasks.add_task(
            notify_admins_new_strategy, user_id, db_strategy.id, strategy.name, user_nickname
        )

        return {
            "code": 0,
            "data": {
                "strategy_id": db_strategy.id,
                "order_no": order_no,
                "payment_params": payment_params,
            }
        }
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
                    "type": "custom",
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

    # 执行守卫：仅管理员可手动执行内置（热门）策略，普通用户引导到结果页查看
    user_id_header = request.headers.get("X-User-Id", "")
    allowed, reason = can_execute_builtin_strategy(db, user_id_header)
    if not allowed:
        return {"code": 2, "message": reason}

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

        # 失效"当天结果"聚合缓存，让结果页立刻能读到这条新数据
        await invalidate_results_cache()

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

        if strategy.script_code:
            namespace = {}
            exec(
                "from stock_service import get_kline_data, get_realtime_quote\n" + strategy.script_code,
                namespace
            )
            check_func = namespace.get('check_stock')
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

        # 失效"当天结果"聚合缓存，让结果页立刻能读到这条新数据
        await invalidate_results_cache()

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


@app.get("/api/results/{user_id}")
async def get_user_results_by_date(
    user_id: int,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    获取用户指定日期的所有策略执行结果（内置 + 自定义）。

    参数:
        user_id: 路径参数，用户 ID
        date: 查询日期 YYYY-MM-DD；不传默认今天

    始终以 MySQL 为准查询，Redis 仅作 60 秒级降压缓存。

    权限：
    - 自定义策略结果：用户自己的，始终可见
    - 内置（热门）策略结果：仅管理员 / 已订阅 / 7 天试用期内可见
    """
    # 校验 / 默认日期
    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return {"code": 1, "message": "日期格式错误，应为 YYYY-MM-DD"}
        run_date = date
    else:
        run_date = datetime.now().strftime("%Y-%m-%d")

    redis = get_redis()
    # 缓存按 user_id + date 分桶
    redis_cache_key = f"results:{user_id}:{run_date}"

    can_see_builtin, _ = can_view_builtin_results(db, user_id)

    # 短 TTL 缓存：同一秒内多次请求直接复用，避免穿透 DB
    if redis:
        try:
            cached = await redis.get(redis_cache_key)
            if cached:
                return {"code": 0, "data": json.loads(cached), "from_cache": True}
        except Exception as e:
            logger.warning(f"Redis 读取用户结果失败: {e}")

    # 1. 查用户自定义策略的结果
    user_results = db.query(StrategyResult).filter(
        StrategyResult.user_id == user_id,
        StrategyResult.run_date == run_date,
    ).order_by(StrategyResult.created_at.desc()).all()

    # 2. 查内置策略的公共结果（strategy_id=0）。无权查看时跳过这次 DB 查询
    if can_see_builtin:
        builtin_results = db.query(StrategyResult).filter(
            StrategyResult.run_date == run_date,
            StrategyResult.strategy_id == 0,
        ).order_by(StrategyResult.created_at.desc()).all()
    else:
        builtin_results = []

    result_list = []

    # 用户自定义策略：按 strategy_id 去重（保留最新一条）
    seen_custom_ids = set()
    for r in user_results:
        try:
            stocks = json.loads(r.stocks_json) if r.stocks_json else []
            # 跳过被写到 user_id 维度的内置格式记录（理论上不会发生，防御性）
            if isinstance(stocks, dict) and "_strategy_key" in stocks:
                continue
            if r.strategy_id in seen_custom_ids:
                continue
            seen_custom_ids.add(r.strategy_id)
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

    # 内置策略：按 _strategy_key 去重（保留最新一条）
    seen_builtin_keys = set()
    for r in builtin_results:
        try:
            meta = json.loads(r.stocks_json) if r.stocks_json else {}
            if not (isinstance(meta, dict) and "_strategy_key" in meta):
                continue
            strategy_key = meta["_strategy_key"]
            if strategy_key in seen_builtin_keys:
                continue
            seen_builtin_keys.add(strategy_key)
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

    # 60 秒短 TTL 写缓存，仅用于同秒高频请求降压
    if redis:
        try:
            await redis.set(redis_cache_key, json.dumps(result_list, ensure_ascii=False), ex=60)
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
    if not quote:
        return {"code": 1, "message": "未找到该股票"}
    
    # 获取K线数据
    kline = get_kline_data(code, market)
    
    # 只返回最近10天的K线
    kline_data = []
    if kline is not None:
        kline_data = kline[-10:] if len(kline) > 10 else kline
    
    return {
        "code": 0,
        "data": {
            **quote,
            "kline": kline_data
        }
    }


# ============================================================
# 第九部分：订阅与支付接口
# ============================================================

# 未订阅用户试用期（首次登录起）
TRIAL_DAYS = 7


def _parse_user_id(user_id_raw) -> Optional[int]:
    """规范化 header 里的 user_id。失败返回 None。"""
    if not user_id_raw:
        return None
    try:
        return int(user_id_raw)
    except (TypeError, ValueError):
        return None


def can_execute_builtin_strategy(db: Session, user_id_raw) -> tuple[bool, str]:
    """
    判断用户是否能手动执行内置（热门）策略。

    规则：仅管理员（User.is_admin=True）可执行。普通用户应到结果页查看
    系统每日 16:00 自动产出的公共结果。
    """
    uid = _parse_user_id(user_id_raw)
    if uid is None:
        return False, "请先登录"

    user = db.query(User).filter(User.id == uid).first()
    if not user:
        return False, "用户不存在"
    if not user.is_admin:
        return False, "热门策略由系统每日自动执行，请到结果页查看"
    return True, ""


def can_view_builtin_results(db: Session, user_id_raw) -> tuple[bool, str]:
    """
    判断用户是否有权查看内置（热门）策略的当日结果。

    规则：管理员 → 允许；已订阅 → 允许；否则按 users.created_at + TRIAL_DAYS 判断试用期。
    """
    uid = _parse_user_id(user_id_raw)
    if uid is None:
        return False, "请先登录"

    user = db.query(User).filter(User.id == uid).first()
    if not user:
        return False, "用户不存在"
    if user.is_admin:
        return True, ""

    sub, _ = get_user_active_subscription(db, uid)
    if sub:
        return True, ""

    trial_deadline = (user.created_at or datetime.now()) + timedelta(days=TRIAL_DAYS)
    if datetime.now() <= trial_deadline:
        return True, ""
    return False, "试用期已结束，请订阅后继续查看热门策略结果"


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
    """查询用户订阅状态和剩余策略配额（含 7 天试用期信息）"""
    sub, pkg = get_user_active_subscription(db, user_id)

    user = db.query(User).filter(User.id == user_id).first()
    trial_deadline = None
    trial_active = False
    trial_days_remaining = 0
    if user:
        trial_deadline = (user.created_at or datetime.now()) + timedelta(days=TRIAL_DAYS)
        delta = trial_deadline - datetime.now()
        trial_active = delta.total_seconds() > 0
        trial_days_remaining = max(0, delta.days + (1 if trial_active and delta.seconds > 0 else 0))

    if not sub or not pkg:
        return {
            "code": 0,
            "data": {
                "has_subscription": False,
                "package_name": None,
                "strategy_limit": 0,
                "strategies_used": 0,
                "strategies_remaining": 0,
                "expired_at": None,
                "trial_active": trial_active,
                "trial_days_remaining": trial_days_remaining,
                "trial_expired_at": trial_deadline.strftime("%Y-%m-%d %H:%M:%S") if trial_deadline else None
            }
        }

    custom_count = db.query(Strategy).filter(
        Strategy.user_id == user_id
    ).count()

    return {
        "code": 0,
        "data": {
            "has_subscription": True,
            "package_name": pkg.name,
            "strategy_limit": pkg.strategy_limit,
            "strategies_used": custom_count,
            "strategies_remaining": max(0, pkg.strategy_limit - custom_count),
            "expired_at": sub.expired_at.strftime("%Y-%m-%d %H:%M:%S") if sub.expired_at else None,
            "trial_active": trial_active,
            "trial_days_remaining": trial_days_remaining,
            "trial_expired_at": trial_deadline.strftime("%Y-%m-%d %H:%M:%S") if trial_deadline else None
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

    # 存储prepay_id，以便后续重新拉起支付
    prepay_id = result["prepay_id"]
    subscription.prepay_id = prepay_id
    db.commit()

    # 生成前端支付参数
    payment_params = build_payment_params(prepay_id)

    return {
        "code": 0,
        "data": {
            "order_no": order_no,
            "payment_params": payment_params
        }
    }


@app.get("/api/subscription/order/{order_no}")
def query_order_status(order_no: str, user_id: int, db: Session = Depends(get_db)):
    """查询订单状态（前端支付后轮询 / 重新拉起支付）"""
    sub = db.query(UserSubscription).filter(
        UserSubscription.order_no == order_no,
        UserSubscription.user_id == user_id
    ).first()

    if not sub:
        return {"code": 1, "message": "订单不存在"}

    data = {
        "status": sub.status,
        "expired_at": sub.expired_at.strftime("%Y-%m-%d %H:%M:%S") if sub.expired_at else None
    }

    # 如果订单处于待支付状态且有prepay_id，返回支付参数以便重新拉起微信支付
    if sub.status == "pending" and sub.prepay_id:
        from wechat_pay import build_payment_params
        data["payment_params"] = build_payment_params(sub.prepay_id)

    return {"code": 0, "data": data}


@app.post("/api/pay/callback")
async def wechat_pay_callback(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """微信支付回调通知"""
    logger.info("进入订单回调")
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
