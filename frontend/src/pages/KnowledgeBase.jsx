import { useEffect, useRef, useState } from 'react'
import { Check, CloudUpload, FileArchive, FileText, MoreHorizontal, Search, Trash2 } from 'lucide-react'
import { PageHeading, Panel, Tag } from '../components/UI/Primitives.jsx'
import { apiRequest, recordWorkspaceEvent } from '../services/api.js'

const categories = ['All sources', 'Syllabus', 'Lecture Notes', 'PPT', 'Past 5-Year Question Papers']
const uploadCategories = [
  { value: 'syllabus', label: 'Syllabus' },
  { value: 'lecture-notes', label: 'Lecture Notes' },
  { value: 'ppt', label: 'PPT' },
  { value: 'past-papers', label: 'Past 5-Year Question Papers' },
]

export default function KnowledgeBase() {
  const fileRef = useRef(null)
  const [documents, setDocuments] = useState([])
  const [uploadCategory, setUploadCategory] = useState('lecture-notes')
  const [uploadSubject, setUploadSubject] = useState('')
  const [uploadUnitLabel, setUploadUnitLabel] = useState('')
  const [category, setCategory] = useState('All sources')
  const [dragging, setDragging] = useState(false)
  const [message, setMessage] = useState('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)

  async function refreshDocuments() {
    setLoading(true)
    try { setDocuments(await apiRequest('/documents')) }
    catch (error) { setMessage(error.message) }
    finally { setLoading(false) }
  }

  useEffect(() => { refreshDocuments() }, [])

  async function uploadFiles(files) {
    setMessage('')
    let uploaded = 0
    for (const file of files) {
      const form = new FormData()
      form.append('file', file)
      form.append('category', uploadCategory)
      form.append('subject', uploadSubject)
      form.append('unit_label', uploadUnitLabel)
      try {
        const indexed = await apiRequest('/documents/upload', { method: 'POST', body: form })
        uploaded += 1
        const extractionDetail = `${indexed.chunk_count} chunks${indexed.page_count ? ` · ${indexed.page_count} pages/slides` : ''}${indexed.unit_label ? ` · ${indexed.unit_label}` : ''}`
        setMessage(`${file.name} indexed: ${extractionDetail}.`)
        recordWorkspaceEvent('Document Indexed', `${file.name} · ${extractionDetail}`)
      } catch (error) {
        setMessage(`${file.name}: ${error.message}`)
      }
    }
    if (uploaded) await refreshDocuments()
    if (uploaded > 1) setMessage(`${uploaded} documents indexed successfully.`)
  }

  async function deleteDocument(document) {
    setMessage('')
    try {
      await apiRequest(`/documents/${document.id}`, { method: 'DELETE' })
      await refreshDocuments()
    } catch (error) { setMessage(error.message) }
  }

  const categoryLabel = (value) => uploadCategories.find((item) => item.value === value)?.label || value
  const filtered = documents.filter((doc) => (category === 'All sources' || categoryLabel(doc.category).toLowerCase() === category.toLowerCase()) && doc.filename.toLowerCase().includes(query.toLowerCase()))
  const count = (name) => name === 'All sources' ? documents.length : documents.filter((doc) => categoryLabel(doc.category).toLowerCase() === name.toLowerCase()).length
  const indexedChunks = documents.reduce((total, document) => total + (document.chunk_count || 0), 0)
  const indexReady = documents.some((document) => document.status === 'indexed')

  return <div className="page-content">
    <PageHeading eyebrow={`SOURCE LIBRARY / ${documents.length} DOCUMENTS`} title="Knowledge base" description="Manage the course material your generated papers draw from." action={<button className="button primary" onClick={() => fileRef.current?.click()}><CloudUpload size={17} /> Add documents</button>} />
    <input ref={fileRef} type="file" multiple accept=".pdf,.docx,.pptx,.txt,.md" hidden onChange={(event) => { const files = [...event.target.files]; event.target.value = ''; uploadFiles(files) }} />
    <div className={`dropzone ${dragging ? 'dragging' : ''}`} onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); uploadFiles([...event.dataTransfer.files]) }} onClick={() => fileRef.current?.click()} role="button" tabIndex={0} onKeyDown={(event) => event.key === 'Enter' && fileRef.current?.click()}><div className="drop-icon"><CloudUpload size={22} /></div><div><b>Drop course files here, or <span>browse</span></b><p>PDF, DOCX, PPTX, TXT · up to 25 MB each</p></div><label className="upload-category" onClick={(event) => event.stopPropagation()}>Document category<select value={uploadCategory} onChange={(event) => setUploadCategory(event.target.value)}>{uploadCategories.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label></div>
    <div className="upload-metadata"><label>Subject (optional)<input value={uploadSubject} onChange={(event) => setUploadSubject(event.target.value)} placeholder="e.g. Cellular Biology" /></label><label>Unit or chapter (optional)<input value={uploadUnitLabel} onChange={(event) => setUploadUnitLabel(event.target.value)} placeholder="e.g. Unit 2: Cell Structure" /></label></div>
    {message && <div className="inline-message" role="status">{message}</div>}
    <div className="source-summary"><div><span className={`summary-dot ${indexReady ? 'mint-dot' : ''}`} /><b>{indexReady ? 'Vector index operational' : 'No indexed sources'}</b><span>{`${indexedChunks} indexed chunks`}</span></div><button className="text-action" onClick={refreshDocuments}>Refresh <MoreHorizontal size={15} /></button></div>
    <Panel title="Your sources" detail="Files available to the question generator" className="sources-panel">
      <div className="source-toolbar"><div className="filter-tabs">{categories.map((item) => <button className={category === item ? 'selected' : ''} key={item} onClick={() => setCategory(item)}>{item}<small>{count(item)}</small></button>)}</div><label className="table-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a source" /></label></div>
      <div className="source-table"><div className="source-table-head"><span>DOCUMENT</span><span>CATEGORY</span><span>CHUNKS</span><span>STATUS</span><span>ADDED</span><span /></div>{filtered.map((doc) => <div className="source-row" key={doc.id}><div className="document-name"><span className="document-icon"><FileText size={17} /></span><span><b>{doc.filename}</b>{(doc.subject || doc.unit_label || doc.page_count) && <small>{[doc.subject, doc.unit_label, doc.page_count ? `${doc.page_count} pages/slides` : ''].filter(Boolean).join(' · ')}</small>}</span></div><span className="source-category">{categoryLabel(doc.category)}</span><span className="chunk-count">{doc.chunk_count}</span><Tag tone={doc.status === 'indexed' ? 'mint' : 'amber'}><i className="mini-dot" />{doc.status}</Tag><span className="source-date">{new Date(doc.uploaded_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span><button className="row-menu" aria-label={`Delete ${doc.filename}`} title="Delete document" onClick={() => deleteDocument(doc)}><Trash2 size={16} /></button></div>)}</div>
      {loading ? <div className="source-empty">Loading workspace documents…</div> : filtered.length === 0 && <div className="source-empty"><FileArchive size={20} />No uploaded documents</div>}
      <div className="table-footer"><span>Showing {filtered.length} of {documents.length} sources</span><span><Check size={13} /> Changes sync automatically</span></div>
    </Panel>
    <div className="privacy-note"><Trash2 size={15} /><span>Documents are scoped to your workspace. Removing a source also removes its indexed content.</span></div>
  </div>
}