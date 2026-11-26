"""本地文件系统 BlobStore：根目录 + 逻辑 key。"""

from collections.abc import Iterator
from pathlib import Path

from app.storage.base import BlobBody, BlobStore


class LocalFsBlobStore(BlobStore):
    backend_id = "local"

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        # 禁止路径穿越：规范化后必须仍在 root 下
        safe = key.replace("\\", "/").lstrip("/")
        if ".." in safe.split("/"):
            raise ValueError(f"非法 storage key: {key}")
        path = (self._root / safe).resolve()
        if not str(path).startswith(str(self._root)):
            raise ValueError(f"非法 storage key: {key}")
        return path

    def put(self, key: str, body: BlobBody, content_type: str | None = None) -> None:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, (bytes, bytearray)):
            path.write_bytes(body)
        else:
            with path.open("wb") as f:
                while True:
                    chunk = body.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)

    def get(self, key: str) -> Iterator[bytes]:
        path = self._path_for(key)
        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    def delete(self, key: str) -> None:
        path = self._path_for(key)
        if path.is_file():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._path_for(key).is_file()
