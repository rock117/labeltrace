# LabelTrace

YOLO 标注与数据集平台。面向甲方以**拍摄视频**为主的交付形态：视频入库 → 抽帧 → 帧级标注 → 不可变版本与导出；并支持素材库归档、多数据集共享引用、来源回溯，以及导入已有 YOLO 图片包。

## 技术栈

| 层 | 选型 |
|----|------|
| API | FastAPI（Python） |
| 数据库 | PostgreSQL |
| 前端 | React + TypeScript + Vite；**产品级 UI**（自有 Design Tokens，非简陋后台模板） |
| 标注画布 | Konva + react-konva（Zustand） |
| 文件 | 可插拔 BlobStore（本地 / S3 兼容） |
| 抽帧 | ffmpeg（或等价） |

## 当前状态

规划阶段。需求与设计在 OpenSpec；业务代码尚未落地。

- 规划：[`openspec/changes/bootstrap-labeltrace-platform/`](openspec/changes/bootstrap-labeltrace-platform/)
- 操作说明：[`docs/guides/数据集从上传到发版.md`](docs/guides/数据集从上传到发版.md)

## 主路径（视频优先）

```text
上传甲方视频 → 按策略抽帧（frame）→ 帧加入数据集
  → 在帧上标检测框 → 发版 → 导出 YOLO（帧图 + labels）
```

- **video**：源文件，目录浏览主入口  
- **frame**：可标注单位（保留到源视频的血缘）  
- 不在整段视频上直接画 YOLO 框（P0）

## 核心概念

- **数据集**：引用 frame/image，不拷贝文件；标注在「数据集 × 素材」。  
- **版本**：工作区可改；已发版只读；迭代 = 追加帧/改标后发新版。  
- **标注类型**：产品必做多种；P0 先做 `rect`，架构可扩展。

## 部署拆分（Docker，规划）

**P0（暂不拆独立 worker、不用 Redis；`JOB_BACKEND=pg`）：**

| 容器 | 作用 |
|------|------|
| **web** | React 静态 + 反代 API |
| **api** | FastAPI + **PG 队列消费者**抽帧/导出（含 ffmpeg） |
| **postgres** | 元数据与任务队列（`jobs`） |
| **minio**（可选） | 对象存储；也可用 volume |

错误处理与日志规范见 design **D11**；任务说明见 `docs/jobs.md`。

## 本地开发

实现后补充 `docker compose up` 与开发热重载方式。当前可：

```bash
openspec status --change bootstrap-labeltrace-platform
openspec validate bootstrap-labeltrace-platform
```

## 文档

| 文档 | 说明 |
|------|------|
| [数据集从上传到发版](docs/guides/数据集从上传到发版.md) | 视频主路径与迭代说明 |
| [proposal](openspec/changes/bootstrap-labeltrace-platform/proposal.md) | 范围 |
| [design](openspec/changes/bootstrap-labeltrace-platform/design.md) | 架构（含视频优先 D2.1） |

## 许可证

待定。
