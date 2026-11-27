# Design

## Context

- 新仓库，无存量实现。需求与行为契约见同 change 下各 `specs/*/spec.md`；动机见 `proposal.md`。
- **业务现实：甲方素材以拍摄视频为主、基本无现成图片** → 主路径为视频入库 + 抽帧；标注/版本/YOLO 导出仍面向 **frame（图）**。
- 已拍板：目录素材库、扁平标签、多数据集共享引用、标注按数据集隔离、不可变版本、可导入 YOLO 图片包、导入隐藏、引用禁硬删、可插拔 BlobStore、标注类型可扩展。
- **技术栈已锁定：FastAPI + PostgreSQL + React**；标注画布 **Konva + react-konva**；抽帧依赖 **ffmpeg**（或等价）。
- 使用者操作说明：`docs/guides/数据集从上传到发版.md`。

## Goals / Non-Goals

**Goals:**

- 给出分层架构、领域实体与持久化（元数据 vs 可插拔二进制存储）。
- 给出 P0 HTTP 接口契约（含导入与删除保护）。
- 明确「无采集源」数据集与素材库可见性如何共存。
- 明确 BlobStore 抽象与至少两种后端实现的配置方式。
- 按已锁定栈指导实现拆分（FastAPI / PG / React）。

**Non-Goals:**

- 不定稿具体 ORM 细枝末节；**UI 须达产品级**（见 D10），组件库可作底座但禁止默认「未换肤后台模板」交差。
- 不做标签分组、组织树、SSO、在线训练的详细设计。
- P0 不做「将导入素材提升进素材库目录」的完整产品流（可预留字段）。
- P0 不要求同一项目内任意混合多后端热迁移工具（可记录 `storage_backend` 以便日后迁移）。

## Decisions

### D1. 总体架构与技术栈

**已锁定技术栈：**

| 层 | 选型 |
|----|------|
| API | **FastAPI**（Python） |
| 元数据 | **PostgreSQL** |
| 前端 | **React + TypeScript + Vite** |
| 标注画布 | **Konva + react-konva** |
| 标注台状态 | **Zustand**（当前图、boxes、选中、撤销等） |
| 二进制 | BlobStore：`local` / `s3`（与栈独立） |

配套建议：API 侧常用 SQLAlchemy/Alembic 或等价迁移；前端 UI 底座可选用 Radix / 轻量头less + **自有设计令牌**（见 D10），标注画布仍为 Konva。

**产品必做标注类型（实现分期，架构一次预留）：**

| 优先级 | 类型 | `shapes[].type` | 说明 |
|--------|------|-----------------|------|
| **P0** | 检测框 | `rect` | YOLO detect；导入/导出 detect 包 |
| P1+ | 分割多边形 | `polygon` | 实例轮廓 |
| P1+ | 实例/语义 mask | `mask` | 刷子/位图；二进制可走 BlobStore |
| P1+ | 关键点 / pose | `keypoint` / `pose` | 点与骨架；pose 可含 skeleton 元数据 |
| P1+ | 旋转框 OBB | `obb` | 带角度 |
| P1+ | 整图分类 | `classification` | 可放 `items` 或 annotation 文档级字段 |

不在当前产品必做：polyline、椭圆、3D、视频 track、框属性等（日后另开需求）。

**标注台（P0）画布能力：** 矩形检测框、拖拽/锚点缩放、滚轮缩放与平移、类别快捷键、上一张/下一张、本地撤销；坐标与 API 的 `shapes`/`format` 对齐后提交。

#### D1.1 标注类型扩展架构（领域一次建模）

目标：**P0 只实现 `rect` 工具与校验**，但领域/API/存储/前端注册表按多类型设计，后续加类型以「注册新 Handler」为主，避免改核心表结构。

```text
                    ┌─ AnnotationTypeRegistry（后端）
Dataset.enabled_types ──┤     type → schema 校验 / 导入 / 导出
                    └─ AnnotationToolRegistry（前端）
                          type → Konva 工具 / 渲染器

Annotation.shapes = { format, items: [ { type, cls?, ...typeSpecific } ] }
DatasetVersion.manifest 原样冻结 shapes（含 type）
```

| 扩展点 | 约定 |
|--------|------|
| **类型判别** | 每条 shape 必有 `type`；整图分类可用 `type=classification` 或文档级 `classification` 字段（二选一，实现时固定并写进 API） |
| **数据集启用集** | `Dataset.enabled_annotation_types: string[]`，P0 默认 `["rect"]`；保存标注时只允许启用集内类型 |
| **校验** | 按 type 分派 validator（P0 仅注册 `rect`）；未知/未启用 → 422 |
| **导入/导出** | 按 type（或数据集任务剖面）选 codec（P0：YOLO detect txt）；新类型加 codec，不改 Asset/Version 主流程 |
| **版本快照** | 不解析业务语义，整份 JSON 冻结；旧版含新 type 的数据仍可只读导出（若 codec 已注册） |
| **前端工具** | 工具栏只渲染 `enabled_annotation_types ∩ 已实现工具`；未实现类型不展示，避免半成品入口 |
| **mask 二进制** | 若 mask 过大不宜进 JSONB，用 `storage_backend`+`storage_key` 挂附件，shape 内只存引用——表结构预留，P0 不实现 |

