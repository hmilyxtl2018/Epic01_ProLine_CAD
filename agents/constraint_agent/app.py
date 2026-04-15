"""ConstraintAgent — 约束检查 + Z3 验证 Agent (Agent2)。

FastAPI 服务入口。
端口: 5002
输入: SiteModel + Constraint Set (CS-001)
输出: Hard Violations + Soft Scores + Reasoning Chain

参考: ExcPlan/Agent Profile §2 ConstraintAgent
"""

from fastapi import FastAPI

from shared.config import settings

app = FastAPI(
    title="ConstraintAgent — 约束诊断 Agent",
    description="规则检查 + Z3 SAT 求解 + 约束诊断",
    version="1.0.0",
)


@app.get("/health")
async def health():
    """健康检查端点。"""
    return {"status": "ok", "agent": "ConstraintAgent", "version": "v1.0"}


@app.post("/mcp/agent/constraint/check")
async def check_constraints(
    site_model_id: str,
    constraint_set_id: str = "CS-001",
):
    """约束检查主端点。

    接收 SiteModel ID 和约束集 ID，执行:
    1. 约束集加载 (load_constraint_set)
    2. 硬约束 Z3 编码与验证 (encode + solve)
    3. UNSAT Core 提取（若冲突）
    4. 软约束评分计算
    5. 冲突报告 + Reasoning Chain 生成

    返回: Violations + SoftScores + mcp_context_id
    """
    raise NotImplementedError("ConstraintAgent 业务逻辑待实现 — 参考 ExcPlan/Agent Profile §2.3")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.CONSTRAINT_AGENT_PORT)
