# ADR-0007 · MinIO Storage & Constraint Corpus Layout

- **Status**: Proposed
- **Date**: 2026-04-24
- **Depends on**: [ADR-0006 Constraint Evidence & Authority Model](./0006-constraint-evidence-authority.md)
- **Driver**: ADR-0006 §8.1 Q1 确定了对象存储复用已有 MinIO；本 ADR 回答具体的**宿主机目录映射、corpus 源头目录结构、Git 追踪策略、初始化脚本**四件事，不再混进 0006。

---

## 1. Context

`docker-compose.yml` 现状：

```yaml
minio:
  image: minio/minio:latest
  volumes:
    - minio_data:/data        # ← 命名卷，Docker 自管，数据不在仓库里
...
volumes:
  minio_data:                  # ← named volume 声明
```

问题：
1. **数据无法版本化 / 审计**：命名卷对宿主开发者不透明，出问题只能 `docker volume inspect`，不利 debug
2. **初始化无迹可循**：启动后 bucket 需要手工建，新开发者 clone 仓库后无法一键起环境
3. **corpus 源头没地方放**：规范 metadata、可公开的短条款文本、允许内网分发的 PDF 目前没有 Git 追踪的安置点

## 2. Decision

### 2.1 目录三分

```
Epic01_ProLine_CAD/
├── .data/                           # ❗ gitignore 全部 — 运行时数据，随时可删重建
│   ├── postgres/
│   ├── minio/                       # ← MinIO bind-mount 目标
│   ├── milvus/
│   └── blazegraph/
│
├── corpus/                          # ✅ git tracked — 源头真相
│   ├── README.md                    # 目录说明、版权红线、贡献规范
│   ├── statutory/                   # L0 法规
│   │   ├── src_gb50016_2014/
│   │   │   ├── metadata.yaml        # title/version/issuing_body/effective_from/tags/url
│   │   │   ├── clauses/
│   │   │   │   └── 5.5.17.txt       # ≤ 2KB 短条款，公开引用
│   │   │   └── blobs/               # ← 全文 PDF，gitignore（版权 / 体积）
│   │   └── src_gb5083_2008/
│   │       ├── metadata.yaml
│   │       └── blobs/
│   ├── industry/                    # L1 行业强标
│   │   └── src_as9100d/
│   │       └── metadata.yaml        # 仅 metadata + 官方购买链接（版权）
│   ├── enterprise/                  # L2 企业（默认空目录，product 后续填）
│   ├── project/                     # L3 项目（agent 自动建档）
│   ├── heuristic/                   # L4 经验（sim 反馈自动写入）
│   └── preference/                  # L5 偏好
│
└── scripts/
    ├── init_minio.py                # 幂等创建 bucket + 策略
    └── sync_corpus_to_minio.py      # corpus/ → MinIO + upsert DB metadata
```

### 2.2 为什么三分

| 目录 | 归属 | 生命周期 | 备份策略 |
|---|---|---|---|
| `.data/minio/` | 运行时数据 | **可重建** | 不备份；挂了就跑 `sync_corpus_to_minio.py` 重灌 |
| `corpus/`（除 blobs） | 源头真相 | **可追溯** | Git 即备份；review 变更 |
| `corpus/**/blobs/` | 受版权 blob | 授权流程管控 | 走 IT 的文档管理系统（走弯路上传入 MinIO） |

核心思路：**Git 跟踪元数据 + 公开短文本，MinIO 存所有 blob，`.data/minio` 仅做本地物化**。MinIO 炸了从 `corpus/` 一键重建；metadata 错了走 PR review。

### 2.3 MinIO Bucket 设计

启动时由 `scripts/init_minio.py` 幂等创建：

```
MinIO endpoint: http://localhost:9000
Access:  minioadmin / minioadmin   (dev only, 生产走 Vault)

Buckets:
├── constraint-corpus/              # 本 ADR 对应，ADR-0006 的 doc_object_key 指向这里
│   ├── statutory/{source_id}/v{version}/{filename}
│   ├── industry/{source_id}/v{version}/{filename}
│   └── ...
├── proof-artifacts/                # 现有预留（审计 PDF）
├── cad-files/                      # 现有预留（GLB/STEP/IGES）
└── mcp-contexts/                   # 现有预留（MCP 运行快照）
```

`constraint-corpus` bucket 的策略：
- `public-read` 只对 `statutory/` 下**非版权禁用**的文件生效（GB 国标公开条款）
- `authenticated-read` 对 `industry/` + `enterprise/` + `project/`（RBAC 白名单）
- `owner-only` 对 `heuristic/`（sim 反馈私有）
- 对象加 `x-amz-meta-authority` / `x-amz-meta-source-id` / `x-amz-meta-version` 便于反查

### 2.4 docker-compose 改动

替换命名卷为宿主机绑定挂载：

```diff
   minio:
     image: minio/minio:latest
     container_name: proline-minio
     environment:
       MINIO_ROOT_USER: minioadmin
       MINIO_ROOT_PASSWORD: minioadmin
     command: server /data --console-address ":9001"
     ports:
       - "9000:9000"
       - "9001:9001"
     volumes:
-      - minio_data:/data
+      - ./.data/minio:/data
     healthcheck: ...

 volumes:
   postgres_data:
-  minio_data:
   blazegraph_data:
   milvus_data:
```

同理可把 postgres/milvus/blazegraph 也改成 `./.data/xxx`（建议同步做，dev 环境一致性），但那不在本 ADR 范围，可顺手加一条 follow-up。

### 2.5 `.gitignore` 增量

在 `Epic01_ProLine_CAD/.gitignore` 追加：

