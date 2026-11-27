# Proposal

## Why

甲方交付的素材**以拍摄视频为主、基本没有现成图片**；训练侧仍需要 YOLO 可用的帧级检测数据。LabelTrace 需以**视频入库 → 抽帧 → 帧级标注 → 数据集版本**为主路径，同时保留图片上传与 YOLO 包导入；并解决素材复用、版本可复现与来源回溯问题。

## What Changes

- 引入**账号注册/登录**（JWT）与**项目**租户边界；项目角色 P0：`owner` / `annotator` / `viewer`（创建者即负责人；邀请按用户名；一人可跨多项目，同项目可多角色）。
- 引入**素材库**（视频优先）：可嵌套目录；支持上传**视频**与图片；视频抽帧生成 **frame** 素材；内容哈希去重；库浏览区分 video / image（frame 策略见 design）。
- 引入**可插拔二进制存储**：视频原片、帧图、导出包经 BlobStore（local / S3 兼容）。
- 引入**扁平标签**：可打在视频或帧上（P0 至少支持打在可浏览素材上）。
- 引入**数据集**：成员以**可标注素材（主要为 frame，亦可 image）**为引用单位；不拷贝二进制。
- 引入**数据集导入**：已有 YOLO 图片包仍可导入（兼容历史/外包结果）。
- 引入**标注工作区**：标在 frame/image 上；产品必做多类型，**P0 先做 `rect`**，架构可扩展。
- 引入**数据集版本**与**删除保护**、**来源回溯**（帧可追溯到源视频）。
- 明确 **P0 不做**：完整视频时间轴逐帧 scrub UI、跨帧 track_id、除 `rect` 外标注类型实现、标签分组、组织树、在线训练、跨项目共享；「提升导入隐藏图进库」可后做。

## Capabilities

### New Capabilities

- `project-workspace`: 项目边界、成员与角色
- `asset-library`: 目录树、图片上传、可见性、去重、BlobStore、删除保护
- `video-ingest`: 视频上传、元数据、按策略抽帧为 frame Asset、与源视频血缘
- `asset-tags`: 扁平标签
- `datasets`: 数据集、类别、引用帧/图、划分
- `dataset-import`: 导入已有 YOLO 图片数据集包
- `annotation`: 帧/图上的检测框标注（可扩展类型）
- `dataset-versioning`: 版本、diff、按版本导出 YOLO
- `lineage`: 含「帧 → 源视频」的回溯

### Modified Capabilities

- （无 — 新仓库，尚无主规格）

## Impact

- 技术栈：**FastAPI + PostgreSQL + React（Vite/TS）+ Konva**；抽帧依赖（如 ffmpeg）需纳入部署。
- 主用户路径变为：**上传甲方视频 → 抽帧 → 审查剔除 → 入集 → 标框 → 发版导出**；纯图片为辅。
- **UI 须产品级设计**（统一 tokens、专业工具气质、完整空态/进度；禁止简陋未换肤后台页），见 design D10。
- 规划详见本 change 的 specs / design / tasks；操作说明见 `docs/guides/`。
