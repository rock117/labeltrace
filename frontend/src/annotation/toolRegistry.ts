/**
 * 标注工具注册表：只挂载「已实现 ∩ 数据集已启用」的类型。
 * 交互习惯对齐常见产品（Roboflow 等）：工具条 + 单键快捷键。
 */

import { ANNOTATION_TYPE_OPTIONS } from '../lib/annotationShapes'

export type AnnotationToolType =
  | 'rect'
  | 'polygon'
  | 'mask'
  | 'keypoint'
  | 'obb'
  | 'classification'

export type ToolDef = {
  type: AnnotationToolType
  label: string
  implemented: boolean
  shortcut?: string
  hint: string
}

const SHORTCUT: Partial<Record<AnnotationToolType, string>> = {
  rect: 'B',
  polygon: 'P',
  mask: 'W',
  keypoint: 'K',
  obb: 'O',
  classification: 'C',
}

const IMPLEMENTED: ToolDef[] = ANNOTATION_TYPE_OPTIONS.map((o) => ({
  type: o.type,
  label: o.label,
  implemented: true,
  shortcut: SHORTCUT[o.type],
  hint: o.hint,
}))

export function resolveToolbarTools(enabledAnnotationTypes: string[]): ToolDef[] {
  const enabled = new Set(enabledAnnotationTypes)
  return IMPLEMENTED.filter((t) => t.implemented && enabled.has(t.type))
}

export function toolHint(tools: ToolDef[], active: AnnotationToolType): string {
  return tools.find((t) => t.type === active)?.hint ?? ''
}
