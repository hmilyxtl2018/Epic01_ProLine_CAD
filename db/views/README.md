# db/views — Data Architect 视图速查

只读 VIEW，落在 Postgres 里，让所有人不写 JOIN 就能看清实体之间的关系。

定义在迁移：
- [0025_v_constraints_at_node.py](../alembic/versions/0025_v_constraints_at_node.py)
- [0026_data_architect_views.py](../alembic/versions/0026_data_architect_views.py)
- [0027_time_dimension_views.py](../alembic/versions/0027_time_dimension_views.py)

## 视图清单

| 视图                          | 一句话                                        | 典型用途                              |
| ----------------------------- | --------------------------------------------- | ------------------------------------- |
| `v_hierarchy_tree`            | 每个节点的祖先链 + 深度，按 RDS 排好          | 看整张工厂层级；前端面包屑/树视图基础 |
| `v_constraint_set_summary`    | 每个 ConstraintSet 的健康度统计               | 工艺师看自己集合够不够"可发布"        |
| `v_constraint_bindings`       | 单条约束 ↔ 节点原始绑定（不展开继承）         | 审约束时看"它绑了哪些节点"            |
| `v_active_constraints_at_node`| 单条约束 ↔ 实际命中节点（**展开继承**）        | 工位视角看"我身上有哪些约束在管我"    |
| `v_node_constraint_load`      | 每个节点上活跃且已审批的约束计数（含继承）    | 仪表盘热力图；找"约束最多的工位"     |
| `v_constraint_temporal`       | 单条约束的时间档案 + 四态结论                  | 找"已过期 / 30 天内将失效 / 未到生效"约束 |
| `v_active_constraints_now`    | 当前 NOW() 生效 + 相位展平的命中视图           | 按 `phase = 'OPERATION'` 直接查无需写 JSON 操作符 |

## 与可读 SQL 模板的关系

`db/queries/` 里的业务 SQL 模板都直接 SELECT 上面这些视图，不再写 JOIN。
新增"业务问题 → SQL"模板时优先看这些视图能否覆盖。

## 演示数据上的预期值

```sql
-- 7 个 LOCATION + 几个 PRODUCT/FUNCTION 节点
SELECT count(*) FROM v_hierarchy_tree;

-- CS-DEMO-001：4 条约束，3 hard + 1 soft，3 approved，approved_percent=75
SELECT * FROM v_constraint_set_summary;

-- 3 个 Station：S10/S20 各 3 条命中（1 direct + 2 inherited），S30 只继承 2 条
SELECT * FROM v_node_constraint_load WHERE node_kind='Station' ORDER BY rds_code;
```