**禁止：** 为每种标注类型复制一套 `AnnotationXxx` 表或按类型拆数据集主键；禁止用无 type 的裸 bbox 数组作为长期契约（P0 起即带 `type`）。

```text
React + Vite
  ├── 素材库 / 数据集 / 导入页
  └── 标注台（react-konva + Zustand）
        │ HTTPS JSON
        ▼
FastAPI（鉴权、领域用例）
   ├── PostgreSQL（元数据、标注、版本快照、导入记录）
   └── BlobStore 抽象
         ├── LocalFsBlobStore（本地目录）
         ├── S3BlobStore（S3 / MinIO 等兼容实现）
         └── （可扩展其它后端）
```

- 开发环境二进制默认 `local`，生产可切 `s3`。  
- 选型依据：P0 仅 YOLO detect；Konva 与 Label Studio 等同技术路线，足够支撑框标注，并便于后续多边形/关键点/OBB；mask 与 CVAT 级能力另阶段评估。

### D2. 领域实体（逻辑模型）

| 实体 | 职责 |
|------|------|
| Project | 租户边界 |
| Membership | 角色集合：`owner` / `annotator` / `viewer`（一人一项目一条记录，可多角色；跨项目独立） |
| Folder | 项目内目录树（面向库可见素材） |
| Asset | 媒体素材；`media_kind`：`image` \| `video` \| `frame`；存储与可见性字段同前；frame 另含 `parent_video_id`、`frame_index` |
| Tag / AssetTag | 扁平标签 |
| Dataset | 数据集；工作区类别；**`enabled_annotation_types`** |
| DatasetClass | 有序类别名（检测/分割等共用 names；pose kpt 名可另挂元数据） |
| DatasetAsset | 引用 + `split` |
| Annotation | `(dataset_id, asset_id)`；`shapes` 为带 `type` 的异构列表 |
| DatasetVersion | 不可变快照（含当时 `enabled_annotation_types` + shapes） |
| DatasetImport | 导入记录；P0 绑定 detect codec，日后按类型扩展 |
| FrameExtractJob | 一次抽帧任务及设置（mode/stride 等）；产出若干 frame |

**不变式：**

1. Folder / Asset / Tag / Dataset / DatasetImport 均属同一 Project。  
2. Annotation 的 asset 必须已在 DatasetAsset 中。  
3. DatasetVersion 发布后只读。  
4. `library_visible = true` 的 Asset 必须有且仅有一个 `folder_id`。  
5. `library_visible = false` 的 Asset 可以 `folder_id` 为空（典型：导入产生）。  
6. 存在 DatasetAsset 或任一 Version manifest 引用时，禁止硬删 Asset 与其对象文件。  
7. Annotation 中每条 shape 的 `type` 必须属于该 Dataset 的 `enabled_annotation_types`，且服务端已注册该 type 的校验器。  
8. 可标注并作为 Dataset 成员的 P0 单位为 `image` 或 `frame`；`video` 不直接作为检测框标注对象。  
9. `frame` 必须有 `parent_video_id`；删除策略上删视频前须处理其子帧引用（P0 可禁止删仍有入集/版本引用的视频及其帧）。

### D2.1 视频优先：领域与主路径

```text
甲方视频
  → 上传 Asset(media_kind=video)
  → 抽帧任务（步长 / 时间间隔可配）
  → 候选 frame × N（挂在该 ExtractJob 下）
  → 【人工审查】浏览 / 多选删除大量无用帧（模糊、重复、无目标…）
  → 将保留的 frame 加入 Dataset
  → 标注 → 发版 → 导出 YOLO
```

审查是主路径上的一环：抽帧只是「候选集」，不是自动全部入集。

| 决策 | 选择 | 说明 |
|------|------|------|
| 标注对象 | **frame / image** | 不在整段 video 上画 YOLO 框 |
| 抽帧 | P0 **物化落盘**为 frame Asset | 复用现有标注/版本/导出；占空间换简单 |
| **抽帧设置** | 每次抽帧任务记录策略（见下） | 必有；同一视频可多次不同设置抽帧 |
| 库浏览 | 目录以 **video** 为主入口；frame 挂在视频详情 / 某次抽帧任务下 | 避免海量帧刷屏 |
| **抽帧后审查** | P0 **必做**：在入集前淘汰无用帧 | 见下「候选帧审查」 |
| 入集 | 「某次抽帧任务中**仍保留**的帧 → 批量/勾选加入」 | 默认不要「未审查全量入集」 |
| **数据集体现设置** | 工作区 / 版本汇总抽帧任务及参数 | 见成员来源摘要 |
| 时间轴 UI | **非 P0** | 审查用缩略图网格 + 多选即可 |
| track_id | **非 P0** | 属标注扩展 |

