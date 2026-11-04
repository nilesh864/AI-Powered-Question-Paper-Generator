import { lazy, Suspense, useState } from 'react'
import { motion } from 'framer-motion'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Navbar from './components/Navbar.jsx'
import Sidebar from './components/Sidebar.jsx'
import { useAuth } from './context/AuthContext.jsx'

const AuthPage = lazy(() => import('./pages/AuthPage.jsx'))
const Dashboard = lazy(() => import('./pages/Dashboard.jsx'))
const KnowledgeBase = lazy(() => import('./pages/KnowledgeBase.jsx'))
const LandingPage = lazy(() => import('./pages/LandingPage.jsx'))
const PaperEditor = lazy(() => import('./pages/PaperEditor.jsx'))
const PaperGeneratorWizard = lazy(() => import('./pages/PaperGeneratorWizard.jsx'))
const PaperHistory = lazy(() => import('./pages/PaperHistory.jsx'))

function RequireAuth({ children }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="page-content" aria-label="Checking session" />
  return user ? children : <Navigate to="/login" replace state={{ from: location }} />
}

function Workspace({ children }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()
  return <div className="app-shell"><Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} /><div className="app-main"><Navbar onMenu={() => setMenuOpen(true)} /><motion.div className="route-view" key={location.pathname} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }}><Suspense fallback={<div className="page-content" aria-label="Loading page" />} >{children}</Suspense></motion.div></div></div>
}

export default function App() {
  return <Suspense fallback={<div className="page-content" aria-label="Loading page" />}><Routes><Route path="/" element={<LandingPage />} /><Route path="/login" element={<AuthPage />} /><Route path="/auth" element={<Navigate to="/login" replace />} /><Route path="/dashboard/*" element={<RequireAuth><Navigate to="/app" replace /></RequireAuth>} /><Route path="/documents/*" element={<RequireAuth><Navigate to="/app/knowledge" replace /></RequireAuth>} /><Route path="/generate/*" element={<RequireAuth><Navigate to="/app/generate" replace /></RequireAuth>} /><Route path="/history/*" element={<RequireAuth><Navigate to="/app/history" replace /></RequireAuth>} /><Route path="/app" element={<RequireAuth><Workspace><Dashboard /></Workspace></RequireAuth>} /><Route path="/app/knowledge" element={<RequireAuth><Workspace><KnowledgeBase /></Workspace></RequireAuth>} /><Route path="/app/generate" element={<RequireAuth><Workspace><PaperGeneratorWizard /></Workspace></RequireAuth>} /><Route path="/app/editor/:paperId" element={<RequireAuth><Workspace><PaperEditor /></Workspace></RequireAuth>} /><Route path="/app/history" element={<RequireAuth><Workspace><PaperHistory /></Workspace></RequireAuth>} /><Route path="*" element={<Navigate to="/" replace />} /></Routes></Suspense>
}