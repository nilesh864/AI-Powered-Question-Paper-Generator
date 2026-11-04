import { BookOpenCheck, Boxes, ChartNoAxesCombined, Clock3, FileQuestion, GraduationCap, PanelLeftClose } from 'lucide-react'
import { NavLink, useLocation } from 'react-router-dom'

const links = [
  { to: '/app', label: 'Overview', icon: ChartNoAxesCombined, end: true },
  { to: '/app/knowledge', label: 'Knowledge base', icon: Boxes },
  { to: '/app/generate', label: 'Paper generator', icon: FileQuestion },
  { to: '/app/history', label: 'Paper history', icon: Clock3 },
]

export default function Sidebar({ open, onClose }) {
  const location = useLocation()
  return <>
    <button className={`sidebar-scrim ${open ? 'visible' : ''}`} onClick={onClose} aria-label="Close navigation" />
    <aside className={`sidebar ${open ? 'open' : ''}`}>
      <NavLink to="/" className="brand" onClick={onClose}><span className="brand-mark"><GraduationCap size={21} /></span><span>question<span className="brand-light">paper</span><small>STUDIO / FACULTY</small></span></NavLink>
      <div className="workspace-switch"><span className="workspace-avatar">F</span><span><b>Faculty workspace</b><small>Authenticated account</small></span><PanelLeftClose size={15} /></div>
      <div className="nav-label">WORKSPACE</div>
      <nav className="side-nav">{links.map(({ to, label, icon: Icon, end }) => <NavLink key={to} to={to} end={end} onClick={onClose} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><Icon size={18} strokeWidth={1.8} /><span>{label}</span></NavLink>)}</nav>
      <div className="sidebar-bottom"><div className="index-status"><span className="status-led" /><div><b>Private workspace</b><small>Data scoped to your account</small></div></div><div className="sidebar-foot"><BookOpenCheck size={16} /><span>Faculty tools</span><span className="version">v1.0</span></div></div>
      <span className="sr-only" aria-live="polite">{location.pathname}</span>
    </aside>
  </>
}