"""ParseAgent — 核心业务逻辑。

实现 CAD 文件解析的完整管线:
格式检测 → 实体提取 → 坐标标准化 → 拓扑修补 → 资产识别 → 关系映射 → SiteModel 输出

参考: ExcPlan/Agent Profile §1.3 Action Flow
"""

from __future__ import annotations

import hashlib
import math
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf

from shared.models import (
    Asset,
    AssetType,
    CADFormat,
    CADSource,
    Coords,
    Footprint,
    LinkType,
    OntologyLink,
    SiteModel,
)
from shared.mcp_protocol import MCPContext, generate_context_id, AgentStatus

# DWG 文件头 magic bytes → 版本映射
_DWG_VERSION_MAP: dict[str, str] = {
    "AC1009": "DWG-R12",
    "AC1012": "DWG-R13",
    "AC1014": "DWG-R14",
    "AC1015": "DWG-R2000",
    "AC1018": "DWG-R2004",
    "AC1021": "DWG-R2007",
    "AC1024": "DWG-R2010",
    "AC1027": "DWG-R2013",
    "AC1032": "DWG-R2018",
}

# ODA File Converter 路径 (项目本地)
_ODA_EXE = Path(__file__).resolve().parents[2] / "tools" / "ODAFileConverter" / "ODAFileConverter.exe"

# Block 名称 → 资产类型关键词映射 (中英文)
_BLOCK_ASSET_PATTERNS: dict[AssetType, list[str]] = {
    AssetType.CONVEYOR: [
        "conveyor", "辊道", "输送", "roller", "belt", "chain",
        # ── S1-T1: jijia gold 高频词 ──
        "pallet_conveyor", "rollerconveyor", "板链",
    ],
    AssetType.EQUIPMENT: [
        "cnc", "machine", "机", "清洗", "装配", "压装", "测量", "珩磨",
        "test", "station", "press", "drill", "lathe", "mill",
        "op", "nsi", "托盘", "拆卸", "分组",
        # ── S1-T1: jijia gold 高频词 ──
        "washing", "honing", "grinder", "polish", "抛光",
        "deep rolling", "extar", "harding", "landis",
        "hardener", "harden", "leak", "inspection",
        "process_machine", "workstation", "k-st",
        "缸盖", "缸孔", "缸体", "工艺", "罩",
        "assembly", "disassembly", "machining_center",
    ],
    AssetType.LIFTING_POINT: [
        "hoist", "crane", "吊", "lift", "天车", "行车",
        # ── S1-T1: jijia gold 高频词 ──
        "kbk", "悬挂", "葫芦",
    ],
    AssetType.ZONE: [
        "zone", "area", "区域", "room", "boundary", "围栏",
        # ── S1-T1: jijia gold 高频词 ──
        "厂区", "车间", "区",
    ],
    AssetType.WALL: [
        "wall", "mauer", "стена", "muro", "sciany",
    ],
    AssetType.DOOR: [
        "door", "porta", "дверь", "tür",
    ],
    AssetType.WINDOW: [
        "window", "finestra", "окно", "fenster",
    ],
    AssetType.PIPE: [
        "pipe", "duct", "труба", "tubo",
    ],
    AssetType.COLUMN: [
        "column", "pillar", "colonna", "столб",
    ],
    AssetType.CNC_MACHINE: [
        "cnc_machine", "machine_tool",
    ],
    AssetType.ELECTRICAL_PANEL: [
        "panel", "electrical", "mcc", "switchboard",
    ],
    AssetType.STORAGE_RACK: [
        "rack", "storage", "lumber", "shelf",
    ],
}

# 图层名 → 资产类型启发式映射 (英文 + 多语言 + 领域缩写)
_LAYER_ASSET_MAP: dict[str, AssetType] = {
    # ── 原有英文 ──
    "EQUIPMENT": AssetType.EQUIPMENT,
    "WORKSTATION": AssetType.EQUIPMENT,
    "CRANE": AssetType.LIFTING_POINT,
    "LIFTING": AssetType.LIFTING_POINT,
    "CONVEYOR": AssetType.CONVEYOR,
    "AGV": AssetType.CONVEYOR,
    "ZONE": AssetType.ZONE,
    "SAFETY": AssetType.ZONE,
    "EXCLUSION": AssetType.ZONE,
    "CLEAN": AssetType.ZONE,
    # ── IMP-01: 新增类型对应的英文层名 ──
    "WALL": AssetType.WALL,
    "WALLS": AssetType.WALL,
    "DOOR": AssetType.DOOR,
    "DOORS_WINDOWS": AssetType.DOOR,
    "WINDOW": AssetType.WINDOW,
    "WINDOWS": AssetType.WINDOW,
    "PIPE": AssetType.PIPE,
    "PIPES": AssetType.PIPE,
    "COLUMN": AssetType.COLUMN,
    "COLUMNS": AssetType.COLUMN,
    "ELECTRICAL": AssetType.ELECTRICAL_PANEL,
    "RACK": AssetType.STORAGE_RACK,
    # ── IMP-02: 意大利语 ──
    "TAVOLO": AssetType.EQUIPMENT,
    "MACCHINA": AssetType.EQUIPMENT,
    "PORTA": AssetType.DOOR,
    "MURO": AssetType.WALL,
    "FINESTRA": AssetType.WINDOW,
    # ── IMP-02: 俄语 ──
    "СИСТЕМНЫЙ": AssetType.OTHER,
    "ОБОРУДОВАНИЕ": AssetType.EQUIPMENT,
    "СТЕНА": AssetType.WALL,
    "КРАН": AssetType.LIFTING_POINT,
    # ── IMP-02: 波兰语 ──
    "WIDOCZNE": AssetType.OTHER,
    "NIEWIDOCZNE": AssetType.OTHER,
    "SCIANY": AssetType.WALL,
    # ── IMP-04: 领域缩写 & 英文扩展 ──
    "FURN_EQ": AssetType.EQUIPMENT,
    "FURN": AssetType.EQUIPMENT,
    "FURNITURE": AssetType.EQUIPMENT,
    "DIM": AssetType.ANNOTATION,
    "TXT": AssetType.ANNOTATION,
    "ANNOTATION": AssetType.ANNOTATION,
    "HATCH": AssetType.OTHER,
    "DEFPOINTS": AssetType.OTHER,
    "AIR": AssetType.PIPE,
    "HVAC": AssetType.PIPE,
    "RAIL": AssetType.CONVEYOR,
    "FLOOR": AssetType.ZONE,
    "STRUCTURAL": AssetType.COLUMN,
    # ── S1-T1: jijia gold 高频图层 ──
    "STEP_1": AssetType.CONVEYOR,    # 261 个 Conveyor_2m 主线层
    "AM_0": AssetType.OTHER,         # AutoCAD Mechanical 默认层,熵高,保守归 OTHER
    "_0": AssetType.EQUIPMENT,       # 4 个 CNC/op170e/op180/op20c
}

