import { motion } from 'framer-motion'

export function PageHeading({ eyebrow, title, description, action }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>{action && <div className="heading-action">{action}</div>}</div>
}

export function Panel({ title, detail, action, children, className = '' }) {
  return <section className={`panel ${className}`}><div className="panel-heading"><div><h2>{title}</h2>{detail && <p>{detail}</p>}</div>{action}</div>{children}</section>
}

export function Metric({ label, value, note, icon: Icon, tone = 'mint' }) {
  return <motion.article className="metric" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.28 }}><div className={`metric-icon ${tone}`}><Icon size={17} strokeWidth={1.8} /></div><span className="metric-label">{label}</span><strong>{value}</strong><span className="metric-note">{note}</span></motion.article>
}

export function Tag({ children, tone = 'neutral' }) {
  return <span className={`tag ${tone}`}>{children}</span>
}

export function EmptyState({ icon: Icon, title, detail, action }) {
  return <div className="empty-state"><div className="empty-icon"><Icon size={22} /></div><h3>{title}</h3><p>{detail}</p>{action}</div>
}

export function IconButton({ icon: Icon, label, ...props }) {
  return <button className="icon-button" aria-label={label} title={label} {...props}><Icon size={17} /></button>
}