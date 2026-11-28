# Tasks

> **优先级（2026-11-26 调整）**  
> **先做主体路径**：视频→抽帧→审查→入集→**标注**→**发版/diff**→血缘→产品级 UI。  
> **导入 YOLO 包 / 导出 YOLO zip 降为延后**（不阻塞主体验收；API 可先留占位）。

## 1. 工程骨架与存储

- [x] 1.1 初始化 **FastAPI** API 工程与 **React + TypeScript + Vite** 前端工程（依赖含 `konva`/`react-konva`、`zustand`），并确认本地可分别启动空服务
- [x] 1.2 配置 **PostgreSQL** 连接与迁移工具（如 Alembic），并确认空库可 migrate 成功
- [x] 1.3 定义 `BlobStore` 抽象（put/get/delete/exists），并确认领域层不依赖具体路径或云 SDK
- [x] 1.4 实现 `local` 后端（根目录 + 逻辑 key），并用集成测试验证上传后可按 key 读回
- [x] 1.5 实现 `s3` 兼容后端（可对接 MinIO），并用集成测试（或 testcontainers/本地 MinIO）验证读写与 `local` 行为一致
- [x] 1.6 实现按配置选择默认写入后端，读时按 Asset 的 `storage_backend` 路由，并验证切换默认写入后端后旧文件仍可读
- [x] 1.7 定义 `JobBackend` + `PgJobBackend`（`jobs` 表队列 + SKIP LOCKED/租约）；抽帧/导出只经 `JobService`，并验证创建任务立即返回 job_id、可轮询状态
- [x] 1.8 提供 `JOB_BACKEND` 配置扩展点（P0 仅 `pg`）；文档注明日后独立 worker / 可选 `redis` 的接入方式
- [x] 1.9 落地错误处理与日志规范（D11）：统一异常映射、禁止静默吞错、结构化日志含 request_id/job_id

## 2. 项目与成员（project-workspace）

- [x] 2.1 实现 Project / Membership 表与创建、列表项目 API，并用请求验证仅返回当前用户可访问项目
- [x] 2.2 实现成员添加与角色校验中间件，并验证 `viewer` 调用上传接口返回 403
- [x] 2.3 角色 `admin`→`owner`；列表/改角色 API；项目页赋角色 UI；跨项目独立角色
- [x] 2.4 同一项目多角色（`roles` 集合 + 权限并集）；成员 UI 多选
- [x] 2.5 注册/登录（JWT）+ 前端登录页；邀请按用户名；顶栏展示当前用户
- [x] 2.6 客户端工作区偏好按归属嵌套（D12）：`labeltrace.project` / `session` / `theme` 分区；换项目清空子树；打开页 API 校验归属

## 3. 素材库（asset-library）

- [x] 3.1 实现 Folder 树 CRUD（同级重名 409），并验证嵌套创建与路径/列表正确
- [x] 3.1b 子目录列表返回直接视频/图片数量；素材库子目录右键重命名并展示该数量
- [x] 3.1c 目录视频列表标记已成功抽帧的视频（封面角标）
- [x] 3.2 Asset 支持 `media_kind`（image/video/frame）；实现图片上传（`image`）与 content 读取（RFC 5987 文件名），并验证中文路径展示与 hash 型 storage_key
- [x] 3.3 实现内容哈希去重与移动、目录列表过滤、引用硬删 409（同前约定）

## 3b. 视频入库与抽帧（video-ingest）— 主路径

- [x] 3b.1 集成 ffmpeg（或等价）于 API/Worker，并确认能从样例视频导出 jpg 帧
- [x] 3b.2 实现视频上传（`media_kind=video`）+ 元数据（时长/fps/分辨率），并验证目录可见与去重
- [x] 3b.2b 视频列表封面：上传时 ffmpeg 截帧旁路缓存；`GET /assets/{id}/poster`；素材库列表未点选即可显示封面
- [x] 3b.3 实现 `FrameExtractJob`（mode/stride 或 interval）与抽帧执行，生成带 `extract_job_id` 的 frame，并验证任务参数可回读
- [x] 3b.4 实现按抽帧任务浏览候选帧（**默认按 frame_index/时间升序**，展示时间位置）+ **批量删除**未入集帧，并验证排序与 `discarded_count`
- [x] 3b.5 验证已入集 frame 硬删返回 409；移出数据集后再删成功
- [x] 3b.6 实现「将审查后剩余帧加入数据集」，并验证可与上传 image 并存
- [x] 3b.7 实现数据集 `memberSources` 摘要，发版写入 `member_sources`，并验证发版后改工作区不影响该摘要

