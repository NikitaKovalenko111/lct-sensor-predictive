import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { useAuth } from './context/AuthContext'
import { DataProvider } from './context/DataContext'
import { AdminPage } from './pages/AdminPage'
import { DashboardPage } from './pages/DashboardPage'
import { IncidentsPage } from './pages/IncidentsPage'
import { LoginPage } from './pages/LoginPage'
import { ObjectsPage } from './pages/ObjectsPage'
import { PredictionsPage } from './pages/PredictionsPage'
import { ReportsPage } from './pages/ReportsPage'

function ProtectedApp() {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />

  return (
    <DataProvider>
      <AppLayout />
    </DataProvider>
  )
}

function AdminRoute() {
  const { user } = useAuth()
  return user?.role === 'admin' ? <AdminPage /> : <Navigate to="/" replace />
}

export function App() {
  const { user, loading } = useAuth()
  if (loading) return <div className="app-loader"><span className="spinner" />Загрузка системы</div>

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <LoginPage />} />
      <Route element={<ProtectedApp />}>
        <Route index element={<DashboardPage />} />
        <Route path="predictions" element={<PredictionsPage />} />
        <Route path="incidents" element={<IncidentsPage />} />
        <Route path="objects" element={<ObjectsPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="admin" element={<AdminRoute />} />
      </Route>
      <Route path="*" element={<Navigate to={user ? '/' : '/login'} replace />} />
    </Routes>
  )
}
