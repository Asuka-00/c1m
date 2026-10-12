"""初始数据脚本入口：``python -m app.initial_data``（由 prestart.sh 调用）。"""

import logging

from sqlmodel import Session

from app.bootstrap import init_db
from app.core.db import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init() -> None:
    """打开会话并执行 :func:`app.bootstrap.init_db`。"""
    with Session(engine) as session:
        init_db(session)


def main() -> None:
    """命令行入口：写日志并初始化数据。"""
    logger.info("Creating initial data")
    init()
    logger.info("Initial data created")


if __name__ == "__main__":
    main()
