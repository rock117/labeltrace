# Spec Delta

## Purpose

支持导入已有 YOLO 检测数据集包，在无采集目录血缘的情况下创建或填充数据集、成员划分与标注；导入图默认仅数据集侧可见。

## ADDED Requirements

### Requirement: 导入 YOLO 数据集包
系统 SHALL 以 **zip** 形式接受 YOLO 检测数据包（multipart 上传；含图像、labels 与 `data.yaml`），并创建或填充目标数据集的类别、成员划分与工作标注。P0 支持导入到**新建数据集**或**已有空数据集**；非空数据集 MUST 拒绝。导入为异步任务，完成后可查询状态与 stats。

约定结构（与导出一致）：根目录 `data.yaml`；`train|val|test/images` 与对应 `labels`（同 stem 的 `.txt`，`cls cx cy w h` 归一化；可空）。

#### Scenario: 导入新建数据集
- **WHEN** 用户上传合法 YOLO zip 并指定新建数据集名称
- **THEN** 系统创建数据集，写入 classes，将包内图像与标签变为数据集成员及对应标注（标注 status=submitted）

#### Scenario: 非法包结构被拒绝
- **WHEN** 用户上传缺少必要类别配置或无法解析的 zip
- **THEN** 系统拒绝导入并说明原因

### Requirement: 导入素材默认不在素材库展示
由导入创建的素材 SHALL 标记为非素材库可见（`library_visible = false`）；素材库默认目录浏览 MUST NOT 列出这些素材，但数据集成员列表与标注台 MUST 可访问其内容。

#### Scenario: 素材库默认看不到导入图
- **WHEN** 导入完成后用户打开素材库某普通目录列表
- **THEN** 列表中不出现本次导入产生的、仍为非库可见的素材

#### Scenario: 数据集内可见导入图
- **WHEN** 用户打开刚导入的数据集成员列表
- **THEN** 可以看到导入的图像并可打开标注

### Requirement: 导入来源可追溯
每次成功导入 SHALL 留下导入记录（时间、操作者、包标识或文件名、目标数据集），供血缘查询。

#### Scenario: 查询导入来源
- **WHEN** 用户查看由导入产生的素材或数据集的来源信息
- **THEN** 可获知该导入记录的基本信息（至少含时间与目标数据集）

### Requirement: 导入与内容去重
导入时系统 SHALL 按内容哈希去重：若项目内已存在相同哈希的素材，MUST 复用该素材并建立数据集引用，不得无故再存一份二进制。

#### Scenario: 导入遇到已有哈希
- **WHEN** 包内某图的内容哈希与项目中已有素材相同
- **THEN** 数据集引用已有素材，且不新增重复对象文件
