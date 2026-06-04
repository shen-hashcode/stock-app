"""
全局日志配置。

特性：
- 同时输出到控制台和文件（控制台便于本地观察，文件用于线上排查）
- 文件按大小滚动：50MB × 8 份 = 总量上限约 400MB
- 通过环境变量 LOG_LEVEL 调整级别（默认 DEBUG），取值：DEBUG / INFO / WARNING / ERROR
- 防止 FastAPI 热重载或多次 import 时重复挂 handler

使用：
    from logger import logger
    logger.info("...")
    logger.debug("...")
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# ---------------- 配置项 ----------------

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

# 单文件 50MB；保留 8 份（含当前文件）；总量上限 400MB
LOG_MAX_BYTES = 50 * 1024 * 1024
LOG_BACKUP_COUNT = 8

# 默认 DEBUG，可由环境变量覆盖
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()
_LEVEL = getattr(logging, LOG_LEVEL, logging.DEBUG)

os.makedirs(LOG_DIR, exist_ok=True)

# ---------------- 共享 formatter ----------------

_FORMATTER = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _make_file_handler() -> RotatingFileHandler:
    h = RotatingFileHandler(
        LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    h.setFormatter(_FORMATTER)
    h.setLevel(_LEVEL)
    return h


def _make_console_handler() -> logging.StreamHandler:
    h = logging.StreamHandler(stream=sys.stdout)
    h.setFormatter(_FORMATTER)
    h.setLevel(_LEVEL)
    return h


def _attach(target_logger: logging.Logger) -> None:
    """给目标 logger 挂上文件 + 控制台 handler，避免重复添加。"""
    target_logger.setLevel(_LEVEL)
    target_logger.propagate = False  # 不向 root 冒泡，避免重复输出

    has_file = any(isinstance(h, RotatingFileHandler) for h in target_logger.handlers)
    has_console = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        for h in target_logger.handlers
    )
    if not has_file:
        target_logger.addHandler(_make_file_handler())
    if not has_console:
        target_logger.addHandler(_make_console_handler())


# ---------------- 业务 logger ----------------

# 应用主 logger，模块里写 `from logger import logger` 然后 logger.info(...)
logger = logging.getLogger("stock_app")
_attach(logger)

# SQLAlchemy SQL 日志（DEBUG 级别会打印每条 SQL，INFO 只打印连接事件）
sql_logger = logging.getLogger("sqlalchemy.engine")
_attach(sql_logger)

logger.info(
    f"日志初始化完成 level={LOG_LEVEL} file={LOG_FILE} "
    f"rotate={LOG_MAX_BYTES // (1024*1024)}MB x {LOG_BACKUP_COUNT}"
)