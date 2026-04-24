"""End-to-end smoke: upload sample DXF, run worker once, dump run detail."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

API = os.getenv("DASH_API", "http://127.0.0.1:8000")
SAMPLE = Path(
    os.getenv(
        "DEMO_CAD_PATH",
        r"spikes/spike_01_dwg_parse/test_data/real_world/20180109_机加车间平面布局图.dwg",
    )
)


def main() -> int:
    sess = httpx.Client(base_url=API, timeout=30.0, trust_env=False)
    # 1. cookie login
    r = sess.post(
        "/auth/login-cookie",
        json={"email": "dev@example.com", "password": "dev", "role": "admin"},
    )
    r.raise_for_status()
    csrf = sess.cookies.get("proline_csrf")
    headers = {"X-CSRF-Token": csrf or ""}

    # 2. upload
    with SAMPLE.open("rb") as fh:
        files = {"cad_file": (SAMPLE.name, fh, "application/octet-stream")}
        r = sess.post("/dashboard/runs", files=files, headers=headers)
    r.raise_for_status()
    created = r.json()
    run_id = created["run_id"]
    print(f"[upload] run_id = {run_id}")

    # 3. drive worker once (in-process, reuses backend's DB env)
    from app.workers.parse_agent_worker import process_one
    import app.deps as deps

    deps.init_engine()
    assert deps._SessionLocal is not None
    with deps._SessionLocal() as db:
        result = process_one(db)
    print(f"[worker] processed = {result}")

    # 4. fetch detail
    time.sleep(0.2)
    r = sess.get(f"/dashboard/runs/{run_id}")
    r.raise_for_status()
    detail = r.json()
    print(json.dumps(detail, indent=2, ensure_ascii=False, default=str))
    print(f"\n>>> view in browser: http://localhost:3000/runs/{run_id}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