**候选帧审查（P0）：**

| 点 | 约定 |
|----|------|
| 时机 | 抽帧完成 → **审查** → 再入集（可部分先入集，但产品引导先审） |
| **排序** | **按出现时间升序**（`frame_index` 或等价时间戳）；默认且审查页主列表必须如此，便于沿时间线删连续无用段 |
| 展示 | 缩略图旁显示时间位置（如 `frame_index` 或 `mm:ss.ms`） |
| 操作 | 按 ExtractJob 浏览；单删 / 多选删除；支持框选一段时间范围删除（P0 可用多选模拟；范围删可增强） |
| 删除语义 | **硬删未入集且未进任何版本的 frame**（及 Blob）；已入集则须先移出数据集或走引用保护（409） |
| 统计 | 任务上记录 `extracted_count` / `kept_count` / `discarded_count` |
| 与再次抽帧 | 仍可换参数再开新 ExtractJob |

**抽帧设置（FrameExtractJob）：**

| 字段 | 说明 |
|------|------|
| `mode` | `stride_frames`（每隔 N 帧）或 `interval_ms`（每隔 T 毫秒） |
| `stride` / `interval_ms` | 对应参数 |
| `video_id` | 源视频 |
| `status` / `stats` | 完成帧数等 |
| 可选 | 起止时间范围、最大帧数、分辨率缩放 |

同一视频可先「每 5 帧」抽一版，再「每 1 秒」抽一版 → **两次任务、两套 frame**（`frame_index` 仍对应该视频时间轴位置；用 `extract_job_id` 区分批次）。

**数据集成员可混合来源（P0 即支持）：**

| 成员 media_kind | 典型 origin | 怎么进集 |
|-----------------|-------------|----------|
| `frame` | `extract` | 某次抽帧任务批量加入 |
| `image` | `upload` | 素材库上传后挑选加入 |
| `image` | `import` | YOLO 包导入带入 |

同一数据集可以同时包含「抽帧 + 上传图 + 导入图」。

**数据集如何记录 / 展示数据来源：**

1. **逐成员（权威）** — 不另造平行来源表；看 Asset：  
   - `media_kind`、`origin`  
   - frame：`parent_video_id`、`frame_index`、`extract_job_id` → 抽帧设置  
   - upload：`folder_id`、`filename` / `source_path`  
   - import：`import_id`  

2. **数据集级摘要（展示用，可聚合）** — `GET /datasets/{id}` 返回例如：

```text
memberSources: [
  { kind: "extract", videoId, videoName, extractJobId, mode, stride, frameCount: 120 },
  { kind: "upload",  imageCount: 30 },           // 可再按目录细分
  { kind: "import",  importId, packageName, imageCount: 50 }
]
```

3. **发版快照** — 写入 `member_sources`（或等价）；逐成员保留 `asset_id` + `content_hash`，frame 时 MUST 带上 `parent_video_id`、`frame_index`（原视频第几帧）、`extract_job_id`，保证可回答「这张训练图对应原片哪一帧」。

**帧号含义：** `frame_index` = 相对**源视频时间轴**的帧序号（从 0 或 1 起在实现期固定并全站统一），不是「本抽帧任务里的第几张候选」。抽帧步长只影响抽哪些帧，不改变入选帧的 `frame_index`。

- 一个集**不限制**只能一种来源。  
- 界面应能看出混合构成，而不仅是抽帧摘要。

**存储 key 示例：**

```text
proj/{pid}/assets/videos/{hash}.mp4
proj/{pid}/assets/frames/{video_id}/job_{extract_job_id}/{frame_index}.jpg
```

### D3. 存储分工与可插拔 BlobStore

| 存什么 | 存哪 |
|--------|------|
| 实体关系、标注、版本快照、导入记录 | PostgreSQL |
| 原图、缩略图、导出 zip | **BlobStore**（实现可变） |

**逻辑 object key（与后端无关）：**

```text
proj/{project_id}/assets/{content_hash}{ext}
proj/{project_id}/thumbs/{asset_id}.jpg
proj/{project_id}/exports/{version_id}.zip
```

**抽象接口（概念）：**

```text
BlobStore
  put(key, bytes|stream, content_type) -> void
  get(key) -> stream
  delete(key) -> void
  exists(key) -> bool
  # 可选：presign_get / presign_put（对象存储直传）
```

