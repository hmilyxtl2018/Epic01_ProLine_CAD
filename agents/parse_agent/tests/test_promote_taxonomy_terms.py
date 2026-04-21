"""S2-T4: scripts/promote_taxonomy_terms.py 单元测试。"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.promote_taxonomy_terms import (
    Aggregated,
    _normalize_term,
    aggregate,
    iter_quarantine_records,
    main,
    write_review_csv,
)


# ---------- helpers ----------

def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _rec(
    term="washing", atype="Equipment", evidence=None, ts=1000.0, term_hash="abc12345",
) -> dict:
    return {
        "ts": ts,
        "term": term,
        "asset_type": atype,
        "evidence": list(evidence) if evidence is not None else ["washing_op100"],
        "term_hash": term_hash,
        "approved": False,
    }


# ════════════════ _normalize_term ════════════════

def test_normalize_lowercases_and_trims():
    assert _normalize_term("  HONING  ") == "honing"


def test_normalize_nfkc():
    # 全角字母归一化 → 半角
    assert _normalize_term("ＣＮＣ") == "cnc"


# ════════════════ iter_quarantine_records ════════════════

def test_iter_skips_missing_dir(tmp_path):
    out = list(iter_quarantine_records(tmp_path / "nope"))
    assert out == []


def test_iter_yields_run_id_and_record(tmp_path):
    _write_jsonl(tmp_path / "run_a.jsonl", [_rec(term="t1")])
    _write_jsonl(tmp_path / "run_b.jsonl", [_rec(term="t2")])
    out = list(iter_quarantine_records(tmp_path))
    assert len(out) == 2
    run_ids = {r[0] for r in out}
    assert run_ids == {"run_a", "run_b"}


def test_iter_skips_blank_and_malformed_lines(tmp_path, caplog):
    f = tmp_path / "run.jsonl"
    f.write_text(
        '\n'
        + json.dumps(_rec(term="ok")) + '\n'
        + 'NOT JSON\n'
        + json.dumps(["array_not_obj"]) + '\n'
        + '\n',
        encoding="utf-8",
    )
    out = list(iter_quarantine_records(tmp_path))
    assert len(out) == 1
    assert out[0][1]["term"] == "ok"


# ════════════════ aggregate ════════════════

def test_aggregate_dedupes_by_normalized_term_and_type(tmp_path):
    _write_jsonl(tmp_path / "r1.jsonl", [
        _rec(term="HONING", evidence=["honing_op170"], ts=100.0),
        _rec(term="honing", evidence=["honing_machine"], ts=200.0),
    ])
    _write_jsonl(tmp_path / "r2.jsonl", [
        _rec(term="Honing ", evidence=["honing_op180"], ts=300.0),
    ])
    bucket = aggregate(tmp_path)
    assert len(bucket) == 1
    agg = next(iter(bucket.values()))
    assert agg.count == 3
    assert agg.evidence == {"honing_op170", "honing_machine", "honing_op180"}
    assert agg.first_seen == 100.0
    assert agg.last_seen == 300.0
    assert agg.runs == {"r1", "r2"}


def test_aggregate_separates_different_asset_types(tmp_path):
    _write_jsonl(tmp_path / "r.jsonl", [
        _rec(term="kbk", atype="LiftingPoint"),
        _rec(term="kbk", atype="Conveyor"),
    ])
    bucket = aggregate(tmp_path)
    assert len(bucket) == 2
    keys = set(bucket.keys())
    assert ("kbk", "LiftingPoint") in keys
    assert ("kbk", "Conveyor") in keys


def test_aggregate_skips_invalid_records(tmp_path):
    _write_jsonl(tmp_path / "r.jsonl", [
        {"ts": 1.0, "term": None, "asset_type": "Equipment", "evidence": []},
        {"ts": 2.0, "term": "good", "asset_type": "Equipment", "evidence": ["x"]},
        {"ts": 3.0, "term": "ok", "asset_type": 123, "evidence": []},
        {"ts": 4.0, "term": "   ", "asset_type": "Equipment", "evidence": []},
    ])
    bucket = aggregate(tmp_path)
    assert len(bucket) == 1
    assert ("good", "Equipment") in bucket


def test_aggregate_handles_missing_evidence(tmp_path):
    _write_jsonl(tmp_path / "r.jsonl", [
        {"ts": 1.0, "term": "t", "asset_type": "Equipment"},  # 无 evidence 字段
    ])
    bucket = aggregate(tmp_path)
    agg = bucket[("t", "Equipment")]
    assert agg.evidence == set()
    assert agg.count == 1


# ════════════════ write_review_csv ════════════════

def test_csv_header_and_sort_order(tmp_path):
    bucket = {
        ("alpha", "Equipment"): Aggregated(
            term="alpha", asset_type="Equipment", term_hash="h1",
            count=2, evidence={"a1"}, first_seen=10.0, last_seen=20.0,
            runs={"r1"},
        ),
        ("beta", "Equipment"): Aggregated(
            term="beta", asset_type="Equipment", term_hash="h2",
            count=5, evidence={"b1", "b2"}, first_seen=5.0, last_seen=50.0,
            runs={"r1", "r2"},
        ),
    }
    out = tmp_path / "review.csv"
    n = write_review_csv(bucket, out)
    assert n == 2

    with out.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == [
        "term", "asset_type", "count", "evidence_samples",
        "first_seen", "last_seen", "run_count", "term_hash", "decision",
    ]
    # count DESC → beta(5) 在前, alpha(2) 在后
    assert rows[1][0] == "beta"
    assert rows[1][2] == "5"
    assert rows[1][6] == "2"  # run_count
    assert rows[1][8] == ""   # decision empty for human
    assert rows[2][0] == "alpha"


def test_csv_min_count_filter(tmp_path):
    bucket = {
        ("a", "Equipment"): Aggregated(term="a", asset_type="Equipment",
                                       term_hash="h", count=1),
        ("b", "Equipment"): Aggregated(term="b", asset_type="Equipment",
                                       term_hash="h", count=3),
    }
    out = tmp_path / "r.csv"
    n = write_review_csv(bucket, out, min_count=2)
    assert n == 1
    text = out.read_text(encoding="utf-8-sig")
    assert "b," in text and ",a," not in text


def test_csv_evidence_truncation(tmp_path):
    """超过 _MAX_EVIDENCE_SAMPLES 的 evidence 应被截断。"""
    bucket = {
        ("x", "Equipment"): Aggregated(
            term="x", asset_type="Equipment", term_hash="h", count=10,
            evidence={f"ev_{i}" for i in range(20)},
        ),
    }
    out = tmp_path / "r.csv"
    write_review_csv(bucket, out)
    with out.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    samples = rows[1][3].split(" | ")
    assert len(samples) == 5  # _MAX_EVIDENCE_SAMPLES


def test_csv_creates_parent_directory(tmp_path):
    out = tmp_path / "deep" / "nested" / "r.csv"
    write_review_csv({}, out)
    assert out.exists()


# ════════════════ main CLI ════════════════

def test_main_end_to_end(tmp_path, capsys):
    qdir = tmp_path / "quarantine"
    _write_jsonl(qdir / "run1.jsonl", [
        _rec(term="washing", evidence=["washing_op10"]),
        _rec(term="WASHING", evidence=["washing_op20"]),  # same term, deduped
        _rec(term="kbk", atype="LiftingPoint", evidence=["kbk_main"]),
    ])
    out = tmp_path / "out.csv"
    rc = main([
        "--quarantine-dir", str(qdir),
        "--out", str(out),
    ])
    assert rc == 0
    assert out.exists()
    with out.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    # 1 header + 2 data rows (washing aggregated, kbk separate)
    assert len(rows) == 3


def test_main_missing_quarantine_dir_writes_empty(tmp_path):
    out = tmp_path / "out.csv"
    rc = main([
        "--quarantine-dir", str(tmp_path / "nonexistent"),
        "--out", str(out),
    ])
    assert rc == 0
    with out.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert len(rows) == 1  # header only


def test_main_min_count_flag(tmp_path):
    qdir = tmp_path / "q"
    _write_jsonl(qdir / "r.jsonl", [
        _rec(term="rare"),
        _rec(term="common"),
        _rec(term="common"),
        _rec(term="common"),
    ])
    out = tmp_path / "o.csv"
    rc = main([
        "--quarantine-dir", str(qdir),
        "--out", str(out),
        "--min-count", "2",
    ])
    assert rc == 0
    text = out.read_text(encoding="utf-8-sig")
    assert "common," in text
    assert "rare," not in text
