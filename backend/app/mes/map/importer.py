"""坐标图 / bin 定义集 CSV 解析与校验（B4）。

文件格式（设备集成样例 ``cim-map-csv v1`` / ``cim-bin-csv v1``）：``#`` 开头的文件头为
``key=value``；随后一行列名；再往后是数据行。报错同时给 ``row_no``（数据行号，从 1 起，
文件头和列名不计）与 ``file_line``（原始文件行号，从 1 起）。
"""

import csv
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.core.spec.engine import ENUMS
from app.mes.map.specs import EXCLUDED_BIN_TYPES, GOOD_BIN_TYPES

Row = dict[str, Any]
MAP_COLS = ("substrate_id", "row", "col", "bin_code")
BIN_COLS = ("bin_code", "bin_type", "description")
MAX_ROWS = 200_000


def _enum(name: str) -> set[str]:
    return {k for k, _ in ENUMS[name]}


@dataclass
class Parsed:
    """解析结果：文件头、数据行 ``(row_no, file_line, record)``、结构错误。"""

    header: dict[str, str] = field(default_factory=dict)
    rows: list[tuple[int, int, dict[str, str]]] = field(default_factory=list)
    errors: list[Row] = field(default_factory=list)


def err(
    code: str,
    message: str,
    row_no: int | None = None,
    file_line: int | None = None,
    field_: str | None = None,
) -> Row:
    """逐行报错项：``{row_no, file_line, field, code, message}``。"""
    return {
        "row_no": row_no,
        "file_line": file_line,
        "field": field_,
        "code": code,
        "message": message,
    }


def parse(content: str, cols: tuple[str, ...]) -> Parsed:
    """拆出文件头、列名与数据行（只做结构检查）。"""
    p = Parsed()
    lines = content.lstrip("\ufeff").splitlines()
    i = 0
    while i < len(lines) and (
        not lines[i].strip() or lines[i].lstrip().startswith("#")
    ):
        t = lines[i].strip().lstrip("#").strip()
        if "=" in t:
            k, v = t.split("=", 1)
            p.header[k.strip()] = v.strip()
        i += 1
    if i >= len(lines):
        p.errors.append(
            err("missing_columns", f"column line required: {','.join(cols)}")
        )
        return p
    head = [c.strip() for c in next(csv.reader([lines[i]]))]
    miss = [c for c in cols if c not in head]
    if miss:
        p.errors.append(
            err("missing_columns", f"missing columns: {', '.join(miss)}", None, i + 1)
        )
        return p
    no = 0
    for j in range(i + 1, len(lines)):
        if not lines[j].strip():
            continue
        no += 1
        if no > MAX_ROWS:
            p.errors.append(
                err("too_many_rows", f"at most {MAX_ROWS} data rows", no, j + 1)
            )
            break
        vals = next(csv.reader([lines[j]]))
        rec = {
            h: (vals[k].strip() if k < len(vals) else "") for k, h in enumerate(head)
        }
        p.rows.append((no, j + 1, rec))
    if not p.rows:
        p.errors.append(err("empty", "no data rows"))
    return p


def check_bin_set(content: str) -> tuple[Row, list[Row], list[Row]]:
    """Bin 定义集：返回 (``{code, version}``, 定义行, 错误)。版本取自它自己的文件头。"""
    p = parse(content, ("bin_code", "bin_type"))
    errs = list(p.errors)
    code = p.header.get("bin_definition_set", "")
    ver = p.header.get("version", "")
    if not code:
        errs.append(
            err(
                "missing_header",
                "header bin_definition_set required",
                field_="bin_definition_set",
            )
        )
    if not ver.isdigit() or int(ver) < 1:
        errs.append(
            err(
                "missing_header",
                "header version must be a positive integer",
                field_="version",
            )
        )
    types = _enum("bin_type")
    seen: dict[str, int] = {}
    defs: list[Row] = []
    for no, line, r in p.rows:
        bc, bt = r.get("bin_code", ""), r.get("bin_type", "").lower()
        if not bc:
            errs.append(err("required", "bin_code required", no, line, "bin_code"))
            continue
        if len(bc) > 32:
            errs.append(
                err("too_long", "bin_code: at most 32 characters", no, line, "bin_code")
            )
            continue
        if bt not in types:
            errs.append(
                err(
                    "bad_bin_type",
                    f"bin_type must be one of {sorted(types)}",
                    no,
                    line,
                    "bin_type",
                )
            )
            continue
        if bc in seen:
            errs.append(
                err(
                    "duplicate_bin",
                    f"bin_code {bc} duplicated (row {seen[bc]})",
                    no,
                    line,
                    "bin_code",
                )
            )
            continue
        seen[bc] = no
        defs.append(
            {
                "bin_code": bc,
                "bin_type": bt,
                "description": (r.get("description") or "")[:200] or None,
            }
        )
    return {"code": code, "version": int(ver) if ver.isdigit() else None}, defs, errs


