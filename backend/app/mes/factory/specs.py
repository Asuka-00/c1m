from app.core.spec.engine import Entity, F, register

register(
    # ---------------- org ----------------
    Entity(
        "site",
        "org",
        "Factory / site|工厂|工場",
        [
            F(
                "timezone",
                "str",
                "Time zone|时区|タイムゾーン",
                default="Asia/Taipei",
                max_length=50,
            ),
            F("address", "str", "Address|地址|住所", max_length=300, list=False),
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
        "Area|区域|エリア",
        [
            F("site", "ref", required=True, ref="site"),
            F(
                "area_type",
                "enum",
                "Area type|区域类型|エリア種別",
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
        "Bay / work center|Bay / 工作中心|ベイ / ワークセンター",
        [
            F("area", "ref", required=True, ref="area"),
            F("kind", "enum", "Kind|类型|種別", enum="wc_kind", default="bay"),
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
        "Shift|班次|シフト",
        [
            F("site", "ref", required=True, ref="site"),
            F("start_time", "time", "Start|开始时间|開始時刻", required=True),
            F("end_time", "time", "End|结束时间|終了時刻", required=True),
            F(
                "crosses_midnight",
                "bool",
                "Crosses midnight|跨午夜|日跨ぎ",
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
        "Work calendar|工作日历|稼働カレンダー",
        [
            F("site", "ref", required=True, ref="site"),
            F("year", "int", "Year|年份|年", required=True),
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
        "Calendar day|日历日|カレンダー日",
        [
            F(
                "work_calendar",
                "ref",
                "Calendar|日历|カレンダー",
                required=True,
                ref="work_calendar",
                cascade=True,
            ),
            F("day", "date", "Date|日期|日付", required=True),
            F(
                "day_type",
                "enum",
                "Day type|日类型|日種別",
                enum="day_type",
                default="workday",
            ),
            F(
                "shifts",
                "str",
                "Shifts|班次|シフト",
                max_length=200,
                help="Comma separated shift codes|逗号分隔的班次编码|カンマ区切りのシフトコード",
            ),
            F("note", "str", "Note|备注|備考", max_length=200, list=False),
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
