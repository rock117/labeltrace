import { useAuthBlobUrl } from '../hooks/useAuthBlobUrl'

type Props = {
  assetId: string
  alt?: string
  className?: string
}

/** 带鉴权拉取素材内容，供 <img> 使用。 */
export function AuthImage({ assetId, alt = '', className }: Props) {
  const { url, error } = useAuthBlobUrl(assetId)

  if (error) {
    return (
      <div
        className={className}
        style={{
          width: '100%',
          height: '100%',
          minHeight: 120,
          background: 'var(--lt-bg-muted)',
        }}
      />
    )
  }
  if (!url) {
    return (
      <div
        className={className}
        style={{
          width: '100%',
          height: '100%',
          minHeight: 120,
          background: 'var(--lt-bg-canvas)',
        }}
      />
    )
  }
  return <img src={url} alt={alt} className={className} />
}
