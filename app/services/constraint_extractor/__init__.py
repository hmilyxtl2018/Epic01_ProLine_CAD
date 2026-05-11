"""ConstraintExtractor 服务 — LLM 工艺约束抽取（ADR-0010 / T3+T4+T5）。

T3 阶段先落 prompt 模板与版本常量；T4 实现 ``ConstraintExtractor``
服务类；T5 暴露为 ``POST /sites/{id}/constraints/extract`` HTTP 入口。

**版本字段 vs 模板内容**：

- ``STAGE_A_VERSION`` / ``STAGE_B_VERSION`` 是写入 ``constraint_extractions.prompt_version``
  的字符串，CHECK ``ck_ce_llm_metadata`` 强制 LLM 抽取行必须带它。
- 任何 prompt 内容修改（字符级）都必须同步 bump 版本号（v1 → v2），
  这是审计线的唯一锚点（ADR-0010 §2.2 第 2 条 + L1 gold 测试基线）。

**目录布局**：

```
app/services/constraint_extractor/
    __init__.py                # 本文件，公开版本常量 + load_prompt()
    prompts/
        stage_a_candidates.zh.md
        stage_b_structured.zh.md
    extractor.py               # T4 落
    stub_data.py               # T4 落（fixture 回放）
```
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

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


__all__: list[str] = [
    "STAGE_A_VERSION",
    "STAGE_B_VERSION",
    "load_prompt",
]
