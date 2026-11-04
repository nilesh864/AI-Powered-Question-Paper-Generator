import { useEffect, useState } from 'react'
import { ArrowDownToLine, ArrowUpRight, FileCheck2, FilePlus2, Search } from 'lucide-react'
import { Link } from 'react-router-dom'
import { PageHeading, Panel, Tag } from '../components/UI/Primitives.jsx'
import { apiRequest, saveDownload } from '../services/api.js'

export default function PaperHistory() {
  const [papers, setPapers] = useState([])
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    apiRequest('/generate/history').then(setPapers).catch((exception) => setError(exception.message)).finally(() => setLoading(false))
  }, [])
  async function download(paper) {
    try { const blob = await apiRequest(`/export/${paper.id}/paper`); saveDownload(blob, `${paper.subject}-set-${paper.set_label}.pdf`) } catch (exception) { setError(exception.message) }
  }
  const visible = papers.filter((paper) => paper.subject.toLowerCase().includes(filter.toLowerCase()) || paper.course_code.toLowerCase().includes(filter.toLowerCase()))
  return <div className="page-content"><PageHeading eyebrow={`ASSESSMENT ARCHIVE / ${papers.length} PAPERS`} title="Paper history" description="Browse, revise, and export examinations you’ve created." action={<Link className="button primary" to="/app/generate"><FilePlus2 size={16} /> New paper</Link>} />{error && <div className="inline-message" role="alert">{error}</div>}<Panel title="Generated papers" detail="All courses · sorted by most recent" className="history-panel"><div className="history-toolbar"><div className="filter-tabs"><button className="selected">All papers <small>{papers.length}</small></button></div><label className="table-search"><Search size={15} /><input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Search course or code" /></label></div><div className="history-list">{visible.map((paper, index) => <div className="history-row" key={paper.id}><span className={`history-file-icon history-${index % 3}`}><FileCheck2 size={18} /></span><div className="history-name"><Link to={`/app/editor/${paper.id}`}><b>{paper.subject}</b><ArrowUpRight size={13} /></Link><span>{paper.course_code || 'Course'} · Set {paper.set_label} · {paper.questions?.length || 0} questions</span></div><Tag tone="neutral">Generated</Tag><span className="history-date">{new Date(paper.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</span><span className="history-marks">{paper.total_marks} <small>marks</small></span><button className="icon-button" onClick={() => download(paper)} aria-label="Download paper"><ArrowDownToLine size={16} /></button></div>)}</div>{!loading && visible.length === 0 && <div className="history-empty">{filter ? 'No papers match that search.' : 'No generated papers yet.'}</div>}{loading && <div className="history-empty">Loading generated papers…</div>}<div className="table-footer"><span>Showing {visible.length} of {papers.length} papers</span><span>Retained in your workspace</span></div></Panel></div>
}