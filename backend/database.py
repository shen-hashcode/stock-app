from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root:password@localhost:3306/stock_app")
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    echo=False
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    openid = Column(String(100), unique=True, index=True)
    nickname = Column(String(50))
    phone = Column(String(20))
    created_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)
    
    strategies = relationship("Strategy", back_populates="user")


class Strategy(Base):
    __tablename__ = "strategies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String(100))
    description = Column(Text)
    conditions = Column(Text)  # JSON格式存储条件
    script_code = Column(Text)  # 生成的Python脚本
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    user = relationship("User", back_populates="strategies")
    results = relationship("StrategyResult", back_populates="strategy")


class StrategyResult(Base):
    __tablename__ = "strategy_results"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"))
    run_date = Column(String(20))
    stocks_json = Column(Text)  # JSON格式存储筛选结果
    created_at = Column(DateTime, default=datetime.now)
    
    strategy = relationship("Strategy", back_populates="results")


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
