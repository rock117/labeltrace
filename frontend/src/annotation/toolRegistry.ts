/**
 * 标注工具注册表：只挂载「已实现 ∩ 数据集已启用」的类型。
 * P0 仅 rect；polygon 等未实现，不得出现在工具栏。
 */

export type AnnotationToolType = 'rect'

export type ToolDef = {
  type: AnnotationToolType
  label: string
  implemented: boolean
}

const IMPLEMENTED: ToolDef[] = [
  { type: 'rect', label: '检测框', implemented: true },
]

/** 未实现类型故意不注册，避免半成品入口 */
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
