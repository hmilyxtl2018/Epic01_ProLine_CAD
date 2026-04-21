"""Upload validation: suffix whitelist + magic-byte signatures + size cap.

Why both? Suffix is user-controlled (rename anything to .dwg). Magic bytes are
authoritative for binary CAD formats. STEP/IFC are text; we sniff the first
non-whitespace bytes for the standard ISO header tokens.

Returns a `ValidatedUpload` with the detected format string for downstream
use, or raises `UploadRejected` (mapped to 400 by the route).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


# Format -> (allowed extensions, magic-bytes prefix, is_binary).
# Magic bytes for DWG follow the AutoCAD release header "AC10xx".
# DXF files start with "0\nSECTION\n2\nHEADER" (text) or with autocad's
# binary signature; we accept both forms loosely.
# IFC/STEP are ISO-10303 text, header begins with "ISO-10303-21;".

_BINARY_MAGIC: dict[str, list[bytes]] = {
    "dwg": [b"AC10", b"AC1.", b"AC2."],  # AC1014..AC1032 cover R14..2018+
}

_TEXT_HEADERS: dict[str, list[bytes]] = {
    "ifc": [b"ISO-10303-21"],
    "step": [b"ISO-10303-21"],
    "stp": [b"ISO-10303-21"],
    "dxf": [b"0\r\nSECTION", b"0\nSECTION", b"AutoCAD Binary DXF"],
}

ALLOWED_EXTS = tuple(sorted({"dwg", "dxf", "ifc", "step", "stp"}))

DEFAULT_MAX_BYTES = 50 * 1024 * 1024


class UploadRejected(Exception):
    """Raised on any upload validation failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class ValidatedUpload:
    detected_format: str  # "dwg" / "ifc" / "step" / "dxf"
    extension: str
    size_bytes: int


def _extension(filename: str) -> str:
    name = os.path.basename(filename or "")
    _, _, ext = name.rpartition(".")
    return ext.lower() if ext and ext != name else ""


def _matches_any(prefix_window: bytes, candidates: list[bytes]) -> bool:
    return any(prefix_window.startswith(c) for c in candidates)


def validate_upload(
    *,
    filename: str,
    file_bytes: bytes,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> ValidatedUpload:
    """Run all validations or raise `UploadRejected`."""

    if not file_bytes:
        raise UploadRejected("EMPTY_UPLOAD", "Uploaded file is empty.")

    if len(file_bytes) > max_bytes:
        raise UploadRejected(
            "PAYLOAD_TOO_LARGE",
            f"Upload exceeds {max_bytes // (1024 * 1024)} MB cap.",
        )

    ext = _extension(filename)
    if ext not in ALLOWED_EXTS:
        raise UploadRejected(
            "UNSUPPORTED_FORMAT",
            f"Extension '.{ext}' not allowed. Accepted: {', '.join(ALLOWED_EXTS)}.",
        )

    # Sniff the first 2 KB -- enough for both ISO-10303 headers and AC10xx
    # signatures, but bounded so we never load megabytes for header detection.
    head = file_bytes[:2048]
    head_stripped = head.lstrip()  # text formats may start with comments / BOM

    detected: str | None = None
    if ext in _BINARY_MAGIC and _matches_any(head, _BINARY_MAGIC[ext]):
        detected = ext
    elif ext in _TEXT_HEADERS and _matches_any(head_stripped, _TEXT_HEADERS[ext]):
        detected = ext

    if detected is None:
        raise UploadRejected(
            "MAGIC_MISMATCH",
            f"File contents do not match the '{ext}' format signature.",
        )

    return ValidatedUpload(detected_format=detected, extension=ext, size_bytes=len(file_bytes))
