import { useState } from 'react'
import { api } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'
import { Activity, DollarSign, ArrowRight, Eye, Cpu } from 'lucide-react'
import KelvexLogo from '../components/ui/KelvexLogo'

export default function Login() {
  const { login } = useAuth()
  const [isRegister, setIsRegister] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [orgName, setOrgName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      let tokens
      if (isRegister) {
        tokens = await api.register(email, password, fullName, orgName)
      } else {
        tokens = await api.login(email, password)
      }
      await login(tokens.access_token, tokens.refresh_token)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
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
                <div style={styles.featureDesc}>Danfoss, Copeland, Allen-Bradley — we connect to what you already run</div>
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
              {isRegister ? 'Start analyzing your demand charges in minutes' : 'Sign in to your Kelvex dashboard'}
            </p>
          </div>

          <form onSubmit={handleSubmit} style={styles.form}>
            {isRegister && (
              <>
                <div style={styles.fieldGroup}>
                  <label style={styles.label}>Full name</label>
                  <input type="text" value={fullName} onChange={e => setFullName(e.target.value)} style={styles.input} placeholder="Jane Smith" required />
                </div>
                <div style={styles.fieldGroup}>
                  <label style={styles.label}>Company</label>
                  <input type="text" value={orgName} onChange={e => setOrgName(e.target.value)} style={styles.input} placeholder="Acme Cold Storage" required />
                </div>
              </>
            )}
            <div style={styles.fieldGroup}>
              <label style={styles.label}>Email</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)} style={styles.input} placeholder="you@company.com" required />
            </div>
            <div style={styles.fieldGroup}>
              <label style={styles.label}>Password</label>
              <input type="password" value={password} onChange={e => setPassword(e.target.value)} style={styles.input} placeholder={isRegister ? 'Create a password' : 'Enter your password'} required />
            </div>
            {error && (
              <div style={styles.errorBox}><span style={styles.errorText}>{error}</span></div>
            )}
            <button type="submit" style={styles.submitBtn} disabled={loading}>
              {loading ? <span style={styles.spinner} /> : <>{isRegister ? 'Get Started' : 'Sign In'}<ArrowRight size={16} /></>}
            </button>
          </form>

          <div style={styles.divider}>
            <span style={styles.dividerLine} />
            <span style={styles.dividerText}>{isRegister ? 'Already have an account?' : 'New to Kelvex?'}</span>
            <span style={styles.dividerLine} />
          </div>
          <button onClick={() => { setIsRegister(!isRegister); setError('') }} style={styles.toggleBtn}>
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
  form: { display: 'flex', flexDirection: 'column' as const, gap: 20 },
  fieldGroup: { display: 'flex', flexDirection: 'column' as const, gap: 6 },
  label: { fontSize: 13, fontWeight: 500, color: '#94a3b8', letterSpacing: '0.01em' },
  input: {
    padding: '10px 14px', borderRadius: 8, border: '1px solid rgba(148, 163, 184, 0.12)',
    background: 'rgba(15, 23, 42, 0.6)', color: '#f1f5f9', fontSize: 14, outline: 'none',
    transition: 'border-color 200ms ease, box-shadow 200ms ease', width: '100%',
  },
  errorBox: { padding: '10px 14px', borderRadius: 8, background: 'rgba(248, 113, 113, 0.08)', border: '1px solid rgba(248, 113, 113, 0.15)' },
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
