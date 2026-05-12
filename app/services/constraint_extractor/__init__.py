"""ConstraintExtractor 服务 — LLM 工艺约束抽取（ADR-0010 / T3+T4+T5）。

T3 阶段先落 prompt 模板与版本常量；T4 实现 ``ConstraintExtractor``
服务类；T5 暴露为 ``POST /sites/{id}/constraints/extract`` HTTP 入口。

**版本字段 vs 模板内容**：

- ``STAGE_A_VERSION`` / ``STAGE_B_VERSION`` 是写入 ``constraint_extractions.prompt_version``
  的字符串，CHECK ``ck_ce_llm_metadata`` 强制 LLM 抽取行必须带它。
- 任何 prompt 内容修改（字符级）都必须同步 bump 版本号（v1 → v2），
  这是审计线的唯一锚点（ADR-0010 §2.2 第 2 条 + L1 gold 测试基线）。
- ``STAGE_A_SCHEMA`` / ``STAGE_B_SCHEMA`` 是该版本对应的 JSON Schema 副本，
  与 prompt 同生命周期；服务层用 ``jsonschema`` 做 L0 形状校验。

**目录布局**：

```
app/services/constraint_extractor/
    __init__.py                 # 本文件，公开版本常量 + load_prompt() + STAGE_*_SCHEMA
    prompts/
        stage_a_candidates.zh.md
        stage_b_structured.zh.md
    schemas/
        stage_a_v1.schema.json
        stage_b_v1.schema.json
    thresholds.py               # T4 落（置信度分档 + 整批 G 阈值）
    extractor.py                # T4 落
    stub_data.py                # T4 落（fixture 回放）
```
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

# ── prompt 版本字符串（写入 constraint_extractions.prompt_version） ──
#
# 命名规范：stage_<a|b>_v<int>。任何 prompt 文件内容变化都必须递增整数；
# 这是 LLM 痕迹回放与回归的唯一标识。

STAGE_A_VERSION: str = "stage_a_v1"
STAGE_B_VERSION: str = "stage_b_v1"

# Prompt 文件命名表（按版本字符串映射到资源文件名）
_PROMPT_FILES: dict[str, str] = {
    STAGE_A_VERSION: "stage_a_candidates.zh.md",
    STAGE_B_VERSION: "stage_b_structured.zh.md",
}

# JSON Schema 文件命名表（与 prompt 同版本号）
_SCHEMA_FILES: dict[str, str] = {
    STAGE_A_VERSION: "stage_a_v1.schema.json",
    STAGE_B_VERSION: "stage_b_v1.schema.json",
}


def load_prompt(version: str) -> str:
    """读取一个 prompt 模板文件的全文。

    Args:
        version: 必须是 ``STAGE_A_VERSION`` / ``STAGE_B_VERSION`` 之一。

    Returns:
        模板原文（含 Markdown 头）。

    Raises:
        ValueError: 版本字符串未在白名单中。
        FileNotFoundError: 资源文件丢失（说明发布包损坏）。
    """
    if version not in _PROMPT_FILES:
        raise ValueError(f"unknown prompt version: {version!r}; expected one of {sorted(_PROMPT_FILES)}")
    filename = _PROMPT_FILES[version]
    package = "app.services.constraint_extractor.prompts"
    try:
        return resources.files(package).joinpath(filename).read_text(encoding="utf-8")
    except FileNotFoundError:
        # Helpful diagnostic when running from a sdist / wheel that misses data files.
        here = Path(__file__).resolve().parent / "prompts" / filename
        return here.read_text(encoding="utf-8")


def load_schema(version: str) -> dict[str, Any]:
    """读取并解析对应版本的 JSON Schema。

    服务层用 ``jsonschema.Draft202012Validator(load_schema(STAGE_B_VERSION))``
    做 L0 形状校验，先于 Pydantic 的 L1 契约校验。

    Args:
        version: 必须是 ``STAGE_A_VERSION`` / ``STAGE_B_VERSION`` 之一。
    """
    if version not in _SCHEMA_FILES:
        raise ValueError(f"unknown schema version: {version!r}; expected one of {sorted(_SCHEMA_FILES)}")
    filename = _SCHEMA_FILES[version]
    package = "app.services.constraint_extractor.schemas"
    try:
        raw = resources.files(package).joinpath(filename).read_text(encoding="utf-8")
    except FileNotFoundError:
        raw = (Path(__file__).resolve().parent / "schemas" / filename).read_text(encoding="utf-8")
    parsed: dict[str, Any] = json.loads(raw)
    return parsed


# 模块加载时即解析两份 schema，捕获文件缺失/JSON 损坏。
STAGE_A_SCHEMA: dict[str, Any] = load_schema(STAGE_A_VERSION)
STAGE_B_SCHEMA: dict[str, Any] = load_schema(STAGE_B_VERSION)


__all__: list[str] = [
    "STAGE_A_SCHEMA",
    "STAGE_A_VERSION",
    "STAGE_B_SCHEMA",
    "STAGE_B_VERSION",
    "load_prompt",
    "load_schema",
]
