import { Fragment, useEffect, useRef, useState } from 'react'
import {
  Stage,
  Layer,
  Image as KonvaImage,
  Rect,
  Transformer,
  Label,
  Tag,
  Text,
} from 'react-konva'
import type Konva from 'konva'
import type { DatasetClass, RectShape } from '../lib/types'
import type { AnnotationToolType } from './toolRegistry'

function resolveColor(cls: DatasetClass | undefined, fallbackIdx: number): string {
  if (cls?.color) return cls.color
  const el = document.documentElement
  const key = `--lt-class-${fallbackIdx % 5}`
  return getComputedStyle(el).getPropertyValue(key).trim() || '#0f766e'
}

type Props = {
  imageUrl: string
  naturalWidth: number
  naturalHeight: number
  shapes: RectShape[]
  classes: DatasetClass[]
  activeClassId: string | null
  /** P0 仅 rect；多工具时由工具栏切换 */
  activeTool: AnnotationToolType
  /** 版本快照浏览时为 true：不可绘制/拖拽 */
  readOnly?: boolean
  onChange: (shapes: RectShape[]) => void
}

export function AnnotatorCanvas({
  imageUrl,
  naturalWidth,
  naturalHeight,
  shapes,
  classes,
  activeClassId,
  activeTool,
  readOnly = false,
  onChange,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [img, setImg] = useState<HTMLImageElement | null>(null)
  const [scale, setScale] = useState(1)
  const [stageSize, setStageSize] = useState({ w: 640, h: 480 })
  const [drawing, setDrawing] = useState<{ x: number; y: number } | null>(null)
  const [draft, setDraft] = useState<[number, number, number, number] | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const trRef = useRef<Konva.Transformer>(null)
  const shapeRefs = useRef<(Konva.Rect | null)[]>([])

  const byId = new Map(classes.map((c) => [c.id, c]))

  useEffect(() => {
    const image = new window.Image()
    image.onload = () => setImg(image)
    image.src = imageUrl
  }, [imageUrl])

  useEffect(() => {
    const el = containerRef.current
    if (!el || !naturalWidth) return
    const fit = () => {
      const pad = 16
      const maxW = Math.max(320, el.clientWidth - pad)
      const maxH = Math.max(240, window.innerHeight - 220)
      const s = Math.min(maxW / naturalWidth, maxH / naturalHeight, 1.5)
      setScale(s)
      setStageSize({ w: naturalWidth * s, h: naturalHeight * s })
    }
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(el)
    return () => ro.disconnect()
  }, [naturalWidth, naturalHeight])

  useEffect(() => {
    const tr = trRef.current
    if (!tr) return
    if (readOnly || selected == null || !shapeRefs.current[selected]) {
      tr.nodes([])
      tr.getLayer()?.batchDraw()
      return
    }
    tr.nodes([shapeRefs.current[selected]!])
    tr.getLayer()?.batchDraw()
  }, [selected, shapes, readOnly])

  const toImage = (sx: number, sy: number) => [sx / scale, sy / scale] as const

  const onMouseDown = (e: Konva.KonvaEventObject<MouseEvent>) => {
    if (readOnly || activeTool !== 'rect' || !activeClassId) return
    const stage = e.target.getStage()
    if (!stage) return
    const kind = e.target.getClassName()
    if (
      kind === 'Rect' ||
      kind === 'Transformer' ||
      kind === 'Label' ||
      kind === 'Tag' ||
      kind === 'Text'
    ) {
      return
    }
    setSelected(null)
    const pos = stage.getPointerPosition()
    if (!pos) return
    setDrawing({ x: pos.x, y: pos.y })
    setDraft([pos.x, pos.y, pos.x, pos.y])
  }

  const onMouseMove = (e: Konva.KonvaEventObject<MouseEvent>) => {
    if (!drawing) return
    const pos = e.target.getStage()?.getPointerPosition()
    if (!pos) return
    setDraft([drawing.x, drawing.y, pos.x, pos.y])
  }

  const onMouseUp = () => {
    if (!drawing || !draft || !activeClassId) {
      setDrawing(null)
      setDraft(null)
      return
    }
    const [x1s, y1s, x2s, y2s] = draft
    const [x1, y1] = toImage(Math.min(x1s, x2s), Math.min(y1s, y2s))
    const [x2, y2] = toImage(Math.max(x1s, x2s), Math.max(y1s, y2s))
    setDrawing(null)
    setDraft(null)
    if (x2 - x1 < 4 || y2 - y1 < 4) return
    onChange([
      ...shapes,
      { type: 'rect', classId: activeClassId, bbox: [x1, y1, x2, y2] },
    ])
  }

  const updateBox = (index: number, node: Konva.Rect) => {
    const sx = node.x() / scale
    const sy = node.y() / scale
    const sw = (node.width() * node.scaleX()) / scale
    const sh = (node.height() * node.scaleY()) / scale
    node.scaleX(1)
    node.scaleY(1)
    const next = shapes.map((s, i) =>
      i === index
        ? {
            ...s,
            bbox: [sx, sy, sx + sw, sy + sh] as [number, number, number, number],
          }
        : s,
    )
    onChange(next)
  }

  const activeCls = activeClassId ? byId.get(activeClassId) : undefined
  const activeIdx = classes.findIndex((c) => c.id === activeClassId)

  return (
    <div ref={containerRef} style={{ width: '100%', minHeight: 320 }}>
      <Stage
        width={stageSize.w}
        height={stageSize.h}
        onMouseDown={onMouseDown}
        onMousemove={onMouseMove}
        onMouseup={onMouseUp}
        onMouseLeave={onMouseUp}
        style={{
          background: 'var(--lt-bg-muted)',
          borderRadius: 8,
          cursor: readOnly ? 'default' : 'crosshair',
        }}
      >
        <Layer>
          {img ? (
            <KonvaImage image={img} width={stageSize.w} height={stageSize.h} />
          ) : null}
          {shapes.map((s, i) => {
            if (!s.classId) return null
            const cls = byId.get(s.classId)
            const idx = classes.findIndex((c) => c.id === s.classId)
            const color = resolveColor(cls, idx >= 0 ? idx : i)
            const label = cls?.name ?? s.classId.slice(0, 8)
            const [x1, y1, x2, y2] = s.bbox
            return (
              <Fragment key={i}>
                <Rect
                  ref={(node) => {
                    shapeRefs.current[i] = node
                  }}
                  x={x1 * scale}
                  y={y1 * scale}
                  width={(x2 - x1) * scale}
                  height={(y2 - y1) * scale}
                  stroke={color}
                  strokeWidth={2}
                  fill={`${color}33`}
                  draggable={!readOnly}
                  onClick={() => !readOnly && setSelected(i)}
                  onTap={() => !readOnly && setSelected(i)}
                  onDragEnd={(e) => updateBox(i, e.target as Konva.Rect)}
                  onTransformEnd={(e) => updateBox(i, e.target as Konva.Rect)}
                />
                <Label x={x1 * scale} y={Math.max(0, y1 * scale - 18)}>
                  <Tag fill={color} opacity={0.9} />
                  <Text
                    text={label}
                    fontSize={11}
                    fill="#fff"
                    padding={3}
                    fontFamily="ui-sans-serif, system-ui"
                  />
                </Label>
              </Fragment>
            )
          })}
          {draft ? (
            <Rect
              x={Math.min(draft[0], draft[2])}
              y={Math.min(draft[1], draft[3])}
              width={Math.abs(draft[2] - draft[0])}
              height={Math.abs(draft[3] - draft[1])}
              stroke={resolveColor(activeCls, activeIdx >= 0 ? activeIdx : 0)}
              dash={[4, 4]}
              strokeWidth={1.5}
            />
          ) : null}
          {!readOnly ? (
            <Transformer
              ref={trRef}
              rotateEnabled={false}
              boundBoxFunc={(oldBox, newBox) =>
                newBox.width < 4 || newBox.height < 4 ? oldBox : newBox
              }
            />
          ) : null}
        </Layer>
      </Stage>
    </div>
  )
}

export function classColorCss(cls: DatasetClass | undefined, idx: number): string {
  if (cls?.color) return cls.color
  return `var(--lt-class-${idx % 5})`
}
