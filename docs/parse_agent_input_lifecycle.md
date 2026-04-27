# ParseAgent 原始输入与端到端生命周期

> 一句话：**ParseAgent 的原始输入是用户上传的 1 个 CAD 文件**（`.dwg` 或 `.dxf`），落到本地磁盘后只把"文件路径"传给 Agent。不是数据库行，不是 API JSON，不是几何流——就是一个文件。
>
> 配套阅读：
> - `docs/parse_agent_steps_overview.md` — 输入到达后的 13 步增强管线
> - `docs/parse_agent_rtree_design.md` — 几何加载完成后的空间索引

---

## 1. 它对自己的输入声明（agent.json）

`agents/parse_agent/agent.json::input_schema`：

```json
{
  "type": "object",
  "properties": {
    "cad_file_path": {"type": "string", "description": "Absolute path to .dwg or .dxf"},
    "options": {
      "enable_llm_fallback": true,
      "llm_call_budget": 50,
      "token_budget": 20000,
      "regression_baseline": "..."
    }
  },
  "required": ["cad_file_path"]
}
```

**只有一个必传字段**：`cad_file_path`，绝对路径字符串。其他都是预算 / 开关 / 回归基线。

---

## 2. 端到端数据流（从浏览器到 SiteModel）

```
┌──────────────────────────────────────────────────────────────────────┐
│ 1. 浏览器                                                              │
│    用户在 Dashboard 上传 factory_layout.dwg                            │
└────┬─────────────────────────────────────────────────────────────────┘
     │ multipart/form-data POST /api/dashboard/runs
     ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 2. FastAPI 路由层                                                      │
│    app/routers/dashboard_runs.py                                       │
│    │                                                                  │
│    ├─► app/security/upload.py::validate_upload()                      │
│    │     ├ 后缀检查（.dwg .dxf .ifc .step .stp）                       │
│    │     ├ 魔术字节检查：DWG = AC10/AC1./AC2.；DXF = "0\nSECTION"      │
│    │     └ 大小上限 50MB（DASHBOARD_UPLOAD_MAX_BYTES 可调）            │
│    │                                                                  │
│    ▼                                                                  │
│ 3. 业务服务层                                                          │
│    app/services/runs_service.py::create_run()                          │
│    │                                                                  │
│    ├─► 写文件到磁盘                                                    │
│    │   exp/uploads/<run_id>/<safe_name>.{dwg|dxf}                     │
│    │   （UPLOAD_ROOT 由 DASHBOARD_UPLOAD_ROOT 环境变量覆盖）           │
│    │                                                                  │
│    └─► 在 mcp_contexts 表插入一行：                                    │
│        {                                                              │
│          agent: "ParseAgent",                                         │
│          status: "PENDING",                                           │
│          input_payload: {                                             │
│             upload_path: "exp/uploads/abc.../factory_layout.dwg",     │
│             filename:    "factory_layout.dwg",                        │
│             detected_format: "dwg"                                    │
│          }                                                            │
│        }                                                              │
│                                                                       │
│    ★ 到此 HTTP 请求结束，返回 run_id 给前端                            │
│      (上传文件大小可达 50MB，所以业务和解析必须解耦)                    │
└──────────────────────────────────────────────────────────────────────┘
                                │
                  ──────────────┴───────────────
                  │     PENDING 排队中            │
                  ▼                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 4. 后台 Worker 接力（独立进程）                                         │
│    app/workers/parse_agent_worker.py                                   │
│    `python -m app.workers.parse_agent_worker --loop`                  │
│    │                                                                  │
│    ├─► _claim_pending_run(db)                                         │
│    │     原子拿一个 PENDING 行，flip 到 RUNNING                        │
│    │                                                                  │
│    ├─► 读取 input_payload.upload_path                                  │
│    │     = "exp/uploads/abc.../factory_layout.dwg"                    │
│    │     ★ 这就是 ParseAgent 真正的输入                                │
│    │                                                                  │
│    ├─► _do_parse(input_payload)                                       │
│    │     ├ 检查文件存在 + 非空                                         │
│    │     └ app/services/parse/cad_parser.py::parse_cad()              │
│    │         │                                                        │
│    │         ├─ DXF 分支：直接 ezdxf.readfile()                        │
│    │         │     抽出 entities / layers / blocks / dxf_version /    │
│    │         │     units                                              │
│    │         │                                                        │
│    │         └─ DWG 分支：调本地 ODA File Converter                    │
│    │              tools/ODAFileConverter/ODAFileConverter.exe         │
│    │              （repo 自带，无需运维额外安装）                       │
│    │              .dwg → .dwg.converted.dxf（同目录）                  │
│    │              .converted.dxf 留在原位 → 前端预览要用                │
│    │              然后 fall through 走 _parse_dxf                     │
│    │                                                                  │
│    ├─► 进入 enrichment pipeline (A→M 13 步)                            │
│    │   见 docs/parse_agent_steps_overview.md                          │
│    │   A_normalize → ... → M_provenance_note                          │
│    │                                                                  │
│    └─► 写回                                                           │
│        ├ mcp_contexts.output_payload  (流水帐 JSONB)                   │
│        ├ site_models                  (强 schema 主表)                 │
│        ├ asset_geometries             (每个 asset 的几何)              │
│        ├ taxonomy_terms / quarantine_terms (术语库 / 待审)              │
│        ├ run_evaluations              (5 维 / 4 阶 / 4 闸快照)         │
│        ├ audit_logs                   (来源凭证)                       │
│        └ status = FINISHED                                            │
└──────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 5. 前端展示（用户回到浏览器）                                            │
│    /runs/[id]   → /sites/[runId]                                      │
│    │                                                                  │
│    ├─► API 拉 SiteModel JSON                                          │
│    │                                                                  │
│    └─► /api/dashboard/runs/{id}/cad                                   │
│         流式返回 .converted.dxf（DWG 上传走这条）                       │
│         或原始上传 .dxf（DXF 上传走这条）                                │
│         → MLightCAD / dxf-viewer 渲染                                  │
│         ★ 当前 hatch boundary bug 就是这一步炸的                        │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. 一个具体例子的数据形态变迁表

| # | 步骤 | 数据形态 | 物理位置 | 谁产生 |
|---|------|---------|----------|--------|
| ① | 浏览器上传 | binary blob (multipart) | 网络流 | 用户 |
| ② | 上传校验通过 | `bytes` | Python 进程内存 | `validate_upload()` |
| ③ | 落盘 | `factory_layout.dwg` (bytes 原样) | `exp/uploads/abc-123/factory_layout.dwg` | `create_run()` |
| ④ | 入队 | `mcp_contexts` 行 (PENDING) | PostgreSQL | `create_run()` |
| ⑤ | Worker 接到任务 | `input_payload = {"upload_path": ".../factory_layout.dwg", ...}` | Python 内存 | `_claim_pending_run()` |
| ⑥ | DWG → DXF 转换 | `factory_layout.dwg.converted.dxf` (文本) | 本地磁盘（同目录） | ODA File Converter |
| ⑦ | ezdxf 解析 | `ezdxf.Document` 对象（图层 / 块 / 实体集合） | Python 内存 | `_parse_dxf()` |
| ⑧ | A-M 13 步增强 | `output_payload.llm_enrichment.sections.*` JSON | 内存 → DB | `enrichment/pipeline.py` |
| ⑨ | 产出 SiteModel | 强 schema 行 + `asset_geometries` 行 | PostgreSQL | `K_asset_extract` |
| ⑩ | 前端渲染 | SiteModel JSON + `.converted.dxf` 流 | 浏览器 | MLightCAD / dxf-viewer |

> 第 ⑥ 步留下的 `.converted.dxf` 就是 MLightCAD（hatch boundary 报错）实际渲染的文件。**严格说那个 bug 不是"原始 DWG 出错"，而是"DWG → DXF 中间产物里的 HATCH 在浏览器渲染崩了"**。

---

## 4. 为什么是"文件路径"而不是"文件字节"？

历史上 ParseAgent 几次迭代都考虑过下面 3 种方案：

| 方案 | 优点 | 缺点 | 现状 |
|------|-----|------|------|
| **路径** ✅ 当前 | Worker / Dashboard 跨进程透明；ezdxf 直接 readfile；ODA 转换需要文件 | 路径耦合到本机文件系统，多机部署需要共享盘或 MinIO | **采用** |
| 字节流 (Body) | 真正无状态 | DWG 50MB 走 HTTP 的 worker 内存峰值高；ODA 必须先落盘 | ❌ |
| MinIO 引用 (S3 URL) | 多机部署友好 | 需要把 ODA fallback 也搬到 MinIO 流式 | M2 后期规划 |

> 多机 / Temporal 编排正式上线时，会把 `upload_path` 字段的语义从"本地路径"扩成"MinIO URI"，Worker 端做 stream-to-tempfile。这是 docs/adr/0007-minio-corpus-layout.md 里规划的内容；现在仍是本地路径。

---

## 5. 上传校验是 ParseAgent 之前的最后一道防线

Web 层 `app/security/upload.py` 里的检查不是 ParseAgent 自身，但**ParseAgent 假定它已经跑过**：

```python
ALLOWED_EXTS = (".dwg", ".dxf", ".ifc", ".step", ".stp")

