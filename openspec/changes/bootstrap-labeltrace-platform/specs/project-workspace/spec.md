# Spec Delta

## Purpose

将项目定义为 LabelTrace 的租户边界，包含成员与角色，用于约束素材库、数据集与版本等资源的访问。

## ADDED Requirements

### Requirement: 创建与列出项目
系统 SHALL 允许授权用户创建带名称的项目，并列出其可访问的项目。

#### Scenario: 创建项目
- **WHEN** 授权用户提交合法的项目名称
- **THEN** 系统创建项目并返回其标识

#### Scenario: 列出可访问项目
- **WHEN** 用户请求自己的项目列表
- **THEN** 系统仅返回该用户作为成员的项目

### Requirement: 重命名项目
系统 SHALL 允许项目管理员更新项目名称。

#### Scenario: 管理员重命名项目
- **WHEN** 项目管理员提交新的合法项目名称
- **THEN** 项目名称更新为新名称

### Requirement: 项目成员与角色
系统 SHALL 支持项目成员及角色 `admin`、`annotator`、`viewer`，并 MUST 对变更类操作按角色鉴权。

#### Scenario: 管理员管理成员
- **WHEN** 项目管理员将某用户添加为 `annotator`
- **THEN** 该用户可以标注员权限访问该项目

#### Scenario: 只读成员不可改素材库
- **WHEN** 角色为 `viewer` 的成员尝试上传素材
- **THEN** 系统拒绝该请求（禁止）

### Requirement: 资源归属项目
系统 SHALL 保证目录、素材、标签、数据集均只属于一个项目，并 MUST 拒绝跨项目引用。

#### Scenario: 拒绝跨项目引用素材
- **WHEN** 客户端尝试将项目 A 的素材加入项目 B 的数据集
- **THEN** 系统拒绝该请求
