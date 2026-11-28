/** 标注 shape 联合类型与解析（与后端 Registry 对齐）。 */

export type RectShape = {
  type: 'rect'
  classId: string
  bbox: [number, number, number, number]
}

export type PolygonShape = {
  type: 'polygon'
  classId: string
  points: [number, number][]
}

export type ObbShape = {
  type: 'obb'
  classId: string
  cx: number
  cy: number
  w: number
  h: number
  angle: number
}

export type KeypointShape = {
  type: 'keypoint'
  classId: string
  points: Array<{ x: number; y: number; v?: 0 | 1 | 2 }>
}

export type MaskStroke = {
  points: [number, number][]
  width: number
}

export type MaskShape = {
  type: 'mask'
  classId: string
  strokes: MaskStroke[]
}

export type ClassificationShape = {
  type: 'classification'
  classId: string
}

export type AnnotationShape =
  | RectShape
  | PolygonShape
  | ObbShape
  | KeypointShape
  | MaskShape
  | ClassificationShape

export type AnnotationShapesPayload = {
  format: 'xyxy_abs' | 'image_abs'
  items: AnnotationShape[]
}

export const ANNOTATION_TYPE_OPTIONS: {
  type: AnnotationShape['type']
  label: string
  hint: string
}[] = [
  { type: 'rect', label: '检测框', hint: '拖拽画出矩形' },
  {
    type: 'polygon',
    label: '多边形',
    hint: '单击加点；悬停起点变红后单击闭合，或 Enter /「完成」',
  },
  { type: 'mask', label: '笔刷', hint: '按住拖动画笔' },
  { type: 'keypoint', label: '关键点', hint: '单击落点，同类别连成一组' },
  { type: 'obb', label: '旋转框', hint: '拖拽画框，选中后可旋转' },
  { type: 'classification', label: '整图分类', hint: '在右侧点选类别标签' },
]

function num(v: unknown): number | null {
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function asXy(raw: unknown): [number, number] | null {
  if (!Array.isArray(raw) || raw.length < 2) return null
  const x = num(raw[0])
  const y = num(raw[1])
  if (x == null || y == null) return null
  return [x, y]
}

export function parseAnnotationItems(raw: unknown): AnnotationShape[] {
  if (!Array.isArray(raw)) return []
  const out: AnnotationShape[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const o = item as Record<string, unknown>
    const type = o.type
    const classId = typeof o.classId === 'string' ? o.classId : null
    if (!classId) continue
    if (type === 'rect') {
      const bbox = o.bbox
      if (!Array.isArray(bbox) || bbox.length < 4) continue
      const b = bbox.map(num)
      if (b.some((v) => v == null)) continue
      out.push({
        type: 'rect',
        classId,
        bbox: [b[0]!, b[1]!, b[2]!, b[3]!],
      })
      continue
    }
    if (type === 'polygon') {
      if (!Array.isArray(o.points) || o.points.length < 3) continue
      const points: [number, number][] = []
      for (const p of o.points) {
        const xy = asXy(p)
        if (!xy) break
        points.push(xy)
      }
      if (points.length >= 3) out.push({ type: 'polygon', classId, points })
      continue
    }
    if (type === 'obb') {
      const cx = num(o.cx)
      const cy = num(o.cy)
      const w = num(o.w)
      const h = num(o.h)
      const angle = num(o.angle)
      if (
        cx == null ||
        cy == null ||
        w == null ||
        h == null ||
        angle == null ||
        w <= 0 ||
        h <= 0
      ) {
        continue
      }
      out.push({ type: 'obb', classId, cx, cy, w, h, angle })
      continue
    }
    if (type === 'keypoint') {
      if (!Array.isArray(o.points) || o.points.length < 1) continue
      const points: KeypointShape['points'] = []
      for (const p of o.points) {
        if (p && typeof p === 'object' && !Array.isArray(p)) {
          const r = p as Record<string, unknown>
          const x = num(r.x)
          const y = num(r.y)
          if (x == null || y == null) continue
          const pt: { x: number; y: number; v?: 0 | 1 | 2 } = { x, y }
          if (r.v === 0 || r.v === 1 || r.v === 2) pt.v = r.v
          points.push(pt)
        } else {
          const xy = asXy(p)
          if (xy) points.push({ x: xy[0], y: xy[1] })
        }
      }
      if (points.length >= 1) out.push({ type: 'keypoint', classId, points })
      continue
    }
    if (type === 'mask') {
      if (!Array.isArray(o.strokes) || o.strokes.length < 1) continue
      const strokes: MaskStroke[] = []
      for (const s of o.strokes) {
        if (!s || typeof s !== 'object') continue
        const r = s as Record<string, unknown>
        if (!Array.isArray(r.points) || r.points.length < 1) continue
        const points: [number, number][] = []
        for (const p of r.points) {
          const xy = asXy(p)
          if (xy) points.push(xy)
        }
        const width = num(r.width) ?? 12
        if (points.length >= 1 && width > 0) strokes.push({ points, width })
      }
      if (strokes.length >= 1) out.push({ type: 'mask', classId, strokes })
      continue
    }
    if (type === 'classification') {
      out.push({ type: 'classification', classId })
    }
  }
  return out
}

export function shapesKey(items: AnnotationShape[]): string {
  return JSON.stringify(items)
}

export function shapeSummary(s: AnnotationShape): string {
  if (s.type === 'rect') {
    return `框 [${s.bbox.map((n) => Math.round(n)).join(', ')}]`
  }
  if (s.type === 'polygon') return `多边形 ${s.points.length} 点`
  if (s.type === 'obb') {
    return `旋转框 ${Math.round(s.w)}×${Math.round(s.h)} ∠${Math.round(s.angle)}°`
  }
  if (s.type === 'keypoint') return `关键点 ×${s.points.length}`
  if (s.type === 'mask') {
    const n = s.strokes.reduce((a, st) => a + st.points.length, 0)
    return `笔刷 ${s.strokes.length} 笔 / ${n} 点`
  }
  return '整图分类'
}
