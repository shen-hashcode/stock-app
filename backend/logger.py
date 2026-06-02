import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "app.log")

# 滚动日志：单文件最大50MB，最多保留4个备份（总计约200MB）
handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=50 * 1024 * 1024,
    backupCount=4,
    encoding="utf-8"
)
handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))

# 应用日志
logger = logging.getLogger("stock_app")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# SQL日志（SQLAlchemy engine logger）
sql_logger = logging.getLogger("sqlalchemy.engine")
sql_logger.setLevel(logging.INFO)
sql_logger.addHandler(handler)
