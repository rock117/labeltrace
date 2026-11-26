"""BlobStore 抽象：领域层只依赖本接口，不依赖本地路径或云 SDK。"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import BinaryIO, Union

BlobBody = Union[bytes, BinaryIO]


class BlobStore(ABC):
    """二进制对象存储抽象。"""

    backend_id: str

    @abstractmethod
    def put(self, key: str, body: BlobBody, content_type: str | None = None) -> None:
        """写入对象。key 为逻辑路径，禁止含用户中文展示路径。"""

    @abstractmethod
    def get(self, key: str) -> Iterator[bytes]:
        """按 key 读取，返回可迭代的字节块。"""

    @abstractmethod
    def delete(self, key: str) -> None:
        """删除对象；不存在时幂等成功。"""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """判断对象是否存在。"""
