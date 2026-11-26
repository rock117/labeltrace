import { create } from 'zustand'

type AppStore = {
  ready: boolean
}

const useAppStore = create<AppStore>(() => ({
  ready: true,
}))

function App() {
  const ready = useAppStore((s) => s.ready)

  return (
    <main style={{ fontFamily: 'system-ui', padding: '2rem' }}>
      <h1>LabelTrace</h1>
      <p>前端骨架已就绪（React + Vite + Zustand + Konva）。</p>
      <p>状态：{ready ? 'ok' : 'loading'}</p>
    </main>
  )
}

export default App
