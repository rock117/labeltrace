import { useEffect, useRef, useState } from 'react'
import { Stage, Layer, Image as KonvaImage, Rect, Transformer } from 'react-konva'
import type Konva from 'konva'
import type { RectShape } from '../lib/types'

const CLASS_COLORS = [
  'var(--lt-class-0)',
  'var(--lt-class-1)',
  'var(--lt-class-2)',
  'var(--lt-class-3)',
  'var(--lt-class-4)',
]

function resolveColor(cls: number): string {
  const el = document.documentElement
  const key = `--lt-class-${cls % 5}`
  return getComputedStyle(el).getPropertyValue(key).trim() || '#0f766e'
}

type Props = {
  imageUrl: string
  naturalWidth: number
  naturalHeight: number
  shapes: RectShape[]
  activeClass: number
  onChange: (shapes: RectShape[]) => void
}

export function AnnotatorCanvas({
  imageUrl,
  naturalWidth,
  naturalHeight,
  shapes,
  activeClass,
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
    if (selected == null || !shapeRefs.current[selected]) {
      tr.nodes([])
      tr.getLayer()?.batchDraw()
      return
    }
    tr.nodes([shapeRefs.current[selected]!])
    tr.getLayer()?.batchDraw()
  }, [selected, shapes])

  const toImage = (sx: number, sy: number) => [sx / scale, sy / scale] as const

  const onMouseDown = (e: Konva.KonvaEventObject<MouseEvent>) => {
    const stage = e.target.getStage()
    if (!stage) return
    // 图铺满 Stage 时点击落在 Image 上；仅在点到已有框/变换器时不新画
    const kind = e.target.getClassName()
    if (kind === 'Rect' || kind === 'Transformer') return
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
    if (!drawing || !draft) {
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
      { type: 'rect', cls: activeClass, bbox: [x1, y1, x2, y2] },
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

  void CLASS_COLORS

  return (
    <div
      ref={containerRef}
      style={{
        background: 'var(--lt-bg-canvas)',
        borderRadius: 'var(--lt-radius-lg)',
        border: '1px solid var(--lt-border)',
        overflow: 'auto',
        minHeight: 320,
        position: 'relative',
      }}
    >
      {shapes.length === 0 && !drawing ? (
        <div
          style={{
            position: 'absolute',
            left: 12,
            top: 12,
            zIndex: 2,
            pointerEvents: 'none',
            padding: '0.35rem 0.6rem',
            borderRadius: 'var(--lt-radius)',
            background: 'color-mix(in srgb, var(--lt-bg-elevated) 92%, transparent)',
            border: '1px solid var(--lt-border)',
            color: 'var(--lt-fg-muted)',
            fontSize: 13,
          }}
        >
          在图上按住拖拽即可画检测框
        </div>
      ) : null}
      <Stage
        width={stageSize.w}
        height={stageSize.h}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
        style={{ margin: '0 auto', display: 'block', cursor: 'crosshair' }}
      >
        <Layer>
          {img ? (
            <KonvaImage image={img} width={stageSize.w} height={stageSize.h} />
          ) : null}
          {shapes.map((s, i) => {
            const [x1, y1, x2, y2] = s.bbox
            const color = resolveColor(s.cls)
            return (
              <Rect
                key={i}
                ref={(n) => {
                  shapeRefs.current[i] = n
                }}
                x={x1 * scale}
                y={y1 * scale}
                width={(x2 - x1) * scale}
                height={(y2 - y1) * scale}
                stroke={color}
                strokeWidth={2}
                fill={`${color}33`}
                draggable
                onClick={() => setSelected(i)}
                onTap={() => setSelected(i)}
                onDragEnd={(e) => updateBox(i, e.target as Konva.Rect)}
                onTransformEnd={(e) => updateBox(i, e.target as Konva.Rect)}
              />
            )
          })}
          {draft ? (
            <Rect
              x={Math.min(draft[0], draft[2])}
              y={Math.min(draft[1], draft[3])}
              width={Math.abs(draft[2] - draft[0])}
              height={Math.abs(draft[3] - draft[1])}
              stroke={resolveColor(activeClass)}
              dash={[4, 4]}
              strokeWidth={1.5}
            />
          ) : null}
          <Transformer
            ref={trRef}
            rotateEnabled={false}
            boundBoxFunc={(oldBox, newBox) =>
              newBox.width < 8 || newBox.height < 8 ? oldBox : newBox
            }
          />
        </Layer>
      </Stage>
    </div>
  )
}

export function classColorCss(cls: number): string {
  return `var(--lt-class-${cls % 5})`
}
