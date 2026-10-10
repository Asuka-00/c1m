"""Loads every MES spec module (in phase order) and builds the tables."""

from app.mes import (  # noqa: F401  (registers entities)
    specs_common,
    specs_p2,
    specs_p3,
    specs_p4,
    specs_wo,
)
from app.mes.core import ENTITIES, ENUMS, build_all

ENUMS["entity_type"][:] = [
    (e.code, e.label) for e in ENTITIES.values() if not e.internal
]
build_all()
