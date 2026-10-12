"""核心 FastAPI 依赖：数据库会话。"""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from app.core.db import engine


def get_db() -> Generator[Session]:
    """按请求提供数据库会话，请求结束自动关闭。

    Yields:
        绑定运行时引擎的 Session。
    """
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
