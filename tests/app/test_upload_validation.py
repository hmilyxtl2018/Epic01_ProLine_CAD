"""Pure-unit tests for app.security.upload.validate_upload (no DB / no network)."""

from __future__ import annotations

import pytest

from app.security.upload import (
    DEFAULT_MAX_BYTES,
    UploadRejected,
    validate_upload,
)


_DWG_MAGIC = b"AC1015"
_IFC_HEAD = b"ISO-10303-21;\nHEADER;\n"
_DXF_HEAD = b"0\nSECTION\n2\nHEADER\n"


def test_empty_upload_rejected():
    with pytest.raises(UploadRejected) as ei:
        validate_upload(filename="x.dwg", file_bytes=b"")
    assert ei.value.code == "EMPTY_UPLOAD"


def test_payload_too_large():
    with pytest.raises(UploadRejected) as ei:
        validate_upload(
            filename="x.dwg",
            file_bytes=_DWG_MAGIC + b"\x00" * 16,
            max_bytes=8,
        )
    assert ei.value.code == "PAYLOAD_TOO_LARGE"


def test_unsupported_extension():
    with pytest.raises(UploadRejected) as ei:
        validate_upload(filename="malware.exe", file_bytes=b"MZ\x90\x00")
    assert ei.value.code == "UNSUPPORTED_FORMAT"


def test_extension_without_dot_rejected():
    with pytest.raises(UploadRejected) as ei:
        validate_upload(filename="noext", file_bytes=b"AC1015")
    assert ei.value.code == "UNSUPPORTED_FORMAT"


def test_dwg_magic_mismatch():
    with pytest.raises(UploadRejected) as ei:
        validate_upload(filename="bad.dwg", file_bytes=b"NOTACAD" + b"\x00" * 16)
    assert ei.value.code == "MAGIC_MISMATCH"


def test_ifc_text_mismatch():
    with pytest.raises(UploadRejected) as ei:
        validate_upload(filename="bad.ifc", file_bytes=b"<html>not ifc</html>")
    assert ei.value.code == "MAGIC_MISMATCH"


@pytest.mark.parametrize(
    "filename,payload,expected_format",
    [
        ("ok.dwg", _DWG_MAGIC + b"\x00\x00\x00rest", "dwg"),
        ("OK.DWG", b"AC1024" + b"x" * 32, "dwg"),
        ("model.ifc", _IFC_HEAD + b"FILE_DESCRIPTION(...);", "ifc"),
        ("model.step", _IFC_HEAD + b"...", "step"),
        ("model.STP", _IFC_HEAD + b"...", "stp"),
        ("drawing.dxf", _DXF_HEAD + b"ENDSEC\n", "dxf"),
    ],
)
def test_happy_path(filename, payload, expected_format):
    v = validate_upload(filename=filename, file_bytes=payload)
    assert v.detected_format == expected_format
    assert v.size_bytes == len(payload)
    assert v.extension == filename.rsplit(".", 1)[-1].lower()


def test_default_max_is_50mb():
    assert DEFAULT_MAX_BYTES == 50 * 1024 * 1024
