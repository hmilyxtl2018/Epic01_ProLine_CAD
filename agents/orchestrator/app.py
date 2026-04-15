"""Orchestrator — 流程编排服务。

FastAPI 服务入口。
端口: 5000
职责: CAD 导入 → 触发 Agent 链 → 管理重试与超时 → mcp_context 链路传递

参考: ExcPlan/执行计划 §5.1 Orchestrator 实现
"""

from fastapi import FastAPI, UploadFile, File

from shared.config import settings

app = FastAPI(
    title="Orchestrator — MCP 流程编排",
    description="工作流状态机 + Agent 链路调度 + mcp_context 传递",
    version="1.0.0",
)


@app.get("/health")
async def health():
    """健康检查端点。"""
    return {"status": "ok", "service": "Orchestrator", "version": "v1.0"}


@app.post("/api/v1/import_cad")
async def import_cad(cad_file: UploadFile = File(...)):
    """CAD 导入入口 — 触发完整的 Agent 闭环流程。

    工作流: PENDING → PARSE_RUNNING → CONSTRAINT_CHECKING → LAYOUT_OPTIMIZING → COMPLETE
    支持迭代: 若 Agent3 仍有 hard_violations，自动回环到 Agent2。
    最大迭代: 3 次。
    """
    raise NotImplementedError("Orchestrator 编排逻辑待实现 — 参考执行计划 §5.1")


@app.get("/api/v1/workflow/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """查询工作流状态。"""
    raise NotImplementedError


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.ORCHESTRATOR_PORT)
