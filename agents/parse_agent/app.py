"""ParseAgent — CAD 解析 + 本体识别 Agent (Agent1)。

FastAPI 服务入口。
端口: 5001
输入: CAD 文件 (DWG/IFC/STEP/DXF)
输出: SiteModel + Ontology Graph

参考: ExcPlan/Agent Profile §1 ParseAgent
"""

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse

from shared.config import settings

from agents.parse_agent.agent_loader import load_agent_definition

# 启动期硬校验 agent.json — 失败立即抛错，不允许残缺契约启动
_AGENT_DEF = load_agent_definition()

app = FastAPI(
    title="ParseAgent — 语义识别 Agent",
    description=_AGENT_DEF.raw["description"],
    version=_AGENT_DEF.version,
)
app.state.agent_def = _AGENT_DEF


@app.get("/version")
async def version():
    """返回 agent.json 元数据 + 当前质量基线 (供 CI/调用方核对)。"""
    eval_meta = _AGENT_DEF.evaluation
    tiers = eval_meta.get("tiers", {})
    return {
        "name": _AGENT_DEF.name,
        "version": _AGENT_DEF.version,
        "model": _AGENT_DEF.model,
        "tools": [t["name"] for t in _AGENT_DEF.tools],
        "hooks": list(_AGENT_DEF.hooks.keys()),
        "scores": {
            "gold_current": tiers.get("gold", {}).get("current_score"),
            "gold_target": tiers.get("gold", {}).get("ga_target"),
            "llm_judge_current": tiers.get("bronze", {}).get("current_score"),
            "llm_judge_target": tiers.get("bronze", {}).get("ga_target"),
        },
    }


@app.get("/health")
async def health():
    """健康检查端点。"""
    return {
        "status": "ok",
        "agent": _AGENT_DEF.name,
        "version": _AGENT_DEF.version,
    }


@app.post("/mcp/agent/parse")
async def parse_cad(
    cad_file: UploadFile = File(...),
    format: str = "AUTO",
    coord_system: str = "AUTO",
    ontology_version: str = "AeroOntology-v1.0",
    confidence_threshold: float = 0.90,
):
    """CAD 解析主端点。

    接收 CAD 文件，执行以下流程:
    1. 格式检测 (format_detect)
    2. 实体提取 (entity_extract) + R-Tree 空间索引
    3. 坐标标准化 (coord_normalize)
    4. 拓扑修补 (topology_repair)
    5. 本体资产识别 (classify_entity + confidence_scoring)
    6. 语义关系映射 (ontology_linking)
    7. SiteModel 序列化与持久化

    返回: SiteModel + mcp_context_id
    """
    raise NotImplementedError("ParseAgent 业务逻辑待实现 — 参考 ExcPlan/Agent Profile §1.3")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PARSE_AGENT_PORT)
