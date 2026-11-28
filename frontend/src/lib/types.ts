export type Project = { id: string; name: string }

export type Folder = {
  id: string
  project_id: string
  parent_id: string | null
  name: string
  path: string
  /** 该目录内直接存放的库可见视频 / 图片数 */
  video_count?: number
  image_count?: number
}

export type Asset = {
  id: string
  project_id: string
  media_kind: 'image' | 'video' | 'frame'
  folder_id: string | null
  library_visible: boolean
  origin: string
  content_hash: string
  storage_backend: string
  storage_key: string
  filename: string
  mime: string | null
  width: number | null
  height: number | null
  duration_ms: number | null
  fps: number | null
  parent_video_id: string | null
  frame_index: number | null
  extract_job_id: string | null
  /** 目录列表：该视频是否已有成功抽帧任务 */
  extracted?: boolean
}

export type AssetsPage = {
  items: Asset[]
  total: number
  limit: number
  offset: number
}

export type ExtractJob = {
  id: string
  project_id: string
  video_asset_id: string
  job_id: string | null
  mode: string
  stride: number | null
  interval_ms: number | null
  options: Record<string, unknown>
  status: string
  stats: Record<string, unknown>
  error_message: string | null
  created_by: string
}

/** 项目级抽帧任务（数据集入集用） */
export type ProjectExtractJob = {
  id: string
  project_id: string
  video_asset_id: string
  video_filename: string | null
  mode: string
  stride: number | null
  interval_ms: number | null
  status: string
  stats: Record<string, unknown>
  remaining_frame_count: number
  in_dataset_count: number | null
  created_by: string
  created_at: string | null
}

export type FrameCandidate = {
  id: string
  frame_index: number | null
  time_ms: number
  time_label: string
  filename: string
  extract_job_id: string | null
  parent_video_id: string | null
}

export type ProjectClass = {
  id: string
  project_id: string
  name: string
  color?: string | null
}

export type Tag = {
  id: string
  project_id: string
  name: string
}

/** 按标签筛选返回的库可见素材摘要 */
export type TaggedAsset = {
  id: string
  filename: string
  media_kind: 'image' | 'video' | string
  folder_id: string | null
}

export type DatasetClass = {
  id: string
  name: string
  idx: number
  color?: string | null
}

export type Dataset = {
  id: string
  project_id: string
  name: string
  classes: DatasetClass[]
  enabled_annotation_types: string[]
}

export type DatasetAsset = {
  asset_id: string
  split: string
  media_kind: string
  filename: string
  /** 工作区标注状态；无记录则为 null/undefined */
  annotation_status?: 'draft' | 'submitted' | null
}

export type MemberSource =
  | {
      kind: 'extract'
      extractJobId: string
      videoId: string | null
      videoName: string | null
      mode: string | null
      stride: number | null
      intervalMs: number | null
      frameCount: number
    }
  | { kind: 'upload'; imageCount: number }
  | {
      kind: 'import'
      importId: string | null
      packageName?: string | null
      imageCount: number
    }

export type RectShape = {
  type: 'rect'
  classId: string
  bbox: [number, number, number, number]
}

export type AnnotationShapes = {
  format: 'xyxy_abs'
  items: RectShape[]
}

export type Annotation = {
  dataset_id: string
  asset_id: string
  shapes: AnnotationShapes
  status: string
  updated_by: string
  updated_at: string | null
}

export type VersionClass = { id: string; name: string }

export type Version = {
  id: string
  dataset_id: string
  name: string
  parent_id: string | null
  classes: VersionClass[]
  enabled_annotation_types: unknown[]
  member_sources: unknown[]
  change_summary: {
    added?: number
    removed?: number
    changedAnnotations?: number
    split?: {
      seed?: number | null
      ratios?: { train?: number; val?: number; test?: number }
      counts?: { train?: number; val?: number; test?: number }
    }
  } | null
  created_by: string
  note: string | null
  created_at: string
  entry_count: number
}

export type VersionManifestEntry = {
  assetId: string
  contentHash?: string
  split: string
  mediaKind: string
  filename: string
  shapes: AnnotationShapes
  annotationStatus?: string
  parentVideoId?: string | null
  frameIndex?: number | null
}

export type VersionManifest = {
  entries: VersionManifestEntry[]
}

export type AssetLineage = {
  assetId: string
  origin: string
  importId: string | null
  path: string | null
  filename: string
  mediaKind: string
  libraryVisible: boolean
  tags: { id: string; name: string }[]
  datasets: {
    datasetId: string
    name: string
    split: string
    annotationUpdatedBy: string | null
    annotationUpdatedAt: string | null
  }[]
  versions: { versionId: string; name: string; datasetId: string }[]
  parentVideoId?: string | null
  frameIndex?: number | null
  extractJobId?: string | null
}