| 后端 ID | 说明 | 典型配置 |
|---------|------|----------|
| `local` | 根目录下按 key 落文件 | `BLOB_BACKEND=local`, `BLOB_LOCAL_ROOT=./data` |
| `s3` | S3 API（AWS S3、MinIO、OSS 兼容模式等） | `BLOB_BACKEND=s3`, endpoint/bucket/ak/sk/region |

- 领域层只依赖 `BlobStore` + DB 中的 `storage_backend` + `storage_key`。  
- **P0**：进程级默认一个「写入后端」；读时按 Asset 上记录的 `storage_backend` 选择实现（便于日后换后端而不丢旧文件）。  
- 缩略图、导出包与原图走同一套抽象。  
- 版本快照仍**不复制**原图，靠 hash + BlobStore 取文件；引用禁止硬删仍成立。

### D3.1 展示路径 vs 存储定位（中文 / 空格 / 多层）

**原则：用户可见路径 ≠ BlobStore 路径。** 网页上的目录名、文件名可以含中文、空格与任意深度；二进制定位只使用 `storage_backend` + 基于 `content_hash` 的 `storage_key`。

| 用途 | 字段 / 接口 | 约定 |
|------|-------------|------|
| 多层目录（可中文、空格） | `folders.name`、`folders.path`（冗余面包屑） | UTF-8 文本；同级 `name` 唯一；深度由树表达，不拼进 storage_key |
| 展示用文件名 | `assets.filename` | 保留上传/导入时的原始文件名（可含中文、空格） |
| 可选追溯相对路径 | `assets.source_path` | 如导入包内 `train/产线 A/图 1.jpg`；仅血缘/展示，**不当**存储路径 |
| 二进制定位 | `storage_backend` + `storage_key` | key 形如 `proj/{id}/assets/{hash}{ext}`，**禁止**把用户路径、中文、空格写入 key |
| 网页读图 / 下载 | `GET /assets/{assetId}/content` | URL 使用 UUID，不拼接用户目录路径 |

**示例：**

```text
用户看到的路径：  缺陷样本 / 产线 A / 夜班采样 / 图 1.jpg
folders:          name=缺陷样本 → 产线 A → 夜班采样（Unicode，允许空格）
assets.filename:  图 1.jpg
assets.source_path: （可选）缺陷样本/产线 A/夜班采样/图 1.jpg
storage_backend:  local
storage_key:      proj/3f2c…/assets/a1b2c3d4e5….jpg
读图 URL:         /api/v1/assets/550e8400-e29b-41d4-a716-446655440000/content
```

**下载文件名：** 需要「另存为」原始名时，响应使用  
`Content-Disposition`，并对 `filename` 做 RFC 5987（`filename*=UTF-8''…`）编码，避免中文/空格在下载头中损坏。

**禁止：**

- 使用 `/files/缺陷样本/产线 A/图 1.jpg` 这类用户路径作为内容 URL 或 storage_key。  
- 在 `local` 后端把 `BLOB_LOCAL_ROOT` 下的相对路径建成与用户中文目录镜像（除非运维另有备份策略；产品默认不这么做）。

**导入：** 包内相对路径写入 `source_path` / `filename`；像素仍按 hash 入库；P0 默认不按包内中文目录自动生成库可见 Folder 树。

### D4. 表级字段草案

```text
projects(id, name, created_at, ...)
memberships(project_id, user_id, roles[])

folders(id, project_id, parent_id null, name, path, ...)

assets(
  id, project_id,
  media_kind,                  -- image | video | frame
  parent_video_id null,        -- frame 必填
  frame_index null,            -- frame 必填
  extract_job_id null,         -- frame 必填：对应哪次抽帧设置
  duration_ms null, fps null,  -- video 元数据
  folder_id null,
  library_visible bool,
  origin text,                 -- upload | import | extract
  import_id null,
  content_hash,                -- video/image 内容哈希；frame 可为帧图哈希
  storage_backend, storage_key,
  filename, source_path null,
  width, height, mime, created_at, ...
)
  UNIQUE(project_id, content_hash)  -- frame 若策略为「同视频同帧不重复」可另加 UNIQUE(parent_video_id, frame_index)

tags(id, project_id, name, group_id null)
asset_tags(asset_id, tag_id)

datasets(
  id, project_id, name,
  enabled_annotation_types jsonb,  -- 如 ["rect"]；产品必做全集见 D1
  ...
)
dataset_classes(dataset_id, idx, name)
dataset_assets(dataset_id, asset_id, split)
annotations(dataset_id, asset_id, shapes jsonb, status, updated_by, updated_at, ...)

dataset_versions(id, dataset_id, name, parent_id null, classes jsonb, manifest jsonb, ...)

dataset_imports(
  id, project_id, dataset_id,
  package_name, status, stats jsonb, error_message null,
  created_by, created_at, ...
)

frame_extract_jobs(
  id, project_id, video_asset_id,
  mode,                        -- stride_frames | interval_ms
  stride null,                 -- 每隔 N 帧
  interval_ms null,            -- 每隔 T ms
  options jsonb,               -- 起止、max_frames 等
  status,                      -- pending|running|succeeded|failed
  stats jsonb,                 -- extracted_count, kept_count, discarded_count
  created_by, created_at, ...
)
```

