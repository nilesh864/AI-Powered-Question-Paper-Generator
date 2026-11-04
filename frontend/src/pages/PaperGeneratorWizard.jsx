import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, Check, CircleCheck, FileCheck2, LoaderCircle, Plus, Sparkles, WandSparkles } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { PageHeading, Tag } from '../components/UI/Primitives.jsx'
import { apiRequest, recordWorkspaceEvent } from '../services/api.js'

const steps = ['Subject', 'Blueprint', 'Validation', 'Review papers']
const questionTypes = ['MCQ', 'Short Answer', 'Long Answer', 'Case Study']
const difficultyLevels = [{ key: 'easy', label: 'Easy' }, { key: 'medium', label: 'Medium' }, { key: 'hard', label: 'Hard' }]

function difficultyCounts(questionCount, distribution) {
  const exact = difficultyLevels.map(({ key }) => questionCount * distribution[key] / 100)
  const counts = exact.map(Math.floor)
  const remaining = questionCount - counts.reduce((total, count) => total + count, 0)
  const order = exact.map((count, index) => ({ index, remainder: count - counts[index] })).sort((left, right) => right.remainder - left.remainder || left.index - right.index)
  order.slice(0, remaining).forEach(({ index }) => { counts[index] += 1 })
  return Object.fromEntries(difficultyLevels.map(({ key }, index) => [key, counts[index]]))
}

