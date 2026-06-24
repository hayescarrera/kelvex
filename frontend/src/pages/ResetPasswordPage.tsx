import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
import { api } from '../lib/api'
import KelvexLogo from '../components/ui/KelvexLogo'
import { Eye, EyeOff } from 'lucide-react'

function pwStrength(pw: string) {
  let s = 0
  if (pw.length >= 8) s++
  if (pw.length >= 12) s++
  if (/[A-Z]/.test(pw)) s++
  if (/[0-9]/.test(pw)) s++
  if (/[^A-Za-z0-9]/.test(pw)) s++
  if (s <= 1) return { label: 'Weak', color: '#f87171', width: '20%' }
  if (s <= 2) return { label: 'Fair', color: '#fb923c', width: '40%' }
  if (s <= 3) return { label: 'Good', color: '#facc15', width: '65%' }
  return { label: 'Strong', color: '#34d399', width: '100%' }
}

export default function ResetPasswordPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const token = params.get('token') ?? ''

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (!token) setError('No reset token found in this link.')
  }, [token])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (password.length < 8) return setError('Password must be at least 8 characters.')
    if (password !== confirm) return setError('Passwords do not match.')

    setSubmitting(true)
    try {
      await api.confirmPasswordReset(token, password)
      setDone(true)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'This reset link is invalid or has expired.')
    } finally {
      setSubmitting(false)
    }
  }

  const strength = pwStrength(password)

  const containerStyle: React.CSSProperties = {
    minHeight: '100vh',
    background: 'var(--bg)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  }

  const cardStyle: React.CSSProperties = {
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: 12,
    padding: 40,
    width: '100%',
    maxWidth: 420,
  }

  if (!token || error && !done) {
    return (
      <div style={containerStyle}>
        <div style={cardStyle}>
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <KelvexLogo size={32} />
          </div>
          <h1 style={{ fontSize: 20, fontWeight: 700, textAlign: 'center', marginBottom: 12 }}>Invalid link</h1>
          <p style={{ color: 'var(--muted)', fontSize: 14, textAlign: 'center', marginBottom: 24 }}>
            {error ?? 'This reset link is invalid or has expired.'}
          </p>
          <div style={{ textAlign: 'center' }}>
            <Link to="/forgot-password" style={{ color: 'var(--accent)', fontSize: 14 }}>Request a new link</Link>
          </div>
        </div>
      </div>
    )
  }

  if (done) {
    return (
      <div style={containerStyle}>
        <div style={cardStyle}>
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <KelvexLogo size={32} />
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 40, marginBottom: 16 }}>✓</div>
            <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>Password updated</h1>
            <p style={{ color: 'var(--muted)', fontSize: 14, marginBottom: 24 }}>
              You can now sign in with your new password.
            </p>
            <button
              className="btn btn-accent"
              onClick={() => navigate('/login', { replace: true })}
              style={{ width: '100%', justifyContent: 'center', padding: '11px 0' }}
            >
              Sign in
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={containerStyle}>
      <div style={cardStyle}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <KelvexLogo size={32} />
        </div>

        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>Set a new password</h1>
        <p style={{ color: 'var(--muted)', fontSize: 14, marginBottom: 28 }}>
          Choose a strong password for your account.
        </p>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 6 }}>New password</label>
            <div style={{ position: 'relative' }}>
              <input
                type={showPw ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                autoFocus
                style={{ width: '100%', paddingRight: 40 }}
              />
              <button
                type="button"
                onClick={() => setShowPw(s => !s)}
                style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 0 }}
              >
                {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            {password && (
              <div style={{ marginTop: 6 }}>
                <div style={{ height: 3, background: 'var(--border)', borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: strength.width, background: strength.color, transition: 'width .2s' }} />
                </div>
                <p style={{ fontSize: 11, color: strength.color, marginTop: 3 }}>{strength.label}</p>
              </div>
            )}
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 6 }}>Confirm password</label>
            <input
              type="password"
              value={confirm}
              onChange={e => setConfirm(e.target.value)}
              placeholder="Repeat password"
              style={{ width: '100%' }}
            />
          </div>

          {error && (
            <div style={{ background: 'rgba(239,68,68,.1)', border: '1px solid rgba(239,68,68,.3)', borderRadius: 6, padding: '10px 14px', fontSize: 13, color: '#f87171' }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn btn-accent"
            disabled={submitting}
            style={{ width: '100%', justifyContent: 'center', padding: '11px 0', marginTop: 4 }}
          >
            {submitting ? 'Updating…' : 'Update password'}
          </button>
        </form>
      </div>
    </div>
  )
}
