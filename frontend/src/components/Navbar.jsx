import { useEffect, useMemo, useRef, useState } from 'react'
import { Bell, CheckCheck, FileCheck2, FileText, LogOut, Menu, Search, X } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { apiRequest, markWorkspaceEventsRead, readWorkspaceEvents, recordWorkspaceEvent } from '../services/api.js'

const quickLinks = [
  { label: 'Overview', path: '/app' },
  { label: 'Knowledge base', path: '/app/knowledge' },
  { label: 'Generate a paper', path: '/app/generate' },
  { label: 'Paper history', path: '/app/history' },
]

export default function Navbar({ onMenu }) {
  const { user, signOut } = useAuth()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [documents, setDocuments] = useState([])
  const [papers, setPapers] = useState([])
  const [searchOpen, setSearchOpen] = useState(false)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [events, setEvents] = useState(readWorkspaceEvents)
  const searchRef = useRef(null)
  const pageName = pathname.startsWith('/app/editor/') ? 'Paper studio' : pathname === '/app/knowledge' ? 'Knowledge base' : pathname === '/app/generate' ? 'Paper generator' : pathname === '/app/history' ? 'Paper history' : 'Overview'
  const initials = user?.name.split(/\s+/).map((name) => name[0]).join('').slice(0, 2).toUpperCase() || '?'

  useEffect(() => {
    const refreshIndex = async () => {
      const [documentResult, paperResult] = await Promise.allSettled([apiRequest('/documents'), apiRequest('/generate/history')])
      if (documentResult.status === 'fulfilled') setDocuments(documentResult.value)
      if (paperResult.status === 'fulfilled') setPapers(paperResult.value)
    }
    const refreshEvents = () => {
      setEvents(readWorkspaceEvents())
      refreshIndex()
    }
    refreshIndex()
    window.addEventListener('qps:workspace-event', refreshEvents)
    window.addEventListener('storage', refreshEvents)
    if (!readWorkspaceEvents().length) recordWorkspaceEvent('System Ready', 'Workspace search and notifications are active')
    return () => {
      window.removeEventListener('qps:workspace-event', refreshEvents)
      window.removeEventListener('storage', refreshEvents)
    }
  }, [])

  useEffect(() => {
    const onKeyDown = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setSearchOpen(true)
        setNotificationsOpen(false)
        window.setTimeout(() => searchRef.current?.focus(), 0)
      }
      if (event.key === 'Escape') {
        setSearchOpen(false)
        setNotificationsOpen(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const searchResults = useMemo(() => {
    const term = query.trim().toLowerCase()
    if (!term) return []
    const documentResults = documents.filter((document) => [document.filename, document.subject, document.unit_label, document.category].some((value) => value?.toLowerCase().includes(term))).map((document) => ({
      id: `document-${document.id}`, kind: 'Document', title: document.filename, detail: [document.subject, document.unit_label, `${document.chunk_count || 0} chunks`].filter(Boolean).join(' · '), path: '/app/knowledge', icon: FileText,
    }))
    const paperResults = papers.filter((paper) => [paper.subject, paper.course_code, paper.title, ...(paper.questions || []).map((question) => question.text)].some((value) => value?.toLowerCase().includes(term))).map((paper) => ({
      id: `paper-${paper.id}`, kind: 'Question paper', title: paper.subject, detail: `${paper.course_code || 'Course'} · Set ${paper.set_label} · ${paper.questions?.length || 0} questions`, path: `/app/editor/${paper.id}`, icon: FileCheck2,
    }))
    return [...documentResults, ...paperResults].slice(0, 8)
  }, [documents, papers, query])

  const unreadCount = events.filter((event) => !event.read).length
  function go(path) {
    navigate(path)
    setSearchOpen(false)
    setQuery('')
  }
  function markAllRead() {
    markWorkspaceEventsRead()
    setEvents(readWorkspaceEvents())
  }

  return <header className="topbar">
    <button className="mobile-menu" onClick={onMenu} aria-label="Open navigation"><Menu size={19} /></button>
    <div className="breadcrumb"><span>Workspace</span><i>/</i><b>{pageName}</b></div>
    <div className="topbar-actions">
      <div className="nav-search-wrap">
        <button className="search-shortcut" aria-label="Search workspace" onClick={() => { setSearchOpen(true); setNotificationsOpen(false); window.setTimeout(() => searchRef.current?.focus(), 0) }}><Search size={15} /><span>Search anything...</span><kbd>⌘ K</kbd></button>
        {searchOpen && <div className="nav-popover search-popover">
          <div className="nav-search-input"><Search size={16} /><input ref={searchRef} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search documents, papers, subjects" aria-label="Search documents, papers, and subjects" /><button className="icon-button" onClick={() => setSearchOpen(false)} aria-label="Close search"><X size={15} /></button></div>
          {query.trim() ? <div className="nav-search-results">{searchResults.map((result) => { const Icon = result.icon; return <button className="nav-result" key={result.id} onClick={() => go(result.path)}><Icon size={16} /><span><b>{result.title}</b><small>{result.kind} · {result.detail}</small></span></button> })}{searchResults.length === 0 && <div className="nav-popover-empty">No matching documents or papers.</div>}</div> : <div className="nav-quick-links"><small>QUICK NAVIGATION</small>{quickLinks.map((item) => <button key={item.path} onClick={() => go(item.path)}>{item.label}</button>)}</div>}
        </div>}
      </div>
      <div className="nav-notifications-wrap">
        <button className="top-icon notification-trigger" aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ''}`} aria-expanded={notificationsOpen} onClick={() => { setNotificationsOpen((open) => !open); setSearchOpen(false) }}><Bell size={18} />{unreadCount > 0 && <i />}</button>
        {notificationsOpen && <div className="nav-popover notification-popover"><div className="notification-heading"><span><b>Notifications</b><small>{unreadCount ? `${unreadCount} unread` : 'All caught up'}</small></span><button className="mark-read" onClick={markAllRead} disabled={!unreadCount}><CheckCheck size={14} /> Mark all as read</button></div><div className="notification-list">{events.map((event) => <div className={`notification-item ${event.read ? 'read' : ''}`} key={event.id}><span className="notification-dot" /><span><b>{event.title}</b><small>{event.detail}</small><time>{new Date(event.createdAt).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</time></span></div>)}{events.length === 0 && <div className="nav-popover-empty">No recent system events.</div>}</div></div>}
      </div>
      <div className="profile-chip"><span className="profile-avatar">{initials}</span><span className="profile-identity"><span className="profile-name">{user?.name}</span><small>{user?.email}</small></span><button className="icon-button" aria-label="Sign out" title="Sign out" onClick={signOut}><LogOut size={15} /></button></div>
    </div>
  </header>
}