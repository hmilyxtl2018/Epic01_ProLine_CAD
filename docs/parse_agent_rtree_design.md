# ParseAgent R-Tree 空间索引设计与实施方案

> 状态：**未实现**（M2 PRD 占位，仅在 `agents/parse_agent/app.py` docstring 与 `LayoutAgent.collision_check` 里出现，后者抛 `NotImplementedError`）。
>
> 本文目的：给出"为什么需要 R-Tree、做成什么样、怎么落地"的工程方案。

---

## 1. 为什么需要 R-Tree

CAD 文件解析后的 SiteModel 通常含 **数千～数十万个实体**（LINE / INSERT / HATCH / TEXT…）。后续阶段需要做的几类查询全都是 *"几何邻近 / 包含"*：

| 场景 | 查询 | 暴力 O(N²) 代价 | 期望 |
|------|------|-----------------|------|
| **K_asset_extract**：把同区域的几何归到一个 asset | "和这个 INSERT bbox 相交的所有 LINE/HATCH" | 5万实体 ≈ 25 亿次 bbox 比较 | < 100 ms |
| **L_geom_anomaly**：HATCH 边界自检（你今天踩的 bug 之源） | "这个 HATCH 内部 / 边界上有哪些 LINE 段" | 同上 | < 50 ms |
| **H_topology**（拓扑卡片）：构建 LOCATED_IN / NEAR 关系 | "和资产 A 距离 ≤ d 的资产 B 列表" | N² | < 200 ms |
| **LayoutAgent S3 碰撞检测** | "新放置的设备和已有设备 bbox 是否相交" | 200 资产 × 1000 候选 = 2 亿 | < 20 ms / 候选 |
| **前端框选 / ROI 查询** | "viewport bbox 内有哪些 asset" | 全表扫 | < 30 ms HTTP RT |
| **跨 Run 检索** | "某 sha256 文件在第 X 米半径内有多少 SiteModel 命中" | 全表扫 | < 100 ms SQL |

R-Tree（或 STR-Tree）把"对每个候选都比一遍"压成"先按 bbox 树查 candidate set，再精确判定"，把上面 5 类查询从 O(N²) → O(N log N) 构建 + O(log N + k) 查询。

---

## 2. 选型：内存 vs 持久化，两路并存

不同场景对查询时延、跨进程一致性、数据规模要求不同。**采用双层架构**——**ParseAgent 内部用进程内 STR-Tree，DB 层用 PostGIS GIST**——比单选一种都更稳：

| 维度 | `shapely.STRtree` | PostGIS GIST (`gist_geometry_ops_2d`) |
|------|-------------------|-----------------------------------------|
| 介质 | 进程内 | PostgreSQL |
| 构建一次成本 | 5万实体 ≈ 100ms (CPython) | INSERT + 自动索引 |
| 单次查询 | < 1ms | 1–5ms（含网络） |
| 跨进程共享 | ❌（要重算） | ✅ |
| 跨 Run 检索 | ❌ | ✅ |
| 适用步骤 | K / L / H / I（同事务内反复查） | 前端 ROI、跨 Run 检索、S3 碰撞（持久层） |
| 项目里现有 | 未引入 | docker-compose 已用 PostGIS 16 |

> Python 还有一个 `rtree`（基于 libspatialindex），比 `shapely.STRtree` 更老牌但 API 麻烦。Shapely 2.x 的 `STRtree` 是 GEOS 直接出的，**API 简单到 3 行**，并且 LayoutAgent 后面要做 GEOS 几何运算（`STRtree.query` + `intersects`），用同一栈最省事。

---

## 3. 数据现状盘点（已有 / 待补）

```
site_models.bbox                    Geometry(POLYGON, 0)   ✅ 已建 GIST（迁移 0009）
asset_geometries.geometry           JSONB                   ❌ 没几何列、没索引
asset_geometries.bbox               (无)                    ❌ 没字段
output_payload.llm_enrichment...    JSONB                   ❌ 不可索引
```

> 影响：
> - **Run 级 bbox 查询**（"哪些 SiteModel 在这块地图上"）已经能跑（GIST OK）。
> - **资产级几何查询**（"这个 SiteModel 内 ROI 框里的 asset"）目前要靠 SQL 扫 JSONB —— 慢。
> - 内部步骤（K/L/H/I）**完全没有**索引，全是 list 全扫。

---

## 4. 实施方案

### 4.1 阶段 A — 进程内 STR-Tree（解放 K/L/H/I）

