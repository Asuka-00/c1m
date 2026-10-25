"""批次执行阶段状态机常量。"""

STAGES = ["move_in", "track_in", "track_out", "move_out"]
FROM_STATUS = {
    "move_in": "waiting",
    "track_in": "moved_in",
    "track_out": "running",
    "move_out": "tracked_out",
}
TO_STATUS = {
    "move_in": "moved_in",
    "track_in": "running",
    "track_out": "tracked_out",
}
NEXT_STAGE = {
    "waiting": "move_in",
    "moved_in": "track_in",
    "running": "track_out",
    "tracked_out": "move_out",
}
OOS_RANK = {"warn": 1, "rework": 2, "auto_hold": 3, "block": 4}
OOC_RANK = {"warn": 1, "auto_hold": 2, "hold_equipment": 3}
