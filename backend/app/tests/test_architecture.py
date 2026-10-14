"""Import rules of the modular monolith (a tiny, dependency-free import linter).

Layers (lower never imports higher):

    core  <-  platform.*  <-  mes.common  <-  mes.<domain>  <-  mes.execution

* ``app.core`` imports nothing from ``app.platform`` / ``app.mes``.
* ``app.platform`` imports nothing from ``app.mes``.
* ``mes.common`` imports no other MES module; every MES domain may only use
  the MES modules listed in ``MES_ALLOWED`` (execution may use all of them,
  nothing may use execution).
* Across modules, only a module's public surface is imported: ``service``,
  ``models``, ``schemas``, ``specs``, ``permissions``, ``menus``, ``deps``
  (``mes.common`` and ``core`` are shared kernels: all public).
* Modules form no import cycles. Adapters (``router*.py``, ``deps.py``,
  ``module.py``) are the composition edge and are excluded from the cycle check;
  imports under ``if TYPE_CHECKING:`` are ignored.
* Composition roots (``app/main.py``, ``app/modules.py``, ``app/models.py``,
  ``app/bootstrap.py``, ``app/mes/demo.py``) may import anything.
Tests (``*/tests/*``) and ``app/testing`` are exempt.
"""

import ast
from collections import defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
PUBLIC = {"service", "models", "schemas", "specs", "permissions", "menus", "deps"}
ADAPTERS = ("router", "deps.py", "module.py")
MES_ALLOWED: dict[str, set[str]] = {
    "common": set(),
    "factory": {"common"},
    "product": {"common"},
    "equipment": {"common", "product"},
    "process": {"common", "product", "equipment"},
    "quality": {"common", "product", "process"},
    "map": {"common", "product"},
    "alarm": {"common"},
    "lot": {"common", "product", "process", "quality"},
    "planning": {"common", "product", "process", "lot"},
    "warehouse": {"common", "lot"},
    "reticle": {"common", "product"},
    "execution": {
        "common",
        "factory",
        "product",
        "equipment",
        "process",
        "quality",
        "lot",
        "planning",
        "warehouse",
        "map",
        "alarm",
        "reticle",
    },
}


def owner(mod: str) -> tuple[str, str] | None:
    """('core'|'platform'|'mes', module name) of a dotted module path."""
    p = mod.split(".")
    if p[0] != "app" or len(p) < 2:
        return None
    if p[1] == "core":
        return ("core", "core")
    if p[1] in ("platform", "mes") and len(p) >= 3 and p[2] not in ("demo", "tests"):
        return (p[1], p[2])
    return None


def imports() -> list[tuple[Path, str, str]]:
    """(file, importing module path, imported module path) for runtime imports."""
    out = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP.parent)
        if "alembic" in rel.parts or "tests" in rel.parts or "testing" in rel.parts:
            continue
        mod = ".".join(rel.with_suffix("").parts).removesuffix(".__init__")
        tree = ast.parse(path.read_text())
        skip: set[int] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.If) and "TYPE_CHECKING" in ast.unparse(n.test):
                skip |= {id(x) for x in ast.walk(n)}
        for n in ast.walk(tree):
            if id(n) in skip:
                continue
            if isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                # `from pkg import sub` may import a submodule: record both
                out.append((path, mod, n.module))
                out += [(path, mod, f"{n.module}.{a.name}") for a in n.names]
            elif isinstance(n, ast.Import):
                out += [(path, mod, a.name) for a in n.names]
    return out


def _is_module(dotted: str) -> bool:
    base = APP.parent / Path(*dotted.split("."))
    return base.with_suffix(".py").exists() or (base / "__init__.py").exists()


EDGES = [
    (f, src, dst, owner(src), owner(dst))
    for f, src, dst in imports()
    if owner(src) and owner(dst) and owner(src) != owner(dst)
]


def test_core_and_platform_layering() -> None:
    bad = [
        f"{src} -> {dst}"
        for _, src, dst, a, b in EDGES
        if a and b and (a[0] == "core" or (a[0] == "platform" and b[0] == "mes"))
    ]
    assert not bad, bad


def test_mes_domain_dependencies() -> None:
    bad = [
        f"{src} -> {dst}"
        for _, src, dst, a, b in EDGES
        if a and b and a[0] == b[0] == "mes" and b[1] not in MES_ALLOWED[a[1]]
    ]
    assert not bad, bad


def test_only_public_surface_across_modules() -> None:
    bad = []
    for _, src, dst, _a, b in EDGES:
        if not b or b[0] == "core" or b == ("mes", "common") or not _is_module(dst):
            continue
        rest = dst.split(".")[3:]
        if rest and rest[0] not in PUBLIC:
            bad.append(f"{src} -> {dst}")
    assert not bad, bad


def test_no_module_cycles() -> None:
    graph: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for f, _, _, a, b in EDGES:
        if a and b and not f.name.startswith(ADAPTERS):
            graph[a].add(b)
    seen: dict[tuple[str, str], int] = {}  # 1 = visiting, 2 = done
    cycles: list[list[tuple[str, str]]] = []

    def visit(n: tuple[str, str], path: list[tuple[str, str]]) -> None:
        seen[n] = 1
        for m in graph[n]:
            if seen.get(m) == 1:
                cycles.append([*path[path.index(m) :], m] if m in path else [n, m])
            elif m not in seen:
                visit(m, [*path, m])
        seen[n] = 2

    for n in list(graph):
        if n not in seen:
            visit(n, [n])
    assert not cycles, cycles


def test_every_module_registers() -> None:
    from app.core import registry

    names = {m.name for m in registry.modules()}
    pkgs = {
        f"{layer}.{p.name}"
        for layer in ("platform", "mes")
        for p in (APP / layer).iterdir()
        if (p / "__init__.py").exists() and p.name != "tests"
    }
    assert pkgs == names