export default function PaperGeneratorWizard() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState(false)
  const [generationError, setGenerationError] = useState('')
  const [generationErrorStatus, setGenerationErrorStatus] = useState(null)
  const [sourceCount, setSourceCount] = useState(null)
  const [validationSummary, setValidationSummary] = useState(null)
  const generationStarted = useRef(false)
  const [provider, setProvider] = useState('auto')
  const [form, setForm] = useState({ subject: '', university_name: 'MGM UNIVERSITY', institution_address: 'Aurangabad-431003', program_name: '', course_title: '', course_code: '', semester: '', exam_type: 'First Term Exam A.Y. 2024-25', units: [], total_marks: 100, duration_minutes: 180, question_count: 10, sets: 3, difficulty_level: 'Balanced', difficulty_distribution: { easy: 30, medium: 50, hard: 20 }, question_types: questionTypes, sections: [{ question_type: 'MCQ', question_count: 3, total_marks: 15 }, { question_type: 'Short Answer', question_count: 3, total_marks: 30 }, { question_type: 'Long Answer', question_count: 2, total_marks: 30 }, { question_type: 'Case Study', question_count: 2, total_marks: 25 }] })
  const [result, setResult] = useState(null)

  useEffect(() => { apiRequest('/documents').then((documents) => setSourceCount(documents.length)).catch(() => setSourceCount(null)) }, [])

  function update(field, value) { setForm((current) => ({ ...current, [field]: value })) }
  function updateDifficulty(level, value) {
    const remainingLevels = difficultyLevels.map(({ key }) => key).filter((key) => key !== level)
    const fixedValue = Number(value)
    setForm((current) => {
      const distribution = { ...current.difficulty_distribution }
      const oldRemaining = remainingLevels.reduce((total, key) => total + distribution[key], 0)
      const remainingValue = 100 - fixedValue
      const firstValue = oldRemaining ? Math.round(remainingValue * distribution[remainingLevels[0]] / oldRemaining) : Math.floor(remainingValue / 2)
      distribution[level] = fixedValue
      distribution[remainingLevels[0]] = firstValue
      distribution[remainingLevels[1]] = remainingValue - firstValue
      const singleLevel = difficultyLevels.find(({ key }) => distribution[key] === 100)
      return { ...current, difficulty_distribution: distribution, difficulty_level: singleLevel?.label || 'Balanced' }
    })
  }
  function changeUnit(index, value) { setForm((current) => ({ ...current, units: current.units.map((unit, unitIndex) => unitIndex === index ? value : unit) })) }
  function updateSection(type, field, value) {
    setForm((current) => {
      const sections = current.sections.map((section) => section.question_type === type ? { ...section, [field]: value === '' ? 0 : Number(value) } : section)
      return { ...current, sections, question_count: sections.reduce((total, section) => total + section.question_count, 0) }
    })
  }
  function continueStep() {
    if (step === 1) {
      const questionCount = form.sections.reduce((total, section) => total + section.question_count, 0)
      const sectionMarks = form.sections.reduce((total, section) => total + section.total_marks, 0)
      if (difficultyLevels.reduce((total, { key }) => total + form.difficulty_distribution[key], 0) !== 100) return setGenerationError('Difficulty percentages must add up to 100%.')
      if (questionCount < 3 || questionCount > 50) return setGenerationError('Each paper set must contain between 3 and 50 questions.')
      if (sectionMarks !== form.total_marks) return setGenerationError('Section mark allocations must add up to the maximum marks.')
      if (form.sections.some((section) => section.question_count > 0 && section.total_marks < section.question_count)) return setGenerationError('Each question in an active section must be worth at least one mark.')
      if (form.sections.some((section) => section.question_count === 0 && section.total_marks > 0)) return setGenerationError('Sections without questions cannot have marks allocated.')
      if (!questionCount) return setGenerationError('Add at least one question to the blueprint.')
    }
    setGenerationError('')
    setStep(step + 1)
  }

  async function generate() {
    if (generationStarted.current) return
    generationStarted.current = true
    setBusy(true)
    setGenerationError('')
    try {
      const payload = { ...form, provider, question_types: form.sections.flatMap((section) => Array(section.question_count).fill(section.question_type)) }
      const response = await apiRequest('/generate', { method: 'POST', body: JSON.stringify(payload) })
      if (!response.papers?.length || response.validation_summary?.status !== 'passed') throw new Error('Generation returned without a completed validation summary. Retry the generation.')
      setResult(response.papers)
      setValidationSummary(response.validation_summary)
      recordWorkspaceEvent('Paper Generated', `${response.papers.length} set${response.papers.length === 1 ? '' : 's'} · ${form.subject}`)
    } catch (error) {
      generationStarted.current = false
      setGenerationErrorStatus(error.statusCode || null)
      setGenerationError(error.statusCode === 429
        ? 'API Quota Exceeded. You have reached the daily Gemini API limit.'
        : error.message)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (step === 2 && !result && !generationStarted.current) generate()
  }, [step])

  function retryGeneration() {
    generationStarted.current = false
    setGenerationError('')
    setGenerationErrorStatus(null)
    generate()
  }

  function continueToReview() {
    if (validationSummary?.status === 'passed' && result?.length) setStep(3)
  }

  function openFirstPaper() {
    if (result?.[0]) navigate(`/app/editor/${result[0].id}`)
  }

  const selectedQuestionCount = form.sections.reduce((total, section) => total + section.question_count, 0)

  return <div className="page-content wizard-page">
    <PageHeading eyebrow="ASSESSMENT WORKFLOW / NEW PAPER" title="Build an examination" description="Shape a balanced, syllabus-aligned paper in four deliberate steps." action={<Link className="text-action back-link" to="/app"><ArrowLeft size={15} /> Back to overview</Link>} />
    {result?.length > 0 && <div className="provider-provenance"><Sparkles size={15} /><span>Generated via <b>{validationSummary?.generated_by === 'offline_fallback' ? 'Offline templates' : validationSummary?.generated_by === 'ollama' ? 'Local Ollama' : validationSummary?.generated_by === 'mixed' ? 'Mixed engines' : 'Gemini'}</b></span></div>}
    <div className="wizard-progress">{steps.map((label, index) => <div className={`wizard-step ${index === step ? 'current' : ''} ${index < step ? 'complete' : ''}`} key={label}><span>{index < step ? <Check size={14} /> : String(index + 1).padStart(2, '0')}</span><b>{label}</b>{index < steps.length - 1 && <i />}</div>)}</div>
    <div className="wizard-layout"><div className="wizard-main">
      {generationError && step !== 2 && step !== 3 && <div className="inline-message" role="alert">{generationError}</div>}
      {step === 1 && <section className="engine-selector"><div><b>Generation engine</b><small>Auto tries Gemini, then local Ollama, then templates.</small></div><select aria-label="Generation engine" value={provider} onChange={(event) => setProvider(event.target.value)}><option value="auto">Auto</option><option value="gemini">Online (Gemini)</option><option value="ollama">Local AI (Ollama)</option></select></section>}
      {step === 0 && <section className="wizard-section"><div className="section-intro"><span className="section-index">01</span><div><h2>Choose your subject</h2><p>Start with a course and the syllabus units to assess.</p></div></div><div className="form-field"><label htmlFor="subject">Course or subject name</label><input id="subject" value={form.subject} onChange={(event) => update('subject', event.target.value)} /></div><div className="form-field"><label htmlFor="courseCode">Course code <span>OPTIONAL</span></label><input id="courseCode" value={form.course_code} onChange={(event) => update('course_code', event.target.value)} /></div><div className="form-field"><label>Included syllabus units</label><p className="field-hint">Enter unit labels as they appear in the uploaded syllabus so retrieval and coverage analysis can match them.</p><div className="unit-picker">{form.units.map((unit, index) => <label className="unit-option" key={`${index}-${unit}`}><input type="checkbox" checked onChange={() => update('units', form.units.filter((_, unitIndex) => unitIndex !== index))} /><span><Check size={12} /></span><input className="unit-edit" value={unit} onChange={(event) => changeUnit(index, event.target.value)} aria-label={`Edit ${unit}`} /></label>)}<button className="add-unit" onClick={() => update('units', [...form.units, `Unit ${form.units.length + 1}`])}><Plus size={15} /> Add unit</button></div></div></section>}
      {step === 1 && <section className="wizard-section"><div className="section-intro"><span className="section-index">02</span><div><h2>Set your blueprint</h2><p>Set the exam header, total paper size, and question blueprint.</p></div></div><div className="field-grid exam-metadata-fields"><div className="form-field"><label htmlFor="universityName">University name</label><input id="universityName" maxLength="160" value={form.university_name} onChange={(event) => update('university_name', event.target.value)} /></div><div className="form-field"><label htmlFor="institutionAddress">Institution address</label><input id="institutionAddress" maxLength="200" value={form.institution_address} onChange={(event) => update('institution_address', event.target.value)} /></div><div className="form-field"><label htmlFor="programName">Program name</label><input id="programName" maxLength="160" value={form.program_name} onChange={(event) => update('program_name', event.target.value)} placeholder="e.g. Bachelor of Technology" /></div><div className="form-field"><label htmlFor="courseTitle">Course title</label><input id="courseTitle" maxLength="160" value={form.course_title} onChange={(event) => update('course_title', event.target.value)} placeholder={form.subject || 'Course title'} /></div><div className="form-field"><label htmlFor="semester">Semester</label><input id="semester" maxLength="80" value={form.semester} onChange={(event) => update('semester', event.target.value)} placeholder="e.g. Semester III" /></div><div className="form-field"><label htmlFor="examType">Exam type / session</label><input id="examType" maxLength="160" value={form.exam_type} onChange={(event) => update('exam_type', event.target.value)} /></div><div className="form-field"><label htmlFor="marks">Maximum marks</label><input id="marks" type="number" min="10" max="300" value={form.total_marks} onChange={(event) => update('total_marks', Number(event.target.value))} /></div><div className="form-field"><label htmlFor="duration">Duration (minutes)</label><input id="duration" type="number" min="30" max="600" value={form.duration_minutes} onChange={(event) => update('duration_minutes', Number(event.target.value))} /></div><div className="form-field"><label>Total questions per set</label><output className="blueprint-total">{selectedQuestionCount}</output></div><div className="form-field"><label htmlFor="sets">Paper variants</label><select id="sets" value={form.sets} onChange={(event) => update('sets', Number(event.target.value))}><option value="1">1 set</option><option value="2">2 sets</option><option value="3">3 sets</option></select></div></div><div className="difficulty-breakdown"><div className="difficulty-breakdown-heading"><span><b>Custom difficulty breakdown</b><small>Percentages stay balanced to 100%.</small></span><output>100%</output></div><div className="difficulty-controls">{difficultyLevels.map(({ key, label }) => <label className={`difficulty-control difficulty-${key}`} key={key}><span><b>{label}</b><output>{form.difficulty_distribution[key]}%</output></span><input type="range" min="0" max="100" step="1" aria-label={`${label} difficulty percentage`} value={form.difficulty_distribution[key]} onChange={(event) => updateDifficulty(key, event.target.value)} /></label>)}</div><div className="difficulty-count-preview"><span>Questions per set</span>{difficultyLevels.map(({ key, label }) => <b key={key}>{label} {difficultyCounts(selectedQuestionCount, form.difficulty_distribution)[key]}</b>)}</div></div><div className="section-blueprint">{form.sections.map((section) => <div className="section-blueprint-row" key={section.question_type}><b>{section.question_type}</b><label>Questions<input type="number" min="0" max="50" value={section.question_count} onChange={(event) => updateSection(section.question_type, 'question_count', event.target.value)} /></label><label>Section marks<input type="number" min="0" max="300" value={section.total_marks} onChange={(event) => updateSection(section.question_type, 'total_marks', event.target.value)} /></label><small>{section.question_count ? `${Math.floor(section.total_marks / section.question_count)}–${Math.ceil(section.total_marks / section.question_count)} marks each` : 'Not included'}</small></div>)}</div><div className="blueprint-preview"><div><span>MARK CHECK</span><b>{form.sections.reduce((total, section) => total + section.total_marks, 0)} / {form.total_marks} <small>allocated</small></b></div><div><span>SYLLABUS SCOPE</span><b>{form.units.length} <small>units included</small></b></div><div><span>DELIVERABLES</span><b>{form.sets} <small>parallel sets</small></b></div></div></section>}
      {step === 2 && (
        <section className="wizard-section">
          <div className="section-intro">
            <span className="section-index">03</span>
            <div>
              <h2>Ensemble validation</h2>
              <p>{busy ? 'Generating question sets and running validation checks…' : generationError ? 'Generation did not complete. Resolve the issue and retry.' : validationSummary ? 'Generation and ensemble checks completed.' : 'Validation is ready to run.'}</p>
            </div>
          </div>
          {busy && <div className="validation-progress" role="status"><LoaderCircle className="spin" size={18} /><span>Retrieving syllabus context, drafting questions, and scoring the results…</span></div>}
          {generationError && <div className={`quota-alert ${generationErrorStatus === 429 ? 'quota-alert-error' : ''}`} role="alert"><div><b>{generationErrorStatus === 429 ? 'API Quota Exceeded' : 'Generation failed'}</b><p>{generationErrorStatus === 429 ? 'API Quota Exceeded. You have reached the daily Gemini API limit.' : generationError}</p></div><button className="button primary" onClick={retryGeneration} disabled={busy}>{busy ? 'Retrying…' : 'Try Again'}</button></div>}
          {validationSummary?.generated_by === 'offline_fallback' && <div className="quota-alert"><div><b>Offline template fallback</b><p>These editable template questions were prepared without Gemini. Verify and adapt them against your course material before use.</p></div></div>}
          <div className="validation-list">{[
            { name: 'Syllabus scope', detail: `${form.units.length} selected units · ${sourceCount ?? '…'} indexed workspace documents`, score: busy ? 'Running' : generationError ? 'Retry' : validationSummary ? 'Passed' : 'Waiting' },
            { name: 'Difficulty balance', detail: validationSummary ? `${Object.entries(validationSummary.difficulty_distribution || {}).map(([level, count]) => `${level} ${count}`).join(' · ')} · ${Math.round((validationSummary.average_soft_voting_confidence || 0) * 100)}% average confidence` : 'Soft-voting classifier scores each drafted question', score: busy ? 'Running' : validationSummary ? 'Passed' : generationError ? 'Retry' : 'Waiting' },
            { name: 'Bloom’s taxonomy', detail: validationSummary?.sets?.map((set) => Object.entries(set.bloom_distribution || {}).filter(([, count]) => count).map(([level, count]) => `${level} ${count}`).join(', ')).filter(Boolean).join(' · ') || 'Cognitive levels are assigned after question drafting', score: busy ? 'Running' : validationSummary ? 'Completed' : generationError ? 'Retry' : 'Waiting' },
            { name: 'Duplicate screening', detail: validationSummary ? `${validationSummary.duplicate_screening.checked_questions} checked · ${validationSummary.duplicate_screening.flagged_questions} flagged` : 'Questions are compared with your past-paper collection', score: busy ? 'Running' : validationSummary ? 'Passed' : generationError ? 'Retry' : 'Waiting' },
          ].map((item) => <div className="validation-row" key={item.name}><span className="validation-check">{busy ? <LoaderCircle className="spin" size={17} /> : <CircleCheck size={17} />}</span><span><b>{item.name}</b><small>{item.detail}</small></span><Tag tone={item.score === 'Passed' || item.score === 'Completed' ? 'mint' : item.score === 'Retry' ? 'coral' : 'amber'}>{item.score}</Tag></div>)}</div>
          {validationSummary && <div className="validation-note"><Sparkles size={16} /><span>All checks passed across {validationSummary.sets.length} set(s).</span></div>}
          <div className="validation-continue"><button className="button primary" onClick={continueToReview} disabled={busy || validationSummary?.status !== 'passed' || !result?.length}>Continue to Paper Review <ArrowRight size={16} /></button></div>
        </section>
      )}
      {step === 3 && <section className="wizard-section generate-section"><div className="section-intro"><span className="section-index">04</span><div><h2>Your paper sets are ready</h2><p>Review validation results, then open a set to refine every question.</p></div></div>{result && <><div className="validation-metrics"><div><small>AVG CLASSIFIER CONFIDENCE</small><b>{Math.round((validationSummary?.average_soft_voting_confidence || 0) * 100)}%</b></div><div><small>QUESTIONS SCREENED</small><b>{validationSummary?.duplicate_screening.checked_questions || 0}</b></div><div><small>DIFFICULTY BREAKDOWN</small><b className="difficulty-summary">{difficultyLevels.map(({ key, label }) => <span key={key}>{label} <i>{form.difficulty_distribution[key]}%</i></span>)}</b></div></div><div className="generated-sets">{result.map((paper) => { const summary = validationSummary?.sets?.find((item) => item.paper_id === paper.id); return <div className="generated-set review-set" key={paper.id}><span className="set-letter">{paper.set_label}</span><span><b>Set {paper.set_label} <Tag tone={paper.difficulty_level === 'Hard' ? 'coral' : paper.difficulty_level === 'Easy' ? 'mint' : 'amber'}>{paper.difficulty_level || form.difficulty_level}</Tag></b><small>{paper.questions?.length || form.question_count} questions · {paper.total_marks} marks · Easy {summary?.difficulty_distribution?.Easy ?? 0}, Medium {summary?.difficulty_distribution?.Medium ?? 0}, Hard {summary?.difficulty_distribution?.Hard ?? 0}</small></span><button className="button primary" onClick={() => { localStorage.setItem('qps-current-paper', JSON.stringify(paper)); navigate(`/app/editor/${paper.id}`) }}><FileCheck2 size={16} /> Review</button></div>})}</div><button className="button primary" onClick={openFirstPaper}><WandSparkles size={16} /> Open first paper <ArrowRight size={15} /></button></>}</section>}
      <div className="wizard-footer">{step > 0 ? <button className="button secondary" onClick={() => { if (!busy && step !== 2) setStep(step - 1) }} disabled={busy || step === 2}><ArrowLeft size={15} /> Previous</button> : <span />}{step === 0 || step === 1 ? <button className="button primary" onClick={continueStep} disabled={step === 0 && (!form.subject.trim() || form.units.length === 0)}>Continue <ArrowRight size={15} /></button> : step === 3 && <button className="button secondary" onClick={() => { setStep(0); setResult(null); setValidationSummary(null); setGenerationError(''); setGenerationErrorStatus(null); generationStarted.current = false }}>Start another</button>}</div>
    </div><aside className="wizard-aside"><div className="aside-topline"><Sparkles size={15} /> GENERATION BRIEF</div><h3>{form.subject || 'Untitled course'}</h3><span className="aside-code">{form.course_code || 'COURSE CODE'}</span><div className="aside-rule" /><div className="brief-item"><span>Units selected</span><b>{form.units.length}</b></div><div className="brief-item"><span>Maximum marks</span><b>{form.total_marks}</b></div><div className="brief-item"><span>Questions</span><b>{selectedQuestionCount}</b></div><div className="brief-item"><span>Duration</span><b>{Math.floor(form.duration_minutes / 60)}h {form.duration_minutes % 60}m</b></div><div className="brief-item"><span>Question sets</span><b>{form.sets} variants</b></div><div className="aside-foot"><span className="status-led" />{sourceCount === null ? 'Source count unavailable' : `${sourceCount} workspace documents`}</div></aside></div>
  </div>
}