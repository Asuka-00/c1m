# 工艺/产线视角评审：fsft MES 首期优化与批次状态机

> 评审人：工艺专家 · 2026-10-13 · 只读评审，未改任何代码或文档
> 范围：fsft-mes-optimization.md、decisions.md（D1–D11、P01–P19、N1–N6）、lot-state-machine.md §4 转移表、/workspace/fsft/backend/app/mes/execution 相关代码
> 依据：../../process/knowledge/02-fab-rules.md（Hold、返工、Q-time）、03-yield-defect.md、05-mes-pitfalls.md。凡是工程经验、没有公开出处的内容，都标【推断】。

## 一、必须改

**M1. Q-Time 超时不应自动整批报废**
- 现状：`qtime_actions.py:100-119` 的 scrap 动作把所有晶圆和整批直接改成 scrapped，qty 清零，不需要人审批。转移表 §4 第 110 行也写了「qtime_scrap waiting→scrapped」作为规则。
- 产线实际：Q-time 超时后，通常先 Hold，再由工程师判定（重新清洗、返工、降级、报废）。报废不能撤销，又直接计入良率损失，系统不应自动执行（02-fab-rules §3、§2）。
- 建议：qtime 规则的处置动作只保留 hold（可以挂报废建议的原因码）。真正报废走 adjust，并带原因码和审批。如果短期必须保留这个能力，至少要求规则显式配置、二次确认，并单独记 history 来源。

**M2. 「终态批次不能 Hold」（D4）不适用于 completed**
- 现状：completed（待入库）在 TERMINAL 里（D6，`lot/lots.py:18`），D4 又禁止 Hold 终态批次。结果是：已完工、待入库的批次被发现 WAT 异常或客户投诉时，没法 Hold。
- 隐患：`warehouse/service.py:93-95` 的入库条件里有「非 hold」，等于设计上本来就预期 completed 批次会被 Hold。D4 把这个前提抹掉了，有问题的批次可能照常入库、出货。
- 建议：允许 completed、stored 批次被 Hold（出货前的品质 Hold）；scrapped、merged 维持禁止。

**M3. Track Out 判返工时整批走返工路线，没有子批**
- 现状：`track_out.py:252-276` 中，只要有返工晶圆，就把整批标成 `pending_rework`（前提是工步配了 rework_route_id），然后在 `stages.py:208-228` Move Out 时整批进返工路线，rework_count 也按整批累计。
- 产线实际：返工通常只涉及部分晶圆，应拆出子批去返工，母批继续走或等子批会合（02-fab-rules §2）。整批返工会让合格片多跑一遍工艺，浪费产能，还多了一层风险【推断：多跑工艺的影响取决于返工内容，例如光刻去胶重做对合格片基本无益】。
- 另外，工步没配 rework_route_id 时，pending 直接变 False，返工晶圆仍是 rework 状态，却跟着整批往下走，没有卡控。
- 建议：Track Out 判返工时，按晶圆自动（或提示）拆出返工子批；没有返工路线时，拒绝提交或自动 Hold。

**M4. 返工次数上限要按晶圆管控**
- 现状：`stages.py:227` 只累加批次级 rework_count。晶圆级 rework_count（`track_out.py:248`）虽然有记录，但上限检查 `rework.rework_limit_result` 看的是批次级计数。
- 隐患：拆批、合批之后批次计数会失真，同一片晶圆可能超过返工上限还在继续返工（光刻返工次数影响良率）【推断】。
- 建议：上限按晶圆最大返工次数判断，合批时子批的返工历史也要带过来。

## 二、建议改