**目标**：在 ParseAgent 单 Run 事务内，A→K 一旦扫完原始实体表就构建一棵索引；后续 K/L/H/I/F/G 全部改为通过索引查询。

**新模块**：`agents/parse_agent/spatial_index.py`

```python
# agents/parse_agent/spatial_index.py
"""ParseAgent 进程内空间索引 — 用于 K/L/H/I 步骤反复 "邻近查询"。

设计要点：
1. 一个 Run 一个实例（per-run 缓存，run 结束即弃）；
2. payload 是 dict["entity_id" -> Entity]，几何统一升级为 shapely.geometry；
3. 查询接口固定为 query_bbox / query_intersects / query_nearest，避免泄漏 GEOS 细节。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Sequence
from shapely.geometry import box, shape, Polygon, Point
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree


@dataclass(frozen=True, slots=True)
class IndexedItem:
    entity_id: str
    geom: BaseGeometry
    layer: str
    kind: str  # LINE / INSERT / HATCH / ...


class SpatialIndex:
    """轻量空间索引 — bbox-first，精确判定可选。

    Why STRtree（不是 rtree）:
    - Shapely 2.x 直接出，无 native 依赖（已是 LayoutAgent 必装包）;
    - 构造 O(N log N)，查询 O(log N + k)，对 5W 实体 < 100ms 构建 / < 1ms 查询;
    - 与项目里 GEOS 几何栈一致，便于后续做 intersects / contains / distance。
    """

    def __init__(self, items: Sequence[IndexedItem]):
        self._items = list(items)
        # STRtree 只接受 geom 数组，索引位置 → 原 IndexedItem
        self._tree = STRtree([it.geom for it in self._items])

    @classmethod
    def from_entities(cls, entities: Iterable[dict]) -> "SpatialIndex":
        """从 ParseAgent 的 entity_dump 构建。"""
        items: list[IndexedItem] = []
        for e in entities:
            g = _to_geom(e)  # LINE→LineString, INSERT→Point/box, HATCH→Polygon
            if g is None or g.is_empty:
                continue
            items.append(IndexedItem(
                entity_id=e["id"],
                geom=g,
                layer=e.get("layer", ""),
                kind=e["type"],
            ))
        return cls(items)

    # ── 查询接口 ─────────────────────────────────────────────
    def query_bbox(self, minx: float, miny: float, maxx: float, maxy: float) -> list[IndexedItem]:
        """返回 bbox 与 query 框相交的所有候选（粗查，不做精确判定）。"""
        idxs = self._tree.query(box(minx, miny, maxx, maxy))
        return [self._items[i] for i in idxs]

    def query_intersects(self, geom: BaseGeometry, *, predicate: str = "intersects") -> list[IndexedItem]:
        """精确版：bbox 粗查 + GEOS 关系判定。`predicate` ∈ {intersects, contains, within, touches}.
        """
        idxs = self._tree.query(geom, predicate=predicate)
        return [self._items[i] for i in idxs]

    def query_nearest(self, point: Point, *, k: int = 5) -> list[IndexedItem]:
        idxs = self._tree.nearest(point) if k == 1 else \
               sorted(self._tree.query(point.buffer(self._items_bbox_diag())),
                      key=lambda i: self._items[i].geom.distance(point))[:k]
        idxs = [idxs] if isinstance(idxs, int) else list(idxs)
        return [self._items[i] for i in idxs]


def _to_geom(entity: dict) -> BaseGeometry | None:
    """实体 → shapely geometry（不全的回 None，由调用方过滤）。"""
    t = entity["type"]
    if t == "LINE":
        from shapely.geometry import LineString
        return LineString([entity["start"], entity["end"]])
    if t in ("INSERT", "TEXT", "MTEXT"):
        return Point(entity["x"], entity["y"])
    if t == "HATCH":
        # 用第一条外环；空 boundary 返 None（这是今天 bug 的源头之一）
        rings = entity.get("boundary_paths") or []
        if not rings:
            return None
        try:
            return Polygon(rings[0])
        except Exception:
            return None
    if t in ("CIRCLE", "ELLIPSE"):
        c = Point(entity["cx"], entity["cy"])
        return c.buffer(entity["r"])
    return None
```

**接入点**：在 `agents/parse_agent/service.py`（或 enrichment pipeline 的 K 步入口）：

