"""Seed / remove the MES demo dataset in the default tenant.

uv run python scripts/mes_demo.py seed | remove
"""

import logging
import sys

from sqlmodel import Session

import app.models  # noqa: F401  (registers MES specs)
from app.core.db import engine
from app.mes.demo import remove, seed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mes_demo")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in ("seed", "remove"):
        sys.exit("usage: mes_demo.py seed|remove")
    with Session(engine) as s:
        n = seed(s) if cmd == "seed" else remove(s)
    logger.info("%s: %d row(s)", cmd, n)


if __name__ == "__main__":
    main()
