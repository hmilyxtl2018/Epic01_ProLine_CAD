## 变更描述

<!-- 简要描述这个 PR 做了什么 -->

## 关联 Issue

<!-- 使用 Fixes #xx 或 Relates to #xx -->
Fixes #

## 变更类型

- [ ] feat: 新功能
- [ ] fix: Bug 修复
- [ ] test: 测试
- [ ] docs: 文档
- [ ] chore: 构建/CI
- [ ] refactor: 重构

## 测试结果

```
# 粘贴 pytest 输出
cd spikes && python -m pytest -m p0
```

## Checklist

- [ ] P0 测试全部通过（`cd spikes && pytest -m p0`）
- [ ] 新代码有对应测试
- [ ] ruff check 无 error（`ruff check .`）
- [ ] 没有硬编码的阈值（使用 `Thresholds` 类）
- [ ] mcp_context 链路完整（如涉及 Agent 间通信）
- [ ] 文档注释为中文，标识符为英文
- [ ] commit message 符合 Conventional Commits 规范
