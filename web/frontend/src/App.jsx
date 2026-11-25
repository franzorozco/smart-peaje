import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Alertas from './pages/Alertas'
import Casetas from './pages/Casetas'
import Chat from './pages/Chat'
import Dashboard from './pages/Dashboard'
import Estado from './pages/Estado'
import Login from './pages/Login'
import NoEncontrado from './pages/NoEncontrado'
import Pasos from './pages/Pasos'
import PruebaModelo from './pages/PruebaModelo'
import Tarifas from './pages/Tarifas'
import Usuarios from './pages/Usuarios'
import Vehiculos from './pages/Vehiculos'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="pasos" element={<Pasos />} />
        <Route path="alertas" element={<Alertas />} />
        <Route path="vehiculos" element={<Vehiculos />} />
        <Route path="chat" element={<Chat />} />
        <Route path="estado" element={<Estado />} />
        <Route path="pruebas/m1" element={<PruebaModelo modo="m1" />} />
        <Route path="pruebas/m2" element={<PruebaModelo modo="m2" />} />
        <Route path="pruebas/m3" element={<PruebaModelo modo="m3" />} />
        <Route path="pruebas/m4" element={<PruebaModelo modo="m4" />} />

        <Route
          path="tarifas"
          element={
            <ProtectedRoute adminOnly>
              <Tarifas />
            </ProtectedRoute>
          }
        />
        <Route
          path="casetas"
          element={
            <ProtectedRoute adminOnly>
              <Casetas />
            </ProtectedRoute>
          }
        />
        <Route
          path="usuarios"
          element={
            <ProtectedRoute adminOnly>
              <Usuarios />
            </ProtectedRoute>
          }
        />
      </Route>

      <Route path="*" element={<NoEncontrado />} />
    </Routes>
  )
}
