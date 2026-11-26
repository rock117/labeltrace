import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './layout/AppShell'
import { ProjectsPage } from './pages/ProjectsPage'
import { LibraryPage } from './pages/LibraryPage'
import { DatasetsPage } from './pages/DatasetsPage'
import { AnnotatePage } from './pages/AnnotatePage'
import { VersionsPage } from './pages/VersionsPage'
import { useAppStore } from './store/appStore'
import './styles/tokens.css'
import './styles/base.css'
import './styles/components.css'

function HomeRedirect() {
  const projectId = useAppStore((s) => s.projectId)
  return <Navigate to={projectId ? '/library' : '/projects'} replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<HomeRedirect />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="library" element={<LibraryPage />} />
          <Route path="datasets" element={<DatasetsPage />} />
          <Route path="annotate" element={<AnnotatePage />} />
          <Route path="versions" element={<VersionsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