# Phase 4.2: 系统图层黑名单 — 前缀匹配,强制归为 OTHER 并降低置信度。
# 这些图层来自 CAD 软件内部(Autodesk render/lighting/viewport 等),不是物理工厂实体。
# 保守起见只保留明确的系统图层(避免误伤 AM_0 等 Mechanical 默认图层)。
_SYSTEM_LAYER_PREFIXES: tuple[str, ...] = (
    "ADSK_SYSTEM",    # Autodesk 系统(lighting/viewport/materials)
    "*ADSK_SYSTEM",
    "DEFPOINTS",      # 定义点(不打印的辅助点)
    "СИСТЕМНЫЙ",      # 俄语 "Системный слой" (LLM 明确指出 cold_rolled 中 95807/95856 实体)
)

# S2-T3: 注释类 DXF 实体 — 一旦命中即强制 ANNOTATION (覆盖所有上游分类)。
# 这些实体类型语义明确, 不应再走块名/几何/图层启发式。
_ANNOTATION_ENTITY_TYPES: frozenset[str] = frozenset({
    "TEXT", "MTEXT", "DIMENSION",
    "LEADER", "MULTILEADER", "MLEADER",
    "ATTDEF", "ATTRIB",
    "TOLERANCE",
})

# 实体类型 → 语义关系启发式
_SPATIAL_LINK_TYPES = {
    "INSERT": LinkType.LOCATED_IN,
    "LWPOLYLINE": LinkType.GOVERNED_BY,
}

# IMP-07: 概念层次树 — 子类型 → 父类型 (is-a 降级)
_CONCEPT_HIERARCHY: dict[AssetType, AssetType] = {
    AssetType.CNC_MACHINE: AssetType.EQUIPMENT,
    AssetType.ELECTRICAL_PANEL: AssetType.EQUIPMENT,
    AssetType.STORAGE_RACK: AssetType.EQUIPMENT,
    AssetType.LIFTING_POINT: AssetType.EQUIPMENT,
    AssetType.CONVEYOR: AssetType.EQUIPMENT,
    AssetType.DOOR: AssetType.WALL,
    AssetType.WINDOW: AssetType.WALL,
    AssetType.PIPE: AssetType.EQUIPMENT,
}

# IMP-10: 俄语钢铁行业 block 模式
_RUSSIAN_STEEL_PATTERNS: dict[AssetType, list[str]] = {
    AssetType.EQUIPMENT: ["станок", "пресс", "печь", "прокат", "стан", "машин"],
    AssetType.CONVEYOR: ["рольганг", "конвейер", "транспорт"],
    AssetType.PIPE: ["труба", "воздуховод", "газопровод"],
    AssetType.ZONE: ["участок", "цех", "пролёт"],
}


@dataclass
class ParseResult:
    """execute_full 的完整返回值，包含中间结果用于持久化。"""
    site_model: SiteModel
    mcp_context: MCPContext
    format_detected: str = ""
    raw_entities: list[dict] = field(default_factory=list)
    file_content: bytes = b""
    filename: str = ""


def _configure_oda() -> None:
    """确保 ezdxf 能找到 ODA File Converter。"""
    if _ODA_EXE.exists():
        ezdxf.options.set("odafc-addon", "win_exec_path", str(_ODA_EXE))


