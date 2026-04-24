"""Unit tests for app.services.parse.cad_parser (no DB)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.parse.cad_parser import parse_cad


FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "cad" / "sample_factory.dxf"


def _ensure_fixture() -> Path:
    if not FIXTURE.exists():
        from tests.fixtures.build_sample_dxf import build

        build()
    assert FIXTURE.exists(), "fixture build failed"
    return FIXTURE


def test_parse_dxf_emits_all_four_sections():
    p = _ensure_fixture()
    r = parse_cad(path=p, detected_format="dxf", filename="sample_factory.dxf")

    # 1. fingerprint
    fp = r.fingerprint
    assert fp["filename"] == "sample_factory.dxf"
    assert fp["detected_format"] == "dxf"
    assert fp["size_bytes"] > 0
    assert len(fp["sha256"]) == 64

    # 2. summary
    s = r.summary
    assert s["entity_total"] >= 5
    assert s["layer_count"] >= 3
    assert s["bounding_box"]["max"][0] > 0
    assert s["units"] == "mm"
    # System layers should be filtered.
    assert "0" not in s["layer_names"]
    assert "Defpoints" not in s["layer_names"]
    # Auto blocks (_ARCHTICK etc) should be filtered.
    assert all(not n.startswith("_") for n in s["block_names"])

    # 3. semantics — must include the gold ('conveyor') *and* the quarantine
    # candidate ('roller belt assembly'), no system tokens.
    norms = {c["term_normalized"] for c in r.semantics["candidates"]}
    assert "conveyor" in norms
    assert "roller belt assembly" in norms
    assert "defpoints" not in norms

    # 4. quality
    q = r.quality
    assert q["parse_warnings"] == []
    assert q["confidence_score"] == 1.0
    assert q["artifacts"] == {}


def test_parse_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        parse_cad(path=Path("/nope/never.dxf"), detected_format="dxf", filename="x")


def test_parse_dwg_without_oda_yields_warning(tmp_path):
    p = tmp_path / "fake.dwg"
    p.write_bytes(b"AC1032" + b"\x00" * 1024)  # valid magic, junk body
    r = parse_cad(path=p, detected_format="dwg", filename="fake.dwg")
    assert r.fingerprint["sha256"]
    # Either parsed via ODA (unlikely in CI) or yields a warning.
    if r.summary == {}:
        assert any("dwg" in w.lower() for w in r.quality["parse_warnings"])
        assert r.quality["confidence_score"] <= 0.2
