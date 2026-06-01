from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from contextlib import asynccontextmanager
import json
import asyncio
from datetime import datetime

from database import init_db, get_db, User, Strategy, StrategyResult
from stock_service import get_stock_list, run_strategy, get_kline_data, get_realtime_quote
from strategies.builtin import STRATEGIES as BUILTIN_STRATEGIES
from strategies.steady_rise import STRATEGIES as STEADY_RISE_STRATEGIES

STRATEGIES = {**BUILTIN_STRATEGIES, **STEADY_RISE_STRATEGIES}
from scheduler import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield

app = FastAPI(title="智能选股助手", lifespan=lifespan)
init_db()


class UserCreate(BaseModel):
    openid: str
    nickname: Optional[str] = ""
    phone: Optional[str] = ""


class StrategyCreate(BaseModel):
    name: str
    description: str
    conditions: Optional[str] = "{}"


class CustomStrategyCreate(BaseModel):
    name: str
    description: str


class StrategyResponse(BaseModel):
    id: int
    name: str
    description: str
    conditions: str
    script_code: Optional[str]
    is_active: bool
    created_at: datetime
    
    model_config = {"from_attributes": True}


@app.post("/api/users")
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.openid == user.openid).first()
    if db_user:
        return {"code": 0, "data": {"id": db_user.id, "openid": db_user.openid}}
    
    db_user = User(openid=user.openid, nickname=user.nickname, phone=user.phone)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"code": 0, "data": {"id": db_user.id, "openid": db_user.openid}}


@app.get("/api/strategies/builtin")
def get_builtin_strategies():
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
    db_strategy = Strategy(
        user_id=user_id,
        name=strategy.name,
        description=strategy.description,
        conditions=strategy.conditions
    )
    db.add(db_strategy)
    db.commit()
    db.refresh(db_strategy)
    return {"code": 0, "data": {"id": db_strategy.id}}


@app.post("/api/strategies/custom")
async def create_custom_strategy(user_id: int, strategy: CustomStrategyCreate, db: Session = Depends(get_db)):
    from stock_service import generate_strategy_script, extract_strategy_name
    
    try:
        script_code = await generate_strategy_script(strategy.description)
        name = extract_strategy_name(strategy.name)
        
        db_strategy = Strategy(
            user_id=user_id,
            name=name,
            description=strategy.description,
            script_code=script_code,
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
    strategies = db.query(Strategy).filter(Strategy.user_id == user_id).all()
    return {"code": 0, "data": strategies}


@app.post("/api/strategies/{strategy_id}/run")
async def run_strategy_by_id(strategy_id: int, db: Session = Depends(get_db)):
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")
    
    try:
        conditions = json.loads(strategy.conditions) if strategy.conditions else {}
        strategy_type = conditions.get("type", "")
        
        if strategy_type == "custom" and strategy.script_code:
            script_code = strategy.script_code
            namespace = {}
            exec(
                "from stock_service import get_kline_data, get_realtime_quote\n" + script_code,
                namespace
            )
            check_func = namespace.get('check_stock')
        elif strategy_type in STRATEGIES:
            builtin_strategy = STRATEGIES[strategy_type]
            params = {k: v.get("default") for k, v in builtin_strategy["params"].items()}
            params.update(conditions.get("params", {}))
            check_func = lambda stock, func=builtin_strategy["func"], p=params: func(stock, **p)
        else:
            raise HTTPException(status_code=400, detail="未知策略类型")
        
        stock_list = get_stock_list()
        results = []
        
        for stock in stock_list[:100]:
            try:
                if check_func(stock):
                    quote = get_realtime_quote(stock['code'], stock['market'])
                    stock['quote'] = quote
                    results.append(stock)
            except:
                continue
        
        today = datetime.now().strftime("%Y-%m-%d")
        result_record = StrategyResult(
            strategy_id=strategy_id,
            run_date=today,
            stocks_json=json.dumps(results, ensure_ascii=False)
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
    if strategy_key not in STRATEGIES:
        raise HTTPException(status_code=404, detail="策略不存在")

    try:
        builtin_strategy = STRATEGIES[strategy_key]
        strategy_params = {k: v.get("default") for k, v in builtin_strategy["params"].items()}
        if params:
            strategy_params.update(params)

        check_func = lambda stock, func=builtin_strategy["func"], p=strategy_params: func(stock, **p)

        stock_list = get_stock_list()
        if stock_limit > 0:
            stock_list = stock_list[:stock_limit]

        results = []
        for stock in stock_list:
            try:
                if check_func(stock):
                    quote = get_realtime_quote(stock['code'], stock['market'])
                    stock['quote'] = quote
                    results.append(stock)
            except:
                continue

        return {"code": 0, "data": {"count": len(results), "stocks": results, "params": strategy_params}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/results/{strategy_id}")
def get_strategy_results(strategy_id: int, limit: int = 10, db: Session = Depends(get_db)):
    results = db.query(StrategyResult)\
        .filter(StrategyResult.strategy_id == strategy_id)\
        .order_by(StrategyResult.created_at.desc())\
        .limit(limit)\
        .all()
    return {"code": 0, "data": results}


@app.get("/api/stock/{code}")
def get_stock_info(code: str, market: str):
    quote = get_realtime_quote(code, market)
    kline = get_kline_data(code, market)
    
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
