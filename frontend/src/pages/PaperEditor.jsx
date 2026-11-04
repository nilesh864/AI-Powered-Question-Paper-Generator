import { useEffect, useState } from 'react'
import { ArrowDownToLine, ArrowLeft, Check, CirclePlus, FileText, MoreHorizontal, RefreshCw, Save, Sparkles } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { IconButton, PageHeading, Tag } from '../components/UI/Primitives.jsx'
import { apiRequest, saveDownload } from '../services/api.js'

const paperSectionTitles = {
  MCQ: 'A) Select the correct option.',
  'Short Answer': 'B) Write short notes on.',
  'Long Answer': 'C) Answer the following questions.',
  'Case Study': 'D) Read the case and answer the questions.',
}

function cleanPrintedText(text) {
  return String(text || '').replace(/\[(?:offline\s+template(?:\s*[·|-]\s*set\s+[A-Z])?|template|easy|medium|hard|generated(?:_by)?[^\]]*)\]\s*/gi, '').trim()
}

export default function PaperEditor() {
  const { paperId } = useParams()
  const [paper, setPaper] = useState(null)
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)
  const [regenerating, setRegenerating] = useState(-1)
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    setLoading(true)
    apiRequest(`/generate/${paperId}`)
      .then((loadedPaper) => { if (active) setPaper({ ...loadedPaper, questions: loadedPaper.questions.map((question) => ({ ...question, text: cleanPrintedText(question.text), options: question.options?.map(cleanPrintedText) || [] })) }) })
      .catch((error) => { if (active) setNotice(error.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [paperId])

  function updateQuestion(index, text) { setHasUnsavedChanges(true); setPaper((current) => ({ ...current, questions: current.questions.map((question, questionIndex) => questionIndex === index ? { ...question, text: cleanPrintedText(text) } : question) })) }
  async function regenerate(index) {
    const question = paper.questions[index]
    setRegenerating(index)
    try {
      const updated = await apiRequest('/generate/regenerate', { method: 'POST', body: JSON.stringify({ subject: paper.subject, unit: question.unit, text: question.text }) })
      setHasUnsavedChanges(true)
      setPaper((current) => ({ ...current, questions: current.questions.map((item, questionIndex) => questionIndex === index ? { ...item, ...updated } : item) }))
      setNotice('A new syllabus-grounded question has been generated.')
    } catch (error) {
      setNotice(error.message)
    }
    setRegenerating(-1)
  }

  async function download(kind) {
    try {
      const blob = await apiRequest(`/export/${paper.id}/${kind}`)
      const extension = kind === 'paper-docx' ? 'docx' : 'pdf'
      saveDownload(blob, `${paper.subject.replaceAll(' ', '-')}-set-${paper.set_label}-${kind}.${extension}`)
    } catch (error) { setNotice(error.message) }
  }

  async function savePaper() {
    setSaving(true)
    try {
      const saved = await apiRequest(`/generate/${paper.id}`, { method: 'PUT', body: JSON.stringify(paper) })
      setPaper(saved)
      setHasUnsavedChanges(false)
      setNotice('Changes saved to your workspace.')
    } catch (error) {
      setNotice(error.message)
    }
    setSaving(false)
  }

  let displayQuestionNumber = 0
  const questionGroups = paper ? [...new Set(paper.questions.map((question) => question.question_type || 'Long Answer'))].map((questionType) => ({
    questionType,
    questions: paper.questions.map((question, index) => ({ question, index })).filter(({ question }) => (question.question_type || 'Long Answer') === questionType).map((item) => ({ ...item, displayNumber: ++displayQuestionNumber })),
  })) : []

  if (loading) return <div className="page-content">Loading paper…</div>
  if (!paper) return <div className="page-content"><div className="inline-message" role="alert">{notice || 'Paper could not be loaded.'}</div></div>
  return <div className="page-content editor-page">
    <PageHeading eyebrow={`PAPER EDITOR / SET ${paper.set_label}`} title={paper.course_title || paper.subject} description={`${paper.course_code} · ${paper.questions.length} questions · ${paper.total_marks} marks`} action={<div className="editor-actions"><Link className="text-action" to="/app/history"><ArrowLeft size={15} /> History</Link><button className="button secondary" onClick={() => download('answer-key')}><ArrowDownToLine size={16} /> Answer key</button><button className="button secondary" onClick={() => download('paper-docx')}><FileText size={16} /> Export Word</button><button className="button primary" onClick={() => download('paper')}><ArrowDownToLine size={16} /> Export PDF</button></div>} />
    {notice && <div className="inline-message" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss">×</button></div>}
    <div className="editor-toolbar"><div className="editor-status"><span className="saved-dot" /><span>{hasUnsavedChanges ? 'Unsaved changes' : 'All changes saved'}</span><i />Last edited just now</div><div className="editor-tools"><button className="quiet-select">Set {paper.set_label} <MoreHorizontal size={15} /></button><button className="icon-button" onClick={savePaper} aria-label="Save paper"><Save size={16} /></button></div></div>
    <div className="editor-layout"><main className="paper-sheet">
      <header className="paper-official-header">
        <h2>{(paper.university_name || 'MGM UNIVERSITY').toUpperCase()}</h2>
        <p>{paper.institution_address || 'Aurangabad-431003'}</p>
        <b>{paper.exam_type || 'First Term Exam A.Y. 2024-25'} · Set {paper.set_label}</b>
      </header>
      <div className="paper-meta-grid">
        <div><b>Program:</b> {paper.program_name || '—'}</div><div><b>Sem:</b> {paper.semester || '—'}</div>
        <div><b>Course:</b> {paper.course_title || paper.subject}</div><div><b>Course Code:</b> {paper.course_code || '—'}</div>
        <div><b>Marks:</b> {paper.total_marks}</div><div><b>Time:</b> {paper.duration_minutes} minutes</div>
      </div>
      <section className="paper-instructions"><b>Instructions to the students</b><ol>{(paper.instructions?.length ? paper.instructions : ['All questions are compulsory.', 'Marks are indicated against each question.', 'Illustrate your answers with neat sketches wherever necessary.']).map((instruction, index) => <li key={`${index}-${instruction}`}>{instruction}</li>)}</ol></section>
      {questionGroups.map(({ questionType, questions }) => <section className="paper-question-section" key={questionType}>
        <h3>{paperSectionTitles[questionType] || 'Questions'}</h3>
        {questions.map(({ question, index, displayNumber }) => <article className="paper-question" key={question.id}>
          <div className="question-body"><textarea value={cleanPrintedText(question.text)} rows={Math.min(4, Math.max(2, Math.ceil(question.text.length / 74)))} onChange={(event) => updateQuestion(index, event.target.value)} aria-label={`Edit question ${index + 1}`} /><div className="mcq-options">{question.options?.map((option, optionIndex) => <div className="mcq-option" key={`${question.id}-option-${optionIndex}`}>{String.fromCharCode(65 + optionIndex)}) {cleanPrintedText(option)}</div>)}</div></div>
          <div className="question-number">Q.{displayNumber}.</div><div className="question-marks">({question.marks})</div>
          <IconButton icon={RefreshCw} label="Regenerate question" disabled={regenerating === index} onClick={() => regenerate(index)} />
        </article>)}
      </section>)}
      <button className="add-question" onClick={() => { setHasUnsavedChanges(true); setPaper((current) => ({ ...current, questions: [...current.questions, { id: crypto.randomUUID(), text: '', marks: 10, unit: current.questions[0]?.unit || 'Unit 1', difficulty: 'Medium', bloom: 'Understand', answer: '', question_type: 'Long Answer', options: [] }] })) }}><CirclePlus size={16} /> Add a question</button>
      <div className="paper-end"><span>END OF QUESTION PAPER</span><span>{paper.course_code} / Set {paper.set_label}</span></div>
    </main>
    <aside className="editor-aside"><div className="aside-topline"><Sparkles size={14} /> ENSEMBLE REVIEW</div><div className="review-score"><b>{paper.questions.length ? Math.round(paper.questions.reduce((total, question) => total + (1 - (question.duplicate_score || 0)), 0) * 100 / paper.questions.length) : 0}</b><span>/ 100</span></div><p className="review-caption">Duplicate-adjusted question score</p><div className="review-rule" />{[{ label: 'Syllabus coverage', value: 'See overview', tone: 'neutral' }, { label: 'Question count', value: String(paper.questions.length), tone: 'blue' }, { label: 'Duplicate risk', value: `${Math.round(Math.max(0, ...paper.questions.map((question) => question.duplicate_score || 0)) * 100)}%`, tone: 'mint' }, { label: 'Bloom distribution', value: `${new Set(paper.questions.map((question) => question.bloom)).size} levels`, tone: 'blue' }].map((item) => <div className="review-row" key={item.label}><span>{item.label}</span><Tag tone={item.tone}>{item.value}</Tag></div>)}<button className="button subtle full-width" onClick={savePaper} disabled={saving}><Check size={15} />{saving ? 'Saving…' : 'Save changes'}</button></aside></div>
  </div>
}