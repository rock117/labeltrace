# 优先用本地已有短名镜像；缺失时先跑 scripts/ensure-base-images.*
FROM node:22-bookworm-slim AS build

WORKDIR /app
COPY package.json package-lock.json ./

# 国内 npm 源 + 重试；失败则依次换源
RUN npm config set fetch-retries 5 \
    && npm config set fetch-retry-mintimeout 20000 \
    && npm config set fetch-retry-maxtimeout 120000 \
    && npm config set fetch-timeout 300000 \
    && ok=0; \
    for reg in \
      https://registry.npmmirror.com \
      https://mirrors.cloud.tencent.com/npm/ \
      https://registry.npmjs.org; do \
      echo "npm ci via $reg"; \
      if npm ci --registry="$reg"; then ok=1; break; fi; \
      echo "npm ci failed on $reg, trying next..."; \
    done; \
    test "$ok" -eq 1

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
