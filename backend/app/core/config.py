"""应用配置。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LabelTrace API"
    database_url: str = (
        "postgresql+psycopg2://postgres@127.0.0.1:5432/labeltrace"
    )
    blob_backend: str = "local"
    blob_local_root: str = "./data/blobs"
    blob_s3_bucket: str = "labeltrace"
    blob_s3_endpoint: str = ""
    blob_s3_access_key: str = ""
    blob_s3_secret_key: str = ""
    blob_s3_region: str = "us-east-1"
    job_backend: str = "pg"
    job_poll_interval_sec: float = 0.5
    job_lease_sec: int = 300
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
