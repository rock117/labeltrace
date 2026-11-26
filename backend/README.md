# LabelTrace API

FastAPI 后端。完整本地 / Docker 说明见仓库文档：

**[docs/guides/运行与部署.md](../docs/guides/运行与部署.md)**

## 开发启动

```bash
# 依赖与 .env
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt   # Windows
copy .env.example .env                            # 按需改 DATABASE_URL

.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

- 健康检查：`GET http://127.0.0.1:8001/health`
- OpenAPI：`http://127.0.0.1:8001/docs`
- 默认端口 **8001**（避开本机常见 8000 占用）；前端 Vite 已代理到该端口。

抽帧需要本机 `ffmpeg` / `ffprobe` 在 `PATH` 中。API 启动时会挂载 PG 任务消费者（`JOB_BACKEND=pg`）。
