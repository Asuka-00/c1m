# P3 人员资质：前端草案说明（待确认）

依据：`qa/fsft-fe-qa/docs/mes-phase3-plan.md` 第 13 项，以及后端已有的 `operator_qual` 实体（`mes_operator_qual`）和检查 `operator_qualified` / `qual_expiry_notice`。

## 已做（只用现有接口）
- 列表：沿用通用实体页 `operator_qual`（人员 username、工序、可选设备类型、认证日 certified_on、到期日 expires_on、启用 is_active）。
- 到期预警：`expires_on` 列已过期显示红色“过期”，30 天内显示黄色“临期”；停用的记录不预警（`QUAL_WARN_DAYS = 30`）。
- 进站卡控文案：检查 `operator_qualified` 不通过时显示“{user} 不具备工序 {op} 的有效资质，不能进站。请先取得或续期资质。”（三语），用的是后端 data 里的 `user` / `operation`；通过但 `expires` 在 30 天内时提示到期日。

## 需要后端 / 架构确认
1. 预警天数是否固定 30 天，还是由 `qual_expiry_notice` 的配置下发（前端希望在实体元数据或检查 data 里拿到 `warn_days`）。
2. `operator_qualified` 是阻断（block）还是警告（warn）；是否允许主管覆盖（override），覆盖时需要什么权限。
3. 匹配规则：有设备类型的资质是否优先于只按工序的资质；`expires_on` 当天是否仍有效（前端按“当天有效”处理）。
4. 是否需要“即将到期人员”汇总接口（例如 `GET /mes/exec/reports/qual-expiring?days=30`），前端目前只在列表里标色。
5. 资质履历和考核记录（培训 / 考试）P3 是否要做；目前没有实体，前端没做。
