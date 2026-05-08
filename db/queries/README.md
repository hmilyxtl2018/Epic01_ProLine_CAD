# db/queries — 业务可读 SQL 模板

按业务问题命名的可复用 SQL，前端 / 工艺方 / Service 层都可以直接拷贝执行或
作为 ORM 查询的对照范本。所有查询基于 ADR-0009 时空本体落地后的表与视图。

| 文件 | 业务问题 | 关键依赖 |
|---|---|---|
| [q_constraints_in_scope.sql](q_constraints_in_scope.sql) | 某节点（工位/设备/工序）当前命中的所有有效约束（含继承、含时空过滤） | `v_active_constraints_at_node`（migration 0025） |

## 占位符约定

模板里的 `:name` 是 psql / SQLAlchemy 的命名占位符。直接在 psql 里跑可用：

```bash
psql -v target_rds="'-ENT.AC.SH01.A2.L1.S20'" -v phase="'OPERATION'" \
     -v now="NOW()" -f db/queries/q_constraints_in_scope.sql
```

或在 SQLAlchemy 里：

```python
from sqlalchemy import text
session.execute(
    text(open("db/queries/q_constraints_in_scope.sql").read()),
    {"target_rds": "-ENT.AC.SH01.A2.L1.S20", "phase": "OPERATION", "now": datetime.utcnow()},
).all()
```

## 添加新查询的约定

1. 文件名 `q_<业务动词>_<对象>.sql`，例如 `q_list_unverified_in_set.sql`。
2. 头部块注释必须包含：业务问题、数据基础（依赖的表/视图/迁移版本）、用法。
3. 如查询依赖某个尚未存在的视图，先开 Alembic migration 引入视图（参考 0025），
   再添加 SQL 文件。
4. 列出"演示数据上的预期结果"段，以 `scripts/seed_constraint_demo.py` 的输出
   为基准 —— 这让查询变成可回归的活规约。