```gitignore
# 运行时数据：docker-compose volumes
/.data/

# 受版权的 corpus blob：不入 Git，走 MinIO
/corpus/**/blobs/
```

`.data/.gitkeep` 和 `corpus/**/blobs/.gitkeep` 保留目录骨架。

### 2.6 `metadata.yaml` 规范

每个 `source_id` 目录一份，结构与 `constraint_sources` 表 1:1：

```yaml
# corpus/statutory/src_gb50016_2014/metadata.yaml
source_id: src_gb50016_2014
title: 建筑设计防火规范
authority: statutory
issuing_body: 中华人民共和国住房和城乡建设部
version: GB 50016-2014（2018版）
clause: null                         # 整本；具体条款用 citations 指定
effective_from: 2015-05-01
expires_at: null
tags: [fire_safety, egress, layout]
url_or_ref: https://www.mohurd.gov.cn/...

blobs:                                # 可选，列出 corpus/{...}/blobs/* 下要上传的文件
  - file: GB50016-2014-2018ed.pdf
    visibility: authenticated-read    # public-read | authenticated-read | owner-only
    sha256: <hash, by sync script>    # 脚本自动回填，验证完整性

clauses:                              # 可选，逐条引用（≤ 2KB 文本）
  - clause: "5.5.17"
    text_file: clauses/5.5.17.txt
    tags: [egress, assembly_zone]
```

### 2.7 同步脚本职责

**`scripts/init_minio.py`**（idempotent）：
1. 连接 MinIO，检查/创建 4 个 bucket
2. 应用 bucket policy（上 §2.3）
3. 注入 lifecycle rule：`heuristic/` 90d 自动归档到 Glacier 层（将来）
4. 退出码 0 表示就绪

**`scripts/sync_corpus_to_minio.py`**：
1. 遍历 `corpus/*/src_*/metadata.yaml`
2. 对每个 source：
   - `upsert` 到 `constraint_sources` 表（DB）
   - 对每个 `blobs[]` 项：
     - 计算 sha256
     - 若 MinIO 里不存在或 hash 不一致 → 上传 `s3://constraint-corpus/{authority}/{source_id}/v{version}/{filename}`
     - 回填 `metadata.yaml` 的 `sha256` 字段（git diff 可见）
     - 更新 DB 行的 `doc_object_key`
   - 对每个 `clauses[]` 项：
     - 读 `text_file` 内容（必须 ≤ 2KB，否则 raise）
     - 作为单独 `clause_text` 或生成 `constraint_sources` 子条目
3. dry-run 模式：只打印 diff，不写 MinIO 和 DB
4. CI 运行 `--check` 模式：若 metadata.yaml 与 DB 不一致立即失败

**启动流程**：

```bash
# 一次性 bootstrap
docker-compose up -d postgres minio
alembic upgrade head           # 建表（含 migration 0016/0017）
python scripts/init_minio.py   # 建 bucket
python scripts/sync_corpus_to_minio.py  # 灌种子数据
```

## 3. Trade-offs

- **为什么不用 `docker-compose.override.yml` 保留命名卷作默认**：开发者心智负担。显式 bind-mount 让 "数据在哪" 一目了然。
- **为什么 `corpus/` 不直接当 MinIO data dir（指向 `/data`）**：MinIO 要求完整 bucket 目录结构 + `.minio.sys/` 元数据，混入 git 不现实。必须走 sync 脚本转存。
- **为什么 `blobs/` 不放 Git LFS**：版权文件（AS9100/NADCAP/HB/GJB）根本不允许入任何 Git 历史；项目 SOP 可能敏感。统一走 MinIO 更简单。
- **为什么 `metadata.yaml` 不直接当 seed migration 源**：seed migration 是跨环境契约（prod/staging/dev 一样），而 corpus 可以区分环境（dev-only fixture vs prod-only real files）。二者分离清晰。

## 4. Migration Plan

### 步骤（独立 PR）

1. **docker-compose.yml** — §2.4 的 diff
2. **`.gitignore`** — §2.5 的 5 行
3. **`corpus/` 目录骨架 + README** — 只建目录结构，放 3 个 source 的 metadata.yaml（对应 ADR-0006 §8.1 Q2 MVP）+ `corpus/statutory/src_gb50016_2014/clauses/5.5.17.txt`
4. **`scripts/init_minio.py`** — 用 `minio` python SDK
5. **`scripts/sync_corpus_to_minio.py`** — 第一轮只做 metadata upsert（blob 上传可留 P1）
6. **`Makefile` 或 `scripts/dev.sh`** — 封装 `dev-up` 一键命令
7. **CI**：加 `sync_corpus_to_minio.py --check` 作为必跑门禁

## 5. Open Questions

- 是否顺手把 `postgres / milvus / blazegraph` 的 volume 也改成 bind mount？建议是，但独立 PR。
- `corpus/**/blobs/` 需要一个替代机制让团队传大文件（GitLab Package Registry / 内部 OSS）。MVP 阶段手工上传 MinIO 即可。
- MinIO 凭据在生产环境的管理方式（Vault / Kubernetes Secret）不在本 ADR，延后。

## 6. Done Criteria（本 ADR）

- [ ] docker-compose.yml 合入 §2.4 改动
- [ ] `.gitignore` 合入 §2.5
- [ ] `Epic01_ProLine_CAD/corpus/` 目录创建 + 3 条 MVP 的 `metadata.yaml`
- [ ] `scripts/init_minio.py` + `scripts/sync_corpus_to_minio.py` 可跑通
- [ ] `make dev-up` 从零到 "MinIO 有 bucket + DB 有 3 条 constraint_sources 行" 一键搞定
