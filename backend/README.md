# LabelTrace API

FastAPI 后端。开发启动（默认避开本机占用的 8000）：

```bash
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

健康检查：`GET http://127.0.0.1:8001/health`