数据集详情聚合 `memberSources`（抽帧任务 / 上传图统计 / 导入任务）。发版写入快照字段 `member_sources`。逐成员来源仍以 Asset 字段为准。

**Annotation.shapes / Version.manifest：**

```json
{
  "format": "xyxy_abs",
  "items": [
    { "type": "rect", "cls": 0, "bbox": [10, 20, 110, 220] }
  ]
}
```

发版时冻结：`classes`、`enabled_annotation_types`、每条成员的 `shapes`。扩展新类型时只增加 item 形态与 Registry 实现，不改 Version 主表。

### D5. 导入流程（YOLO 包）

约定包内至少能解析：`data.yaml`（或等价 names）、按 split 的 images 与 labels（或可推断的平面结构）。**P0 仅 detect 框格式**；seg/pose/obb 包格式随对应类型阶段再定。

```text
上传 zip
  → 校验结构
  → 创建 DatasetImport(pending)
  → 解析 names → 写入/覆盖工作区 classes（策略：新建数据集则写入；已有集则按 API 约定合并或拒绝）
  → 对每张图：hash → 复用或新建 Asset(origin=import, library_visible=false, folder_id=null, import_id=...)
  → DatasetAsset + Annotation（由 txt 转内部 shapes）+ split
  → Import succeeded + stats
```

P0 默认：**导入到新建数据集**（实现简单）；导入到已有空数据集可作为同 API 的可选模式。

去重：若复用到已是 `library_visible=true` 的素材，仍只加 DatasetAsset/Annotation，不改其可见性（避免把库内图藏起来）。

### D6. HTTP 接口契约（P0）

约定：Base `/api/v1`；`401/403/404/409/422`；UUID；ISO-8601 UTC。

#### 项目 / 目录与素材 / 标签 / 数据集 / 标注 / 版本

（路径同前一版；素材相关增量如下。）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/folders/{folderId}/assets` | **仅** `library_visible=true`；`tagIds` 可选交集 |
| POST | `/folders/{folderId}/assets` | 上传；新 asset：`origin=upload`, `library_visible=true` |
| DELETE | `/assets/{assetId}` | 硬删；若被数据集或版本引用 → **409** |
| GET | `/assets/{assetId}` | 含 `libraryVisible`, `origin`, `folderId` |
| GET | `/assets/{assetId}/content` | 按 assetId 读字节（含非库可见）；下载时用 `Content-Disposition` + RFC 5987 带上 `filename` |

#### 数据集 / 标注 / 版本（增量要点）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/projects/{projectId}/datasets` | `{ name, classes, enabledAnnotationTypes?: ["rect"] }` |
| GET | `/datasets/{datasetId}` | 含 `classes`、`enabledAnnotationTypes` |
| PATCH | `/datasets/{datasetId}` | 可改启用类型（需校验策略） |
| GET/POST/DELETE/PATCH | `/datasets/{datasetId}/assets...` | 成员与 split（同前） |
| PUT | `/datasets/{datasetId}/assets/{assetId}/annotation` | shapes 每项必含 `type`；按启用类型 + Registry 校验 |
| POST | `/datasets/{datasetId}/versions` | 快照含 `enabled_annotation_types` |

#### 数据集导入

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/projects/{projectId}/dataset-imports` | multipart：YOLO zip + `{ "datasetName" }` 或 `datasetId` |
| GET | `/dataset-imports/{importId}` | 状态与 stats |
| GET | `/datasets/{datasetId}/imports` | 该数据集相关导入记录 |

成功响应示例字段：`{ importId, datasetId, status, stats: { images, reused, created } }`。

#### 回溯

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/assets/{assetId}/lineage` | `{ origin, importId?, path?, tags, datasets[], versions[] }` |
| GET | `/versions/{versionId}/manifest` | 快照条目 |
| POST | `/versions/{versionId}/apply-to-workspace` | 合并快照到所属数据集工作区（同 asset 覆盖标注→draft；缺则入集；多余成员保留） |

#### 版本与导出

同前：发版写快照；导出只读快照 + 按 hash 取对象。因禁止硬删被引用素材，导出不依赖「素材还在不在库里展示」。

### D7. YOLO 导出映射

- `labels/*.txt`：`cls cx cy w h` 归一化。  
- `data.yaml`：names 来自版本 `classes`。  
- 无标注成员：空 label 或跳过（实现固定一种）。

