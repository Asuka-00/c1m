"""Loads every MES spec module (in phase order) and builds the tables."""

from app.mes import specs_common  # noqa: F401  (registers entities)
from app.mes.core import ENTITIES, ENUMS, build_all

ENUMS["entity_type"][:] = [
    (e.code, e.label) for e in ENTITIES.values() if not e.internal
]
build_all()
