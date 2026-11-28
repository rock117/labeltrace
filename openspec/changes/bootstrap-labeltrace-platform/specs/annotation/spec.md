# Spec Delta

## Purpose

提供按数据集隔离的标注工作区；P0 交付 YOLO 检测框，载荷用可扩展的 shape 类型字段，以便后续增加分割、关键点、OBB、分类等类型而不推翻存储模型。

## ADDED Requirements

### Requirement: 标注绑定数据集与素材
系统 SHALL 对每个 `(dataset, asset)` 至多保存一份工作标注；对非数据集成员的素材，MUST 拒绝写入标注。写入时 MUST 满足任务分配规则：`owner` 可标注任意成员；仅有 `annotator` 角色时 MUST 为该成员的 `assignee`；未分配成员对非 `owner` MUST 拒绝。

#### Scenario: 为成员保存框
- **WHEN** 用户为已是数据集成员、且有权标注的素材保存检测框
- **THEN** 系统将该几何与类别持久化到该数据集与该素材下

#### Scenario: 拒绝非成员标注
- **WHEN** 用户尝试为未加入该数据集的素材保存标注
- **THEN** 系统拒绝该请求

#### Scenario: 拒绝标注他人名下成员
- **WHEN** 仅有 annotator 角色的用户对分给其他用户的成员写入标注
- **THEN** 系统拒绝

### Requirement: 跨数据集隔离
同一素材在不同数据集中的标注 SHALL 相互独立；更新其一 MUST NOT 改变另一份。

#### Scenario: 独立标注
- **WHEN** 素材 X 在数据集 A 与数据集 B 中分别有不同检测框
- **THEN** 读取 A 得到 A 的框，读取 B 得到 B 的框

### Requirement: 检测框载荷（P0）
P0 工作标注 SHALL 支持类型为检测框（`rect`）的 YOLO 检测几何，包含稳定类别引用 `classId`（对应项目词表中的类别 id）与边界框，坐标采用项目约定的内部格式。保存时 `classId` MUST 属于该数据集当前启用的类别集合。

#### Scenario: 框的读写一致
- **WHEN** 客户端保存一组检测框后再次加载该标注
- **THEN** 返回的 `classId` 与几何与保存时一致

#### Scenario: 拒绝未知类别
- **WHEN** 客户端提交的 `classId` 不属于该数据集
- **THEN** 系统拒绝该请求

### Requirement: Shape 类型可扩展
每条几何 SHALL 带有类型判别字段 `type`；保存时每条 `type` MUST 属于该数据集的启用标注类型，且 MUST 为服务端已注册可校验的类型。P0 MUST 注册并接受 `rect`。产品必做的其它类型（`polygon`、`mask`、`keypoint`/`pose`、`obb`、`classification`）在架构上预留，启用前 MUST 拒绝写入。

#### Scenario: P0 接受 rect
- **WHEN** 客户端向仅启用 `rect` 的数据集提交仅含 `type=rect` 的 shapes
- **THEN** 系统成功保存

#### Scenario: 拒绝未启用或未实现的类型
- **WHEN** 客户端提交 `type=polygon` 但数据集未启用该类型或服务端尚未注册该类型
- **THEN** 系统拒绝该请求并说明原因

### Requirement: 标注状态
系统 SHALL 至少支持工作标注状态 `draft` 与 `submitted`。产品主路径：用户在工作区标注台**切换成员或离开标注台**时，若当前图有未保存改动，SHALL 自动写入为 `submitted`（离开本张即视为标完，无需每张再点提交）。用户仍可显式「仅存草稿」写入 `draft`，或「提交本张」留在当前图。

#### Scenario: 提交标注
- **WHEN** 用户将标注标记为 `submitted`
- **THEN** 后续读取显示状态为 `submitted`

#### Scenario: 切图即视为本张提交
- **WHEN** 用户在工作区标注台修改了当前图的框，并切换到另一张成员
- **THEN** 系统在离开当前图前将改动保存为 `submitted`，再加载下一张

#### Scenario: 仅存草稿
- **WHEN** 用户显式选择仅存草稿
- **THEN** 当前改动保存为 `draft`（可用于中途停手，不算发版就绪）

