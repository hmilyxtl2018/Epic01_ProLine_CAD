# ADR-006 — 可观测性三件套: structlog + OpenTelemetry + Prometheus

- **Status**: Accepted
- **Date**: 2026-04-21
- **Deciders**: ProLine CAD core team
- **Related**: T2 W2 Dashboard backend (M1), ExcPlan §3.4.3,
  CLAUDE.md §6 (Logging conventions)

## 背景

进入 T2 W2 Dashboard 阶段后,后端 FastAPI 同时承担:

1. **请求级日志** — 每个 HTTP / agent 调用的结构化字段(request_id、
   agent_id、context_id、tenant_id),给排障与审计用。
2. **跨服务链路** — ParseAgent → MCP store → DB → Dashboard 的完整 trace,
   定位"为什么这个 token 走了 5s"必须能下钻到具体 span。
3. **聚合指标** — RPS、P95 延迟、错误率、CDC slot lag、quarantine 队列
   长度;给告警与容量规划用。

把这三件事塞进 print + 一个 `logging.basicConfig` 已经压不住了;尤其
multi-agent 异步并发场景,无 trace_id 关联的日志根本读不出因果。

## 决策

采用 **三件套并行,不互相替代**:

- **structlog 24+** —— 应用层日志唯一入口。所有 `logger.info(event,
  **fields)` 调用统一走 JSON renderer,标准字段集 = `{ts, level, event,
  request_id, trace_id, span_id, agent_id, context_id, tenant_id}`。开发
  环境用 ConsoleRenderer 着色,生产用 JSONRenderer 直进 stdout 给
  collector。
- **OpenTelemetry SDK 1.25+** —— 链路与 trace 的事实标准。FastAPI、
  httpx、SQLAlchemy、psycopg2 全部用对应 instrumentation 自动挂钩。
  Exporter 默认走 OTLP/gRPC 到本地 collector,collector 再分发到
  Tempo / Jaeger。trace_id / span_id 通过 `structlog.contextvars` 注入
  到日志,实现 log↔trace 双向跳转。
- **Prometheus client 0.20+** —— 拉模式指标。FastAPI 暴露 `/metrics`,
  自定义 metric 命名空间 `proline_*`(直方图用 `_seconds`,counter 用
  `_total`)。关键 SLO 指标:`proline_http_request_duration_seconds`、
  `proline_agent_invocation_total{agent,status}`、
  `proline_quarantine_pending`。

三者职责互不重叠:

| 维度       | structlog | OpenTelemetry | Prometheus |
|------------|-----------|---------------|------------|
| 单条事件   | ✅        | ✅ (作为 span event) | ❌ |
| 跨服务链路 | ❌        | ✅            | ❌ |
| 时间序列聚合 | ❌      | ❌            | ✅ |

## 备选方案

- **只用 OTel logs + metrics**: 否,OTel logs SDK 在 2026-04 仍不如
  structlog 成熟(尤其是 contextvars 异步上下文与 Python 3.13 兼容),
  且强绑 collector 让本地开发首跑成本陡增。
- **Loki / ELK 直推**: 否,绕过 OTel collector 等于放弃统一管道,
  未来切后端要重写 exporter。
- **自研 logger + 手撸 trace_id**: 否,已经有人踩过 contextvars 在
  asyncio.gather 下丢失的坑(spike/2026-03-traceid-loss.md),不重复。

## 影响

**正面**

- log / trace / metric 三视图统一 trace_id 关联,定位"哪一次 agent
  调用慢"从猜测变成 30s 工作。
- Dashboard 的 SLO 数字直接来自 Prometheus,不再依赖临时脚本扫日志。
- 标准库化降低 onboard 成本:新成员只学 structlog API,无需理解 trace
  上下文管理。

**负面 / 风险**

- 三个 SDK 加起来约 +25MB venv 体积、+150ms 冷启动。可接受。
- OTel auto-instrumentation 会偶尔误抓 sqlite memory connection 之类
  无关 span,需要在 `opentelemetry.sdk.trace.sampling` 加 sampler
  过滤(M1 完成)。
- Prometheus 多进程模式(gunicorn 多 worker)需 `prometheus_multiproc_dir`
  共享目录,部署文档要单独说明。

## 验证

- 启动 FastAPI 后:
  - `curl :8000/metrics` 返回 `proline_http_request_duration_seconds_*`
  - 一次请求的日志行同时含 `trace_id` 与 `span_id`,值能在 Tempo UI
    中检索到对应 trace。
  - OTel collector 收到至少一个 root span 来自 FastAPI、一个子 span
    来自 SQLAlchemy。
- 单测 `tests/observability/test_log_trace_correlation.py`:在 mock
  collector 下断言 `record.trace_id == span.context.trace_id`。
