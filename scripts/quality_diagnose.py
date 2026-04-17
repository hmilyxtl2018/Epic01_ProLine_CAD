"""根因分析器 — 针对低分 DWG 自动定位问题层和修复优先级.

用法:
    # 单文件深挖
    python scripts/quality_diagnose.py --file example_2000.dwg

    # 全量扫描,按 overall 升序排,先看最差的
    python scripts/quality_diagnose.py --all

    # 低分阈值 & 维度阈值(默认 overall<0.3 或某维度<0.25 才诊断)
    python scripts/quality_diagnose.py --all --overall-threshold 0.3 --dim-threshold 0.25

输出:
    1. 客观指标 (coord_validity / layer_purity / link_symmetry)
    2. LLM 低分维度 + 证据摘要
    3. 根因标签清单 (可自动 vs 需人工)
    4. 推荐修复动作 (按 ROI 排序)

设计目标: 让 "看到低分 → 知道为啥低 → 知道改哪" 这条链走自动化.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Windows 控制台默认 GBK,对 emoji/bullet 报 UnicodeEncodeError.
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

RESULTS_DIR = PROJECT_ROOT / "exp" / "parse_results" / "run_p0_all"
MATRIX_PATH = RESULTS_DIR / "llm_quality_matrix.json"


# ════════════════════════════════════════════════════════════════════
#  根因标签表 — 每个标签描述一类可识别的失败模式
# ════════════════════════════════════════════════════════════════════

ROOT_CAUSE_TAGS: dict[str, dict] = {
    "coord_origin_dump": {
        "desc": "多数 asset 的 coord 落在原点附近,提示 INSERT 块未应用变换",
        "fix_difficulty": "medium",
        "fix_hint": "service.py 增强 INSERT 嵌套变换,或用 block_ref.dxf.insert + extrusion",
    },
    "coord_scale_outlier": {
        "desc": "少数 asset 坐标量级远超其他(亿级 vs 万级),提示 UCS/paper-space 变换错误",
        "fix_difficulty": "medium",
        "fix_hint": "service.py 检测 |coord|>1e8 的离群点,打 coord_source='suspect' 并 confidence-=0.3",
    },
    "block_name_semantic_miss": {
        "desc": "存在有明确业务语义的块名(Dryer/Saw/Hoist等)但被判为 Equipment/Other",
        "fix_difficulty": "low",
        "fix_hint": "service.py 扩展 _BLOCK_ASSET_PATTERNS,加 Equipment 子类型枚举",
    },
    "layer_semantic_miss": {
        "desc": "有明确语义的图层(sanitary/HVAC/COIL等)被简单判为 Other",
        "fix_difficulty": "low",
        "fix_hint": "service.py 扩展 _LAYER_ASSET_MAP,支持正则或国际化关键词",
    },
    "geom_closed_miss": {
        "desc": "存在首末点距离<eps 的 LWPOLYLINE/POLYLINE 未被判闭合 → Zone 漏判",
        "fix_difficulty": "low",
        "fix_hint": "service.py classify_entity 增加启发式闭合检测(首末距 < bbox 对角 * 0.01)",
    },
    "subtype_missing": {
        "desc": "Equipment 占比高但未细分(CNC/Saw/Planer/Dryer),降低 semantic_richness",
        "fix_difficulty": "medium",
        "fix_hint": "shared/models.py 扩展 AssetType 枚举,service.py 按 block_name 关键词细分",
    },
    "annotation_noise": {
        "desc": "DIMENSION/TEXT/MTEXT/LEADER/TOLERANCE 被分为 Other,稀释分类准确率",
        "fix_difficulty": "low",
        "fix_hint": "service.py classify_entity 针对 entity_type ∈ {DIMENSION,TEXT,MTEXT,LEADER,MULTILEADER,TOLERANCE} → asset_type=Annotation(需新增)",
    },
    "data_sparse": {
        "desc": "实体 >1 万但 link <10 或 asset_type 集中在单一值 → 数据本身信息稀少",
        "fix_difficulty": "high",
        "fix_hint": "不建议通过 parser 修复.改 eval 权重或在矩阵里标 'degraded/sparse' 剔除 avg",
    },
    "system_layer_residue": {
        "desc": "系统/辅助层(ADSK_SYSTEM/DEFPOINTS/СИСТЕМНЫЙ等)仍占大比例",
        "fix_difficulty": "low",
        "fix_hint": "service.py _SYSTEM_LAYER_PREFIXES 补充关键词(当前已覆盖 4 个,但可能有本地化变体)",
    },
    "link_inflation": {
        "desc": "FEEDS 链接数 > Conveyor 数 * 2,提示链接算法过度生成",
        "fix_difficulty": "medium",
        "fix_hint": "service.py build_ontology_graph 收紧 KD-tree 阈值,或去重双向链接",
    },
    "zone_undergenerated": {
        "desc": "Equipment>20 但 Zone==0,LOCATED_IN==0 → 没有空间上下文",
        "fix_difficulty": "medium",
        "fix_hint": "service.py HATCH→Zone + closed LWPOLYLINE→Zone 规则需覆盖更多几何类型",
    },
}


# ════════════════════════════════════════════════════════════════════
#  客观指标
# ════════════════════════════════════════════════════════════════════

def compute_coord_validity(assets: list[dict]) -> dict:
    """有多少 asset 的 coord 属于'有效'范围.
    
    判据:
      - 非原点 (|x|+|y| > 1e-3)
      - 有限 (非 NaN/inf)
      - 量级合理 (|x|,|y| < 1e8, DWG 单位通常毫米,10^8 mm = 100 km 已超厂区)
    """
    if not assets:
        return {"total": 0, "valid": 0, "ratio": 0.0, "outliers": []}
    total = len(assets)
    valid = 0
    origin = 0
    outliers = []
    for a in assets:
        c = a.get("coords") or {}
        x, y = c.get("x", 0), c.get("y", 0)
        if not (math.isfinite(x) and math.isfinite(y)):
            continue
        if abs(x) + abs(y) < 1e-3:
            origin += 1
            continue
        if abs(x) > 1e8 or abs(y) > 1e8:
            outliers.append({
                "guid": a.get("asset_guid", "?"),
                "type": a.get("type"),
                "layer": a.get("layer"),
                "block": a.get("block_name"),
                "coords": (round(x, 1), round(y, 1)),
            })
            continue
        valid += 1
    return {
        "total": total,
        "valid": valid,
        "ratio": round(valid / total, 4),
        "origin_count": origin,
        "outlier_count": len(outliers),
        "outliers": outliers[:5],  # 代表样本
    }


def compute_layer_purity(assets: list[dict]) -> dict:
    """每层的 asset_type 分布熵 (越低=越"纯").
    
    返回每层熵 + 全局加权平均熵.低分通常意味着"layer 映射规则能分离类型".
    """
    by_layer = defaultdict(Counter)
    for a in assets:
        by_layer[a.get("layer") or "<none>"][a.get("type") or "<none>"] += 1
    
    entries = []
    total_weighted_entropy = 0.0
    total_count = 0
    for lyr, types in by_layer.items():
        n = sum(types.values())
        if n == 0:
            continue
        H = 0.0
        for c in types.values():
            p = c / n
            if p > 0:
                H -= p * math.log2(p)
        entries.append({
            "layer": lyr,
            "count": n,
            "entropy": round(H, 3),
            "dominant_type": types.most_common(1)[0][0],
            "type_dist": dict(types),
        })
        total_weighted_entropy += H * n
        total_count += n
    entries.sort(key=lambda e: -e["count"])
    
    return {
        "layers": len(entries),
        "weighted_avg_entropy": round(total_weighted_entropy / max(total_count, 1), 3),
        "top_layers": entries[:8],
    }


def compute_link_symmetry(links: list[dict]) -> dict:
    """双向 FEEDS 链接对数 / 总 FEEDS 数. 高对称意味着'管道'而非'散点'."""
    feeds = [l for l in links if l.get("link_type") == "FEEDS"]
    if not feeds:
        return {"total_feeds": 0, "bidirectional_pairs": 0, "symmetry_ratio": 0.0}
    pair_set = set()
    feed_set = set()
    for l in feeds:
        s, t = l.get("source_guid"), l.get("target_guid")
        feed_set.add((s, t))
    for s, t in feed_set:
        if (t, s) in feed_set:
            pair_set.add(frozenset([s, t]))
    return {
        "total_feeds": len(feeds),
        "bidirectional_pairs": len(pair_set),
        "symmetry_ratio": round(2 * len(pair_set) / len(feeds), 4),
    }


# ════════════════════════════════════════════════════════════════════
#  根因检测
# ════════════════════════════════════════════════════════════════════

def detect_root_causes(site_model: dict, llm_row: dict | None, coord_val: dict,
                       purity: dict, sym: dict) -> list[tuple[str, str]]:
    """返回 [(tag, 具体证据句), ...]"""
    tags: list[tuple[str, str]] = []
    assets = site_model.get("assets", [])
    links = site_model.get("links", [])
    n_assets = len(assets)
    
    # coord_origin_dump
    if coord_val.get("origin_count", 0) > n_assets * 0.15 and n_assets > 20:
        tags.append(("coord_origin_dump",
                     f"{coord_val['origin_count']}/{n_assets} assets 位于原点 ({coord_val['origin_count']/n_assets:.1%})"))
    
    # coord_scale_outlier
    if coord_val.get("outlier_count", 0) >= 1:
        sample = coord_val["outliers"][0]
        tags.append(("coord_scale_outlier",
                     f"{coord_val['outlier_count']} asset 坐标量级异常, 例: {sample['type']} {sample['block'] or ''} @ {sample['coords']}"))
    
    # layer_semantic_miss / system_layer_residue
    other_assets = [a for a in assets if (a.get("type") or "").lower() == "other"]
    if other_assets and n_assets > 0:
        other_ratio = len(other_assets) / n_assets
        by_lyr = Counter(a.get("layer") or "<none>" for a in other_assets)
        top_lyr = by_lyr.most_common(3)
        SYS_PREFIXES = ("ADSK_SYSTEM", "*ADSK_SYSTEM", "DEFPOINTS", "СИСТЕМНЫЙ")
        # Other 中还有多少是系统层未过滤的
        sys_residue = sum(c for l, c in by_lyr.items() if any(l.startswith(p) for p in SYS_PREFIXES))
        if sys_residue > n_assets * 0.05:
            tags.append(("system_layer_residue",
                         f"{sys_residue}/{n_assets} Other 仍在系统层 (top: {top_lyr[0]})"))
        # 有明确业务语义关键词的层却全被判 Other
        SEMANTIC_KEYWORDS = ("sanitary", "HVAC", "COIL", "air", "cooling", "drain",
                             "crane", "hoist", "conveyor", "dust", "aspiration")
        biz_layers_in_other = [(l, c) for l, c in top_lyr
                               if any(k.lower() in l.lower() for k in SEMANTIC_KEYWORDS)]
        if biz_layers_in_other:
            tags.append(("layer_semantic_miss",
                         f"业务关键词图层被判 Other: {biz_layers_in_other}"))
        if other_ratio > 0.4:
            tags.append(("layer_semantic_miss",
                         f"Other 占比 {other_ratio:.1%} (>40%), top 层: {top_lyr}"))
    
    # block_name_semantic_miss
    BLOCK_KEYWORDS = ("dryer", "saw", "planer", "mill", "lathe", "cnc", "press",
                      "furnace", "annealing", "coiler", "roller", "tank", "vessel",
                      "crane", "hoist", "dust", "aspiration")
    suspicious_blocks = []
    for a in assets:
        blk = (a.get("block_name") or "").lower()
        t = a.get("type") or ""
        if blk and any(k in blk for k in BLOCK_KEYWORDS) and t in ("Equipment", "Other"):
            suspicious_blocks.append((a.get("block_name"), t))
    if suspicious_blocks:
        sample = Counter(suspicious_blocks).most_common(3)
        tags.append(("block_name_semantic_miss",
                     f"{len(suspicious_blocks)} asset 的 block_name 有业务语义但未细分: {sample}"))
    
    # subtype_missing
    type_dist = Counter(a.get("type") for a in assets)
    eq_count = type_dist.get("Equipment", 0)
    if eq_count >= 10 and eq_count / max(n_assets, 1) > 0.3:
        # 看 Equipment 的 block_name 多样性
        eq_blocks = Counter(a.get("block_name") for a in assets if a.get("type") == "Equipment" and a.get("block_name"))
        if len(eq_blocks) >= 5:
            tags.append(("subtype_missing",
                         f"Equipment {eq_count} 个, {len(eq_blocks)} 种不同 block_name, 未细分子类型"))
    
    # zone_undergenerated
    zone_count = type_dist.get("Zone", 0)
    located_in = sum(1 for l in links if l.get("link_type") == "LOCATED_IN")
    if eq_count > 20 and zone_count == 0:
        tags.append(("zone_undergenerated",
                     f"Equipment={eq_count} 但 Zone=0, 无 LOCATED_IN 空间上下文"))
    elif eq_count > 20 and located_in < eq_count * 0.2:
        tags.append(("zone_undergenerated",
                     f"Equipment={eq_count}, LOCATED_IN={located_in} (<20%), Zone 覆盖不足"))
    
    # annotation_noise
    ann_hints = sum(1 for a in assets
                    if any(k in (a.get("label") or "").upper() for k in ("DIM", "TEXT"))
                    or (a.get("type") == "Other" and (a.get("layer") or "").strip() in ("0", "")))
    if ann_hints > 10 and ann_hints / max(n_assets, 1) > 0.1:
        tags.append(("annotation_noise",
                     f"~{ann_hints} 个 asset 疑似标注/尺寸被误分为 Other"))
    
    # data_sparse
    if n_assets > 5000 and len(links) < 20:
        tags.append(("data_sparse",
                     f"{n_assets} asset 但仅 {len(links)} link — 数据语义稀疏"))
    elif n_assets > 1000 and purity["weighted_avg_entropy"] < 0.3 and len(type_dist) <= 2:
        tags.append(("data_sparse",
                     f"单一图层 / 单一 type 主导 (entropy={purity['weighted_avg_entropy']})"))
    
    # link_inflation
    conv_count = type_dist.get("Conveyor", 0)
    feeds_count = sum(1 for l in links if l.get("link_type") == "FEEDS")
    if conv_count > 0 and feeds_count > conv_count * 2:
        tags.append(("link_inflation",
                     f"FEEDS={feeds_count} vs Conveyor={conv_count} (比例 {feeds_count/conv_count:.1f}x)"))
    
    return tags


# ════════════════════════════════════════════════════════════════════
#  诊断报告
# ════════════════════════════════════════════════════════════════════

DIMS = ["classification_accuracy", "confidence_calibration", "coverage",
        "semantic_richness", "actionability"]


def diagnose_file(filename: str, site_model: dict, llm_row: dict | None,
                  dim_threshold: float) -> None:
    assets = site_model.get("assets", [])
    links = site_model.get("links", [])
    
    print(f"\n{'═'*90}")
    print(f"  文件: {filename}")
    print(f"  assets={len(assets)}  links={len(links)}  zones={len(site_model.get('zones',[]))}")
    print(f"{'═'*90}")
    
    # ── 客观指标 ──
    coord_val = compute_coord_validity(assets)
    purity = compute_layer_purity(assets)
    sym = compute_link_symmetry(links)
    
    print(f"\n[客观指标]")
    print(f"  coord_validity   : {coord_val['ratio']:.1%} ({coord_val['valid']}/{coord_val['total']}) "
          f"| origin={coord_val['origin_count']} outlier={coord_val['outlier_count']}")
    print(f"  layer_purity     : weighted_entropy={purity['weighted_avg_entropy']:.3f} "
          f"({purity['layers']} 层)  — 越低=图层映射越干净")
    print(f"  link_symmetry    : {sym['symmetry_ratio']:.1%} "
          f"({sym['bidirectional_pairs']} 双向对 / {sym['total_feeds']} FEEDS)")
    
    # ── Top 层组成 ──
    print(f"\n[Top 图层]  (层名 × 数量 × 熵 × 主导类型)")
    for e in purity["top_layers"][:5]:
        dist = ", ".join(f"{t}:{c}" for t, c in e["type_dist"].items())
        print(f"  {e['layer']:40s}  n={e['count']:<5d}  H={e['entropy']:.2f}  → {dist}")
    
    # ── LLM 维度低分 ──
    if llm_row:
        print(f"\n[LLM 评估]  overall={llm_row.get('overall', -1):.3f}")
        low_dims = [(d, llm_row.get(d, -1)) for d in DIMS if llm_row.get(d, 1) < dim_threshold]
        if low_dims:
            print(f"  低分维度 (<{dim_threshold}):")
            for d, s in low_dims:
                stdev = llm_row.get("score_stdev", {}).get(d, 0)
                j = llm_row.get("judgments", {}).get(d, {})
                obs = (j.get("observation") or "")[:200]
                eids = ", ".join(j.get("evidence_ids", []))
                print(f"    • {d:25s} = {s:.2f} ±{stdev:.2f}  (LLM confi={j.get('confidence',0):.2f})")
                print(f"      证据: [{eids}]")
                if obs:
                    print(f"      {obs}{'…' if len(j.get('observation',''))>200 else ''}")
        else:
            print(f"  所有维度 ≥ {dim_threshold}")
        
        # LLM 反馈 chip
        missed = llm_row.get("missed_types", [])
        if missed:
            print(f"\n  LLM 识别的缺失类型 ({len(missed)} 条):")
            for m in missed[:5]:
                print(f"    - {m}")
    else:
        print(f"\n[LLM 评估]  (未找到 llm_quality_matrix.json 记录)")
    
    # ── 根因检测 ──
    tags = detect_root_causes(site_model, llm_row, coord_val, purity, sym)
    print(f"\n[根因标签]  {len(tags)} 项命中")
    if not tags:
        print(f"  (无自动可识别的根因)")
    else:
        # 按修复难度 low→medium→high 排序
        order = {"low": 0, "medium": 1, "high": 2}
        tags_sorted = sorted(tags, key=lambda t: order.get(ROOT_CAUSE_TAGS[t[0]]["fix_difficulty"], 9))
        for tag, evidence in tags_sorted:
            meta = ROOT_CAUSE_TAGS[tag]
            diff = meta["fix_difficulty"]
            marker = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(diff, "⚪")
            print(f"  {marker} [{diff:6s}] {tag}")
            print(f"     证据: {evidence}")
            print(f"     修复: {meta['fix_hint']}")


# ════════════════════════════════════════════════════════════════════
#  Main
# ════════════════════════════════════════════════════════════════════

def load_dumps() -> dict[str, tuple[dict, dict]]:
    """返回 {filename: (meta, site_model)}"""
    out = {}
    for d in sorted(RESULTS_DIR.iterdir()):
        if not d.is_dir():
            continue
        meta_p = d / "meta.json"
        sm_p = d / "site_model.json"
        if not (meta_p.exists() and sm_p.exists()):
            continue
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        sm = json.loads(sm_p.read_text(encoding="utf-8"))
        out[meta.get("filename", d.name)] = (meta, sm)
    return out


def load_llm_matrix() -> dict[str, dict]:
    """返回 {filename: llm_row}"""
    if not MATRIX_PATH.exists():
        return {}
    rows = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    return {r["filename"]: r for r in rows}


def main():
    ap = argparse.ArgumentParser(description="ParseAgent 质量根因分析器")
    ap.add_argument("--file", type=str, default="", help="指定 filename (子串匹配)")
    ap.add_argument("--all", action="store_true", help="扫描全部 8 个 DWG")
    ap.add_argument("--overall-threshold", type=float, default=0.35,
                    help="--all 模式下,只诊断 overall < 此阈值的文件 (默认 0.35)")
    ap.add_argument("--dim-threshold", type=float, default=0.30,
                    help="维度低分阈值 (默认 0.30)")
    args = ap.parse_args()
    
    dumps = load_dumps()
    matrix = load_llm_matrix()
    
    if not dumps:
        print(f"未找到 dump 结果: {RESULTS_DIR}")
        sys.exit(1)
    
    # 选择目标文件
    if args.file:
        targets = [n for n in dumps if args.file in n]
        if not targets:
            print(f"没有匹配 '{args.file}' 的文件. 可用:")
            for n in dumps:
                print(f"  - {n}")
            sys.exit(1)
    elif args.all:
        targets = list(dumps.keys())
        # 按 overall 升序 (最差的先诊断)
        targets.sort(key=lambda n: matrix.get(n, {}).get("overall", 1.0))
        if args.overall_threshold < 1.0:
            targets = [n for n in targets
                       if matrix.get(n, {}).get("overall", 1.0) < args.overall_threshold]
            print(f"筛选 overall < {args.overall_threshold}: {len(targets)} 个文件\n")
    else:
        print("必须指定 --file <name> 或 --all")
        print("\n可用文件:")
        for n in dumps:
            s = matrix.get(n, {}).get("overall", "?")
            s_str = f"{s:.3f}" if isinstance(s, float) else str(s)
            print(f"  {s_str:>7s}  {n}")
        sys.exit(0)
    
    for name in targets:
        meta, sm = dumps[name]
        llm_row = matrix.get(name)
        diagnose_file(name, sm, llm_row, args.dim_threshold)
    
    print(f"\n{'═'*90}")
    print(f"  诊断完成: {len(targets)} 个文件")
    print(f"{'═'*90}\n")


if __name__ == "__main__":
    main()
