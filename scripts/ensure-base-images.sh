#!/usr/bin/env bash
# Prefer local base images; if missing, pull via China mirrors and retag to short names.
# Usage: bash scripts/ensure-base-images.sh
# Optional: DOCKER_MIRRORS=m.daocloud.io/docker.io/library,dockerproxy.net/library

set -euo pipefail

if [[ -n "${DOCKER_MIRRORS:-}" ]]; then
  IFS=',' read -r -a MIRRORS <<< "$DOCKER_MIRRORS"
elif [[ -n "${DOCKER_MIRROR:-}" ]]; then
  MIRRORS=("$DOCKER_MIRROR")
else
  MIRRORS=(
    "m.daocloud.io/docker.io/library"
    "docker.m.daocloud.io/library"
    "dockerproxy.net/library"
    "docker.1ms.run/library"
    "hub.rat.dev/library"
    "docker.xuanyuan.me/library"
  )
fi

IMAGES=(
  "python:3.12-slim"
  "postgres:16-alpine"
  "node:22-bookworm-slim"
  "nginx:1.27-alpine"
)

has_local() {
  docker image inspect "$1" >/dev/null 2>&1
}

echo "Docker mirrors: ${MIRRORS[*]}"
for img in "${IMAGES[@]}"; do
  if has_local "$img"; then
    echo "[local] $img"
    continue
  fi

  ok=0
  for mirror in "${MIRRORS[@]}"; do
    mirror="${mirror%/}"
    remote="${mirror}/${img}"
    echo "[pull ] ${remote} -> ${img}"
    if docker pull "$remote"; then
      docker tag "$remote" "$img"
      echo "[tag  ] ${remote} -> ${img}"
      ok=1
      break
    fi
  done

  if [[ "$ok" -eq 0 ]]; then
    echo "[retry] docker.io/${img}"
    docker pull "$img"
  fi
done

echo "Base images ready."