## 4. 扁平标签（asset-tags）

- [x] 4.1 实现项目内 Tag 创建/列表（重名拒绝），并验证 API 行为
- [x] 4.2 实现素材挂载/摘除/覆盖标签，并验证多标签关联
- [x] 4.3 实现按多标签交集筛选**库可见**素材列表，并验证筛选结果
- [x] 4.4 侧栏「标签」页：创建/列表；点选标签列出其下库可见素材；素材库右键打标签

## 5. 数据集（datasets）

- [x] 5.1 实现 Dataset 创建（含有序 classes、`enabled_annotation_types` 默认 `["rect"]`）与详情 API，并验证类别与启用类型读回正确
- [x] 5.1b 创建数据集只提交名称；默认启用当时全部项目类别，新建类别追加到各数据集末尾，数据集页可取消勾选（YOLO 导入按名字复用或新建）
- [x] 5.2 实现 DatasetAsset 加入/移除（不拷贝、不硬删文件），并验证同一 asset 可属两个数据集
- [x] 5.2c 成员任务分配：`assignee_user_id`；owner 批量分配；annotator 只见/只标自己的；未分配非 owner 不可标；标注台 mine/all
- [x] 5.2d 入集默认 `assignee` = 项目 owner（优先当前操作者）；已有未分配回填
- [x] 5.3 实现 split 更新（train/val/test/unassigned），并验证读回一致
- [x] 5.4 增加跨项目引用防护测试，验证将他项素材加入本项数据集被拒绝
- [x] 5.5 验证「仅含非库可见成员」的数据集可列表与打开内容

## 7. 标注（annotation）— 主体优先

- [x] 7.1 实现 `(dataset, asset)` 标注 PUT/GET（shapes 含必填 `type`；P0 校验仅 `rect`），并验证非成员写入被拒
- [x] 7.2 实现按 Dataset 启用类型 + 后端 Registry 校验，提交未启用/`polygon` 等返回 422，并补充测试
- [x] 7.2b 注册并实现 polygon/mask/keypoint/obb/classification 校验与标注台工具；数据集可改启用类型；YOLO 导出仍仅 rect
- [x] 7.3 增加跨数据集隔离测试：同图两数据集标注互不影响
- [x] 7.4 固定内部坐标 `format` 的序列化约定并补充单测（与 design Open Question 收口后一致）
- [x] 7.5 前端工具注册表只挂载已实现且数据集已启用的类型；工具栏 = 启用 ∩ 已实现

## 8a. 版本发版（主体：不含 YOLO 导出）

- [x] 8.1 实现发版：写入 classes + manifest 快照（含 `member_sources`），并验证发版后改工作区不影响该版本
- [x] 8.2 实现相对父版本的变更摘要（增/删/改标计数），并验证有父版本时摘要可读
- [x] 8.1a 发版门槛：全部成员标注 `submitted`；空数据集/未提交则拒绝（对齐 dataset-versioning spec）
- [x] 8.1b 版本只读浏览：版本页「查看快照」→ 标注台 `version=` 只读模式（与工作区可区分）
- [x] 5.2b UI：数据集成员可移出（调用已有 DELETE 引用 API，不硬删文件）
- [x] 8.1c 版本「应用到工作区」合并：同图覆盖标注为 draft、缺则入集、工作区多余成员保留
- [x] 12.1 重命名：项目 / 数据集 / 目录 / 素材显示名（PATCH API + UI）
- [x] 12.2 ~~标完再划：工作区手动设 split~~ → 改为发版时按比例随机划分；工作区不展示 unassigned
- [x] 8.1d 发版 API/UI：train/val/test 比例 + seed；写入成员并冻进快照；工作区隐藏划分标签

## 9. 回溯（lineage）

- [x] 9.1 实现 `GET /assets/{id}/lineage`（origin、importId?、path、标签、数据集、版本；frame 含源视频与帧号），并验证帧血缘（导入字段可先可空）
- [x] 9.2 实现版本组成查询（或复用 manifest），并验证与发版快照一致
- [x] 9.3 确认标注 `updated_by` / `updated_at` 在标注或血缘响应中可读

## 10. 产品级 UI 与前端主路径

