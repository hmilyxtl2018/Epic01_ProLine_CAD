"""ParseAgent 结果持久化 — 文件层。

将 ParseService 7 步管线的结果持久化到文件系统，
文件布局对齐 DB 表结构，便于后期直接入库。

目录结构:
  exp/parse_results/{run_id}/{file_hash}/
    meta.json              轻量元数据 + format_detect 结果
    raw_entities.jsonl     entity_extract 原始态 (每行一个 dict)
    assets.jsonl           classify_entity 后的 Asset (每行一个 Pydantic JSON)
    site_model.json        完整 SiteModel (含 assets 全量, 对齐 site_models 表)
    mcp_context.json       MCPContext (对齐 mcp_contexts 表)

DB 对齐关系:
  meta.json          → 无专表, 用于本地审计/调试
  raw_entities.jsonl → 未来可 bulk INSERT 到 raw_entities 分析表
  assets.jsonl       → SiteModel.assets 的行级展开, 便于单资产查询
  site_model.json    → site_models 表 1:1 写入
  mcp_context.json   → mcp_contexts 表 1:1 写入
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from shared.models import SiteModel
from shared.mcp_protocol import MCPContext


class ParseResultWriter:
    """将 ParseAgent 结果写入文件系统。"""

    def __init__(self, base_dir: Path | str = "exp/parse_results"):
        self.base_dir = Path(base_dir)

    def write(
        self,
        filename: str,
        file_content: bytes,
        format_detected: str,
        raw_entities: list[dict],
        site_model: SiteModel,
        mcp_context: MCPContext,
        run_id: str | None = None,
    ) -> Path:
        """写入一次解析的全部结果，返回输出目录路径。"""
        if run_id is None:
            run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        file_hash = hashlib.sha256(file_content).hexdigest()[:8]
        out_dir = self.base_dir / run_id / file_hash
        out_dir.mkdir(parents=True, exist_ok=True)

        self._write_meta(out_dir, filename, file_content, file_hash, format_detected, mcp_context)
        self._write_raw_entities(out_dir, raw_entities)
        self._write_assets(out_dir, site_model)
        self._write_site_model(out_dir, site_model)
        self._write_mcp_context(out_dir, mcp_context)

        return out_dir

    # ── 内部方法 ──

    def _write_meta(
        self,
        out_dir: Path,
        filename: str,
        file_content: bytes,
        file_hash: str,
        format_detected: str,
        mcp_context: MCPContext,
    ) -> None:
        meta = {
            "filename": filename,
            "file_size_bytes": len(file_content),
            "file_sha256": hashlib.sha256(file_content).hexdigest(),
            "file_hash_short": file_hash,
            "format_detected": format_detected,
            "agent": mcp_context.agent,
            "mcp_context_id": mcp_context.mcp_context_id,
            "latency_ms": mcp_context.latency_ms,
            "status": mcp_context.status.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step_summary": [
                {k: v for k, v in step.items()}
                for step in mcp_context.step_breakdown
            ],
        }
        (out_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _write_raw_entities(self, out_dir: Path, raw_entities: list[dict]) -> None:
        with (out_dir / "raw_entities.jsonl").open("w", encoding="utf-8") as f:
            for entity in raw_entities:
                f.write(json.dumps(entity, ensure_ascii=False) + "\n")

    def _write_assets(self, out_dir: Path, site_model: SiteModel) -> None:
        with (out_dir / "assets.jsonl").open("w", encoding="utf-8") as f:
            for asset in site_model.assets:
                f.write(asset.model_dump_json() + "\n")

    def _write_site_model(self, out_dir: Path, site_model: SiteModel) -> None:
        (out_dir / "site_model.json").write_text(
            site_model.model_dump_json(indent=2), encoding="utf-8"
        )

    def _write_mcp_context(self, out_dir: Path, mcp_context: MCPContext) -> None:
        (out_dir / "mcp_context.json").write_text(
            mcp_context.model_dump_json(indent=2), encoding="utf-8"
        )


class ParseResultReader:
    """从文件系统读取 ParseAgent 结果。"""

    @staticmethod
    def read_meta(result_dir: Path) -> dict:
        return json.loads((result_dir / "meta.json").read_text(encoding="utf-8"))

    @staticmethod
    def read_raw_entities(result_dir: Path) -> list[dict]:
        entities = []
        with (result_dir / "raw_entities.jsonl").open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entities.append(json.loads(line))
        return entities

    @staticmethod
    def read_assets_iter(result_dir: Path):
        """流式读取 assets — 不一次加载全部到内存。"""
        from shared.models import Asset
        with (result_dir / "assets.jsonl").open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield Asset.model_validate_json(line)

    @staticmethod
    def read_site_model(result_dir: Path) -> SiteModel:
        return SiteModel.model_validate_json(
            (result_dir / "site_model.json").read_text(encoding="utf-8")
        )

    @staticmethod
    def read_mcp_context(result_dir: Path) -> MCPContext:
        return MCPContext.model_validate_json(
            (result_dir / "mcp_context.json").read_text(encoding="utf-8")
        )
