"""S3BlobStore 集成测试（moto 模拟 S3，行为与 local 一致）。"""

import boto3
from moto import mock_aws

from app.storage.s3 import S3BlobStore


@mock_aws
def test_s3_put_get_exists_delete() -> None:
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="labeltrace-test")
    store = S3BlobStore(bucket="labeltrace-test", client=client)

    key = "proj/abc/assets/cafebabe.png"
    payload = b"png-bytes"

    assert store.exists(key) is False
    store.put(key, payload, content_type="image/png")
    assert store.exists(key) is True
    assert b"".join(store.get(key)) == payload

    store.delete(key)
    assert store.exists(key) is False
