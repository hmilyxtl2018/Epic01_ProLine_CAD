# 贡献指南 — ProLine CAD

感谢你对 ProLine CAD 项目的贡献！请阅读以下指南以确保协作流畅。

---

## 分支策略

```
main          ← 稳定发布分支（受保护，需 PR + CI 通过）
  └── develop ← 日常集成分支
       ├── feature/M2-parse-agent-cad-module
       ├── feature/M3-constraint-z3-gateway
       └── fix/issue-15-dwg-parsing-timeout
```

- **main**: 稳定版本，仅通过 develop → main 的 PR 合并
- **develop**: 日常开发集成，所有 feature 分支的合并目标
- **feature/\***: 功能分支，命名规则 `feature/<milestone>-<简短描述>`
- **fix/\***: 修复分支，命名规则 `fix/<issue-id>-<简短描述>`

---

## 代码规范

### 语言约定

| 场景 | 语言 |
|------|------|
| 代码标识符（变量名、函数名、类名） | **英文** |
| API 端点与参数名 | **英文** |
| 文档注释（docstring）、代码注释 | **中文** |
| 测试描述与用例 ID | **中文**（含 S1-TC01 格式 ID） |
| PRD / 执行计划文档 | **中文** |
| commit message | **英文** |

### 代码风格

- 使用 **ruff** 进行 lint 和 format（配置在 `pyproject.toml`）
- 行宽上限 **120** 字符
- 源文件分区使用注释分隔符：`# ════════════════ 标题 ════════════════`
- 数据模型使用 **Pydantic v2** (`BaseModel`)
- 异步接口使用 **async/await**

```bash
# 提交前检查
ruff check .
ruff format .
```

### TDD 约定

- `spikes/` 中的源码为 stub（`raise NotImplementedError`），实现时填入方法体，不重构类结构
- `agents/` 中的 Agent 服务同样遵循 TDD，初始为 stub
- **Thresholds 不可削弱** — Go/No-Go 阈值在 `spikes/conftest.py::Thresholds` 中定义，测试必须 assert 这些阈值
- 测试用例 ID（如 `S1-TC01`）映射到 `PRD/step5.2-关键技术验证计划.md`

---

## PR 流程

1. 从 `develop` 创建 feature 分支
2. 开发并通过本地测试（至少 P0 全部通过）
3. 推送并创建 PR → `develop`
4. 确保 CI Pipeline 通过（ruff + pytest）
5. 至少 1 位 reviewer 批准
6. Squash merge 到 develop

### PR Checklist

- [ ] 关联了对应的 GitHub Issue（`Fixes #xx` 或 `Relates to #xx`）
- [ ] P0 测试通过（`cd spikes && pytest -m p0`）
- [ ] 新代码有对应测试
- [ ] mcp_context 链路完整（如涉及 Agent 间通信）
- [ ] ruff check 无 error
- [ ] 没有硬编码的阈值（使用 `Thresholds` 类）

---

## Commit Message 规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]
[optional footer]
```

**类型**:

| Type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `test` | 测试相关 |
| `docs` | 文档更新 |
| `chore` | 构建/CI/工具链 |
| `refactor` | 重构（不改变行为） |

**Scope 示例**: `parse-agent`, `constraint-agent`, `layout-agent`, `orchestrator`, `shared`, `spike-01`, `ci`, `docker`

**示例**:
```
feat(parse-agent): implement CAD format detection module
fix(constraint-agent): correct Z3 distance encoding to use squared comparison
test(spike-03): add R-Tree collision detection benchmark
chore(ci): add pytest-cov to GitHub Actions workflow
```

---

## 目录职责

| 目录 | 用途 | 修改时注意 |
|------|------|-----------|
| `agents/` | 正式 Agent 实现 | 需对应测试 + mcp_context |
| `shared/` | 共享数据模型与协议 | 改动影响所有 Agent，需谨慎 |
| `spikes/` | 技术验证实验 | 保持独立，不依赖 agents/ |
| `db/` | 数据库 DDL | 新增迁移文件，不修改已有 |
| `PRD/` | 产品需求文档 | 只读参考，由 PM 维护 |
| `ExcPlan/` | 执行计划文档 | 只读参考 |

---

## 问题与讨论

- Bug / 功能请求 → 创建 GitHub Issue（使用对应模板）
- 技术讨论 → GitHub Discussions 或 Issue 评论
- 紧急问题 → 直接联系项目维护者
