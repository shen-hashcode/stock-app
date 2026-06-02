"""
智能选股助手 - 数据库模块

本模块负责：
1. 定义数据库连接配置
2. 定义SQLAlchemy ORM模型（User, Strategy, StrategyResult）
3. 提供数据库初始化和会话管理工具

数据库表结构：
- users: 用户表（存储微信用户信息）
- strategies: 策略表（存储用户创建的选股策略）
- strategy_results: 结果表（存储策略执行后的筛选结果）

关系：
- User 1:N Strategy（一个用户可创建多个策略）
- Strategy 1:N StrategyResult（一个策略可有多次执行结果）
"""

# ============================================================
# 第一部分：导入依赖
# ============================================================

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import logging
from dotenv import load_dotenv

# 加载.env环境变量文件
load_dotenv()

# 导入logger使SQL日志输出到文件
from logger import sql_logger  # noqa: F401


# ============================================================
# 第二部分：数据库连接配置
# ============================================================

# 从环境变量读取数据库连接URL，默认使用MySQL
# 格式: mysql+pymysql://用户名:密码@主机:端口/数据库名
# 测试环境可改为SQLite: sqlite:///./test.db
DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root:root@localhost:3306/stock_app")

# 创建数据库引擎
# 参数说明:
#   pool_size: 连接池大小（保持10个空闲连接）
#   max_overflow: 超出pool_size后最多可创建的连接数
#   pool_recycle: 连接回收时间（秒），避免MySQL超时断开
#   echo: 是否打印SQL语句（调试时设为True）
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    echo=True
)

# 创建会话工厂
# autocommit=False: 不自动提交事务
# autoflush=False: 不自动刷新
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建ORM模型基类
Base = declarative_base()


# ============================================================
# 第三部分：用户表模型
# ============================================================

class User(Base):
    """
    用户表 (users)
    
    存储微信小程序用户的基本信息
    通过微信登录获取openid，实现用户唯一标识
    
    字段说明:
        id: 主键，自增
        openid: 微信用户唯一标识（由wx.login获取）
        nickname: 用户昵称
        phone: 手机号码
        created_at: 注册时间
        is_active: 账号是否启用（支持软删除）
    
    关联关系:
        strategies: 该用户创建的所有策略（一对多）
    """
    __tablename__ = "users"
    
    # 主键ID，自动递增
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 微信openid，唯一索引，用于快速查询
    openid = Column(String(100), unique=True, index=True)
    
    # 用户昵称
    nickname = Column(String(50))
    
    # 手机号码（登录用，唯一）
    phone = Column(String(20), unique=True, index=True)

    # 密码哈希（bcrypt）
    password_hash = Column(String(128), nullable=True)

    # 注册时间，默认当前时间
    created_at = Column(DateTime, default=datetime.now)
    
    # 账号状态，默认启用
    is_active = Column(Boolean, default=True)


# ============================================================
# 第四部分：策略表模型
# ============================================================

class Strategy(Base):
    """
    策略表 (strategies)
    
    存储用户创建的选股策略
    支持两种类型:
    1. 内置策略实例：用户选择内置策略并配置参数
    2. AI自定义策略：用户用自然语言描述，AI生成Python脚本
    
    字段说明:
        id: 主键，自增
        user_id: 外键，关联users表
        name: 策略名称
        description: 策略描述
        conditions: 策略条件（JSON格式）
            - 内置策略: {"type": "rise_pullback", "params": {"days": 3, ...}}
            - 自定义策略: {"type": "custom", "description": "..."}
        script_code: AI生成的Python脚本代码（仅自定义策略）
        is_active: 是否启用
        created_at: 创建时间
        updated_at: 更新时间（自动更新）
    
    关联关系:
        user: 所属用户（多对一）
        results: 该策略的所有执行结果（一对多）
    """
    __tablename__ = "strategies"
    
    # 主键ID
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 用户ID
    user_id = Column(Integer, index=True)
    
    # 策略名称
    name = Column(String(100))
    
    # 策略描述
    description = Column(Text)
    
    # 策略条件（JSON格式）
    # 示例: {"type": "rise_pullback", "params": {"days": 3, "rise_pct": 13}}
    conditions = Column(Text)
    
    # AI生成的Python脚本代码（仅自定义策略使用）
    # 脚本需定义 check_stock(stock_info) 函数
    script_code = Column(Text)
    
    # 是否启用（用于定时任务筛选）
    is_active = Column(Boolean, default=True)
    
    # 创建时间
    created_at = Column(DateTime, default=datetime.now)
    
    # 更新时间（自动更新）
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# ============================================================
# 第五部分：策略结果表模型
# ============================================================

class StrategyResult(Base):
    """
    策略结果表 (strategy_results)
    
    存储策略执行后的筛选结果
    每次执行策略会生成一条记录
    
    字段说明:
        id: 主键，自增
        strategy_id: 外键，关联strategies表
        run_date: 执行日期（格式: YYYY-MM-DD）
        stocks_json: 筛选结果（JSON格式的股票列表）
            示例: [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "market": "sh",
                    "market_cap": 21000.5,
                    "quote": {
                        "price": 1680.00,
                        "change_pct": 1.25,
                        "volume": 12500000
                    }
                },
                ...
            ]
        created_at: 记录创建时间
    
    关联关系:
        strategy: 所属策略（多对一）
    """
    __tablename__ = "strategy_results"
    
    # 主键ID
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 策略ID
    strategy_id = Column(Integer, index=True)
    
    # 执行日期（字符串格式，如 "2024-01-15"）
    run_date = Column(String(20))
    
    # 筛选结果（JSON格式存储股票列表）
    stocks_json = Column(Text)
    
    # 记录创建时间
    created_at = Column(DateTime, default=datetime.now)


# ============================================================
# 第六部分：数据库工具函数
# ============================================================

def init_db():
    """
    初始化数据库
    
    根据ORM模型创建所有表结构
    如果表已存在，则跳过
    
    调用时机:
        1. 应用启动时（main.py中调用）
        2. 首次部署时
    """
    Base.metadata.create_all(bind=engine)


def get_db():
    """
    获取数据库会话（生成器函数）
    
    用于FastAPI的依赖注入系统
    自动管理会话的创建和关闭
    
    使用方式:
        @app.get("/api/xxx")
        def some_endpoint(db: Session = Depends(get_db)):
            # 使用db进行数据库操作
            ...
    
    工作流程:
        1. 创建数据库会话
        2. 通过yield将会话传递给接口函数
        3. 接口函数执行完毕后，自动关闭会话
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
