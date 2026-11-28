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

## 快速开始（两种方式都保留）

**A. Docker 全套** — 服务器部署 / 演示

```bash
powershell -File scripts/ensure-base-images.ps1   # Windows；Linux/macOS 用 .sh
docker compose up -d --build
```

- Web：http://127.0.0.1:38471 · API：http://127.0.0.1:8001/docs  

**B. 宿主机热重载** — 日常改代码（PG 仍用 Docker）

```bash
powershell -File scripts/dev-db.ps1
powershell -File scripts/dev-api.ps1   # 另开终端
powershell -File scripts/dev-web.ps1   # 另开终端
```

- UI：http://127.0.0.1:5173  

详细说明：**→ [docs/guides/运行与部署.md](docs/guides/运行与部署.md)**

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

## 部署拆分（Docker Compose，P0）

| 容器 | 作用 |
|------|------|
| **web** | React 静态 + nginx 反代 `/api`（`127.0.0.1:38471`） |
| **api** | FastAPI + **PG 队列消费者**抽帧（含 ffmpeg，`:8001`） |
| **postgres** | 元数据与任务队列（`jobs`） |
| **blobs** volume | 本地对象存储挂载 |

错误处理与日志规范见 design **D11**；任务说明见 `docs/jobs.md`。

## 文档

| 文档 | 说明 |
|------|------|
| [运行与部署](docs/guides/运行与部署.md) | 本地运行、环境变量、Docker |
| [数据集从上传到发版](docs/guides/数据集从上传到发版.md) | 视频主路径与迭代说明 |
| [与主流标注平台的差异与待补功能](docs/与主流标注平台的差异与待补功能.md) | 相对 Roboflow/CVAT 等差异与可能需要的功能 |
| [后台任务](docs/jobs.md) | JobBackend / 日后 worker |
| [OpenSpec 变更](openspec/changes/bootstrap-labeltrace-platform/) | 需求、设计、任务 |

## 许可证

待定。
