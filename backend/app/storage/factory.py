"""按配置选择 BlobStore；读时按 Asset.storage_backend 路由。"""

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.storage.base import BlobStore
from app.storage.local import LocalFsBlobStore
from app.storage.s3 import S3BlobStore


def get_default_write_backend(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    return s.blob_backend


def _build_local(settings: Settings) -> BlobStore:
    return LocalFsBlobStore(settings.blob_local_root)


def _build_s3(settings: Settings) -> BlobStore:
    return S3BlobStore(
        bucket=settings.blob_s3_bucket,
        endpoint_url=settings.blob_s3_endpoint or None,
        access_key=settings.blob_s3_access_key or None,
        secret_key=settings.blob_s3_secret_key or None,
        region=settings.blob_s3_region,
    )


_BUILDERS = {
    "local": _build_local,
    "s3": _build_s3,
}


@lru_cache
def _cached_store(backend_id: str) -> BlobStore:
    settings = get_settings()
    builder = _BUILDERS.get(backend_id)
    if builder is None:
        raise ValueError(f"未知 BlobStore 后端: {backend_id}")
    return builder(settings)


def get_blob_store(backend_id: str | None = None) -> BlobStore:
    """获取 BlobStore。未指定时使用默认写入后端。"""
    settings = get_settings()
    bid = backend_id or settings.blob_backend
    return _cached_store(bid)


def clear_blob_store_cache() -> None:
    _cached_store.cache_clear()
