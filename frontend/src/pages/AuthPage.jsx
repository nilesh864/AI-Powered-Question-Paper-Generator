import { useState } from 'react'
import { ArrowLeft, ArrowRight, GraduationCap, LockKeyhole, Mail, UserRound } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

export default function AuthPage() {
  const { authenticate } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [mode, setMode] = useState('login')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  async function submit(event) {
    event.preventDefault(); setError(''); setBusy(true)
    const form = Object.fromEntries(new FormData(event.currentTarget))
    try { await authenticate(mode === 'login' ? 'login' : 'register', form); navigate(location.state?.from?.pathname || '/app', { replace: true }) } catch (exception) { setError(exception.message) }
    setBusy(false)
  }
  return <main className="auth-page"><Link className="auth-back" to="/"><ArrowLeft size={16} /> Back to home</Link><section className="auth-card"><div className="auth-brand"><span className="brand-mark"><GraduationCap size={22} /></span><span>question<span className="brand-light">paper</span></span></div><div className="eyebrow">FACULTY WORKSPACE</div><h1>{mode === 'login' ? 'Welcome back.' : 'Create your account.'}</h1><p>Sign in to continue to your assessment workspace.</p><form onSubmit={submit} autoComplete="off">{mode === 'register' && <label className="auth-input"><UserRound size={17} /><input required minLength="2" name="name" value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" placeholder="Full name" /></label>}<label className="auth-input"><Mail size={17} /><input required type="email" name="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="off" placeholder="University email" /></label><label className="auth-input"><LockKeyhole size={17} /><input required minLength="8" maxLength="72" name="password" value={password} onChange={(event) => setPassword(event.target.value)} type="password" autoComplete={mode === 'register' ? 'new-password' : 'off'} placeholder="Password" /></label>{error && <div className="auth-error" role="alert">{error}</div>}<button className="button primary auth-submit" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}<ArrowRight size={16} /></button></form><div className="auth-switch">{mode === 'login' ? 'New to Question Paper Studio?' : 'Already have an account?'} <button onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setName(''); setEmail(''); setPassword(''); setError('') }}>{mode === 'login' ? 'Create account' : 'Sign in'}</button></div><div className="auth-divider"><span /> <small>SECURE FACULTY ACCESS</small> <span /></div><small className="auth-footnote">Your credentials are protected with encrypted password storage.</small></section></main>
}