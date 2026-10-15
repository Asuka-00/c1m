"""CORS：跨域时暴露 Idempotent-Replayed 回放头。"""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_cors_exposes_idempotent_replayed() -> None:
    c = TestClient(app)
    r = c.get(
        f"{settings.API_V1_STR}/utils/health-check/",
        headers={"Origin": settings.FRONTEND_HOST},
    )
    exposed = r.headers.get("access-control-expose-headers", "")
    assert "Idempotent-Replayed" in [h.strip() for h in exposed.split(",")]