def _read_dwg_via_oda(file_content: bytes, filename: str) -> ezdxf.document.Drawing:
    """通过 ODA 将 DWG bytes 转为 ezdxf Drawing。"""
    _configure_oda()
    from ezdxf.addons import odafc

    suffix = Path(filename).suffix or ".dwg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_content)
        tmp_path = tmp.name
    try:
        return odafc.readfile(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


class ParseService:
    """CAD 解析服务 — ParseAgent 的核心。"""

    @staticmethod
    def _compute_entity_centroid(e, etype: str) -> tuple[float | None, float, float]:
        """IMP-11 (Phase B): 为无 insert/start 属性的几何实体计算质心。

        返回 (x, y, z)；x 为 None 表示无法计算（或结果等同原点）。
        支持: CIRCLE, ARC, ELLIPSE (center),
              LWPOLYLINE/POLYLINE (顶点均值),
              SPLINE (fit/control 点均值),
              HATCH (首条边界路径顶点均值),
              3DFACE/SOLID (角点均值)。
        """
        try:
            # 中心点类
            if etype in ("CIRCLE", "ARC", "ELLIPSE") and hasattr(e.dxf, "center"):
                c = e.dxf.center
                return float(c[0]), float(c[1]), float(c[2]) if len(c) > 2 else 0.0

            # 顶点均值类
            pts: list[tuple[float, float, float]] = []

            if etype == "LWPOLYLINE":
                try:
                    for v in e.get_points("xy"):
                        pts.append((float(v[0]), float(v[1]), 0.0))
                except Exception:
                    pass

            elif etype == "POLYLINE":
                try:
                    for vtx in e.vertices:
                        loc = vtx.dxf.location
                        pts.append((float(loc[0]), float(loc[1]),
                                    float(loc[2]) if len(loc) > 2 else 0.0))
                except Exception:
                    pass

            elif etype == "SPLINE":
                try:
                    fit = list(getattr(e, "fit_points", []) or [])
                    if not fit:
                        fit = list(getattr(e, "control_points", []) or [])
                    for p in fit:
                        pts.append((float(p[0]), float(p[1]),
                                    float(p[2]) if len(p) > 2 else 0.0))
                except Exception:
                    pass

            elif etype == "HATCH":
                try:
                    paths = getattr(e, "paths", None)
                    if paths:
                        first = None
                        for p in paths:
                            first = p
                            break
                        if first is not None:
                            # EdgePath / PolylinePath 都有 vertices 方法或 edges
                            if hasattr(first, "vertices"):
                                for v in first.vertices:
                                    pts.append((float(v[0]), float(v[1]), 0.0))
                            elif hasattr(first, "edges"):
                                for edge in first.edges:
                                    if hasattr(edge, "start"):
                                        s = edge.start
                                        pts.append((float(s[0]), float(s[1]), 0.0))
                except Exception:
                    pass

            elif etype in ("3DFACE", "SOLID", "TRACE"):
                for attr in ("vtx0", "vtx1", "vtx2", "vtx3"):
                    if hasattr(e.dxf, attr):
                        v = getattr(e.dxf, attr)
                        pts.append((float(v[0]), float(v[1]),
                                    float(v[2]) if len(v) > 2 else 0.0))

            if pts:
                n = len(pts)
                x = sum(p[0] for p in pts) / n
                y = sum(p[1] for p in pts) / n
                z = sum(p[2] for p in pts) / n
                return x, y, z

        except Exception:
            pass

        return None, 0.0, 0.0

    def format_detect(self, file_content: bytes, filename: str) -> str:
        """步骤 1.1: 格式检测 — 读取文件头 magic bytes，匹配 DWG 版本。"""
        ext = Path(filename).suffix.upper()
        if ext in (".DXF",):
            return "DXF"
        # DWG: 前 6 字节是 AC 版本标识
        if len(file_content) < 6:
            return "UNKNOWN"
        magic = file_content[:6].decode("ascii", errors="replace")
        if magic in _DWG_VERSION_MAP:
            return _DWG_VERSION_MAP[magic]
        # 可能是带 BOM 或其他情况
        if magic.startswith("AC"):
            return f"DWG-{magic}"
        return "UNKNOWN"

    def entity_extract(self, file_content: bytes, format_str: str) -> list[dict]:
        """步骤 1.2: 实体提取 — 解析所有 CAD entities。

        丰富信号字段:
        - block_name: INSERT 实体的块定义名称
        - is_closed / vertex_count: LWPOLYLINE/POLYLINE 的闭合状态与顶点数
        """
        doc = _read_dwg_via_oda(file_content, "input.dwg")
        msp = doc.modelspace()
        entities: list[dict] = []
        for e in msp:
            etype = e.dxftype()
            rec: dict = {
                "type": etype,
                "layer": e.dxf.layer if hasattr(e.dxf, "layer") else "0",
                "handle": e.dxf.handle if hasattr(e.dxf, "handle") else "",
            }
            # 提取坐标 (如有)
            if hasattr(e.dxf, "insert"):
                pt = e.dxf.insert
                rec["coords"] = {"x": float(pt[0]), "y": float(pt[1]), "z": float(pt[2]) if len(pt) > 2 else 0.0}
                rec["coord_source"] = "insert"
            elif hasattr(e.dxf, "start"):
                pt = e.dxf.start
                rec["coords"] = {"x": float(pt[0]), "y": float(pt[1]), "z": float(pt[2]) if len(pt) > 2 else 0.0}
                rec["coord_source"] = "start"

            # IMP-11 (Phase B): 几何质心回退 — 许多实体类型 (LWPOLYLINE/HATCH/
            # CIRCLE/ARC/SPLINE/REGION/3DSOLID/WIPEOUT) 没有 insert/start 属性,
            # 会导致 Asset 坐标回退到默认 (0,0,0)。为这些实体计算几何质心。
            if "coords" not in rec:
                cx, cy, cz = self._compute_entity_centroid(e, etype)
                if cx is not None:
                    rec["coords"] = {"x": cx, "y": cy, "z": cz}
                    rec["coord_source"] = "centroid"

            # INSERT → block_name
            if etype == "INSERT" and hasattr(e.dxf, "name"):
                rec["block_name"] = e.dxf.name

            # TEXT / MTEXT → text_content (IMP-06)
            if etype == "TEXT" and hasattr(e.dxf, "text"):
                rec["text_content"] = e.dxf.text
            elif etype == "MTEXT":
                try:
                    rec["text_content"] = e.plain_text()
                except Exception:
                    if hasattr(e.dxf, "text"):
                        rec["text_content"] = e.dxf.text

            # LWPOLYLINE / POLYLINE → is_closed, vertex_count
            if etype in ("LWPOLYLINE", "POLYLINE"):
                rec["is_closed"] = bool(getattr(e, "is_closed", False))
                try:
                    rec["vertex_count"] = len(list(e.vertices()))
                except Exception:
                    rec["vertex_count"] = 0

            entities.append(rec)
        return entities

    def coord_normalize(self, entities: list[dict], coord_system: str) -> list[dict]:
        """步骤 1.3: 坐标标准化 — WCS/UCS 变换，单位归一化到 mm。"""
        for e in entities:
            e["coord_system"] = "WCS"
            e["unit"] = "mm"
        return entities

    def topology_repair(self, entities: list[dict]) -> tuple[list[dict], float]:
        """步骤 1.4: 拓扑修补 — 闭合 polyline、去重、自交检测。

        返回: (修补后的实体列表, geometry_integrity_score)
        """
        seen_handles: set[str] = set()
        repaired: list[dict] = []
        duplicates = 0
        for e in entities:
            h = e.get("handle", "")
            if h and h in seen_handles:
                duplicates += 1
                continue
            if h:
                seen_handles.add(h)
            repaired.append(e)

        total = len(entities)
        integrity = 1.0 - (duplicates / total) if total > 0 else 1.0
        return repaired, round(integrity, 4)

    def classify_entity(self, entities: list[dict], ontology_version: str) -> list[Asset]:
        """步骤 2: 本体资产识别 — 多信号置信度评分。

        置信度 = 0.30×block_name_match + 0.25×geometry_pattern
                + 0.20×layer_hint + 0.15×entity_complexity + 0.10×reference_check

        分类优先级: block_name > geometry_pattern > layer_hint > fallback(OTHER)
        """
        assets: list[Asset] = []
        for e in entities:
            layer = e.get("layer", "").upper()
            etype = e.get("type", "")
            block_name = e.get("block_name", "")

            # ── 信号 1: block_name 匹配 (0.30) ──
            block_score = 0.0
            block_type: AssetType | None = None
            if block_name:
                bn_lower = block_name.lower()
                # 匿名块检测 (A$C*, 纯数字编号如 U0~U99)
                is_anon = (
                    bn_lower.startswith("a$c")
                    or bn_lower.startswith("*")
                    or (bn_lower.startswith("u") and bn_lower[1:].isdigit())
                )
                if not is_anon:
                    for atype, keywords in _BLOCK_ASSET_PATTERNS.items():
                        if any(kw in bn_lower or kw in block_name for kw in keywords):
                            block_score = 1.0
                            block_type = atype
                            break
                    if block_type is None:
                        # 有命名但未匹配已知模式 → 中等信号
                        block_score = 0.3

            # ── 信号 2: 几何模式 (0.25) ──
            geom_score = 0.0
            geom_type: AssetType | None = None
            has_coords = "coords" in e
            if has_coords:
                geom_score = 0.5
            if etype in ("LWPOLYLINE", "POLYLINE") and e.get("is_closed"):
                vc = e.get("vertex_count", 0)
                if vc >= 4:
                    geom_score = 1.0
                    geom_type = AssetType.ZONE
                else:
                    geom_score = 0.6
            elif etype == "HATCH" and has_coords:
                # Phase 4.1: HATCH 是闭合填充区域 → Zone 候选 (几何质心已在 entity_extract 记录)
                geom_score = 0.9
                geom_type = AssetType.ZONE
            elif etype == "INSERT" and has_coords:
                geom_score = 0.8

            # ── 信号 3: 图层名启发式 (0.20) ──
            layer_score = 0.0
            layer_type: AssetType | None = None
            for key, atype in _LAYER_ASSET_MAP.items():
                if key in layer:
                    layer_score = 1.0
                    layer_type = atype
                    break

            # ── 信号 4: 实体复杂度 (0.15) ──
            complexity_score = 0.0
            if etype == "INSERT":
                complexity_score = 0.8
            elif etype in ("LWPOLYLINE", "POLYLINE"):
                vc = e.get("vertex_count", 0)
                complexity_score = min(1.0, vc / 20.0)  # 越多顶点越复杂
            elif etype in ("LINE", "ARC", "CIRCLE"):
                complexity_score = 0.3
            elif etype in ("MTEXT", "TEXT", "DIMENSION"):
                complexity_score = 0.1

            # ── 信号 5: 引用检查 (0.10) ──
            ref_score = 1.0 if e.get("handle") else 0.0

            # ── 加权汇总 ──
            confidence = round(
                0.30 * block_score
                + 0.25 * geom_score
                + 0.20 * layer_score
                + 0.15 * complexity_score
                + 0.10 * ref_score,
                4,
            )

            # ── 类型决策: 优先级 block > geometry > layer > OTHER ──
            asset_type = block_type or geom_type or layer_type or AssetType.OTHER

            coords_data = e.get("coords", {})

            # ── IMP-05: Zone 二次验证 ──
            if asset_type == AssetType.ZONE:
                # 验证 1: 图层明确指向非 Zone 类型 → 图层信号覆盖几何
                if layer_type and layer_type != AssetType.ZONE:
                    asset_type = layer_type
                # 验证 2: (0,0,0) 精确原点 + 低置信 → 降级为 OTHER
                elif (coords_data.get("x", 0.0) == 0.0
                      and coords_data.get("y", 0.0) == 0.0
                      and confidence < 0.4):
                    asset_type = AssetType.OTHER

            # ── IMP-07: 概念层次降级匹配 ──
            if asset_type == AssetType.OTHER and confidence > 0.15:
                # 检查是否有任何信号能映射到概念层次树中的父类型
                hint_type = block_type or geom_type or layer_type
                if hint_type and hint_type in _CONCEPT_HIERARCHY:
                    asset_type = _CONCEPT_HIERARCHY[hint_type]
                    confidence = max(confidence, 0.3)

            # ── IMP-10: 俄语钢铁行业 block 模式 (补充匹配) ──
            if asset_type == AssetType.OTHER and block_name:
                bn_lower = block_name.lower()
                for atype, keywords in _RUSSIAN_STEEL_PATTERNS.items():
                    if any(kw in bn_lower for kw in keywords):
                        asset_type = atype
                        confidence = max(confidence, 0.35)
                        break

            # Phase 4.2: 系统图层黑名单 — 覆盖其他分类结果,强制降级为 OTHER 低置信度
            if any(layer.startswith(prefix) for prefix in _SYSTEM_LAYER_PREFIXES):
                asset_type = AssetType.OTHER
                confidence = min(confidence, 0.15)

            # ── S2-T3: ANNOTATION 实体最终覆盖 (位置最末,胜过所有规则) ──
            # TEXT/MTEXT/DIMENSION 等实体类型语义明确, 即使在系统图层上也应被识别为注释,
            # 给下游 (text_extraction, label-asset 关联) 提供准确信号。
            if etype in _ANNOTATION_ENTITY_TYPES:
                asset_type = AssetType.ANNOTATION
                confidence = max(confidence, 0.85)

            asset = Asset(
                type=asset_type,
                coords=Coords(
                    x=coords_data.get("x", 0.0),
                    y=coords_data.get("y", 0.0),
                    z=coords_data.get("z", 0.0),
                ),
                confidence=confidence,
                layer=e.get("layer", ""),
                block_name=block_name,
                coord_source=e.get("coord_source", ""),
            )
            assets.append(asset)
        return assets

    @staticmethod
    def filter_anomalous_coords(assets: list[Asset]) -> list[Asset]:
        """IMP-03: 坐标异常过滤 — 标记原点嫌疑 + 离群点降置信。

        规则:
        1. (0,0,0) 精确原点 + confidence < 0.3 → type 降为 OTHER
        2. 计算 P5/P95 分位的 bounding box
        3. 超出 bbox 3 倍 IQR → confidence *= 0.5, type 降为 OTHER
        """
        if not assets:
            return assets

        # 收集有效坐标用于统计
        xs = [a.coords.x for a in assets if not (a.coords.x == 0.0 and a.coords.y == 0.0)]
        ys = [a.coords.y for a in assets if not (a.coords.x == 0.0 and a.coords.y == 0.0)]

        if len(xs) < 4:
            return assets

        xs_sorted = sorted(xs)
        ys_sorted = sorted(ys)
        n = len(xs_sorted)
        p5_idx = max(0, int(n * 0.05))
        p95_idx = min(n - 1, int(n * 0.95))

        x_p5, x_p95 = xs_sorted[p5_idx], xs_sorted[p95_idx]
        y_p5, y_p95 = ys_sorted[p5_idx], ys_sorted[p95_idx]

        x_iqr = x_p95 - x_p5 if x_p95 != x_p5 else 1.0
        y_iqr = y_p95 - y_p5 if y_p95 != y_p5 else 1.0

        x_lo = x_p5 - 3 * x_iqr
        x_hi = x_p95 + 3 * x_iqr
        y_lo = y_p5 - 3 * y_iqr
        y_hi = y_p95 + 3 * y_iqr

        for a in assets:
            cx, cy = a.coords.x, a.coords.y
            # 规则 1: (0,0,0) 精确原点 + 低置信
            if cx == 0.0 and cy == 0.0 and a.coords.z == 0.0 and a.confidence < 0.3:
                a.type = AssetType.OTHER

            # 规则 3: 离群点
            elif cx < x_lo or cx > x_hi or cy < y_lo or cy > y_hi:
                a.confidence = round(a.confidence * 0.5, 4)
                a.type = AssetType.OTHER

        return assets

    @staticmethod
    def associate_text_labels(
        assets: list[Asset],
        raw_entities: list[dict],
        max_radius: float = 2000.0,
    ) -> tuple[list[Asset], list[OntologyLink]]:
        """IMP-06: 空间标签关联 — 将 TEXT/MTEXT 内容关联到最近的非文本资产。

        返回: (更新后的 assets, 新增的 LABELED_BY links)
        """
        # 收集文本实体 (有坐标 + 有内容)
        text_entries: list[tuple[float, float, str]] = []
        for ent in raw_entities:
            tc = ent.get("text_content", "").strip()
            if not tc:
                continue
            c = ent.get("coords")
            if not c:
                continue
            text_entries.append((float(c["x"]), float(c["y"]), tc))

        if not text_entries or not assets:
            return assets, []

        # 筛选可关联的资产 (非 OTHER, 有有效坐标)
        candidate_indices: list[int] = []
        candidate_coords: list[tuple[float, float]] = []
        for i, a in enumerate(assets):
            if a.type != AssetType.OTHER:
                candidate_indices.append(i)
                candidate_coords.append((a.coords.x, a.coords.y))

        if not candidate_indices:
            return assets, []

        links: list[OntologyLink] = []

        # KD-tree or brute-force
        try:
            from scipy.spatial import cKDTree
            tree = cKDTree(candidate_coords)
            for tx, ty, text in text_entries:
                dist, idx = tree.query([tx, ty])
                if dist <= max_radius:
                    asset_idx = candidate_indices[idx]
                    if not assets[asset_idx].label:
                        assets[asset_idx].label = text
                        links.append(OntologyLink(
                            source_guid=assets[asset_idx].asset_guid,
                            target_guid=assets[asset_idx].asset_guid,
                            link_type=LinkType.LABELED_BY,
                            metadata={"label": text, "distance_mm": round(dist, 1)},
                        ))
        except ImportError:
            # Brute-force fallback
            for tx, ty, text in text_entries:
                best_dist = float("inf")
                best_idx = -1
                for j, (cx, cy) in enumerate(candidate_coords):
                    d = math.sqrt((tx - cx) ** 2 + (ty - cy) ** 2)
                    if d < best_dist:
                        best_dist = d
                        best_idx = j
                if best_dist <= max_radius and best_idx >= 0:
                    asset_idx = candidate_indices[best_idx]
                    if not assets[asset_idx].label:
                        assets[asset_idx].label = text
                        links.append(OntologyLink(
                            source_guid=assets[asset_idx].asset_guid,
                            target_guid=assets[asset_idx].asset_guid,
                            link_type=LinkType.LABELED_BY,
                            metadata={"label": text, "distance_mm": round(best_dist, 1)},
                        ))

        return assets, links

    @staticmethod
    def propagate_spatial_context(
        assets: list[Asset],
        k: int = 5,
        radius: float = 3000.0,
    ) -> list[Asset]:
        """IMP-08: KNN 空间上下文传播 — 用邻域共识增强/降级分类置信度。

        规则:
        - ≥3/k 邻居同类型, 自身 OTHER → 提升为该类型 (conf=0.35)
        - 自身有类型且邻居一致 → confidence × 1.2 (上限 0.95)
        - 自身有类型但邻居冲突 → confidence × 0.9
        - Zone 和 OTHER (无坐标) 不参与传播
        """
        if len(assets) < 2:
            return assets

        # 收集有有效坐标的资产索引
        valid_indices: list[int] = []
        coords_2d: list[tuple[float, float]] = []
        for i, a in enumerate(assets):
            if not (a.coords.x == 0.0 and a.coords.y == 0.0 and a.coords.z == 0.0):
                valid_indices.append(i)
                coords_2d.append((a.coords.x, a.coords.y))

        if len(valid_indices) < 2:
            return assets

        try:
            from scipy.spatial import cKDTree
            tree = cKDTree(coords_2d)

            for vi_pos, ai in enumerate(valid_indices):
                a = assets[ai]
                if a.type == AssetType.ZONE:
                    continue

                dists, idxs = tree.query(coords_2d[vi_pos], k=min(k + 1, len(coords_2d)))
                if not hasattr(idxs, '__len__'):
                    continue

                # 排除自身
                neighbor_types: list[AssetType] = []
                for ni in idxs:
                    if ni == vi_pos:
                        continue
                    if ni < len(valid_indices) and dists[list(idxs).index(ni)] <= radius:
                        neighbor_types.append(assets[valid_indices[ni]].type)

                if not neighbor_types:
                    continue

                type_counts = Counter(neighbor_types)
                majority_type, majority_count = type_counts.most_common(1)[0]

                if a.type == AssetType.OTHER and majority_count >= 3 and majority_type != AssetType.OTHER:
                    a.type = majority_type
                    a.confidence = 0.35
                elif a.type != AssetType.OTHER and a.type == majority_type:
                    a.confidence = min(0.95, round(a.confidence * 1.2, 4))
                elif a.type != AssetType.OTHER and majority_count >= 3 and a.type != majority_type:
                    a.confidence = round(a.confidence * 0.9, 4)

        except ImportError:
            pass  # No scipy → skip propagation

        return assets

    @staticmethod
    def detect_flat_drawing_mode(entities: list[dict], threshold: float = 0.90) -> bool:
        """IMP-10: 平面图模式检测 — 当 >threshold 实体在同一图层时返回 True。"""
        if not entities:
            return False
        layer_counts: dict[str, int] = {}
        for e in entities:
            layer = e.get("layer", "0")
            layer_counts[layer] = layer_counts.get(layer, 0) + 1
        max_count = max(layer_counts.values())
        return max_count / len(entities) >= threshold

    def build_ontology_graph(self, assets: list[Asset]) -> list[OntologyLink]:
        """步骤 3: 语义关系映射 — LOCATED_IN (空间最近 zone) + FEEDS (设备序列)。

        Phase C (IMP-12): 用 KD-tree 最近 zone 查询替代原先的 equipment × zones
        笛卡尔积；对坐标原点的 equipment 跳过 LOCATED_IN；阈值 10000mm。
        """
        links: list[OntologyLink] = []
        _ZONE_LIKE = {AssetType.ZONE}
        _EQUIP_LIKE = {
            AssetType.EQUIPMENT, AssetType.LIFTING_POINT, AssetType.CONVEYOR,
            AssetType.CNC_MACHINE, AssetType.ELECTRICAL_PANEL, AssetType.STORAGE_RACK,
        }
        zones = [a for a in assets if a.type in _ZONE_LIKE]
        equipment = [a for a in assets if a.type in _EQUIP_LIKE]

        MAX_DIST = 10000.0  # 10 m 阈值

        if zones and equipment:
            try:
                from scipy.spatial import cKDTree
                zone_coords = [(z.coords.x, z.coords.y) for z in zones]
                tree = cKDTree(zone_coords)
                for eq in equipment:
                    # 原点坐标 equipment 跳过 (无空间信息)
                    if eq.coords.x == 0.0 and eq.coords.y == 0.0 and eq.coords.z == 0.0:
                        continue
                    dist, idx = tree.query((eq.coords.x, eq.coords.y), k=1)
                    if dist <= MAX_DIST:
                        links.append(
                            OntologyLink(
                                source_guid=eq.asset_guid,
                                target_guid=zones[int(idx)].asset_guid,
                                link_type=LinkType.LOCATED_IN,
                            )
                        )
            except ImportError:
                # Fallback: 无 scipy 时回退到 O(n*m) 暴力近邻 (仍优于笛卡尔积)
                for eq in equipment:
                    if eq.coords.x == 0.0 and eq.coords.y == 0.0:
                        continue
                    best_z = None
                    best_d = float("inf")
                    for z in zones:
                        dx = eq.coords.x - z.coords.x
                        dy = eq.coords.y - z.coords.y
                        d = (dx * dx + dy * dy) ** 0.5
                        if d < best_d:
                            best_d = d
                            best_z = z
                    if best_z is not None and best_d <= MAX_DIST:
                        links.append(
                            OntologyLink(
                                source_guid=eq.asset_guid,
                                target_guid=best_z.asset_guid,
                                link_type=LinkType.LOCATED_IN,
                            )
                        )

        # 设备间序列关系 (保留原逻辑)
        for i in range(len(equipment) - 1):
            links.append(
                OntologyLink(
                    source_guid=equipment[i].asset_guid,
                    target_guid=equipment[i + 1].asset_guid,
                    link_type=LinkType.FEEDS,
                )
            )
        return links

    # ── 质量度量 ──

    LOW_CONFIDENCE_THRESHOLD = 0.4

    @staticmethod
    def _compute_quality_stats(
        assets: list[Asset],
        low_threshold: float = 0.4,
    ) -> dict:
        """计算资产质量聚合指标 + QualityVerdict。"""
        total = len(assets)
        if total == 0:
            return {
                "avg_confidence": 0.0,
                "min_confidence": 0.0,
                "max_confidence": 0.0,
                "stdev_confidence": 0.0,
                "low_confidence_count": 0,
                "low_confidence_ratio": 0.0,
                "classified_ratio": 0.0,
                "verdict": "FAILED",
            }

        confs = [a.confidence for a in assets]
        avg = sum(confs) / total
        min_c = min(confs)
        max_c = max(confs)
        variance = sum((c - avg) ** 2 for c in confs) / total
        stdev = round(math.sqrt(variance), 4)

        low_count = sum(1 for c in confs if c < low_threshold)
        low_ratio = round(low_count / total, 4)

        classified = sum(1 for a in assets if a.type != AssetType.OTHER)
        classified_ratio = round(classified / total, 4)

        # QualityVerdict 路由
        if classified_ratio < 0.1:
            verdict = "DEGRADED"
        elif low_ratio > 0.3:
            verdict = "SUCCESS_WITH_WARNINGS"
        elif avg < 0.3:
            verdict = "DEGRADED"
        else:
            verdict = "SUCCESS"

        return {
            "avg_confidence": round(avg, 4),
            "min_confidence": round(min_c, 4),
            "max_confidence": round(max_c, 4),
            "stdev_confidence": stdev,
            "low_confidence_count": low_count,
            "low_confidence_ratio": low_ratio,
            "classified_ratio": classified_ratio,
            "verdict": verdict,
        }

    @staticmethod
    def refine_confidence(assets: list[Asset]) -> list[Asset]:
        """IMP-13 (Phase D): 置信度连续化 — 为同类同 block_name 的
        资产加入实例级修饰符，打破分数离散分础。

        修饰符:
        - coord_quality: coord_source=='insert'|'start' 且非原点 → +0.05;
                         'centroid' → +0.03;
                         空/默认原点 → -0.05 (但不低于 0.05)
        - label_bonus:   asset.label 非空 → +0.03
        最终 conf clamp 在 [0.05, 0.98] 区间。
        OTHER 类型不调整 (避免反向拉高)。
        """
        for a in assets:
            if a.type == AssetType.OTHER:
                continue
            delta = 0.0
            src = a.coord_source
            at_origin = (a.coords.x == 0.0 and a.coords.y == 0.0 and a.coords.z == 0.0)
            if src in ("insert", "start") and not at_origin:
                delta += 0.05
            elif src == "centroid" and not at_origin:
                delta += 0.03
            elif at_origin or not src:
                delta -= 0.05
            if a.label:
                delta += 0.03
            a.confidence = round(max(0.05, min(0.98, a.confidence + delta)), 4)
        return assets

    def build_site_model(
        self,
        cad_source: CADSource,
        assets: list[Asset],
        links: list[OntologyLink],
        integrity_score: float,
    ) -> SiteModel:
        """步骤 4: SiteModel 序列化与生成。"""
        type_counts: dict[str, int] = {}
        for a in assets:
            t = a.type.value
            type_counts[t] = type_counts.get(t, 0) + 1

        layer_counts: dict[str, int] = {}
        for a in assets:
            layer_counts[a.layer] = layer_counts.get(a.layer, 0) + 1

        quality = self._compute_quality_stats(assets, self.LOW_CONFIDENCE_THRESHOLD)

        return SiteModel(
            cad_source=cad_source,
            assets=assets,
            links=links,
            geometry_integrity_score=integrity_score,
            statistics={
                "total_assets": len(assets),
                "total_links": len(links),
                "asset_types": type_counts,
                "layer_distribution": layer_counts,
                "quality": quality,
            },
        )

    def execute(self, file_content: bytes, filename: str, **options) -> tuple[SiteModel, MCPContext]:
        """完整执行管线 — 串联步骤 1-4，输出 SiteModel + MCP Context。

        Phase 2 增强: IMP-06 文本关联, IMP-08 空间传播, IMP-09 闭环迭代
        """
        start = time.perf_counter()
        ctx = MCPContext(
            mcp_context_id=generate_context_id("parse"),
            agent="ParseAgent",
            agent_version="v1.0",
            input_payload={"filename": filename, "size_bytes": len(file_content)},
        )
        steps: list[dict] = []

        # 1.1 格式检测
        fmt = self.format_detect(file_content, filename)
        steps.append({"step": "format_detect", "result": fmt})

        # 1.2 实体提取
        entities = self.entity_extract(file_content, fmt)
        steps.append({"step": "entity_extract", "count": len(entities)})

        # 1.3 坐标标准化
        entities = self.coord_normalize(entities, options.get("coord_system", "WCS"))
        steps.append({"step": "coord_normalize", "count": len(entities)})

        # 1.4 拓扑修补
        entities, integrity = self.topology_repair(entities)
        steps.append({"step": "topology_repair", "integrity": integrity, "count": len(entities)})

        # IMP-10: 平面图模式检测
        flat_mode = self.detect_flat_drawing_mode(entities)
        steps.append({"step": "detect_flat_drawing_mode", "flat_mode": flat_mode})

        # ── IMP-09: 闭环迭代 (最多 3 轮) ──
        max_rounds = options.get("max_iteration_rounds", 3)
        ontology_ver = options.get("ontology_version", "AeroOntology-v1.0")
        prev_type_dist: Counter | None = None

        for round_idx in range(max_rounds):
            # 2. 资产识别
            assets = self.classify_entity(entities, ontology_ver)

            # 2.5 坐标异常过滤 (IMP-03)
            assets = self.filter_anomalous_coords(assets)

            # 2.6 文本标签关联 (IMP-06)
            assets, label_links = self.associate_text_labels(assets, entities)

            # 2.7 空间上下文传播 (IMP-08)
            assets = self.propagate_spatial_context(assets)

            # 收敛检测
            type_dist = Counter(a.type for a in assets)
            if type_dist == prev_type_dist:
                steps.append({"step": "iteration_converged", "round": round_idx + 1})
                break
            prev_type_dist = type_dist

        steps.append({"step": "classify_and_refine", "asset_count": len(assets), "rounds": round_idx + 1})

        # Phase D: 置信度连续化
        assets = self.refine_confidence(assets)
        steps.append({"step": "refine_confidence", "asset_count": len(assets)})

        # 3. 关系映射
        links = self.build_ontology_graph(assets)
        links.extend(label_links)  # IMP-06: 添加 LABELED_BY 边
        steps.append({"step": "build_ontology_graph", "link_count": len(links)})

        # 4. SiteModel 生成
        sha = hashlib.sha256(file_content).hexdigest()
        cad_source = CADSource(filename=filename, sha256=sha, format=CADFormat.DWG)
        site_model = self.build_site_model(cad_source, assets, links, integrity)
        steps.append({"step": "build_site_model", "site_model_id": site_model.site_model_id})

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        ctx.latency_ms = elapsed_ms
        ctx.step_breakdown = steps
        ctx.output_payload = {"site_model_id": site_model.site_model_id, "asset_count": len(assets)}

        # 根据 QualityVerdict 设置 Agent 状态
        verdict = site_model.statistics.get("quality", {}).get("verdict", "SUCCESS")
        if verdict == "SUCCESS_WITH_WARNINGS":
            ctx.status = AgentStatus.SUCCESS_WITH_WARNINGS
        elif verdict == "DEGRADED":
            ctx.status = AgentStatus.SUCCESS_WITH_WARNINGS
        else:
            ctx.status = AgentStatus.SUCCESS

        return site_model, ctx

    def execute_full(self, file_content: bytes, filename: str, **options) -> ParseResult:
        """完整执行管线 — 同 execute()，但额外返回中间结果用于持久化。"""
        start = time.perf_counter()
        ctx = MCPContext(
            mcp_context_id=generate_context_id("parse"),
            agent="ParseAgent",
            agent_version="v1.0",
            input_payload={"filename": filename, "size_bytes": len(file_content)},
        )
        steps: list[dict] = []

        fmt = self.format_detect(file_content, filename)
        steps.append({"step": "format_detect", "result": fmt})

        raw_entities = self.entity_extract(file_content, fmt)
        steps.append({"step": "entity_extract", "count": len(raw_entities)})

        entities = self.coord_normalize(list(raw_entities), options.get("coord_system", "WCS"))
        steps.append({"step": "coord_normalize", "count": len(entities)})

        entities, integrity = self.topology_repair(entities)
        steps.append({"step": "topology_repair", "integrity": integrity, "count": len(entities)})

        # IMP-10: 平面图模式检测
        flat_mode = self.detect_flat_drawing_mode(entities)
        steps.append({"step": "detect_flat_drawing_mode", "flat_mode": flat_mode})

        # ── IMP-09: 闭环迭代 (最多 3 轮) ──
        max_rounds = options.get("max_iteration_rounds", 3)
        ontology_ver = options.get("ontology_version", "AeroOntology-v1.0")
        prev_type_dist: Counter | None = None
        label_links: list[OntologyLink] = []

        for round_idx in range(max_rounds):
            assets = self.classify_entity(entities, ontology_ver)
            assets = self.filter_anomalous_coords(assets)
            assets, label_links = self.associate_text_labels(assets, entities)
            assets = self.propagate_spatial_context(assets)

            type_dist = Counter(a.type for a in assets)
            if type_dist == prev_type_dist:
                steps.append({"step": "iteration_converged", "round": round_idx + 1})
                break
            prev_type_dist = type_dist

        steps.append({"step": "classify_and_refine", "asset_count": len(assets), "rounds": round_idx + 1})

        # Phase D: 置信度连续化
        assets = self.refine_confidence(assets)
        steps.append({"step": "refine_confidence", "asset_count": len(assets)})

        links = self.build_ontology_graph(assets)
        links.extend(label_links)
        steps.append({"step": "build_ontology_graph", "link_count": len(links)})

        sha = hashlib.sha256(file_content).hexdigest()
        cad_source = CADSource(filename=filename, sha256=sha, format=CADFormat.DWG)
        site_model = self.build_site_model(cad_source, assets, links, integrity)
        steps.append({"step": "build_site_model", "site_model_id": site_model.site_model_id})

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        ctx.latency_ms = elapsed_ms
        ctx.step_breakdown = steps
        ctx.output_payload = {"site_model_id": site_model.site_model_id, "asset_count": len(assets)}

        # 根据 QualityVerdict 设置 Agent 状态
        verdict = site_model.statistics.get("quality", {}).get("verdict", "SUCCESS")
        if verdict == "SUCCESS_WITH_WARNINGS":
            ctx.status = AgentStatus.SUCCESS_WITH_WARNINGS
        elif verdict == "DEGRADED":
            ctx.status = AgentStatus.SUCCESS_WITH_WARNINGS
        else:
            ctx.status = AgentStatus.SUCCESS

        return ParseResult(
            site_model=site_model,
            mcp_context=ctx,
            format_detected=fmt,
            raw_entities=raw_entities,
            file_content=file_content,
            filename=filename,
        )
