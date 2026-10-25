"""质量模块公开 API（DC 计划、抽样、规格界限、SPC 判异）。"""

from app.mes.quality.dc import (
    dc_plan_for as dc_plan_for,
)
from app.mes.quality.dc import (
    out_of_spec as out_of_spec,
)
from app.mes.quality.dc import (
    sampling as sampling,
)
from app.mes.quality.spc import ooc_check as ooc_check
from app.mes.quality.spc import spc_chart as spc_chart
