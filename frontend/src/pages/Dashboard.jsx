import { useEffect, useState } from 'react'
import { ArrowDownRight, ArrowRight, BookOpen, CircleHelp, FileCheck2, FilePlus2, Layers3, Sparkles } from 'lucide-react'
import { motion } from 'framer-motion'
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Link } from 'react-router-dom'
import { Metric, PageHeading, Panel, Tag } from '../components/UI/Primitives.jsx'
import { apiRequest } from '../services/api.js'

const difficultyColors = { Easy: '#a8e9c7', Medium: '#e6c66d', Hard: '#f18e72' }

export default function Dashboard() {
  const [analytics, setAnalytics] = useState(null)
  const [papers, setPapers] = useState([])
  const [error, setError] = useState('')
  useEffect(() => {
    Promise.all([apiRequest('/generate/analytics'), apiRequest('/generate/history')])
      .then(([liveAnalytics, livePapers]) => { setAnalytics(liveAnalytics); setPapers(livePapers) })
      .catch((exception) => setError(exception.message))
  }, [])
  const activity = analytics?.papers_per_week || []
  const difficulty = Object.entries(analytics?.difficulty_breakdown || {}).map(([name, value]) => ({ name, value, color: difficultyColors[name] }))
  const coverage = analytics?.unit_coverage || []
  const questionTotal = analytics?.generated_questions || 0
  return <div className="page-content">
    <PageHeading eyebrow={`FACULTY WORKSPACE · ${new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: '2-digit', year: 'numeric' }).toUpperCase()}`} title="Assessment overview" description="Live totals and distribution from your uploaded documents and generated papers." action={<Link className="button primary" to="/app/generate"><FilePlus2 size={17} /> Build a paper</Link>} />
    {error && <div className="inline-message" role="alert">{error}</div>}
    <div className="metric-grid"><Metric label="Total uploads" value={analytics?.total_uploads ?? '—'} note={`${analytics?.indexed_uploads ?? 0} indexed`} icon={Layers3} tone="blue" /><Metric label="Generated papers" value={analytics?.generated_papers ?? '—'} note="In this workspace" icon={FileCheck2} /><Metric label="Questions generated" value={questionTotal || '—'} note="Scored by ensemble" icon={CircleHelp} tone="amber" /><Metric label="Syllabus coverage" value={analytics?.syllabus_coverage_percent == null ? 'N/A' : `${analytics.syllabus_coverage_percent}%`} note={analytics?.syllabus_coverage_percent == null ? 'Upload a syllabus with Unit labels' : 'Units represented in generated papers'} icon={BookOpen} tone="coral" /></div>
    <div className="chart-grid">
      <Panel title="Paper activity" detail="Generated assessments · last 8 weeks" action={<button className="quiet-select">Last 8 weeks <ArrowDownRight size={14} /></button>}>
        <div className="activity-legend"><span><i className="legend-dot mint-dot" /> Papers generated</span><span className="legend-total">{Math.max(0, ...activity.map((item) => item.papers || 0))}<small>peak week</small></span></div>
        <div className="activity-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={activity} margin={{ top: 12, right: 4, bottom: 0, left: -22 }}><defs><linearGradient id="paperFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#9be5bd" stopOpacity={0.25} /><stop offset="100%" stopColor="#9be5bd" stopOpacity={0} /></linearGradient></defs><CartesianGrid stroke="#27332f" vertical={false} /><XAxis dataKey="week" tickLine={false} axisLine={false} tick={{ fill: '#82918a', fontSize: 11 }} dy={9} /><YAxis tickLine={false} axisLine={false} tick={{ fill: '#82918a', fontSize: 11 }} /><Tooltip contentStyle={{ background: '#1b2824', border: '1px solid #34423c', borderRadius: 6, color: '#e8eee9', fontSize: 12 }} /><Area type="monotone" dataKey="papers" stroke="#a8e9c7" strokeWidth={2.5} fill="url(#paperFill)" /></AreaChart></ResponsiveContainer></div>
      </Panel>
      <Panel title="Question difficulty" detail="Ensemble predictions on your papers">
        {questionTotal ? <div className="difficulty-content"><div className="donut-wrap"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={difficulty} innerRadius={58} outerRadius={78} paddingAngle={4} dataKey="value" stroke="none">{difficulty.map((item) => <Cell key={item.name} fill={item.color} />)}</Pie><Tooltip contentStyle={{ background: '#1b2824', border: '1px solid #34423c', borderRadius: 6, color: '#e8eee9', fontSize: 12 }} /></PieChart></ResponsiveContainer><div className="donut-center"><b>{questionTotal}</b><small>questions</small></div></div><div className="difficulty-legend">{difficulty.map((item) => <div key={item.name}><span><i style={{ background: item.color }} />{item.name}</span><b>{Math.round(item.value * 100 / questionTotal)}%</b></div>)}</div></div> : <div className="source-empty">Difficulty results appear after your first generated paper.</div>}
      </Panel>
    </div>
    <div className="lower-grid">
      <Panel title="Syllabus coverage" detail="Matched unit labels in uploaded syllabus files">
        {coverage.length ? <div className="coverage-list">{coverage.map((item, index) => <div className="coverage-row" key={item.unit}><span>{item.unit}</span><div className="coverage-track"><motion.i initial={{ width: 0 }} animate={{ width: `${item.covered ? 100 : 0}%` }} transition={{ delay: index * 0.08, duration: 0.6 }} /></div><b>{item.covered ? `${item.question_count} Q` : '0 Q'}</b></div>)}</div> : <div className="source-empty">Coverage is unavailable until a syllabus with recognizable Unit or Chapter numbers is uploaded.</div>}
      </Panel>
      <Panel title="Recent papers" detail="Your latest generated assessments" action={<Link to="/app/history" className="text-action">See all <ArrowRight size={14} /></Link>}>
        <div className="recent-list">{papers.slice(0, 3).map((paper, index) => <Link to={`/app/editor/${paper.id}`} className="recent-row" key={paper.id}><span className={`recent-icon recent-${index}`}><FileCheck2 size={17} /></span><span className="recent-info"><b>{paper.subject}</b><small>{paper.course_code} · Set {paper.set_label}</small></span><span className="recent-date">{new Date(paper.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span></Link>)}{!papers.length && <div className="source-empty">No generated papers yet.</div>}</div>
      </Panel>
    </div>
    {analytics?.syllabus_coverage_percent != null && <motion.div className="insight-banner" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}><span className="insight-icon"><Sparkles size={17} /></span><p><b>Live assessment coverage</b><span>{analytics.syllabus_coverage_percent}% of the numbered syllabus units appear in your generated questions.</span></p><Link to="/app/generate" className="icon-button"><ArrowRight size={17} /></Link></motion.div>}
  </div>
}