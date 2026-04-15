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

app = FastAPI(
    title="ParseAgent — 语义识别 Agent",
    description="CAD 解析 + 几何修补 + 本体映射",
    version="1.0.0",
)


@app.get("/health")
async def health():
    """健康检查端点。"""
    return {"status": "ok", "agent": "ParseAgent", "version": "v1.0"}


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