- [x] 10.0 落地 Design Tokens（**默认 light + 可切换 dark**）+ 布局壳 + 基础组件皮肤 + 主题切换入口，对照 D10 自检
- [x] 10.1 素材库页（产品级媒体浏览）：上传视频 + 抽帧 + **按时间排序的候选帧审查**，并手工走通
- [x] 10.1b 素材库规模浏览：目录内视频/图片分 Tab 分页封面网格；frame 仅在视频→抽帧任务审查区；列表 API 支持 media_kind + limit/offset + total
- [x] 10.2 数据集页（来源摘要可视化）：加入审查后剩余帧、从库勾选图片（上传仅在素材库；导入入口可后置），并手工走通
- [x] 10.2b 多视频入集：`GET /projects/{id}/extract-jobs`；数据集页多选抽帧任务批量 from-extract；素材库可对当前任务选数据集入集
- [x] 10.3 标注台（核心页视觉）：对 **frame** 画框，类别色与 tokens 一致，展示源视频/帧号，并手工走通
- [x] 10.3b 标注台：切图/离开有改动则自动 `submitted`；主路径「下一张」；可选「仅存草稿」
- [x] 10.3c 标注进度：成员列表带 annotation_status；标注台显示已提交/总数，胶片条区分已提交/草稿
- [x] 10.3d 标注台「提交全部草稿」API+按钮；首尾张禁用上一张/下一张（不循环）
- [x] 10.3e 标注台胶片按 全部/未标/草稿/已提交 筛选 +「下一张未标注」；角标区分未标注
- [x] 10.3f Spec：未标注 vs 无目标(null) 负样本语义；空 submitted 可发版；指南同步（UI「无目标」角标可随后做）
- [x] 10.3g 标注台上一张/下一张按当前筛选列表翻页（非全库顺序）
- [x] 10.4 版本页：发版、diff 摘要（导出下载可后置），含空态/进度设计，并手工走通
- [x] 10.4b 版本页可下拉切换同项目数据集（发版/导出不绑死「上次选中」）
- [x] 10.5 统一空态/加载/错误/无权限样式，并在主路径各页抽查

## 11. 主体集成验收

- [x] 11.1 主路径：上传视频 → 抽帧 → **审查删帧** → 入集 → **标框** → **发版**（导出 YOLO 不阻塞）
- [x] 11.2 按 specs 勾验主体项（帧血缘、引用禁删、发版后追加、viewer 禁传等；导入隐藏/导出一致性延后）
- [x] 11.3 对照 design 接口表核对已实现路径与错误码，并记下 Open Questions 最终选择

---

## YOLO 导入 / 导出

### 6. 数据集导入（dataset-import）

- [x] 6.1 实现 `DatasetImport` 记录与 YOLO zip 解析（data.yaml + images/labels），非法包返回 422
- [x] 6.2 实现导入创建 Asset（`origin=import`, `library_visible=false`）+ 成员 + 标注 + split，并验证素材库目录看不到、数据集内看得到
- [x] 6.3 实现导入去重复用已有 hash，并验证 `stats.reused` 与不重复存盘
- [x] 6.4 实现导入状态查询 API，并验证成功后血缘可关联 `importId`

### 8b. YOLO 导出

- [x] 8.3 实现按版本导出 YOLO zip（异步 job + 下载；包内文件名规则；空 label 负样本；UI 版本页）
- [x] 8.3b 导出选剖面：detect/segment/obb/pose/classify；UI 下拉；产物分 key；mask 不进 YOLO 剖面
- [x] 8.4 验证：素材仅留在历史版本中时硬删仍 409（`asset_has_references`），且该版本仍可导出

### 7c. 数据集类别（稳定 classId）

- [x] 7c.1 shapes 改用 `classId`；DatasetClass 可维护（PUT classes）；发版冻结 `[{id,name}]`；导出按序映射 YOLO 下标
- [x] 7c.2 数据集页类别编辑 UI；标注台按类选色/快捷键；无类或非法 classId 拒绝发版
- [x] 7c.3 类别改为项目词表；数据集按 classIds 有序启用；导入按名字复用或新建项目类别。不迁移旧 dataset_classes

## 后续规划（不阻塞本 change）

- 视频时间轴 scrub UI、跨帧 track_id
- YOLO seg / pose / OBB 包导入导出；mask 位图 BlobStore；pose skeleton 元数据
- 各类型对应导入导出与版本兼容

## Workflow follow-up

- 主体 / 导入 / 导出验收通过后，可 OpenSpec archive。
- 用户流程说明见 `docs/guides/数据集从上传到发版.md`（随产品变更同步更新，不替代 spec）。
