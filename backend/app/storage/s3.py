"""S3 兼容 BlobStore（AWS S3 / MinIO 等）。"""

from collections.abc import Iterator
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from app.storage.base import BlobBody, BlobStore


class S3BlobStore(BlobStore):
    backend_id = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "us-east-1",
        client: BaseClient | None = None,
    ) -> None:
        self._bucket = bucket
        if client is not None:
            self._client = client
        else:
            kwargs: dict[str, Any] = {"region_name": region}
            if endpoint_url:
                kwargs["endpoint_url"] = endpoint_url
            if access_key and secret_key:
                kwargs["aws_access_key_id"] = access_key
                kwargs["aws_secret_access_key"] = secret_key
            self._client = boto3.client("s3", **kwargs)

    def put(self, key: str, body: BlobBody, content_type: str | None = None) -> None:
        extra: dict[str, Any] = {}
        if content_type:
            extra["ContentType"] = content_type
        if isinstance(body, (bytes, bytearray)):
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=bytes(body), **extra
            )
        else:
            self._client.upload_fileobj(
                body,
                self._bucket,
                key,
                ExtraArgs=extra or None,
            )

    def get(self, key: str) -> Iterator[bytes]:
        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        body = resp["Body"]
        while True:
            chunk = body.read(1024 * 1024)
            if not chunk:
                break
            yield chunk

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