- **S1. 加工中 Hold 允许 Track Out、不允许 Move Out（D2）**：方向正确，晶圆已经在机台里，中途停下反而更糟。不过要明确两点：一是 Track Out 后仍要做数据采集和 SPC 判定；二是自动推进 `stages.py:303` 已经判断 on_hold 并会停下，这条要写进测试。
- **S2. Abort（撤销 Track In，D5）建议排进下一期，不要无限期推迟**：机台宕机、配方下载失败时，没有 Abort 的操作员只能编造 Track Out 数据或报废，量测和历史都会被污染（05-mes-pitfalls 第 14 条）。本期至少给出临时 SOP：用工程 Hold 加 adjust 处理。
- **S3. 「加工中批次不能报废」（D3）**：手动报废禁止是对的；Track Out 时的报废（全部或部分）仍然允许，这样也合理。Q-time 只扫 waiting 批次（`qtime_actions.py:156`）。建议把 moved_in（已进站、未开工）也纳入 Q-time 预警和 Hold，因为它还没开工，同样会超时【推断】。
- **S4. 合批检查（N4、merge.py:36-61）**：「先状态机、再业务规则」的顺序可以接受。业务规则里建议补几项：
  - pending_rework、返工次数是否一致
  - Q-time 起算时间：合并后取最早的
  - Future Hold：源批挂的 Future Hold 要带到目标批
  - 优先级：取较高的
  
  另外，现在合批前都要求没有 Hold，这是对的。
- **S5. Hold 释放权限**：转移表只规定 release 可以在任意状态执行，没规定谁能释放。建议按 Hold 来源或原因码限定释放部门（例如 SPC Hold 只能由工艺工程师释放）。这和优化清单第 12 项按钮权限有关。
- **S6. 自动 Hold 碰到终态批次时返回 skipped（P11）**：静默跳过可能掩盖问题，比如 SPC 发现某机台异常，但相关批次已入库。建议在 warning 之外发一条通知或事件，方便追溯同机台的批次。
- **S7. 优化清单**：本期不做 RTD、SPC、EAP，可以接受。建议加一项「报废/返工审批流与原因码治理」，并在 outbox 事件里预留 wafer 级字段，给后面的良率和共性分析用（03-yield-defect §3）。

## 三、可以接受

- **报废到 0 不自动释放 Hold（P15 方案 A）**：保留 Hold 的责任和审计记录，符合产线做法；看板默认不显示终态批次也合理。
- **拆批不能拆完（P13）**：母批剩 0 等同于改名，会扰乱谱系；还有 `split.py` 的 min_wafers 规则兜底。
- **合批检查顺序（N4）**：先状态后规则，错误码也分开了，没问题（补充项见 S4）。
- **8 个状态、四段式过站（D1）**、Hold 与流程状态正交且可以叠加多条、jump 和 move_in 在 Hold 时禁止、子批继承 Hold（P12）：都符合 02-fab-rules §1。
- 按 id 排序加锁、幂等键、Hold 中禁止入库：这些是工程层面的设计，工艺上没有异议。

## 四、六条已定规则汇总

| 规则 | 结论 |
|---|---|
| Hold 中允许 Track Out、不允许 Move Out | 可以接受（附带 S1） |
| 加工中不能报废（含 Q-Time） | 手动报废禁止：可以接受；但 Q-Time 自动报废本身必须改（M1） |
| 终态批次不能 Hold | 必须改：completed、stored 要允许 Hold（M2） |
| 报废到 0 不自动释放 Hold | 可以接受 |
| 拆批不能拆完 | 可以接受 |
| 合批检查顺序 | 可以接受，建议补规则（S4） |

## 补充评审：D19 / D20（2026-10-13）

**D19：Q-Time 计时到 Move In 停表 —— 建议改（有条件接受）**
- 真实产线的 Q-Time 管的是晶圆暴露在环境中的时间（氧化、吸湿、颗粒），通常到下一工步**开始加工（Track In / 进腔）**才停表【推断，各厂按工步定义】。本系统是四段式，Move In 之后批次可能停在 `moved_in` 状态，在机台口等待，晶圆仍然暴露在环境中。按 D19，这段时间不计入 Q-Time，会出现漏管。
- 建议：停表点改成 Track In；或者至少把 `moved_in` 批次也纳入超时预警和 Hold（与前文 S3 一致）。如果本期坚持 Move In 停表，应在 decisions 里写明这个风险，并给一份操作规程，限制批次 Move In 后多久内必须 Track In。
- 把"加工中时长监控"留给 EAP 侧可以接受。

**D20：原因码与 trigger —— 可以接受**
- 规则自配原因码优先、否则用 `qtime_expired`，trigger 统一为 qtime，这些都合理。建议 Hold 记录里同时存 Q-Time 规则 ID、起止工步和超时时长，方便工程师处置、做报表追溯；释放权限按 S5 限定到工艺工程师。
