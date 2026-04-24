"""
scripts/init_minio.py
=====================

ADR-0007 §2.3 / §2.7 · MinIO bucket bootstrap (idempotent).

职责
----
1. 连接 MinIO，幂等地创建 4 个 bucket：
     - constraint-corpus   规范语料（ADR-0006 / 0007 主力）
     - proof-artifacts     审计/证据 PDF
     - cad-files           GLB/STEP/IGES
     - mcp-contexts        MCP 运行快照

2. 应用 bucket 策略（ADR-0007 §2.3）：
     - constraint-corpus 对 `statutory/*` 前缀允许 **匿名 GetObject**
       （仅限 GB 国标公开条款，行业强标/企业/项目/经验/偏好走
       authenticated-read，由应用层 STS/presign 发放）
     - 其它 bucket 默认 private（不设公共策略）

3. 打印 bucket 清单 + 版本 + 状态，退出码 0 表示就绪。

4. 所有操作**幂等**：重复运行不会报错，只会跳过已存在项。

CLI
---
    python scripts/init_minio.py \
        [--endpoint localhost:9000] \
        [--access-key minioadmin] \
        [--secret-key minioadmin] \
        [--secure] \
        [--dry-run]

环境变量（CLI 未指定时使用）
    MINIO_ENDPOINT         default: localhost:9000
    MINIO_ROOT_USER        default: minioadmin
    MINIO_ROOT_PASSWORD    default: minioadmin
    MINIO_SECURE           default: false  (set "1"/"true" 开启 HTTPS)

退出码
    0   一切就绪（或 dry-run 预览成功）
    1   连接失败 / 未知异常
    2   参数错误

参考
----
- ADR-0007 §2.3 bucket 定义
- ADR-0007 §2.7 init_minio.py 职责
- ADR-0006 §8.1 Q1 对象存储与 doc_object_key 的关系
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import Optional

try:
    from minio import Minio
    from minio.error import S3Error
except ImportError as e:
    print(
        "ERROR: `minio` package not installed. "
        "Run: pip install minio>=7.2",
        file=sys.stderr,
    )
    raise SystemExit(1) from e


# ──────────────────────────────────────────────────────────────────────
# 1. Bucket 规格表 —— ADR-0007 §2.3
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BucketSpec:
    name: str
    purpose: str
    public_prefix: Optional[str] = None  # 对该前缀开 anonymous GetObject；None = 全私


BUCKET_SPECS: tuple[BucketSpec, ...] = (
    BucketSpec(
        name="constraint-corpus",
        purpose="规范/条款/经验语料（ADR-0006 evidence 后端）",
        public_prefix="statutory/",  # GB 国标公开条款可匿名 GET
    ),
    BucketSpec(
        name="proof-artifacts",
        purpose="审计 / 证据 PDF（proof 可视化产物）",
        public_prefix=None,
    ),
    BucketSpec(
        name="cad-files",
        purpose="CAD 原件：GLB / STEP / IGES 等",
        public_prefix=None,
    ),
    BucketSpec(
        name="mcp-contexts",
        purpose="MCP 运行快照（multi-agent context checkpoints）",
        public_prefix=None,
    ),
)


def _public_read_prefix_policy(bucket: str, prefix: str) -> dict:
    """
    生成 S3 bucket policy：对 `bucket/prefix*` 允许匿名 GetObject。

    仅 GetObject；不放 ListBucket（防止枚举）、不放写权限。
    """
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": f"AllowPublicReadOn_{prefix.rstrip('/').replace('/', '_')}",
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/{prefix}*"],
            }
        ],
    }


# ──────────────────────────────────────────────────────────────────────
# 2. 连接工厂 + 幂等操作
# ──────────────────────────────────────────────────────────────────────


def build_client(endpoint: str, access_key: str, secret_key: str, secure: bool) -> Minio:
    """创建 Minio client。不做任何远程调用。"""
    return Minio(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
    )


def ensure_bucket(client: Minio, spec: BucketSpec, dry_run: bool, log: logging.Logger) -> str:
    """
    幂等确保 bucket 存在 + policy 生效。返回 "created" / "exists" / "dry-run"。
    """
    exists = client.bucket_exists(spec.name)

    if dry_run:
        action = "would-create" if not exists else "would-verify"
        log.info("  [%s] %-22s %s", action, spec.name, spec.purpose)
        if spec.public_prefix:
            log.info("      · would attach policy: public-read on `%s*`", spec.public_prefix)
        return "dry-run"

    if not exists:
        client.make_bucket(spec.name)
        log.info("  [created]       %-22s %s", spec.name, spec.purpose)
        state = "created"
    else:
        log.info("  [exists]        %-22s %s", spec.name, spec.purpose)
        state = "exists"

    # 附加 bucket policy（若声明）—— 也幂等：get_bucket_policy 比较后再 set
    if spec.public_prefix:
        policy = _public_read_prefix_policy(spec.name, spec.public_prefix)
        policy_json = json.dumps(policy, separators=(",", ":"), sort_keys=True)

        current = None
        try:
            current_raw = client.get_bucket_policy(spec.name)
            current = json.dumps(
                json.loads(current_raw), separators=(",", ":"), sort_keys=True
            )
        except S3Error as e:
            # NoSuchBucketPolicy 是正常情况（新 bucket 无策略）
            if e.code != "NoSuchBucketPolicy":
                raise

        if current == policy_json:
            log.info("      · policy up-to-date (public-read on `%s*`)", spec.public_prefix)
        else:
            client.set_bucket_policy(spec.name, policy_json)
            log.info(
                "      · policy set: public-read on `%s*` (anonymous GetObject only)",
                spec.public_prefix,
            )

    return state


# ──────────────────────────────────────────────────────────────────────
# 3. CLI 入口
# ──────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="ADR-0007 · MinIO bucket bootstrap (idempotent).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--endpoint",
        default=os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
        help="MinIO endpoint (host:port, 不带协议).",
    )
    p.add_argument(
        "--access-key",
        default=os.environ.get("MINIO_ROOT_USER", "minioadmin"),
        help="MinIO access key.",
    )
    p.add_argument(
        "--secret-key",
        default=os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin"),
        help="MinIO secret key.",
    )
    p.add_argument(
        "--secure",
        action="store_true",
        default=os.environ.get("MINIO_SECURE", "").lower() in {"1", "true", "yes"},
        help="Use HTTPS (默认关：dev 环境 http).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印计划，不实际创建 / 改 policy.",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="DEBUG 级别日志（打印 minio SDK 细节）.",
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    log = logging.getLogger("init_minio")

    log.info("── MinIO endpoint: %s (secure=%s) ──", args.endpoint, args.secure)
    log.info("── Access key:     %s ──", args.access_key)
    log.info("── Mode:           %s ──", "DRY-RUN" if args.dry_run else "APPLY")

    client = build_client(args.endpoint, args.access_key, args.secret_key, args.secure)

    # 预检：ping 一下（list_buckets 成功即可达）
    try:
        existing = [b.name for b in client.list_buckets()]
        log.info("Connected. Existing buckets: %s", existing or "(none)")
    except Exception as e:  # noqa: BLE001
        log.error("Cannot reach MinIO at %s: %s", args.endpoint, e)
        return 1

    # 逐个 ensure
    summary: dict[str, int] = {"created": 0, "exists": 0, "dry-run": 0}
    log.info("")
    log.info("Ensuring %d buckets:", len(BUCKET_SPECS))
    try:
        for spec in BUCKET_SPECS:
            state = ensure_bucket(client, spec, args.dry_run, log)
            summary[state] = summary.get(state, 0) + 1
    except S3Error as e:
        log.error("S3 error while ensuring buckets: %s", e)
        return 1
    except Exception as e:  # noqa: BLE001
        log.error("Unexpected error: %s", e)
        return 1

    log.info("")
    log.info(
        "Summary: created=%d, already-exists=%d, dry-run=%d.",
        summary["created"],
        summary["exists"],
        summary["dry-run"],
    )

    # 收尾：再列一次最终清单
    if not args.dry_run:
        final = sorted(b.name for b in client.list_buckets())
        log.info("Final bucket list on server: %s", final)

    return 0


if __name__ == "__main__":
    sys.exit(main())