_BINARY_MAGIC = {
    "dwg": [b"AC10", b"AC1.", b"AC2."],   # AutoCAD R14..2018+
}
_TEXT_MAGIC = {
    "stp": [b"ISO-10303-21"],
    "dxf": [b"0\r\nSECTION", b"0\nSECTION", b"AutoCAD Binary DXF"],
}
```

也就是说：**只有 dwg/dxf 走 ParseAgent**；ifc/step/stp 走另一条管线（M3 规划）。如果上传的文件后缀和魔术字节不匹配，HTTP 直接 4xx，永远不会进 ParseAgent。

---

## 6. 输入相关的常见误解澄清

### ❌ 误解 1：「ParseAgent 的输入是 agent.json 里那堆 tools 的调用」

**不对**。`tools` 是 ParseAgent **运行过程中**自己向工具调度器发起的调用（仅在 H4 LLM fallback 阶段触发）：

| 工具 | 实际作用 | 是输入吗 |
|------|---------|---------|
| `lookup_block_definition` | 读已加载到内存的 ezdxf Document 的子片段 | ❌ 内部能力 |
| `list_layer_entities` | 同上，读图层实体样本 | ❌ 内部能力 |
| `search_similar_blocks` | RAG 历史 gold 库 (planned) | ❌ 内部能力 |
| `propose_taxonomy_term` | 把候选词写到 quarantine 队列 (write-deferred) | ❌ 内部能力（且是输出方向） |

它们是 ParseAgent 在做"难题"时给自己用的工具，不是它的输入。

### ❌ 误解 2：「ParseAgent 输入的是 mcp_contexts 行」

**也不对**。Worker 从 `mcp_contexts` 表拿到的是 PENDING 任务**指针**，真正进 ParseAgent 的还是 `input_payload.upload_path` 指向的那个本地文件。`mcp_contexts` 是任务队列 + 流水帐，不是数据载体。

### ❌ 误解 3：「ParseAgent 自己处理 HTTP 请求」

**不对**。HTTP 请求由 FastAPI 处理；ParseAgent 是后台 Worker，跟 HTTP 完全不耦合。这种分离让上传请求最快几十毫秒就能 ACK，解析慢就让它慢，不会卡死前端。

---

## 7. 白话总结（图纸审计员比喻）

> 想象你是个图纸审计员：
> 1. **输入** ＝ 老板甩你桌子上的一份 CAD 图纸（`.dwg` 或 `.dxf` 文件）；
> 2. **第一步**（H1）你先看封面是不是正经 CAD 而不是别人改后缀的 zip；
> 3. **第二步**（H2-H3）你用 ezdxf 把图打开，把每个图层、每个图块、每个实体记下来；
> 4. **第三步**（A→K 13 步增强）你按行业字典把脏中英混合命名清洗、与你脑子里的"标准术语库"对齐、识别哪个块是设备 / 传送带 / 安全区 / 工位 / 注释；
> 5. **第四步**（F/G/I）打质量分 + 写审核结论；
> 6. **输出**：一份结构化、可被下游约束 / 布局 Agent 直接吃的 SiteModel。

老板甩到桌上的图，就是 ParseAgent 的"输入"——一个文件，仅此而已。
