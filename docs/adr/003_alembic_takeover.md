# ADR 003 — Alembic 接管数据库迁移

- **Status**: Accepted
- **Date**: 2026-04-20
- **Deciders**: ProLine CAD core team
- **Related**: CLAUDE.md §2 (Build Commands), §4 (Things to Avoid),
  ExcPlan/next3_tasks_execution_plan.md §3.4.1.1

## 背景

`db/migrations/001_initial.sql` 是裸 SQL 文件,无 `down`、无 checksum、无依赖图。
随着 Schema 演进进入 PostGIS / TimescaleDB / pgvector,继续手写 SQL 会:

- 无法做"零停机字段重命名"(expand → migrate → contract)
- 无法在 CI 中跑 `upgrade head && downgrade -1 && upgrade head` 三步循环回归
- Pydantic ↔ DDL 漂移检测无法可靠 diff(没有 SQLAlchemy metadata)
- 多人 PR 合并时缺少线性版本链,容易产生隐式冲突

## 决策

采用 **Alembic 1.13+** 接管 `db/migrations/`,以 `db/alembic/` 为新规范目录。

1. **Baseline 策略**:`001_initial.sql` 被冻结,新增 revision `0001_baseline.py`
   作为 no-op 占位。已存在数据库通过 `alembic stamp 0001_baseline` 切入。
2. **Metadata 真源**:新增 `shared/db_schemas.py`(SQLAlchemy 2.0 Declarative),
   完全镜像 `001_initial.sql` 的列结构 + 默认值 + FK,使
   `alembic revision --autogenerate` 在 stamped 数据库上产出 **空 diff**。
3. **后续 revision 命名**:`0001b_<topic>` / `0002_<topic>` / `0003_<topic>` 以下,
   全部 `--autogenerate` 起手,人工审 diff 后提交。
4. **CI 三步循环**:每个 PR 必须通过
   `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`,
   防止 `downgrade()` 漏写或不可逆。
5. **Pydantic 不动**:`shared/models.py` 仍是运行时真源;`db_schemas.py` 仅描述
   存储形态。两者通过 `scripts/check_schema_drift.py`(子任务 B4)对齐。
6. **Secrets**:Alembic env.py 仅从 `POSTGRES_DSN` 环境变量读取,严禁在
   `alembic.ini` 写明文 DSN(CLAUDE.md §8)。

## 备选方案

- **继续裸 SQL + 自研版本表**:被否,重复造轮子且无社区生态。
- **Atlas / sqitch**:被否,Python 工具链外部依赖,与 FastAPI/SQLAlchemy 栈失耦。
- **Django ORM 迁移**:不适用,本项目无 Django。

## 后果

**正面**

- 所有 schema 变更可逆、可审、可回放
- `--autogenerate` 显著降低重复劳动
- ER 图可自 `metadata` 反推
- 与 SQLAlchemy session 共享同一组模型,后续 ORM 化路径平滑

**负面 / 成本**

- 新增依赖:`sqlalchemy>=2.0.30`、`alembic>=1.13.0`(已写入 `pyproject.toml`)
- 团队需熟悉 Alembic 三步循环工作流
- `shared/db_schemas.py` 必须与 Pydantic 保持同步,漂移由 B4 CI 守护

## 验证

- [ ] `alembic upgrade head` 在干净 PG16 容器中通过
- [ ] `alembic stamp 0001_baseline` 后 `alembic revision --autogenerate -m smoke` 产出空脚本
- [ ] `alembic downgrade -1 && alembic upgrade head` 通过