### D8. 鉴权与角色（P0 摘要）

**账号层**：`users`（username + password_hash）；`POST /auth/register|login` 发 JWT；前端 Bearer。注册 ≠ 进项目。

**项目角色**（membership.roles 集合，权限取并集）：

| 角色 | 允许 |
|------|------|
| owner（负责人） | 全权限含管成员、导入、发版、硬删（仍受引用保护）；**创建项目者自动获得** |
| annotator（标注员） | 标注；读成员与内容；可抽帧/入集；不可发版、不可管成员；导入默认仅 owner |
| viewer（只读） | 只读 |

赋角色方式：项目负责人在成员面板用对方**已注册用户名**邀请并勾选角色。一人可跨多项目；同一项目可多角色。

### D9. Docker 部署与后台任务扩展

#### P0 部署（api 与 worker 暂不拆容器）

```text
┌─────────────┐     ┌──────────────────────────────┐
│  web        │────▶│  api（单容器）                 │
│  nginx+React│     │  FastAPI + PG 队列消费者       │
└─────────────┘     │  （含 ffmpeg，抽帧/导出）      │
                    └───────────┬──────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
        ┌──────────┐    blob volume / MinIO   （无 Redis）
        │ postgres │←── jobs 表即队列（SKIP LOCKED）
        └──────────┘
```

| 服务 | 职责 |
|------|------|
| **web** | React 静态 + 反代 `/api` |
| **api** | FastAPI + 迁移 + **同容器内**跑 PG 队列消费者（镜像带 ffmpeg） |
| **postgres** | 元数据 + **任务队列**（`jobs`） |
| **minio**（可选） | 对象存储；也可用 volume |

P0 **不部署**独立 worker、**不部署** Redis。队列与状态均在 PostgreSQL。

#### 后台任务：PG 队列 + 可替换后端

长任务（抽帧、导出）**不要**堵在 HTTP 请求线程里同步干完；P0 用 **PostgreSQL 任务表**作队列（`FOR UPDATE SKIP LOCKED` + 租约），接口可日后换 Redis。

```text
JobService.enqueue(job_type, payload) → INSERT jobs(pending) → job_id
     │
     ├─ P0: PgJobBackend
     │      · 队列 = jobs 表；claim: SKIP LOCKED + lease
     │      · api 同容器内 poller/worker 线程执行 handler
     │      · 状态：pending/running/succeeded/failed + progress
     │
     └─ 以后可选: RedisQueueJobBackend 或独立 worker 容器
            · 同 JobBackend 接口；Compose 可加 redis / worker
```

| 约定 | 说明 |
|------|------|
| 抽象 | `JobBackend`：`enqueue` / （可选）`cancel`；**状态与队列以 DB `jobs` 为准** |
| P0 | `PgJobBackend`；`JOB_BACKEND=pg`；api 启动挂载消费者（可配置 poll 间隔/并发） |
| 租约 | `locked_by` + `lease_until`；过期可被其他消费者回收，避免僵尸 running |
| HTTP | `POST` 创建任务立即返回 `job_id`；客户端轮询 `GET /jobs/{id}` |
| 扩展 | `JOB_BACKEND=pg\|redis`；切后端时 **不必改**抽帧/导出业务代码 |
| 拆分 worker | 同一套 handlers；以后 worker 容器只跑 consumer，api 只 `enqueue` |

**禁止：** 业务模块直接 `Thread`/`subprocess` 裸调、绕过 `JobService`；禁止再引入进程内「无 DB 队列」作为默认后端。

#### 以后拆分（预留，非 P0）

```text
api（只入队） → PG jobs 或 Redis → worker×N（ffmpeg + 同一 handlers）
```

默认可继续 `JOB_BACKEND=pg` 仅拆进程；若队列压力大再引入 Redis。web / postgres / blob 不变。
#### 数据卷

| 卷 / 桶 | 内容 |
|---------|------|
| `pgdata` | 数据库（含 job 状态） |
| `blobdata` 或 MinIO | video / frame / export |

#### Compose 示意（P0）

```yaml
services:
  web:
  api:        # FastAPI + in-process jobs + ffmpeg
  postgres:
  # minio:    # 可选
  # 以后: redis / worker
```

### D10. 产品级 UI / 体验（非简陋后台）

本产品是**日常工作台**（素材、抽帧审查、标注、版本），界面须达到**可交付甲方/内部正式使用**的完成度，而不是「能点通的脚手架页」。

#### 业界参考（可借鉴，不抄品牌）

**可以且建议参考**以 Roboflow 为代表的现代 CV 数据平台，以及 CVAT / Label Studio 等标注工具的**交互范式**，用于对齐「专业产品」预期：