### Requirement: 未标注与无目标（负样本）区分
系统 MUST 区分「尚未处理」与「已确认无检测目标」：
- **未标注**：该成员尚无工作标注记录（或等价：无有效标注且未提交）；表示标注员尚未完成处理，MUST NOT 视为训练用负样本。
- **无目标 / null**：存在工作标注且 `status = submitted`，且 shapes 中无几何项（空框列表）；表示人工确认本图无可标对象，MAY 作为检测任务负样本进入发版快照与导出。
系统 SHALL 允许将空 shapes 提交为 `submitted`（显式无目标）。产品 UI SHOULD 在进度/胶片条上将「已提交且无框」与「已提交且有框」可区分展示（例如「无目标」），且 MUST NOT 把未标注与无目标混为同一状态。

#### Scenario: 空提交表示无目标
- **WHEN** 用户对某成员提交 `submitted` 且 shapes 不含任何检测框
- **THEN** 该成员视为已处理的无目标样本（null），计数上属于已提交而非未标注

#### Scenario: 未标注不得当作负样本
- **WHEN** 某成员尚无工作标注记录
- **THEN** 其状态为未标注；发版条件仍视为未完成；语义上 MUST NOT 等同于已确认无目标

#### Scenario: 有框则不是未标注
- **WHEN** 某成员工作标注中已有几何项（无论 draft 或 submitted）
- **THEN** 进度与筛选不得将其列为未标注

### Requirement: 标注进度可见
工作区标注台 SHALL 展示当前数据集成员的标注进度（至少：已提交、草稿、未标注数量与总成员数）；成员列表（胶片条）MUST 能区分已提交 / 草稿 / 未标注，并 SHALL 支持按状态筛选列表，以及跳转到下一张未标注成员。已提交且无框的成员 SHOULD 显示为无目标（或等价文案），以免与有框图混淆。

#### Scenario: 看到已标注进度
- **WHEN** 用户打开含若干成员的数据集工作区标注台
- **THEN** 界面显示已提交 / 草稿 / 未标注数量（或等价进度信息）

#### Scenario: 只看未标注
- **WHEN** 用户将胶片条筛选为「未标注」
- **THEN** 列表仅显示尚无有效标注的成员（无标注记录且无框）；已有框或 draft/submitted 的成员 MUST NOT 出现在「未标注」中

#### Scenario: 打开图片时状态与库一致
- **WHEN** 用户打开某成员且库中已有工作标注（含 shapes）
- **THEN** 前端成员状态与该标注一致（至少不再显示为未标注）

#### Scenario: 跳到下一张未标注
- **WHEN** 用户触发「下一张未标注」且后方仍有未标注成员
- **THEN** 标注台打开该成员

#### Scenario: 上一张下一张遵循当前筛选
- **WHEN** 用户将胶片筛选为「未标注」（或草稿/已提交）并点击上一张/下一张
- **THEN** 导航仅在该筛选结果内移动，而不是按全库成员序号相邻跳转；到筛选首尾时不可再翻

#### Scenario: 一键提交全部草稿
- **WHEN** 用户在工作区标注台触发「提交全部草稿」
- **THEN** 该数据集中所有 `draft` 工作标注变为 `submitted`（shapes 不变）；尚无标注记录的成员不受影响

### Requirement: 批量提交草稿
系统 SHALL 支持将数据集工作区内所有 `draft` 标注一次性升为 `submitted`（不修改 shapes）；无标注记录的成员 MUST NOT 被凭空创建为空提交。产品 UI SHALL 提供「提交全部草稿」入口。

#### Scenario: 一键提交全部草稿
- **WHEN** 用户在标注台触发提交全部草稿，且存在若干 draft 标注
- **THEN** 这些记录状态变为 `submitted`，已提交进度相应增加

### Requirement: 工作区与版本浏览分离
默认标注台绑定**数据集工作区**（实时可编辑）。按版本打开时 MUST 进入只读快照模式，展示该版本冻结的 shapes，不得写入工作区标注接口或改写版本快照。

#### Scenario: 工作区可编辑
- **WHEN** 用户从数据集进入标注台（未指定版本）
- **THEN** 可保存/提交工作标注，顶栏或等价位置标明工作区

#### Scenario: 版本模式只读
- **WHEN** 用户从版本列表打开某版本浏览
- **THEN** 画布与列表展示该版本快照标注，保存/提交入口不可用（或不可写）
