"""external_event_id 生成：``sim:{run_id}:{设备}:{序号}``，同一场景重放得到相同 ID。"""

from __future__ import annotations

MAX_LEN = 128  # 与后端 external_event_id 列一致


def event_id(run_id: str, equipment: str, seq: int) -> str:
    eid = f"sim:{run_id}:{equipment}:{seq}"
    if len(eid) > MAX_LEN:
        raise ValueError(f"external_event_id 超过 {MAX_LEN} 字符：{eid[:40]}...")
    return eid


class SeqCounter:
    """按设备单调递增的序号；同一场景从 1 开始，所以重放时序号与 ID 完全一致。"""

    def __init__(self) -> None:
        self._n: dict[str, int] = {}

    def next(self, equipment: str) -> int:
        self._n[equipment] = self._n.get(equipment, 0) + 1
        return self._n[equipment]
