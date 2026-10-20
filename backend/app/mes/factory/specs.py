"""工厂模型实体规格：厂区、区域、工作中心、班次、日历。"""

from app.core.spec.engine import Entity, F, register

register(
    # ---------------- org ----------------
    Entity(
        "site",
        "org",
        "Factory / site",
        [
            F(
                "timezone",
                "str",
                "Time zone",
                default="Asia/Taipei",
                max_length=50,
            ),
            F("address", "str", "Address", max_length=300, list=False),
            F("is_active", "bool", default=True),
        ],
        phase=1,
        icon="Factory",
    ),
)


register(
    Entity(
        "area",
        "org",
        "Area",
        [
            F("site", "ref", required=True, ref="site"),
            F(
                "area_type",
                "enum",
                "Area type",
                enum="area_type",
                default="fab",
            ),
            F("is_active", "bool", default=True),
        ],
        phase=1,
        icon="LayoutGrid",
        order=1,
    ),
)


register(
    Entity(
        "workcenter",
        "org",
        "Bay / work center",
        [
            F("area", "ref", required=True, ref="area"),
            F("kind", "enum", "Kind", enum="wc_kind", default="bay"),
            F("is_active", "bool", default=True),
        ],
        phase=1,
        tree=True,
        icon="Network",
        order=2,
    ),
)


register(
    Entity(
        "shift",
        "org",
        "Shift",
        [
            F("site", "ref", required=True, ref="site"),
            F("start_time", "time", "Start", required=True),
            F("end_time", "time", "End", required=True),
            F(
                "crosses_midnight",
                "bool",
                "Crosses midnight",
                default=False,
            ),
            F("sort_order", "int", default=0),
        ],
        phase=1,
        unique=[("site", "code")],
        icon="Clock",
        order=3,
    ),
)


register(
    Entity(
        "work_calendar",
        "org",
        "Work calendar",
        [
            F("site", "ref", required=True, ref="site"),
            F("year", "int", "Year", required=True),
            F("is_active", "bool", default=True),
        ],
        phase=1,
        children=["calendar_day"],
        icon="CalendarDays",
        order=4,
    ),
)


register(
    Entity(
        "calendar_day",
        "org",
        "Calendar day",
        [
            F(
                "work_calendar",
                "ref",
                "Calendar",
                required=True,
                ref="work_calendar",
                cascade=True,
            ),
            F("day", "date", "Date", required=True),
            F(
                "day_type",
                "enum",
                "Day type",
                enum="day_type",
                default="workday",
            ),
            F(
                "shifts",
                "str",
                "Shifts",
                max_length=200,
                help="Comma separated shift codes",
            ),
            F("note", "str", "Note", max_length=200, list=False),
        ],
        phase=1,
        has_code=False,
        parent="work_calendar",
        unique=[("work_calendar", "day")],
        icon="Calendar",
        order=5,
        sort_default="day",
        label_field="day",
    ),
)
