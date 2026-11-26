"""默认写入后端与按 storage_backend 读路由。"""

from pathlib import Path

import boto3
from moto import mock_aws

from app.storage.local import LocalFsBlobStore
from app.storage.s3 import S3BlobStore


def test_switch_default_write_keeps_old_readable(tmp_path: Path) -> None:
    """旧文件记在 local；切换默认写入到 s3 后仍可按 backend 读回。"""
    local = LocalFsBlobStore(tmp_path / "local")
    key = "proj/x/assets/hash1.jpg"
    local.put(key, b"old-local-bytes")

    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="labeltrace")
        s3 = S3BlobStore(bucket="labeltrace", client=client)
        s3.put(key, b"new-s3-bytes")

        # 读路由：按记录的 storage_backend 选实现
        backends = {"local": local, "s3": s3}
        assert b"".join(backends["local"].get(key)) == b"old-local-bytes"
        assert b"".join(backends["s3"].get(key)) == b"new-s3-bytes"
