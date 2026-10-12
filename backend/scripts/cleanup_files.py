"""Delete uploaded files that no config value references.

    uv run python scripts/cleanup_files.py [--hours 24] [--tenant <uuid>] [--dry-run]

Files younger than --hours are kept (in-progress uploads). Run e.g. from cron.
"""

import argparse
import logging
import uuid
from datetime import timedelta

from sqlmodel import Session

from app.core.db import engine
from app.platform.files.service import cleanup_unreferenced

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cleanup_files")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hours", type=float, default=24, help="grace period (default 24)")
    ap.add_argument("--tenant", type=uuid.UUID, help="only this tenant's files")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    with Session(engine) as session:
        victims = cleanup_unreferenced(
            session, timedelta(hours=a.hours), a.tenant, a.dry_run
        )
    for f in victims:
        logger.info(
            "%s %s (%s, tenant=%s)",
            "would delete" if a.dry_run else "deleted",
            f.id,
            f.filename,
            f.tenant_id,
        )


if __name__ == "__main__":
    main()
