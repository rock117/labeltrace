import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useAppStore } from '../store/appStore'
import { StateBlock } from './StateBlock'

export function RequireProject({ children }: { children: ReactNode }) {
  const projectId = useAppStore((s) => s.projectId)
  if (!projectId) {
    return (
      <StateBlock
        title="未选择项目"
        description="请先在「项目」页创建或选择一个项目，再使用素材库、数据集与标注台。"
        action={
          <Link to="/" className="lt-btn lt-btn-primary">
            前往项目
          </Link>
        }
      />
    )
  }
  return <>{children}</>
}
