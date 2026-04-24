# Constraint Corpus — 规范语料源头目录

> ADR-0007 §2.1 定义的 6 级权威来源（statutory/industry/enterprise/project/heuristic/preference）的**元数据**。
> 真正的 PDF blob 走 MinIO（见 ADR-0007 §2.2），**不入 Git**。

## 目录约定

```
corpus/
├── statutory/            L0 法规 / 适航
├── industry/             L1 行业强标 / 军标 / AESQ
├── enterprise/           L2 企业 / OEM
├── project/              L3 项目工艺（Agent 自动建档）
├── heuristic/            L4 经验（sim 反馈自动写入）
└── preference/           L5 偏好
```

每个 `src_<id>/` 目录下：

- `metadata.yaml`   ← **Git 追踪**，对应 `constraint_sources` 表 1:1
- `clauses/*.txt`   ← 可选，≤ 2KB 的公开条款文本
- `blobs/*.pdf`     ← **gitignore**，版权文件通过 MinIO 管理

## 同步方式

```bash
python scripts/init_minio.py                  # 建 bucket
python scripts/sync_corpus_to_minio.py        # 读 metadata.yaml → upsert DB + 上传 MinIO
python scripts/sync_corpus_to_minio.py --check # CI 门禁
```

## 当前 MVP seed（6 份真实来源）

| source_id | Authority | 标题 | 发布方 |
|---|---|---|---|
| `src_as9100d_2016` | industry | AS9100D Quality Management Systems — Aviation, Space & Defense | SAE / IAQG |
| `src_as9102b_2014` | industry | AS9102B First Article Inspection Requirement | SAE / IAQG |
| `src_as13004_2021` | industry | AS13004 Process Failure Mode and Effects Analysis (PFMEA) and Control Plans | SAE / AESQ |
| `src_as13100_2021` | industry | AS13100 AESQ QMS Requirements for Aero Engine Design & Production | SAE / AESQ |
| `src_gb_t_19001_2016` | industry | GB/T 19001-2016 质量管理体系要求 | 国家市场监督管理总局 |
| `src_gjb_9001c_2017` | industry | GJB 9001C-2017 质量管理体系要求 | 中央军委装备发展部 |

> ⚠️ 本目录只保留**公开元数据**（标准号、名称、发布机构、生效日期、官方索引 URL）。
> 标准全文受 SAE International / IAQG / 国军标编辑委员会版权保护，**严禁**把 PDF 直接 commit 进 Git。
> 需要全文时走企业采购流程 → 上传 MinIO → `metadata.yaml.blobs[]` 登记 sha256。
