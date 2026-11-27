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
系统 SHALL 允许项目负责人更新项目名称。

#### Scenario: 负责人重命名项目
- **WHEN** 项目负责人提交新的合法项目名称
- **THEN** 项目名称更新为新名称

### Requirement: 账号注册与登录
系统 SHALL 支持用户名+密码注册与登录，并签发访问令牌；未登录 MUST NOT 访问需鉴权的业务 API。注册仅创建平台账号，不自动加入任何项目。

#### Scenario: 注册并登录
- **WHEN** 用户提交未占用的用户名与合法密码完成注册（或已有账号登录）
- **THEN** 系统返回访问令牌与用户信息，后续请求可凭令牌访问

#### Scenario: 未登录被拒
- **WHEN** 未带有效令牌请求项目列表
- **THEN** 系统拒绝（401）

### Requirement: 项目成员与角色
系统 SHALL 支持项目成员及角色 `owner`（负责人）、`annotator`（标注员）、`viewer`（只读），并 MUST 对变更类操作按角色鉴权。**创建项目的用户 MUST 成为该项目的 `owner`**。负责人可按**已注册用户名**邀请成员并设置角色集合。同一用户可同时属于多个项目；**同一项目内同一用户可同时持有多个角色**（成员记录唯一，角色为集合），鉴权按角色权限**并集**计算（例如同时为 `annotator` 与 `viewer` 时具备写权限）。

#### Scenario: 负责人管理成员
- **WHEN** 项目负责人将某用户添加为含 `annotator` 的角色集合
- **THEN** 该用户可以标注员权限访问该项目

#### Scenario: 同一项目内多角色
- **WHEN** 项目负责人将用户 U 的角色设为 `annotator` 与 `viewer`
- **THEN** U 具备写权限（因含 annotator），且成员详情返回这两个角色

#### Scenario: 同一用户跨项目不同角色
- **GIVEN** 用户 U 在项目 A 为 `owner`
- **WHEN** 项目 B 的负责人将 U 添加为 `annotator`
- **THEN** U 仍以 `owner` 访问 A，并以 `annotator` 访问 B

#### Scenario: 负责人变更成员角色集合
- **WHEN** 项目负责人将某成员角色集合改为仅 `viewer`
- **THEN** 该成员之后的写操作被拒绝，只读访问仍可用

#### Scenario: 只读成员不可改素材库
- **WHEN** 仅拥有 `viewer` 角色的成员尝试上传素材
- **THEN** 系统拒绝该请求（禁止）

### Requirement: 资源归属项目
系统 SHALL 保证目录、素材、标签、数据集均只属于一个项目，并 MUST 拒绝跨项目引用。

#### Scenario: 拒绝跨项目引用素材
- **WHEN** 客户端尝试将项目 A 的素材加入项目 B 的数据集
- **THEN** 系统拒绝该请求