| 宜参考 | 不宜照搬 |
|--------|----------|
| 上传视频 → 抽帧采样 → 当图片批标注的流程感 | Logo、配色商标、插画与营销落地页 |
| 数据集/批次浏览、来源与版本心智 | 对方专有组件或版权素材 |
| 标注台：画布为主、侧栏类别、快捷键、紧凑工具条 | 未授权复刻对方整站视觉体系 |
| 媒体网格、空态与进度的完成度 | 为像而像的装饰，忽略我们「审查删帧 / 版本血缘」差异 |

我方差异仍要做在自己的信息架构上：抽帧任务与审查、`memberSources`、不可变版本、帧→原视频第几帧等。参考的是**完成度与工具感**，产品仍是 LabelTrace。

#### 质量标准（P0 验收也看观感）

| 要求 | 说明 |
|------|------|
| 统一设计体系 | 颜色、字号、间距、圆角、阴影、状态色用 **CSS 变量 / Design Tokens** 一处定义，全站复用 |
| 专业工具气质 | 对齐业界 CV 平台水准：清晰层级、稳定栅格、克制装饰；**禁止**默认紫渐变、随意大圆角堆砌、空洞大空白凑版 |
| 字体 | 选用有辨识度的产品字体组合（中文 + 数字/英文），避免纯系统默认堆砌无层级 |
| 信息密度分档 | **浏览/管理**适中留白；**标注台 / 抽帧审查**偏紧凑，优先画布与缩略图 |
| 状态完整 | 空态、加载、进度（抽帧/导出 job）、错误、无权限均有设计，而非空白或裸 alert |
| 媒体呈现 | 视频/帧/图缩略图统一比例与占位；审查网格按时间排列且可读时间码 |
| 交互反馈 | 主按钮、危险删除、多选、快捷键有可见反馈；长任务有进度与可离开提示 |
| 响应式 | 桌面优先（标注/审查）；窄屏不崩，管理页可用 |
| 主题 | 默认 **light**，可切换 **dark**（见上节） |

#### 关键界面（须单独设计，禁止「表格 + 默认按钮」糊弄）

1. **项目 / 总览** — 入口与最近数据集/任务  
2. **素材库** — 目录树 + 视频为主的媒体浏览  
3. **抽帧与审查** — 参数面板 + **时间序缩略图网格** + 批量删除（高频页）  
4. **数据集** — 成员、来源摘要（抽帧/上传/导入）；**工作区不展示划分/unassigned**（避免迷惑）  
5. **标注台（工作区）** — 画布为主、类别与快捷键、上下帧、源视频/帧号；**默认可编辑**，顶栏标明「工作区」  
6. **版本与导出** — 版本列表、diff 摘要；**「查看快照」**进入只读标注视图（路由带 `version=`，徽章「版本 · 只读」）；划分结果以版本快照为准；导出进度与下载可后置  
7. **发版门槛** — 全部成员标注 `submitted` 后方可发版；发版时按 train/val/test 比例 + seed 随机划分并冻进快照；数据集支持移出成员（删引用、不硬删文件）  
8. **应用到工作区** — 从版本只读视图可将快照**合并**进工作区：同 asset 覆盖标注（置 `draft`）、缺则入集+写标、工作区多出的成员保留；不改版本快照  

#### 技术落点

- 先定 **tokens + 布局壳（顶栏/侧栏/内容）+ 基础组件皮肤**，再堆业务页。  
- 可用 headless 组件（如 Radix）保证无障碍与行为；**视觉必须定制**，不直接用组件库默认主题交差。  
- 标注画布（Konva）与壳层视觉统一（选中色、类别色板与 tokens 对齐）。  
- 建议产出轻量 **UI 规范一页**（色板、字号、关键页线框或高保真）再大规模写页面；可与实现并行迭代，但不得长期停留在无样式状态。

#### 主题

| 项 | 约定 |
|----|------|
| **默认** | **浅色工具风**（light） |
| **可切换** | 支持切换到**中性深色工具风**（dark）；用户偏好可持久化（localStorage / 用户设置） |
| 实现 | 两套 tokens（或同一 token 名下 light/dark 两套值），挂在 `data-theme` / `class` 上；组件不写死单色 |
| P0 范围 | 仅 light / dark 两套，不做更多品牌主题包 |

#### 非目标（避免过度）

- 不做营销落地页式大英雄区。  
- P0 不追求多主题商店；做好 light（默认）+ dark（可切换）即可。

## Risks / Trade-offs

