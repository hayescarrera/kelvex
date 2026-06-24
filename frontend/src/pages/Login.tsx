import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'
import { Activity, DollarSign, ArrowRight, Eye, Cpu, EyeOff } from 'lucide-react'
import KelvexLogo from '../components/ui/KelvexLogo'

function getPasswordStrength(pw: string): { score: number; label: string; color: string } {
  let score = 0
  if (pw.length >= 8) score++
  if (pw.length >= 12) score++
  if (/[A-Z]/.test(pw)) score++
  if (/[0-9]/.test(pw)) score++
  if (/[^A-Za-z0-9]/.test(pw)) score++
  if (score <= 1) return { score, label: 'Weak', color: '#f87171' }
  if (score <= 2) return { score, label: 'Fair', color: '#fb923c' }
  if (score <= 3) return { score, label: 'Good', color: '#facc15' }
  return { score, label: 'Strong', color: '#34d399' }
}

function friendlyError(err: unknown): string {
  if (!(err instanceof Error)) return 'Something went wrong. Please try again.'
  const msg = err.message.toLowerCase()
  if (msg.includes('incorrect') || msg.includes('invalid') || msg.includes('401'))
    return 'Incorrect email or password.'
  if (msg.includes('already') || msg.includes('exists') || msg.includes('409'))
    return 'An account with that email already exists.'
  if (msg.includes('422') || msg.includes('validation'))
    return 'Please check your details and try again.'
  if (msg.includes('network') || msg.includes('fetch'))
    return 'Cannot reach the server. Check your connection.'
  return err.message
}

