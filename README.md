# LabelTrace

YOLO 标注与数据集平台。面向甲方以**拍摄视频**为主的交付形态：视频入库 → 抽帧 → 帧级标注 → 不可变版本与导出；并支持素材库归档、多数据集共享引用、来源回溯。

## 技术栈

| 层 | 选型 |
|----|------|
| API | FastAPI（Python） |
| 数据库 | PostgreSQL |
| 前端 | React + TypeScript + Vite；产品级 UI（自有 Design Tokens） |
| 标注画布 | Konva + react-konva（Zustand） |
| 文件 | 可插拔 BlobStore（本地 / S3 兼容） |
| 抽帧 | ffmpeg；任务队列 `JOB_BACKEND=pg` |

## 快速开始

详细步骤（环境变量、迁移、Docker、排错）见：

**→ [docs/guides/运行与部署.md](docs/guides/运行与部署.md)**

最短路径：

```bash
# 1) 数据库
docker compose up -d postgres

# 2) API（另开终端）
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\pip install -r requirements.txt
# Windows: copy .env.example .env   # 按需改 DATABASE_URL
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

# 3) 前端
cd frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`；API `http://127.0.0.1:8001/docs`。

## 主路径（视频优先）

```text
上传甲方视频 → 按策略抽帧（frame）→ 审查删帧 → 帧加入数据集
  → 在帧上标检测框 → 发版 →（YOLO 导出可后置）
```

- **video**：源文件，目录浏览主入口  
- **frame**：可标注单位（保留到源视频的血缘）  
- 不在整段视频上直接画 YOLO 框（P0）

## 核心概念

- **数据集**：引用 frame/image，不拷贝文件；标注在「数据集 × 素材」。  
- **版本**：工作区可改；已发版只读；迭代 = 追加帧/改标后发新版。  
- **标注类型**：P0 为 `rect`；架构可扩展其它类型。

## 部署拆分（Docker，P0）

| 容器 | 作用 |
|------|------|
| **web** | React 静态 + 反代 API（镜像待完善） |
| **api** | FastAPI + **PG 队列消费者**抽帧（含 ffmpeg） |
| **postgres** | 元数据与任务队列（`jobs`）；Compose 已可起 |
| **minio**（可选） | 对象存储；也可用本地 volume |

错误处理与日志规范见 design **D11**；任务说明见 `docs/jobs.md`。

## 文档

| 文档 | 说明 |
|------|------|
| [运行与部署](docs/guides/运行与部署.md) | 本地运行、环境变量、Docker |
| [数据集从上传到发版](docs/guides/数据集从上传到发版.md) | 视频主路径与迭代说明 |
| [后台任务](docs/jobs.md) | JobBackend / 日后 worker |
| [OpenSpec 变更](openspec/changes/bootstrap-labeltrace-platform/) | 需求、设计、任务 |

## 许可证

待定。
