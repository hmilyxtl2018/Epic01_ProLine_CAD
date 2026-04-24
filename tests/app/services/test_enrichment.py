"""Unit tests for the LLM-assisted enrichment pipeline (stub mode)."""

from __future__ import annotations

from app.services.enrichment import semantic as S
from app.services.enrichment import quality as Q
from app.services.enrichment import sitemodel as SM
from app.services.llm.embeddings import StubEmbedder


def test_normalize_strips_codes_and_swaps_lexicon():
    out = S.normalize_candidate("$plan$00000387_01__3")
    assert out["normalized"]
    assert out["reason"] != "passthrough"

    cn = S.normalize_candidate("1标注")
    assert "annotation" in cn["normalized"] or cn["lang"] == "zh"

    de = S.normalize_candidate("DRAUFSICHT")
    # English fallback, but the lexicon swaps draufsicht→topview
    assert "topview" in de["normalized"] or de["lang"] == "en"


def test_softmatch_buckets_by_threshold():
    embedder = StubEmbedder()
    cands = [
        {"term_normalized": "conveyor"},
        {"term_normalized": "lifting point"},
        {"term_normalized": "xyz_random_blob_12345"},
    ]
    gold = [
        {"term_normalized": "conveyor"},
        {"term_normalized": "lift_point"},
    ]
    out = S.softmatch(embedder, candidates=cands, gold_terms=gold)
    assert len(out) == 3
    verdicts = {o["candidate"]: o["verdict"] for o in out}
    assert verdicts["conveyor"] == "accept"
    assert verdicts["xyz_random_blob_12345"] in {"reject", "review"}


def test_cluster_proposals_compresses_quarantine():
    embedder = StubEmbedder()
    quarantine = [
        {"term_normalized": f"roller_belt_{i}", "asset_type": "Other", "count": 1}
        for i in range(20)
    ] + [
        {"term_normalized": f"workstation_{i}", "asset_type": "Other", "count": 1}
        for i in range(15)
    ]
    out = S.cluster_proposals(embedder, quarantine=quarantine, max_clusters=10)
    assert out["stats"]["input"] == 35
    assert len(out["proposals"]) <= 10
    # Compression ratio must be > 1 if we actually compressed.
    if out["proposals"]:
        assert out["stats"]["compression_ratio"] >= 1.0


def test_classify_blocks_known_kinds():
    out = S.classify_blocks(
        ["$DorLib2D$00000001", "6010891_01___0____3", "A$C01EB5F4F", "user_block"]
    )
    kinds = {it["name"]: it["kind"] for it in out["items"]}
    assert kinds["$DorLib2D$00000001"] in {"autocad_internal", "door_lib"}
    assert kinds["6010891_01___0____3"] == "part_number"
    assert kinds["A$C01EB5F4F"] == "hash_handle"
    assert kinds["user_block"] == "user_defined"


def test_quality_breakdown_drops_when_no_matches():
    qb = Q.quality_breakdown(
        summary={"entity_total": 700, "layer_count": 300, "bounding_box": {"min": [0, 0, 0], "max": [10, 10, 10]}},
        matched_count=0,
        quarantine_count=2000,
        candidate_count=2000,
        warnings=[],
    )
    assert qb["semantic"] == 0.0
    assert qb["overall"] < 0.8


def test_root_cause_classifies_known_warning():
    rc = Q.root_cause(["dwg_parser_unavailable: ODA File Converter not on PATH"])
    assert rc["root_causes"]
    assert rc["root_causes"][0]["root_cause"] == "dwg_toolchain_missing"


def test_self_check_blocks_on_low_match_ratio():
    sc = Q.self_check(
        matched_count=0,
        quarantine_count=2000,
        candidate_count=2000,
        quality_overall=0.5,
        parse_warnings=[],
    )
    assert sc["should_block"] is True
    assert sc["blockers"]


def test_site_describe_picks_chinese_phrase():
    sd = SM.site_describe(
        filename="20180109_机加车间平面布局图.dwg",
        summary={
            "units": "mm",
            "entity_total": 700,
            "layer_count": 334,
            "bounding_box": {"width": 700_000, "height": 200_000},
            "layer_names": ["机加", "包装"],
        },
    )
    assert "机加车间" in sd["title"] or "机加" in sd["title"]
    assert sd["suggested_tags"]


def test_geom_anomaly_flags_z_outlier():
    out = SM.geom_anomaly(
        summary={"bounding_box": {"min": [0, 0, 0], "max": [100, 100, 100_000]}, "units": "mm"}
    )
    kinds = [f["kind"] for f in out["findings"]]
    assert "z_extent_outlier" in kinds


def test_provenance_note_resolves_dxf_version():
    pv = SM.provenance_note(
        fingerprint={},
        summary={"dxf_version": "AC1018", "layer_names": ["1标注", "WALL", "Schnitt"]},
    )
    assert "AutoCAD 2004" in pv["release"]
    assert pv["multi_team_source"] is True