- **[风险] 非库可见素材「找不到」** → 数据集成员列表与血缘必须可打开原图；文档说明导入不等于进素材库。  
- **[风险] 去重复用库内图时用户以为「又藏了一份」** → 复用不改 `library_visible`；stats 返回 `reused`。  
- **[风险] manifest JSONB 过大** → 超阈值拆 `version_items`。  
- **[取舍] 版本不复制 blob** → 必须靠引用禁止硬删；P1 可考虑冷归档拷贝。  
- **[风险] 切换默认后端后旧文件仍在旧 backend** → Asset 必须持久化 `storage_backend`；读路径按记录路由，避免只认全局配置。  
- **[取舍] P0 不做自动跨后端搬迁** → 换存储时需运维拷贝或后续迁移任务。  
- **[取舍] P0 api 与 worker 同容器、PG 队列消费** → 无 Redis；重负载时拆独立 worker 容器即可，抽象不变。  
- **[风险] running 任务随进程崩溃卡住** → 靠 `lease_until` 回收 + 启动时扫描过期租约；失败写入 `error_message` 并打错误日志（见 D11）。  

### D11. 错误处理与日志（实现硬规范）

**错误处理（禁止静默）：**

| 规则 | 说明 |
|------|------|
| 禁止 | 空的 `except:` / `except Exception: pass`；吞掉后无日志、无状态变更 |
| 边界 | HTTP 层统一异常映射（领域错误 → 4xx；未预期 → 500 + 日志）；任务 handler 失败 → `jobs.status=failed` + `error_message` |
| 对外 | 客户端可见 `detail`/`code`；内部堆栈只进日志 |
| 可恢复 | IO/外部依赖失败显式重试或失败终态，不假装成功 |

**日志（须能快速排错）：**

| 规则 | 说明 |
|------|------|
| 格式 | 结构化关键字段：`ts`、`level`、`logger`、`msg`、`request_id`、`user_id?`、`job_id?`、`job_type?`、`project_id?` |
| 请求 | 每个 HTTP 请求分配 `request_id`（响应头回传）；出入站记 method/path/status/latency |
| 任务 | enqueue / claim / succeed / fail 必须打日志；失败带 `exc_info` |
| 级别 | 业务拒绝用 warning；系统故障用 error；禁止用 print 代替 logger |
| 敏感 | 不记密码、完整对象存储密钥；文件路径可记 storage_key |
- **[风险] 赶功能导致 UI 简陋** → P0 验收含 D10 质量标准；先 tokens/壳层再堆页；审查与标注台优先投入视觉。

## Migration Plan

- 绿库按表草案创建。  
- 日后「提升进素材库」：设 `library_visible=true` 并指定 `folder_id`。  
- 标签分组：`tags.group_id` 可空升级。  
- 新增存储后端：实现 `BlobStore` 并注册 backend id，无需改领域表结构（除非新增 id 枚举校验）。

## Open Questions

1. ~~库内坐标用 `xyxy_abs` 还是归一化？~~ **已定：`format=xyxy_abs`（像素绝对坐标 `[x1,y1,x2,y2]`）**；导出 YOLO 时再归一化（导出延后）。  
2. ~~标注 GET 无记录时 `404` 还是空 `draft`？~~ **已定：返回空 draft（200）**，便于标注台。  
3. ~~annotator 是否允许发版 / 导入 / 抽帧？~~ **已定：annotator 可抽帧与标注；发版仅 owner；导入延后。角色名由 admin 更名为 owner。**  
4. 导入到**已有非空**数据集时：合并、拒绝，还是仅允许空集/新建？（**导入延后**，本 change 不收口）  
5. ~~对象存储是否 P0 就做浏览器直传（presign），还是一律经 API 中转？~~ **已定：一律经 API。**  
6. ~~UI 底座：Radix + 自研皮肤，或其它 headless？~~ **已定：自研 tokens + CSS 组件皮肤（无默认后台主题）；P0 未引入 Radix。**  
7. ~~默认抽帧策略？~~ **已定：仅手动触发；UI 默认 stride=30，API 可传 stride/interval；样例/验收常用 stride=5。**  
8. ~~frame 审查删除后 GC？~~ **已定：硬删即清 blob，无单独 GC。**

### 11.3 接口核对摘要（主体已实现）

| 区域 | 结论 |
|------|------|
| 项目/成员 | `POST/GET /projects`、`GET/POST .../members`、`PATCH .../members/{userId}`；viewer 写操作 403；发版/管成员仅 owner |
| 目录/素材 | folders CRUD；`POST/GET .../assets`；content RFC5987；硬删引用 409 |
| 抽帧 | `POST .../extract-jobs`；frames 时间升序；batch-delete → `discarded_count` |
| 数据集 | `POST/GET .../datasets`（含列表）；成员/from-extract；不可直接加 video |
| 标注 | PUT/GET shapes+`type`；空 draft 200；未启用类型 422 |
| 版本 | 发版快照+`member_sources`+diff；manifest 只读；发版后改工作区不影响版本 |
| 血缘 | `GET .../lineage`；frame 含 parentVideoId/frameIndex |
| 延后 | dataset import、YOLO zip 导出（tasks 6.x / 8.3–8.4） |
