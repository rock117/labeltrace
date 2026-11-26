# 优先用本地已有短名镜像；缺失时先跑 scripts/ensure-base-images.*
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

# apt 多镜像回退（当前 slim 可能是 trixie；单源易 Ign/超时）
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      SRC=/etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
      SRC=/etc/apt/sources.list; \
    else \
      SRC=; \
    fi; \
    if [ -n "$SRC" ]; then cp "$SRC" /tmp/apt-sources.bak; fi; \
    ok=0; \
    for host in mirrors.tuna.tsinghua.edu.cn mirrors.ustc.edu.cn mirrors.aliyun.com deb.debian.org; do \
      echo "apt via $host"; \
      if [ -n "$SRC" ]; then \
        cp /tmp/apt-sources.bak "$SRC"; \
        sed -i "s|deb.debian.org|${host}|g; s|security.debian.org|${host}|g" "$SRC"; \
      fi; \
      if apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 update \
         && DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=5 install -y --no-install-recommends ffmpeg; then \
        ok=1; \
        break; \
      fi; \
      rm -rf /var/lib/apt/lists/*; \
    done; \
    test "$ok" -eq 1; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt \
    || pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
    || pip install -r requirements.txt -i https://pypi.org/simple/

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN sed -i 's/\r$//' /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

RUN mkdir -p /data/blobs

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
