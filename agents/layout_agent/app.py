"""LayoutAgent — 布局优化 Agent (Agent3)。

FastAPI 服务入口。
端口: 5003
输入: Violations + Soft Targets + SiteModel
输出: Top3 candidates + Reasoning Chain

参考: ExcPlan/Agent Profile §3 LayoutAgent
"""

from fastapi import FastAPI

from shared.config import settings

app = FastAPI(
    title="LayoutAgent — 布局优化 Agent",
    description="GA 遗传算法 + R-Tree 碰撞检测 + TopK 方案生成",
    version="1.0.0",
)


@app.get("/health")
async def health():
    """健康检查端点。"""
    return {"status": "ok", "agent": "LayoutAgent", "version": "v1.0"}


@app.post("/mcp/agent/layout/optimize")
async def optimize_layout(
    site_model_id: str,
    violations: list[str] | None = None,
    soft_targets: list[str] | None = None,
    search_space_size: int = 1000,
):
    """布局优化主端点。

    接收 SiteModel ID 和约束冲突信息，执行:
    1. 搜索空间定义 (build_search_space)
    2. GA 种群初始化 (initialize_population)
    3. 遗传算法迭代 + R-Tree 碰撞检测
    4. 候选方案 Z3 验证
    5. Top3 评分排序 + Reasoning Chain

    返回: Top3 candidates + mcp_context_id
    """
    raise NotImplementedError("LayoutAgent 业务逻辑待实现 — 参考 ExcPlan/Agent Profile §3.3")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.LAYOUT_AGENT_PORT)
