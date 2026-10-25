"""通知事件类型注册表：业务模块在导入时登记事件（编码、英文名称、默认严重度、关联对象类型）。"""

from dataclasses import dataclass

SEVERITIES = ("info", "warning", "critical")


@dataclass(frozen=True)
class EventType:
    """事件类型。

    Attributes:
        code: 事件编码（如 ``mes.qtime_exceeded``）。
        label: 英文名称（兜底；显示文案在前端 ``notify.event.<code>.label``）。
        severity: 默认严重度（info / warning / critical）。
        object_type: 关联对象类型（lot / equipment ...），用于跳转。
        direct: 定向事件（如待审批）：由业务指定接收人，不可订阅。
    """

    code: str
    label: str
    severity: str = "info"
    object_type: str | None = None
    direct: bool = False


EVENT_TYPES: dict[str, EventType] = {}


def register_event(
    code: str,
    label: str,
    severity: str = "info",
    object_type: str | None = None,
    direct: bool = False,
) -> EventType:
    """登记事件类型（重复登记以最后一次为准）。

    Raises:
        ValueError: 严重度不合法。
    """
    if severity not in SEVERITIES:
        raise ValueError(f"severity must be one of {SEVERITIES}")
    ev = EventType(code, label, severity, object_type, direct)
    EVENT_TYPES[code] = ev
    return ev
