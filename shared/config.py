"""ProLine CAD — 配置管理。

从环境变量读取配置，支持 .env 文件和 Docker 环境变量注入。
"""

from __future__ import annotations

import os


class Settings:
    """应用配置 — 从环境变量读取，提供默认值。"""

    # ── 数据库 ──
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "proline_cad")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "proline")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "proline_dev")

    # ── GraphDB ──
    GRAPHDB_URL: str = os.getenv("GRAPHDB_URL", "http://localhost:9999/blazegraph")

    # ── 对象存储 (MinIO/S3) ──
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "proline-audit")

    # ── 消息队列 (Kafka) ──
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

    # ── 向量数据库 (Milvus) ──
    MILVUS_HOST: str = os.getenv("MILVUS_HOST", "localhost")
    MILVUS_PORT: int = int(os.getenv("MILVUS_PORT", "19530"))

    # ── Agent 服务端口 ──
    PARSE_AGENT_PORT: int = int(os.getenv("PARSE_AGENT_PORT", "5001"))
    CONSTRAINT_AGENT_PORT: int = int(os.getenv("CONSTRAINT_AGENT_PORT", "5002"))
    LAYOUT_AGENT_PORT: int = int(os.getenv("LAYOUT_AGENT_PORT", "5003"))
    ORCHESTRATOR_PORT: int = int(os.getenv("ORCHESTRATOR_PORT", "5000"))

    # ── LLM ──
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")

    @property
    def postgres_dsn(self) -> str:
        """PostgreSQL 连接字符串。"""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