```python
# 解析完成后立即构建索引
spatial_idx = SpatialIndex.from_entities(parsed_entities)
ctx["spatial_index"] = spatial_idx     # 注入到 enrichment pipeline ctx

# K_asset_extract: "和 INSERT 重叠的 LINE/HATCH 都归到这个 asset"
neighbors = ctx["spatial_index"].query_intersects(insert_geom, predicate="intersects")

# L_geom_anomaly: "这个 HATCH 内部有 LINE 段吗？"
inside = ctx["spatial_index"].query_intersects(hatch_geom, predicate="contains")
if not inside and hatch.boundary.is_empty:
    anomalies.append({"hatch_id": hatch.id, "reason": "empty boundary"})  # 你今天看到的 bug
```

**测试**：`agents/parse_agent/tests/test_spatial_index.py` 至少覆盖
- 100 实体构造正确性
- bbox 粗查 / intersects 精确查
- HATCH 空 boundary 不进索引
- 50K 实体构建 < 200ms（CI gate）

---

### 4.2 阶段 B — PostGIS GIST 索引（解放跨 Run / 前端 ROI）

**目标**：把 `asset_geometries` 的几何变成可索引的 PostGIS 列，以支持：
- 前端"viewport ROI 内的 asset 列表"（一个 SQL 完成）；
- S3 LayoutAgent 持久化方案候选间的碰撞检测；
- 跨 Run 查询（"这个区域历史上出现过哪些资产类型"）。

**Alembic 迁移 0019**（草案，等用户确认后再创建文件）：

```python
# db/alembic/versions/0019_asset_geometries_postgis.py
def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")  # 幂等
    # 1) bbox：所有几何都有，PostGIS POLYGON
    op.add_column("asset_geometries",
        sa.Column("bbox", Geometry(geometry_type="POLYGON", srid=0), nullable=True))
    # 2) centroid：用于 nearest-N 查询（PgSQL 用 KNN <-> 算子）
    op.add_column("asset_geometries",
        sa.Column("centroid", Geometry(geometry_type="POINT", srid=0), nullable=True))
    # 3) GIST 索引（关键）
    op.execute("CREATE INDEX idx_asset_geom_bbox ON asset_geometries USING GIST (bbox);")
    op.execute("CREATE INDEX idx_asset_geom_centroid ON asset_geometries USING GIST (centroid);")
    # 4) 回填：把 JSONB.geometry 转 PostGIS（执行一次性脚本，不在 migration 内）
```

**回填脚本**：`scripts/backfill_0019.py`，用 `shapely → wkb_hex → ST_GeomFromWKB` 一次性导入历史数据。

**ParseAgent 写入侧**：在 `K_asset_extract` 写 `asset_geometries` 时，同时写 `bbox`、`centroid`：

```python
from geoalchemy2.shape import from_shape

ag = AssetGeometry(
    site_model_id=sm.id,
    geometry=g.__geo_interface__,           # 原 JSONB（保留）
    bbox=from_shape(g.envelope, srid=0),     # 新 PostGIS
    centroid=from_shape(g.centroid, srid=0), # 新 PostGIS
    ...
)
```

**API 端点**：`/api/dashboard/sites/{sm_id}/spatial-query`

```python
# app/api/dashboard/sites.py（新增）
@router.get("/sites/{sm_id}/spatial-query")
def spatial_query(
    sm_id: UUID,
    minx: float, miny: float, maxx: float, maxy: float,
    db: Session = Depends(get_db),
):
    """前端 ROI 框选 → 命中的 asset 列表（GIST 索引保证 ms 级）."""
    rows = db.execute(text("""
        SELECT asset_guid, sub_type, ST_AsGeoJSON(geometry) AS geojson
        FROM asset_geometries
        WHERE site_model_id = :sm
          AND bbox && ST_MakeEnvelope(:minx, :miny, :maxx, :maxy)
        ORDER BY ST_Area(bbox) DESC
        LIMIT 500
    """), {"sm": sm_id, "minx": minx, ...}).all()
    return {"hits": [...]}
```

**前端接入**：在 `sites/[runId]` 的 ParsedView 拖拽框选时调用此接口，把命中的 cluster 高亮（取代当前的"Synthesize 1200×800 网格"模拟）。

---

### 4.3 阶段 C — LayoutAgent S3 碰撞检测落地（消化掉 NotImplementedError）

LayoutAgent 现有占位：

```python
# agents/layout_agent/service.py
def collision_check(self, candidate: dict) -> list[dict]:
    """R-Tree 碰撞检测 — 避免 N² 暴力比较。"""
    raise NotImplementedError
```

直接把阶段 A 的 `SpatialIndex` 抽到 `shared/spatial.py`（或 `agents/_common/spatial.py`），LayoutAgent 复用：

