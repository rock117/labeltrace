# Spec Delta

## Purpose

提供按数据集隔离的标注工作区；P0 交付 YOLO 检测框，载荷用可扩展的 shape 类型字段，以便后续增加分割、关键点、OBB、分类等类型而不推翻存储模型。

## ADDED Requirements

### Requirement: 标注绑定数据集与素材
系统 SHALL 对每个 `(dataset, asset)` 至多保存一份工作标注；对非数据集成员的素材，MUST 拒绝写入标注。

#### Scenario: 为成员保存框
- **WHEN** 用户为已是数据集成员的素材保存检测框
- **THEN** 系统将该几何与类别持久化到该数据集与该素材下

#### Scenario: 拒绝非成员标注
- **WHEN** 用户尝试为未加入该数据集的素材保存标注
- **THEN** 系统拒绝该请求

### Requirement: 跨数据集隔离
同一素材在不同数据集中的标注 SHALL 相互独立；更新其一 MUST NOT 改变另一份。

#### Scenario: 独立标注
- **WHEN** 素材 X 在数据集 A 与数据集 B 中分别有不同检测框
- **THEN** 读取 A 得到 A 的框，读取 B 得到 B 的框

### Requirement: 检测框载荷（P0）
P0 工作标注 SHALL 支持类型为检测框（`rect`）的 YOLO 检测几何，包含类别索引与边界框，坐标采用项目约定的内部格式。

#### Scenario: 框的读写一致
- **WHEN** 客户端保存一组检测框后再次加载该标注
- **THEN** 返回的类别索引与几何与保存时一致

### Requirement: Shape 类型可扩展
每条几何 SHALL 带有类型判别字段 `type`；保存时每条 `type` MUST 属于该数据集的启用标注类型，且 MUST 为服务端已注册可校验的类型。P0 MUST 注册并接受 `rect`。产品必做的其它类型（`polygon`、`mask`、`keypoint`/`pose`、`obb`、`classification`）在架构上预留，启用前 MUST 拒绝写入。

#### Scenario: P0 接受 rect
- **WHEN** 客户端向仅启用 `rect` 的数据集提交仅含 `type=rect` 的 shapes
- **THEN** 系统成功保存

#### Scenario: 拒绝未启用或未实现的类型
- **WHEN** 客户端提交 `type=polygon` 但数据集未启用该类型或服务端尚未注册该类型
- **THEN** 系统拒绝该请求并说明原因

### Requirement: 标注状态
系统 SHALL 至少支持工作标注状态 `draft` 与 `submitted`。

#### Scenario: 提交标注
- **WHEN** 用户将标注标记为 `submitted`
- **THEN** 后续读取显示状态为 `submitted`
