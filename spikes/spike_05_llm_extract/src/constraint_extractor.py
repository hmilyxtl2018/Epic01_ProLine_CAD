"""LLM 约束提取器 — Stub"""
from dataclasses import dataclass, field
import json


@dataclass
class ConstraintRule:
    id: str = ""
    type: str = ""  # "hard" | "soft"
    rule: str = ""
    source_ref: str | None = None

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type, "rule": self.rule, "source_ref": self.source_ref}


@dataclass
class ExtractionResult:
    constraints: list[ConstraintRule] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({"constraints": [c.to_dict() for c in self.constraints]}, ensure_ascii=False)


class ConstraintExtractor:
    def __init__(self, strategy: str = "few_shot", llm_backend=None):
        self.strategy = strategy
        self.llm_backend = llm_backend  # 注入 Mock: fn(doc, strategy) -> dict

    def extract(self, document: str) -> ExtractionResult:
        raise NotImplementedError("ConstraintExtractor.extract 尚未实现")
