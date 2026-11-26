/**
 * 标注工具注册表：只挂载「已实现 ∩ 数据集已启用」的类型。
 *
 * 切换策略（与 design D1.1 对齐）：
 * - 数据集 `enabled_annotation_types` 决定「本集允许哪些类型」
 * - 工具栏 = 已实现 ∩ 已启用；点工具栏切换当前绘制工具（activeTool）
 * - 未实现类型不注册、不展示，避免半成品入口
 * - 加新类型：在 IMPLEMENTED 注册 + 画布 Handler；不必改数据集主键
 */

export type AnnotationToolType =
  | 'rect'
  | 'polygon'
  | 'mask'
  | 'keypoint'
  | 'pose'
  | 'obb'
  | 'classification'

export type ToolDef = {
  type: AnnotationToolType
  label: string
  implemented: boolean
  /** 快捷键提示（可选） */
  shortcut?: string
}

const IMPLEMENTED: ToolDef[] = [
  { type: 'rect', label: '检测框', implemented: true, shortcut: 'R' },
]

/** 未实现类型故意不注册到 IMPLEMENTED，避免半成品入口 */
const NOT_IMPLEMENTED = [
  'polygon',
  'mask',
  'keypoint',
  'pose',
  'obb',
  'classification',
] as const

export function resolveToolbarTools(enabledAnnotationTypes: string[]): ToolDef[] {
  const enabled = new Set(enabledAnnotationTypes)
  return IMPLEMENTED.filter((t) => t.implemented && enabled.has(t.type))
}

export function assertNoUnimplementedEntries(tools: ToolDef[]): void {
  for (const t of tools) {
    if ((NOT_IMPLEMENTED as readonly string[]).includes(t.type)) {
      throw new Error(`未实现类型不得出现在工具栏: ${t.type}`)
    }
  }
}
