import { Fragment, useEffect, useRef, useState } from 'react'
import {
  Stage,
  Layer,
  Image as KonvaImage,
  Rect,
  Line,
  Circle,
  Transformer,
  Label,
  Tag,
  Text,
  Group,
} from 'react-konva'
import type Konva from 'konva'
import type { DatasetClass } from '../lib/types'
import type { AnnotationShape } from '../lib/annotationShapes'
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
  shapes: AnnotationShape[]
  classes: DatasetClass[]
  activeClassId: string | null
  activeTool: AnnotationToolType
  readOnly?: boolean
  selectedIndex: number | null
  onSelect: (index: number | null) => void
  onChange: (shapes: AnnotationShape[]) => void
  brushWidth?: number
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
  selectedIndex,
  onSelect,
  onChange,
  brushWidth = 18,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [img, setImg] = useState<HTMLImageElement | null>(null)
  const [scale, setScale] = useState(1)
  const [stageSize, setStageSize] = useState({ w: 640, h: 480 })
  const [drawingRect, setDrawingRect] = useState<{
    x: number
    y: number
  } | null>(null)
  const [draftRect, setDraftRect] = useState<
    [number, number, number, number] | null
  >(null)
  const [polyDraft, setPolyDraft] = useState<[number, number][]>([])
  const [polyCursor, setPolyCursor] = useState<[number, number] | null>(null)
  const [hoverClose, setHoverClose] = useState(false)
  const [brushDraft, setBrushDraft] = useState<[number, number][] | null>(null)
  const trRef = useRef<Konva.Transformer>(null)
  const nodeRefs = useRef<(Konva.Node | null)[]>([])

  const byId = new Map(classes.map((c) => [c.id, c]))
  const canDraw =
    !readOnly &&
    Boolean(activeClassId) &&
    activeTool !== 'classification'

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
    setPolyDraft([])
    setPolyCursor(null)
    setHoverClose(false)
    setBrushDraft(null)
    setDrawingRect(null)
    setDraftRect(null)
  }, [activeTool, imageUrl, activeClassId])

  useEffect(() => {
    const tr = trRef.current
    if (!tr) return
    const node =
      selectedIndex != null ? nodeRefs.current[selectedIndex] : null
    const shape = selectedIndex != null ? shapes[selectedIndex] : null
    const transformable =
      !readOnly &&
      node &&
      shape &&
      (shape.type === 'rect' || shape.type === 'obb')
    if (!transformable) {
      tr.nodes([])
      tr.getLayer()?.batchDraw()
      return
    }
    tr.nodes([node])
    tr.rotateEnabled(shape.type === 'obb')
    tr.getLayer()?.batchDraw()
  }, [selectedIndex, shapes, readOnly])

  const finishPolygon = () => {
    if (!activeClassId || polyDraft.length < 3) return
    onChange([
      ...shapes,
      { type: 'polygon', classId: activeClassId, points: polyDraft },
    ])
    setPolyDraft([])
    setPolyCursor(null)
    setHoverClose(false)
  }

  const cancelPolygon = () => {
    setPolyDraft([])
    setPolyCursor(null)
    setHoverClose(false)
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return
      if (e.key === 'Escape') {
        cancelPolygon()
        setBrushDraft(null)
        setDrawingRect(null)
        setDraftRect(null)
        onSelect(null)
      }
      if (
        (e.key === 'Enter' || e.key === 'NumpadEnter') &&
        activeTool === 'polygon' &&
        polyDraft.length >= 3
      ) {
        e.preventDefault()
        finishPolygon()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTool, polyDraft, activeClassId, shapes, onChange, onSelect])

  const toImage = (sx: number, sy: number) =>
    [sx / scale, sy / scale] as [number, number]

  const nearFirstVertex = (ix: number, iy: number) => {
    if (polyDraft.length < 3) return false
    const [fx, fy] = polyDraft[0]
    const thresh = 12 / scale
    const dx = ix - fx
    const dy = iy - fy
    return dx * dx + dy * dy <= thresh * thresh
  }

  const hitUI = (e: Konva.KonvaEventObject<MouseEvent>) => {
    const kind = e.target.getClassName()
    return (
      kind === 'Transformer' ||
      kind === 'Label' ||
      kind === 'Tag' ||
      kind === 'Text'
    )
  }

  const onMouseDown = (e: Konva.KonvaEventObject<MouseEvent>) => {
    if (!canDraw || !activeClassId) return
    if (hitUI(e)) return
    const stage = e.target.getStage()
    if (!stage) return
    const pos = stage.getPointerPosition()
    if (!pos) return
    const [ix, iy] = toImage(pos.x, pos.y)

    if (activeTool === 'rect' || activeTool === 'obb') {
      if (
        e.target.getClassName() === 'Rect' ||
        e.target.getClassName() === 'Group'
      ) {
        return
      }
      onSelect(null)
      setDrawingRect({ x: pos.x, y: pos.y })
      setDraftRect([pos.x, pos.y, pos.x, pos.y])
      return
    }

    if (activeTool === 'polygon') {
      const name = e.target.name?.() ?? ''
      // 已完成多边形被点中 → 选中，不加点
      if (
        (e.target.getClassName() === 'Line' ||
          e.target.getClassName() === 'Circle') &&
        !name.startsWith('poly-draft')
      ) {
        return
      }
      onSelect(null)
      // 点回起点（或起点大圆）→ 闭合
      if (name === 'poly-draft-0' || nearFirstVertex(ix, iy)) {
        finishPolygon()
        return
      }
      setPolyDraft((prev) => [...prev, [ix, iy]])
      return
    }

    if (activeTool === 'keypoint') {
      onSelect(null)
      const last = shapes[shapes.length - 1]
      if (
        last &&
        last.type === 'keypoint' &&
        last.classId === activeClassId
      ) {
        onChange([
          ...shapes.slice(0, -1),
          {
            ...last,
            points: [...last.points, { x: ix, y: iy, v: 2 as const }],
          },
        ])
      } else {
        onChange([
          ...shapes,
          {
            type: 'keypoint',
            classId: activeClassId,
            points: [{ x: ix, y: iy, v: 2 }],
          },
        ])
      }
      return
    }

    if (activeTool === 'mask') {
      onSelect(null)
      setBrushDraft([[ix, iy]])
    }
  }

  const onMouseMove = (e: Konva.KonvaEventObject<MouseEvent>) => {
    const pos = e.target.getStage()?.getPointerPosition()
    if (!pos) return
    const [ix, iy] = toImage(pos.x, pos.y)

    if (activeTool === 'polygon' && polyDraft.length > 0) {
      setPolyCursor([ix, iy])
    }
    if (drawingRect) {
      setDraftRect([drawingRect.x, drawingRect.y, pos.x, pos.y])
    }
    if (brushDraft) {
      setBrushDraft((prev) => (prev ? [...prev, [ix, iy]] : prev))
    }
  }

  const finishBrush = () => {
    if (!brushDraft || !activeClassId) {
      setBrushDraft(null)
      return
    }
    if (brushDraft.length < 1) {
      setBrushDraft(null)
      return
    }
    onChange([
      ...shapes,
      {
        type: 'mask',
        classId: activeClassId,
        strokes: [{ points: brushDraft, width: brushWidth }],
      },
    ])
    setBrushDraft(null)
  }

  const onMouseUp = () => {
    if (brushDraft) {
      finishBrush()
      return
    }
    if (!drawingRect || !draftRect || !activeClassId) {
      setDrawingRect(null)
      setDraftRect(null)
      return
    }
    const [x1s, y1s, x2s, y2s] = draftRect
    const [x1, y1] = toImage(Math.min(x1s, x2s), Math.min(y1s, y2s))
    const [x2, y2] = toImage(Math.max(x1s, x2s), Math.max(y1s, y2s))
    setDrawingRect(null)
    setDraftRect(null)
    if (x2 - x1 < 4 || y2 - y1 < 4) return
    if (activeTool === 'obb') {
      onChange([
        ...shapes,
        {
          type: 'obb',
          classId: activeClassId,
          cx: (x1 + x2) / 2,
          cy: (y1 + y2) / 2,
          w: x2 - x1,
          h: y2 - y1,
          angle: 0,
        },
      ])
      return
    }
    onChange([
      ...shapes,
      { type: 'rect', classId: activeClassId, bbox: [x1, y1, x2, y2] },
    ])
  }

  const updateRect = (index: number, node: Konva.Rect) => {
    const sx = node.x() / scale
    const sy = node.y() / scale
    const sw = (node.width() * node.scaleX()) / scale
    const sh = (node.height() * node.scaleY()) / scale
    node.scaleX(1)
    node.scaleY(1)
    onChange(
      shapes.map((s, i) =>
        i === index && s.type === 'rect'
          ? { ...s, bbox: [sx, sy, sx + sw, sy + sh] as [number, number, number, number] }
          : s,
      ),
    )
  }

  const updateObb = (index: number, node: Konva.Rect) => {
    const s = shapes[index]
    if (!s || s.type !== 'obb') return
    const w = (node.width() * node.scaleX()) / scale
    const h = (node.height() * node.scaleY()) / scale
    node.scaleX(1)
    node.scaleY(1)
    onChange(
      shapes.map((item, i) =>
        i === index && item.type === 'obb'
          ? {
              ...item,
              cx: node.x() / scale,
              cy: node.y() / scale,
              w: Math.max(2, w),
              h: Math.max(2, h),
              angle: node.rotation(),
            }
          : item,
      ),
    )
  }

  const activeCls = activeClassId ? byId.get(activeClassId) : undefined
  const activeIdx = classes.findIndex((c) => c.id === activeClassId)
  const activeColor = resolveColor(activeCls, activeIdx >= 0 ? activeIdx : 0)

  const cursor =
    readOnly || activeTool === 'classification'
      ? 'default'
      : activeTool === 'mask'
        ? 'cell'
        : 'crosshair'

  return (
    <div ref={containerRef} style={{ width: '100%', minHeight: 320 }}>
      {activeTool === 'polygon' && !readOnly && polyDraft.length > 0 ? (
        <div
          style={{
            display: 'flex',
            gap: 8,
            alignItems: 'center',
            flexWrap: 'wrap',
            marginBottom: 8,
            fontSize: 13,
            color: 'var(--lt-fg-muted)',
          }}
        >
          <span>
            已点 {polyDraft.length} 个角
            {polyDraft.length >= 3
              ? ' · 悬停起点变红后单击闭合，或 Enter /「完成」'
              : ' · 至少 3 点才能闭合'}
          </span>
          <button
            type="button"
            className="lt-btn lt-btn-primary"
            disabled={polyDraft.length < 3}
            onClick={finishPolygon}
          >
            完成
          </button>
          <button type="button" className="lt-btn" onClick={cancelPolygon}>
            取消
          </button>
        </div>
      ) : null}
      <Stage
        width={stageSize.w}
        height={stageSize.h}
        onMouseDown={onMouseDown}
        onMousemove={onMouseMove}
        onMouseup={onMouseUp}
        onDblClick={() => {
          if (activeTool === 'polygon' && polyDraft.length >= 3) {
            finishPolygon()
          }
        }}
        onMouseLeave={() => {
          if (brushDraft) finishBrush()
          else onMouseUp()
        }}
        style={{
          background: 'var(--lt-bg-muted)',
          borderRadius: 8,
          cursor,
        }}
      >
        <Layer>
          {img ? (
            <KonvaImage image={img} width={stageSize.w} height={stageSize.h} />
          ) : null}

          {shapes.map((s, i) => {
            const cls = byId.get(s.classId)
            const idx = classes.findIndex((c) => c.id === s.classId)
            const color = resolveColor(cls, idx >= 0 ? idx : i)
            const label = cls?.name ?? s.classId.slice(0, 8)
            const selected = selectedIndex === i

            if (s.type === 'rect') {
              const [x1, y1, x2, y2] = s.bbox
              return (
                <Fragment key={i}>
                  <Rect
                    ref={(node) => {
                      nodeRefs.current[i] = node
                    }}
                    x={x1 * scale}
                    y={y1 * scale}
                    width={(x2 - x1) * scale}
                    height={(y2 - y1) * scale}
                    stroke={color}
                    strokeWidth={selected ? 3 : 2}
                    fill={`${color}33`}
                    draggable={!readOnly}
                    onClick={(e) => {
                      e.cancelBubble = true
                      if (!readOnly) onSelect(i)
                    }}
                    onTap={(e) => {
                      e.cancelBubble = true
                      if (!readOnly) onSelect(i)
                    }}
                    onDragEnd={(e) => updateRect(i, e.target as Konva.Rect)}
                    onTransformEnd={(e) => updateRect(i, e.target as Konva.Rect)}
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
            }

            if (s.type === 'polygon') {
              const flat = s.points.flatMap(([x, y]) => [x * scale, y * scale])
              return (
                <Fragment key={i}>
                  <Line
                    ref={(node) => {
                      nodeRefs.current[i] = node
                    }}
                    points={flat}
                    closed
                    stroke={color}
                    strokeWidth={selected ? 3 : 2}
                    fill={`${color}44`}
                    onClick={(e) => {
                      e.cancelBubble = true
                      if (!readOnly) onSelect(i)
                    }}
                  />
                  <Label
                    x={s.points[0][0] * scale}
                    y={Math.max(0, s.points[0][1] * scale - 18)}
                  >
                    <Tag fill={color} opacity={0.9} />
                    <Text text={label} fontSize={11} fill="#fff" padding={3} />
                  </Label>
                </Fragment>
              )
            }

            if (s.type === 'obb') {
              return (
                <Fragment key={i}>
                  <Rect
                    ref={(node) => {
                      nodeRefs.current[i] = node
                    }}
                    x={s.cx * scale}
                    y={s.cy * scale}
                    width={s.w * scale}
                    height={s.h * scale}
                    offsetX={(s.w * scale) / 2}
                    offsetY={(s.h * scale) / 2}
                    rotation={s.angle}
                    stroke={color}
                    strokeWidth={selected ? 3 : 2}
                    fill={`${color}33`}
                    draggable={!readOnly}
                    onClick={(e) => {
                      e.cancelBubble = true
                      if (!readOnly) onSelect(i)
                    }}
                    onDragEnd={(e) => updateObb(i, e.target as Konva.Rect)}
                    onTransformEnd={(e) => updateObb(i, e.target as Konva.Rect)}
                  />
                  <Label
                    x={s.cx * scale - 20}
                    y={Math.max(0, s.cy * scale - s.h * scale * 0.5 - 18)}
                  >
                    <Tag fill={color} opacity={0.9} />
                    <Text text={label} fontSize={11} fill="#fff" padding={3} />
                  </Label>
                </Fragment>
              )
            }

            if (s.type === 'keypoint') {
              return (
                <Group
                  key={i}
                  ref={(node) => {
                    nodeRefs.current[i] = node
                  }}
                  onClick={(e) => {
                    e.cancelBubble = true
                    if (!readOnly) onSelect(i)
                  }}
                >
                  {s.points.length > 1 ? (
                    <Line
                      points={s.points.flatMap((p) => [
                        p.x * scale,
                        p.y * scale,
                      ])}
                      stroke={color}
                      strokeWidth={1.5}
                      dash={[4, 4]}
                    />
                  ) : null}
                  {s.points.map((p, pi) => (
                    <Circle
                      key={pi}
                      x={p.x * scale}
                      y={p.y * scale}
                      radius={selected ? 6 : 5}
                      fill={color}
                      stroke="#fff"
                      strokeWidth={1}
                    />
                  ))}
                  <Label
                    x={s.points[0].x * scale}
                    y={Math.max(0, s.points[0].y * scale - 18)}
                  >
                    <Tag fill={color} opacity={0.9} />
                    <Text text={label} fontSize={11} fill="#fff" padding={3} />
                  </Label>
                </Group>
              )
            }

            if (s.type === 'mask') {
              return (
                <Group
                  key={i}
                  ref={(node) => {
                    nodeRefs.current[i] = node
                  }}
                  onClick={(e) => {
                    e.cancelBubble = true
                    if (!readOnly) onSelect(i)
                  }}
                >
                  {s.strokes.map((st, si) => (
                    <Line
                      key={si}
                      points={st.points.flatMap(([x, y]) => [
                        x * scale,
                        y * scale,
                      ])}
                      stroke={color}
                      strokeWidth={st.width * scale}
                      lineCap="round"
                      lineJoin="round"
                      opacity={selected ? 0.85 : 0.65}
                      tension={0.2}
                    />
                  ))}
                </Group>
              )
            }

            nodeRefs.current[i] = null
            return null
          })}

          {polyDraft.length > 0 ? (
            <Line
              points={[
                ...polyDraft.flatMap(([x, y]) => [x * scale, y * scale]),
                ...(polyCursor
                  ? [polyCursor[0] * scale, polyCursor[1] * scale]
                  : []),
              ]}
              stroke={activeColor}
              strokeWidth={1.5}
              dash={[6, 4]}
            />
          ) : null}
          {polyDraft.map(([x, y], i) => {
            const isFirst = i === 0
            const canClose = polyDraft.length >= 3 && isFirst
            const hot = canClose && hoverClose
            return (
              <Circle
                key={`pd-${i}`}
                name={`poly-draft-${i}`}
                x={x * scale}
                y={y * scale}
                radius={hot ? 10 : 4}
                fill={hot ? '#dc2626' : activeColor}
                stroke={hot ? '#fff' : undefined}
                strokeWidth={hot ? 2 : 0}
                hitStrokeWidth={canClose ? 16 : 0}
                onMouseEnter={() => {
                  if (canClose) setHoverClose(true)
                }}
                onMouseLeave={() => setHoverClose(false)}
                onMouseDown={(ev) => {
                  if (!canClose) return
                  ev.cancelBubble = true
                  finishPolygon()
                }}
              />
            )
          })}

          {brushDraft && brushDraft.length > 0 ? (
            <Line
              points={brushDraft.flatMap(([x, y]) => [x * scale, y * scale])}
              stroke={activeColor}
              strokeWidth={brushWidth * scale}
              lineCap="round"
              lineJoin="round"
              opacity={0.7}
            />
          ) : null}

          {draftRect ? (
            <Rect
              x={Math.min(draftRect[0], draftRect[2])}
              y={Math.min(draftRect[1], draftRect[3])}
              width={Math.abs(draftRect[2] - draftRect[0])}
              height={Math.abs(draftRect[3] - draftRect[1])}
              stroke={activeColor}
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
