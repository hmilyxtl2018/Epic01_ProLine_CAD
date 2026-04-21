<!--
Pull Request template — ProLine CAD.
Three sections (Risk / Rollback / Test plan) are MANDATORY per CLAUDE.md §8.
A reviewer must reject the PR if any of these is empty or "n/a".
-->

## 变更描述

<!-- 1-3 句话说明 PR 做了什么以及为什么。链接 PRD/ADR/Issue。 -->

Fixes #

## 变更类型

- [ ] feat
- [ ] fix
- [ ] refactor
- [ ] test
- [ ] docs
- [ ] chore (build/CI/deps)
- [ ] migration (DB schema change)

---

## Risk (必填)

<!--
说明本次变更的影响半径,选择并补充细节:
- single-agent  ── 仅影响某个 agent 内部行为
- cross-agent   ── 改变 MCP 协议字段、共享模型 (shared/models.py) 或事件
- db / schema   ── 触发 Alembic migration
- public api    ── 修改 /api/* 或 dashboard 对外契约
- security      ── 触及鉴权、密钥、加密、依赖升级 (CVE 相关)
对每条勾选项,说明最坏情况:谁会被打断、数据会不会损坏。
-->

- 影响范围:
- 最坏情况:
- 已识别的副作用:

## Rollback (必填)

<!--
精确到单条命令的回滚预案。"revert PR" 不算,要给具体的 revision id /
feature flag / wheel tag / migration downgrade。
-->

- 回滚命令 / 步骤:
- 预计回滚耗时:
- 回滚后是否有残留数据需要清理 (yes/no, 怎么清理):

## Test plan (必填)

<!-- 列出实际跑过的命令以及输出摘要;贴关键 pytest 输出片段。 -->

- [ ] 单元测试:
  ```
  pytest <path> -q
  ```
- [ ] L1 gold regression (若涉及 agent 输出):
  ```
  python scripts/gold_eval.py
  ```
- [ ] schema drift (若改了 Pydantic 或 DDL):
  ```
  python scripts/check_schema_drift.py
  ```
- [ ] agent 隔离 (若改了 agents/):
  ```
  python scripts/check_agent_isolation.py
  ```
- [ ] 前端 (若涉及 dashboard):
  ```
  npm run lint && npm run test && npm run build
  ```

新增/修改的测试文件:

---

## Checklist

- [ ] CI 三段全绿 (schema-check / unit / integration / gold-regression)
- [ ] ruff check / ruff format / mypy 无 error
- [ ] mcp_context_id 在新代码路径中正确传递
- [ ] 没有硬编码阈值 (使用 `Thresholds` / `agent.json::evaluation.baseline`)
- [ ] 没有 emoji (CLAUDE.md §11)
- [ ] 没有跨 agent import (CLAUDE.md §5)
- [ ] 没有秘钥、token、DSN 硬编码 (CLAUDE.md §8)
- [ ] 文档注释为中文,标识符为英文
- [ ] Conventional Commits commit message
- [ ] 新增依赖已写入 `pyproject.toml`,未追加 `requirements.txt`
- [ ] 若新增 migration: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` 通过
