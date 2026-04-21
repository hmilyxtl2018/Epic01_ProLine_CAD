# ADR-005 — PostGIS 空间索引 + TimescaleDB MCP 时序

- **Status**: Accepted
- **Date**: 2026-04-21
- **Deciders**: ProLine CAD core team
- **Supersedes**: 无
- **Related**: ADR-003 (Alembic 接管), 迁移 `0002_postgis_spatial`,
  `0003_timescale_mcp`, ExcPlan/next3_tasks_execution_plan.md §3.4.1.2-3

## 背景

T3 进入"非纯关系型"阶段后,两类访问模式无法用裸 PostgreSQL 高效满足:

1. **空间检索** — 给定一个 BBox / 多边形,O(log n) 找出所有相交的
   `asset_geometries`(批量提资模式 = "圈选 → 出量")。B-tree 索引在二维
   坐标上退化为全表扫描。
2. **MCP context 时序** — `mcp_context` 表按 `inserted_at` 写入,按时间窗
   查询(最近 1h / 24h)+ 按 agent_id 聚合,典型 Hot-Cold 时序模式。普通表
   随时间膨胀,vacuum 与索引代价线性增长。

## 决策

- **空间**: 在 0002 启用 `CREATE EXTENSION postgis`,为 `asset_geometries`
  增加 `geom geometry(POLYGON, 4326)` 列与 GIST 索引
  `idx_asset_geometries_geom_gist`。坐标系固定 EPSG:4326(WGS84),与上游
  CAD parser 约定一致。
- **时序**: 在 0003 启用 `CREATE EXTENSION timescaledb`,将 `mcp_context`
  转为 hypertable(`chunk_time_interval=1 day`),并为 (`agent_id`,
  `inserted_at DESC`) 建复合 B-tree。压缩策略推迟到 M2(数据量足够后)。
- **镜像策略**: 两个扩展在 SQLAlchemy 元数据中通过 `geoalchemy2.Geometry`
  与 `Index(..., postgresql_using='gist')` 表达,使
  `--autogenerate` 在已升级数据库上仍产空 diff。
- **本地降级**: PostGIS 镜像 `postgis/postgis:16-3.4-alpine` 不含
  TimescaleDB。`db/docker-compose.db-lite.yml` 在本地仅验证 0002,通过
  `alembic stamp 0003_timescale_mcp` 跳过;0003 仅在 CI 全功能镜像
  `timescale/timescaledb-ha:pg16-all` 上回归。
- **CI 三步循环**: 仍按 ADR-003 §4 执行 `upgrade head / downgrade -1 /
  upgrade head`。`down_revision` 必须正确卸载 GIST 索引与 hypertable,
  否则回滚保留垃圾索引导致下次 upgrade 重名失败。

## 备选方案

- **应用层 R-tree(rtree-py)**: 否,把空间过滤推到 Python 端意味着每次
  查询都要全表拉到内存。仅适合 < 10K 行原型。
- **InfluxDB / ClickHouse 独立时序集群**: 否,M1 阶段 mcp_context 写入量
  < 1k/min,引入第二套存储等于双写一致性问题 + 运维成本翻倍。
  M3 之后再评估。
- **不索引、依赖 SeqScan**: 否,一次 BBox 查询在 1M 行上 > 2s,违反
  T2 W2 Dashboard 的 P95 < 500ms 目标。

## 影响

**正面**

- 圈选出量从 O(n) 降到 O(log n),Dashboard 地图层可以实时刷新。
- mcp_context 按时间分块后,删除"30 天前"只是 drop chunk(秒级),
  不再触发 vacuum 风暴。
- GeoAlchemy2 + Pydantic v2 的 `WKBElement` 桥已经存在,Schema 漂移
  检测脚本不需要特殊分支。

**负面 / 风险**

- 本地 dev 环境分两套 compose(lite vs full),开发者需要知道何时切换。
  通过 `scripts/dev_up.ps1` 默认拉 lite 镜像 + 文档化降级路径来缓解。
- TimescaleDB 的 `_timescaledb_internal` schema 会出现在 alembic
  autogenerate 的 diff 里,必须在 `env.py:include_object` 显式过滤,
  否则每次都误报 drift。已在 0003 落地。
- pg_dump / pg_restore 跨主版本时 hypertable 元数据需要 `--no-acl
  --no-owner` + 重建 chunk,运维 Runbook 单独成文(M2 交付)。

## 验证

- `db/docker-compose.db-lite.yml` 起 PostGIS,跑通 0001b → 0002 → 回滚 →
  0002 三步,产物含 `idx_asset_geometries_geom_gist`(2026-04-21 通过)。
- CI workflow `full_quality.yml` 的 `db-fixture-tests` job 在 ha 镜像上
  额外跑 0003 hypertable 创建 + 回滚,断言 `_timescaledb_catalog.hypertable`
  在 downgrade 后行数为 0。