export default function Login() {
  const { login, homeRoute } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? null

  const [isRegister, setIsRegister] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [fullName, setFullName] = useState('')
  const [orgName, setOrgName] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const strength = isRegister ? getPasswordStrength(password) : null

  const validate = (): string | null => {
    if (isRegister) {
      if (!fullName.trim()) return 'Full name is required.'
      if (!orgName.trim()) return 'Company name is required.'
      if (password.length < 8) return 'Password must be at least 8 characters.'
      if (password !== confirmPassword) return 'Passwords do not match.'
    }
    if (!email.includes('@')) return 'Enter a valid email address.'
    if (!password) return 'Password is required.'
    return null
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const validationError = validate()
    if (validationError) { setError(validationError); return }
    setError('')
    setLoading(true)
    try {
      let tokens
      if (isRegister) {
        tokens = await api.register(email, password, fullName, orgName)
      } else {
        tokens = await api.login(email, password)
      }
      await login(tokens.access_token, tokens.refresh_token, rememberMe)
      navigate(isRegister ? '/onboarding' : (from ?? homeRoute), { replace: true })
    } catch (err) {
      setError(friendlyError(err))
    } finally {
      setLoading(false)
    }
  }

  const switchMode = () => {
    setIsRegister(r => !r)
    setError('')
    setConfirmPassword('')
  }

  return (
    <div style={styles.container}>
      {/* Left panel — branding */}
      <div style={styles.brandPanel}>
        <div style={styles.brandContent}>
          <div style={styles.logoMark}>
            <KelvexLogo size={28} />
          </div>
          <h1 style={styles.brandName}>Kelvex</h1>
          <p style={styles.brandTagline}>
            The operating system for cold storage facilities
          </p>
          <div style={styles.features}>
            <div style={styles.feature}>
              <div style={styles.featureIcon}><Eye size={18} /></div>
              <div>
                <div style={styles.featureTitle}>Full facility visibility</div>
                <div style={styles.featureDesc}>Every compressor, every zone, every facility — one dashboard</div>
              </div>
            </div>
            <div style={styles.feature}>
              <div style={styles.featureIcon}><DollarSign size={18} /></div>
              <div>
                <div style={styles.featureTitle}>Lower your energy bill</div>
                <div style={styles.featureDesc}>See exactly where your money goes and how to spend less of it</div>
              </div>
            </div>
            <div style={styles.feature}>
              <div style={styles.featureIcon}><Cpu size={18} /></div>
              <div>
                <div style={styles.featureTitle}>Works with your equipment</div>
                <div style={styles.featureDesc}>Modbus and BACnet native — connects to your existing controllers with no equipment replacement</div>
              </div>
            </div>
            <div style={styles.feature}>
              <div style={styles.featureIcon}><Activity size={18} /></div>
              <div>
                <div style={styles.featureTitle}>Built for cold storage ops</div>
                <div style={styles.featureDesc}>Not a generic energy tool — designed for how your facilities actually work</div>
              </div>
            </div>
          </div>
        </div>
        <div style={styles.gridBg} />
      </div>

      {/* Right panel — auth form */}
      <div style={styles.formPanel}>
        <div style={styles.formWrapper}>
          <div style={styles.formHeader}>
            <h2 style={styles.formTitle}>{isRegister ? 'Create your account' : 'Welcome back'}</h2>
            <p style={styles.formSubtitle}>
              {isRegister
                ? 'Start monitoring your cold storage operations in minutes'
                : 'Sign in to your Kelvex dashboard'}
            </p>
          </div>

          <form onSubmit={handleSubmit} style={styles.form} noValidate>
            {isRegister && (
              <>
                <div style={styles.fieldGroup}>
                  <label style={styles.label}>Full name</label>
                  <input
                    type="text" value={fullName} onChange={e => setFullName(e.target.value)}
                    style={styles.input} placeholder="Jane Smith" autoComplete="name"
                  />
                </div>
                <div style={styles.fieldGroup}>
                  <label style={styles.label}>Company</label>
                  <input
                    type="text" value={orgName} onChange={e => setOrgName(e.target.value)}
                    style={styles.input} placeholder="Acme Cold Storage" autoComplete="organization"
                  />
                </div>
              </>
            )}

            <div style={styles.fieldGroup}>
              <label style={styles.label}>Email</label>
              <input
                type="email" value={email} onChange={e => setEmail(e.target.value)}
                style={styles.input} placeholder="you@company.com" autoComplete="email"
              />
            </div>

            <div style={styles.fieldGroup}>
              <label style={styles.label}>Password</label>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password} onChange={e => setPassword(e.target.value)}
                  style={{ ...styles.input, paddingRight: 40 }}
                  placeholder={isRegister ? 'Create a password (8+ chars)' : 'Enter your password'}
                  autoComplete={isRegister ? 'new-password' : 'current-password'}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(s => !s)}
                  style={styles.eyeBtn}
                  tabIndex={-1}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
              {isRegister && password && strength && (
                <div style={{ marginTop: 6 }}>
                  <div style={{ display: 'flex', gap: 3, marginBottom: 3 }}>
                    {[1, 2, 3, 4].map(i => (
                      <div key={i} style={{
                        flex: 1, height: 3, borderRadius: 2,
                        background: i <= strength.score ? strength.color : 'rgba(148,163,184,0.15)',
                        transition: 'background 200ms',
                      }} />
                    ))}
                  </div>
                  <span style={{ fontSize: 11, color: strength.color }}>{strength.label}</span>
                </div>
              )}
            </div>

            {isRegister && (
              <div style={styles.fieldGroup}>
                <label style={styles.label}>Confirm password</label>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
                  style={{
                    ...styles.input,
                    borderColor: confirmPassword && confirmPassword !== password
                      ? 'rgba(248,113,113,0.4)' : undefined,
                  }}
                  placeholder="Repeat your password"
                  autoComplete="new-password"
                />
              </div>
            )}

            {error && (
              <div style={styles.errorBox}>
                <span style={styles.errorText}>{error}</span>
              </div>
            )}

            {!isRegister && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <label style={{ ...styles.rememberRow, margin: 0 }}>
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={e => setRememberMe(e.target.checked)}
                    style={{ accentColor: '#38bdf8', width: 14, height: 14 }}
                  />
                  <span style={{ fontSize: 13, color: '#94a3b8' }}>Remember me</span>
                </label>
                <a href="/forgot-password" style={{ fontSize: 13, color: '#38bdf8', textDecoration: 'none' }}>
                  Forgot password?
                </a>
              </div>
            )}

            <button type="submit" style={styles.submitBtn} disabled={loading}>
              {loading
                ? <span style={styles.spinner} />
                : <>{isRegister ? 'Get Started' : 'Sign In'}<ArrowRight size={16} /></>}
            </button>
          </form>

          <div style={styles.divider}>
            <span style={styles.dividerLine} />
            <span style={styles.dividerText}>
              {isRegister ? 'Already have an account?' : 'New to Kelvex?'}
            </span>
            <span style={styles.dividerLine} />
          </div>

          <button onClick={switchMode} style={styles.toggleBtn}>
            {isRegister ? 'Sign in instead' : 'Create an account'}
          </button>
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: { display: 'flex', minHeight: '100vh' },
  brandPanel: {
    flex: '0 0 45%', background: 'linear-gradient(160deg, #0a0f1a 0%, #0c1929 40%, #0f1f35 100%)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '48px 56px',
    position: 'relative', overflow: 'hidden', borderRight: '1px solid rgba(148, 163, 184, 0.06)',
  },
  brandContent: { position: 'relative', zIndex: 1, maxWidth: 420 },
  logoMark: {
    width: 48, height: 48, borderRadius: 12,
    background: 'linear-gradient(135deg, rgba(56, 189, 248, 0.15), rgba(56, 189, 248, 0.05))',
    border: '1px solid rgba(56, 189, 248, 0.2)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#38bdf8', marginBottom: 24,
  },
  brandName: { fontSize: 36, fontWeight: 700, color: '#f1f5f9', letterSpacing: '-0.02em', marginBottom: 8 },
  brandTagline: { fontSize: 16, color: '#94a3b8', lineHeight: 1.5, marginBottom: 48 },
  features: { display: 'flex', flexDirection: 'column' as const, gap: 28 },
  feature: { display: 'flex', gap: 14, alignItems: 'flex-start' },
  featureIcon: {
    width: 36, height: 36, borderRadius: 8, background: 'rgba(56, 189, 248, 0.08)',
    border: '1px solid rgba(56, 189, 248, 0.12)', display: 'flex', alignItems: 'center',
    justifyContent: 'center', color: '#38bdf8', flexShrink: 0,
  },
  featureTitle: { fontSize: 14, fontWeight: 600, color: '#e2e8f0', marginBottom: 2 },
  featureDesc: { fontSize: 13, color: '#64748b', lineHeight: 1.4 },
  gridBg: {
    position: 'absolute' as const, inset: 0,
    backgroundImage: 'linear-gradient(rgba(56, 189, 248, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(56, 189, 248, 0.03) 1px, transparent 1px)',
    backgroundSize: '48px 48px',
    maskImage: 'radial-gradient(ellipse at center, black 30%, transparent 80%)',
    WebkitMaskImage: 'radial-gradient(ellipse at center, black 30%, transparent 80%)',
  },
  formPanel: { flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '48px 56px', background: '#111827' },
  formWrapper: { width: '100%', maxWidth: 380 },
  formHeader: { marginBottom: 32 },
  formTitle: { fontSize: 22, fontWeight: 600, color: '#f1f5f9', marginBottom: 6, letterSpacing: '-0.01em' },
  formSubtitle: { fontSize: 14, color: '#64748b' },
  form: { display: 'flex', flexDirection: 'column' as const, gap: 18 },
  fieldGroup: { display: 'flex', flexDirection: 'column' as const, gap: 6 },
  label: { fontSize: 13, fontWeight: 500, color: '#94a3b8', letterSpacing: '0.01em' },
  input: {
    padding: '10px 14px', borderRadius: 8, border: '1px solid rgba(148, 163, 184, 0.12)',
    background: 'rgba(15, 23, 42, 0.6)', color: '#f1f5f9', fontSize: 14, outline: 'none',
    transition: 'border-color 200ms ease, box-shadow 200ms ease', width: '100%', boxSizing: 'border-box' as const,
  },
  eyeBtn: {
    position: 'absolute' as const, right: 10, top: '50%', transform: 'translateY(-50%)',
    background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', padding: 2,
    display: 'flex', alignItems: 'center',
  },
  rememberRow: {
    display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', userSelect: 'none' as const,
  },
  errorBox: {
    padding: '10px 14px', borderRadius: 8,
    background: 'rgba(248, 113, 113, 0.08)', border: '1px solid rgba(248, 113, 113, 0.15)',
  },
  errorText: { color: '#f87171', fontSize: 13 },
  submitBtn: {
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '11px 20px',
    borderRadius: 8, border: 'none', background: 'linear-gradient(135deg, #0ea5e9, #38bdf8)',
    color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer',
    transition: 'opacity 200ms ease, transform 100ms ease', marginTop: 4,
  },
  spinner: {
    width: 18, height: 18, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff',
    borderRadius: '50%', display: 'inline-block', animation: 'spin 0.6s linear infinite',
  },
  divider: { display: 'flex', alignItems: 'center', gap: 12, margin: '28px 0 20px' },
  dividerLine: { flex: 1, height: 1, background: 'rgba(148, 163, 184, 0.1)' },
  dividerText: { fontSize: 12, color: '#64748b', whiteSpace: 'nowrap' as const },
  toggleBtn: {
    width: '100%', padding: '10px 16px', borderRadius: 8,
    border: '1px solid rgba(148, 163, 184, 0.12)', background: 'transparent',
    color: '#94a3b8', fontSize: 14, fontWeight: 500, cursor: 'pointer',
    transition: 'border-color 200ms ease, color 200ms ease',
  },
}
