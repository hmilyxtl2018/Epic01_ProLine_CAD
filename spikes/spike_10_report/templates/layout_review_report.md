# 航空产线布局评审报告模板 (Spike-10)

> 本模板用于Spike-10报告生成测试，验证从结构化数据自动生成PDF报告。

---

## {{project_name}} 产线布局规划评审报告

**项目编号**: {{project_id}}  
**评审日期**: {{review_date}}  
**版本**: {{version}}  

---

### 1. 项目概况

| 项目 | 内容 |
|------|------|
| 产线名称 | {{line_name}} |
| 厂房面积 | {{factory_area}} m² |
| 设备数量 | {{equipment_count}} 台 |
| 工位数量 | {{station_count}} 个 |
| 目标年产量 | {{target_annual_output}} 架 |

### 2. 布局方案总览

{{layout_overview_image}}

### 3. 碰撞检测结果

| 检测项 | 数量 | 状态 |
|--------|------|------|
| 设备重叠 | {{collision_count}} | {{collision_status}} |
| 安全区侵入 | {{safety_zone_violations}} | {{safety_status}} |
| 禁区违规 | {{exclusion_zone_violations}} | {{exclusion_status}} |
| 通道占用 | {{passage_violations}} | {{passage_status}} |

**碰撞详情:**
{{collision_details_table}}

### 4. 工艺约束满足情况

| 约束类别 | 总数 | 满足 | 违反 | 满足率 |
|----------|------|------|------|--------|
| 环境约束 | {{env_total}} | {{env_pass}} | {{env_fail}} | {{env_rate}}% |
| 空间约束 | {{space_total}} | {{space_pass}} | {{space_fail}} | {{space_rate}}% |
| 时序约束 | {{time_total}} | {{time_pass}} | {{time_fail}} | {{time_rate}}% |
| 安全约束 | {{safety_total}} | {{safety_pass}} | {{safety_fail}} | {{safety_rate}}% |

**违反约束详情:**
{{constraint_violation_details}}

### 5. 仿真分析结果

| 指标 | 数值 | 目标 | 达成 |
|------|------|------|------|
| 年产量(架) | {{sim_annual_output}} | {{target_annual_output}} | {{output_achieved}} |
| 节拍时间(h) | {{sim_takt_time}} | {{target_takt_time}} | {{takt_achieved}} |
| 瓶颈工位 | {{bottleneck_station}} | - | - |
| 设备利用率 | {{avg_utilization}}% | ≥80% | {{util_achieved}} |

### 6. 问题清单

| 序号 | 类别 | 问题描述 | 严重性 | 建议措施 |
|------|------|---------|--------|---------|
{{issue_rows}}

### 7. 评审结论

**评审结果**: {{review_result}}

- [ ] 通过，可进入下一阶段
- [ ] 有条件通过，需整改后复审
- [ ] 不通过，需重新设计

**评审人签字:**

| 角色 | 姓名 | 日期 |
|------|------|------|
| 工艺工程师 | {{engineer_name}} | {{review_date}} |
| 质量工程师 | {{qa_name}} | {{review_date}} |
| 项目经理 | {{pm_name}} | {{review_date}} |

---
*本报告由 ProLine CAD 系统自动生成*