```python
def collision_check(self, candidate: dict) -> list[dict]:
    if self._idx is None:
        self._idx = SpatialIndex.from_entities(self._site_assets)
    candidate_geom = box(*candidate["bbox"])
    hits = self._idx.query_intersects(candidate_geom, predicate="intersects")
    # 排除自身
    return [{"asset_id": h.entity_id, "kind": h.kind} for h in hits
            if h.entity_id != candidate["asset_id"]]
```

GA 迭代时 `_idx` 只在被移动 asset 改变时**部分重建**（STRtree 不可增量，但 200 资产重建 < 5ms，可接受）。

---

## 5. 如何配套到 13 步管线？

把 R-Tree 当作 **K_asset_extract 完成后的副产物**，挂在 enrichment pipeline 的 ctx 上：

```
A · E ──► (clean tokens)
B · C ──► (semantic alignment)
D     ──► (cluster proposals)
K     ──► assets[] + ★ SpatialIndex 构建（ctx["spatial_index"]）
              │
              ├─► L_geom_anomaly  使用 ctx["spatial_index"] 做 HATCH 自检
              ├─► H_audit_narrative 用近邻关系生成 LOCATED_IN 描述
              ├─► I_self_check     用 spatial_index 验证 "孤儿实体" 比例
              └─► run_evaluations  写 spatial_index_size 维度
F · G · I ──► quality + cp-a
J · M · H ──► narrative
```

并在 `output_payload.llm_enrichment.metrics` 加：

```jsonc
{
  "spatial_index": {
    "items": 48213,
    "build_ms": 87,
    "queries": 1342,           // 整个 Run 共触发查询次数
    "avg_query_ms": 0.4
  }
}
```

UI 端在 `/runs/{id}` 的 "Pipeline Profile" 卡片里直接展示这块——可观测性免费拿到。

---

## 6. 落地路线图（建议优先级）

| Step | 工作量 | 价值 | 阻塞 |
|------|-------|------|------|
| **B1** 写 `agents/parse_agent/spatial_index.py` + 单测 | 0.5 day | 解决 HATCH bug 的查询基础 | 无 |
| **B2** L_geom_anomaly 接入索引（HATCH boundary 校验） | 0.5 day | **直接修今天 MLightCAD 预览的 hatch boundary 报错** | B1 |
| **B3** Alembic 0019 迁移 + asset_geometries 写 bbox/centroid | 0.5 day | 数据库索引就位 | B1 |
| **B4** `/spatial-query` API + 前端 ROI 接入 | 1 day | 前端框选体验立刻可用 | B3 |
| **B5** LayoutAgent.collision_check 复用 SpatialIndex | 0.5 day | S3 阶段开锁 | B1 |
| **B6** Run 视图 spatial_index 指标卡 | 0.5 day | 可观测性 | B1 |

总计 ≈ 3.5 个工作日，可以拆成 2 个 PR：B1+B2+B5（纯内存 + 业务收益）和 B3+B4+B6（数据库 + 前端）。

---

## 7. 与今天 MLightCAD 预览 Bug 的关系

报错 `Failed to convert hatch boundaries!`（`vz`/`area` 在 `bundle.js:4963`）直接对应一种几何异常——**HATCH 没有合法的 boundary**。当前 ParseAgent 没在 `L_geom_anomaly` 里检测，所以一路把坏 HATCH 塞到 SiteModel；前端 MLightCAD 试图渲染时炸掉。

**B1 + B2 就能直接修这个 bug 的"上游半"**：
- B1 在构建 SpatialIndex 时，`_to_geom` 已经过滤掉 `boundary_paths is None / empty / Polygon 构造异常` 的 HATCH；
- B2 把这些过滤记进 `L_geom_anomaly.anomalies[]`，UI 上以"已知坏几何"形式呈现而不是黑灯静默。

至于"前端半"——MLightCAD 自身对 hatch boundary 的容错——属于 viewer 层 bug，建议在 `web/scripts/mlight-entry.mjs` 里再加一层 try/catch，避免单 entity 错误炸掉整张图。

---

## 8. 不做什么（明确范围）

- **不引入 `rtree` Python 包**：和 `shapely.STRtree` 重复，且要装 native lib。
- **不在 PostGIS 上启 SP-GiST / BRIN**：GIST 已经够用；SP-GiST 仅对点云有优势。
- **不缓存 STR-Tree 跨 Run**：每 Run 几何不同，缓存命中率几乎为 0；构建 < 100ms 不值得维护。
- **不上 pgvector 几何嵌入**：跑题，pgvector 是给 B_softmatch 用的语义向量，几何用 PostGIS 就好。