def check_map(
    content: str, bins: dict[str, str] | None
) -> tuple[Row, list[Row], list[Row]]:
    """坐标图：返回 (文件头, 按基板汇总, 错误)。

    ``bins`` 为引用定义集的 ``{bin_code: bin_type}``；为 None 表示定义集不存在
    （由调用方报 422 ``bin_set_not_found``）。
    """
    p = parse(content, MAP_COLS)
    errs = list(p.errors)
    h = p.header
    head: Row = {
        "substrate_type": h.get("substrate_type", ""),
        "origin_location": h.get("origin_location", ""),
        "x_axis": h.get("x_axis", ""),
        "y_axis": h.get("y_axis", ""),
        "bin_definition_set": h.get("bin_definition_set", ""),
        "bin_definition_version": h.get("bin_definition_version", ""),
        "rows": h.get("rows"),
        "cols": h.get("cols"),
    }
    for k, en in (
        ("substrate_type", "substrate_type"),
        ("origin_location", "origin_location"),
        ("x_axis", "x_axis"),
        ("y_axis", "y_axis"),
    ):
        if head[k] not in _enum(en):
            errs.append(
                err(
                    "bad_header",
                    f"header {k} must be one of {sorted(_enum(en))}",
                    field_=k,
                )
            )
    if not head["bin_definition_set"]:
        errs.append(
            err(
                "missing_header",
                "header bin_definition_set required",
                field_="bin_definition_set",
            )
        )
    v = head["bin_definition_version"]
    if not str(v).isdigit():
        errs.append(
            err(
                "missing_header",
                "header bin_definition_version must be an integer",
                field_="bin_definition_version",
            )
        )
    lim: dict[str, int | None] = {}
    for k in ("rows", "cols"):
        x = head[k]
        if x is not None and (not str(x).isdigit() or int(x) < 1):
            errs.append(
                err("bad_header", f"header {k} must be a positive integer", field_=k)
            )
            x = None
        lim[k] = int(x) if x is not None else None
    subs: dict[str, Row] = {}
    for no, line, r in p.rows:
        sid = r["substrate_id"]
        if not sid:
            errs.append(
                err("required", "substrate_id required", no, line, "substrate_id")
            )
            continue
        if len(sid) > 64:
            errs.append(
                err(
                    "too_long",
                    "substrate_id: at most 64 characters",
                    no,
                    line,
                    "substrate_id",
                )
            )
            continue
        rc: list[int] = []
        bad = False
        for k in ("row", "col"):
            t = r[k]
            if not t.lstrip("-").isdigit():
                errs.append(err("bad_int", f"{k} must be an integer", no, line, k))
                bad = True
                continue
            n = int(t)
            m = lim["rows" if k == "row" else "cols"]
            if n < 0 or (m is not None and n >= m):
                rng = f"0..{m - 1}" if m is not None else ">= 0"
                errs.append(
                    err("out_of_range", f"{k} {n} out of range {rng}", no, line, k)
                )
                bad = True
            rc.append(n)
        bc = r["bin_code"]
        if not bc:
            errs.append(err("required", "bin_code required", no, line, "bin_code"))
            bad = True
        elif bins is not None and bc not in bins:
            errs.append(
                err(
                    "unknown_bin",
                    f"bin_code {bc} not defined in the bin set",
                    no,
                    line,
                    "bin_code",
                )
            )
            bad = True
        if bad:
            continue
        s = subs.setdefault(sid, {"code": sid, "cells": {}, "first": no})
        key = (rc[0], rc[1])
        if key in s["cells"]:
            errs.append(
                err(
                    "duplicate_coord",
                    f"{sid} ({rc[0]},{rc[1]}) duplicated (row {s['cells'][key][1]})",
                    no,
                    line,
                    "row",
                )
            )
            continue
        s["cells"][key] = (bc, no)
    out = []
    for s in subs.values():
        cells = s["cells"]
        counts = Counter(bc for bc, _ in cells.values())
        total = len(cells)
        bt = bins or {}
        out.append(
            {
                "code": s["code"],
                "rows": lim["rows"] or (max(r for r, _ in cells) + 1),
                "cols": lim["cols"] or (max(c for _, c in cells) + 1),
                "total_qty": total,
                "bin_counts": dict(sorted(counts.items())),
                "good_qty": sum(
                    n for b, n in counts.items() if bt.get(b) in GOOD_BIN_TYPES
                ),
                "excluded_qty": sum(
                    n for b, n in counts.items() if bt.get(b) in EXCLUDED_BIN_TYPES
                ),
                "cells": [(r, c, bc) for (r, c), (bc, _) in sorted(cells.items())],
            }
        )
    return head, out, errs
