import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuth } from '../contexts/AuthContext'
import KelvexLogo from '../components/ui/KelvexLogo'
import { Eye, EyeOff, CheckCircle } from 'lucide-react'

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

export default function AcceptInvitePage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { login } = useAuth()
  const token = params.get('token') ?? ''

  // Token verification state
  const [verifying, setVerifying] = useState(true)
  const [tokenError, setTokenError] = useState<string | null>(null)
  const [inviteInfo, setInviteInfo] = useState<{ email: string; role: string; org_name: string; expires_at: string } | null>(null)

  // Form state
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (!token) {
      setTokenError('No invite token found in this link.')
      setVerifying(false)
      return
    }
    api.verifyInviteToken(token)
      .then(info => {
        setInviteInfo(info)
        setVerifying(false)
      })
      .catch((e: unknown) => {
        setTokenError(e instanceof Error ? e.message : 'This invite link is invalid or has expired.')
        setVerifying(false)
      })
  }, [token])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)

    if (!fullName.trim()) return setFormError('Please enter your name.')
    if (password.length < 8) return setFormError('Password must be at least 8 characters.')
    if (password !== confirm) return setFormError('Passwords do not match.')

    setSubmitting(true)
    try {
      const tokens = await api.acceptInvite({ token, full_name: fullName, password })
      // Store tokens and log in
      localStorage.setItem('access_token', tokens.access_token)
      localStorage.setItem('refresh_token', tokens.refresh_token)
      await login(inviteInfo!.email, password)
      navigate('/', { replace: true })
    } catch (e: unknown) {
      setFormError(e instanceof Error ? e.message : 'Something went wrong. Please try again.')
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
    maxWidth: 440,
  }

  if (verifying) {
    return (
      <div style={containerStyle}>
        <div style={cardStyle}>
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <p style={{ color: 'var(--muted)', fontSize: 14 }}>Validating invite link…</p>
          </div>
        </div>
      </div>
    )
  }

  if (tokenError) {
    return (
      <div style={containerStyle}>
        <div style={cardStyle}>
          <div style={{ textAlign: 'center', marginBottom: 28 }}>
            <KelvexLogo size={32} />
          </div>
          <h1 style={{ fontSize: 20, fontWeight: 700, textAlign: 'center', marginBottom: 12 }}>Invalid invite</h1>
          <p style={{ color: 'var(--muted)', fontSize: 14, textAlign: 'center', marginBottom: 24 }}>{tokenError}</p>
          <p style={{ color: 'var(--muted)', fontSize: 13, textAlign: 'center' }}>
            Ask your admin to send a new invite, or{' '}
            <a href="mailto:ben@kelvex.io" style={{ color: 'var(--accent)' }}>contact support</a>.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div style={containerStyle}>
      <div style={cardStyle}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <KelvexLogo size={32} />
        </div>

        {/* Welcome header */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 6 }}>
            You've been invited to Kelvex
          </h1>
          <p style={{ color: 'var(--muted)', fontSize: 14, lineHeight: 1.5 }}>
            You're joining <strong style={{ color: 'var(--text)' }}>{inviteInfo!.org_name}</strong> as{' '}
            <strong style={{ color: 'var(--text)' }}>{inviteInfo!.role}</strong>.
          </p>
        </div>

        {/* Pre-filled email */}
        <div style={{
          background: 'var(--bg)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          padding: '10px 14px',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginBottom: 24,
        }}>
          <CheckCircle size={14} color="var(--ok)" />
          <span style={{ fontSize: 14, color: 'var(--muted)' }}>Invited as</span>
          <span style={{ fontSize: 14, fontWeight: 600 }}>{inviteInfo!.email}</span>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 6 }}>Your name</label>
            <input
              type="text"
              value={fullName}
              onChange={e => setFullName(e.target.value)}
              placeholder="Jordan Alvarez"
              autoFocus
              style={{ width: '100%' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 6 }}>Set your password</label>
            <div style={{ position: 'relative' }}>
              <input
                type={showPw ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                style={{ width: '100%', paddingRight: 40 }}
              />
              <button
                type="button"
                onClick={() => setShowPw(s => !s)}
                style={{
                  position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                  background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 0,
                }}
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

          {formError && (
            <div style={{
              background: 'rgba(239,68,68,.1)',
              border: '1px solid rgba(239,68,68,.3)',
              borderRadius: 6,
              padding: '10px 14px',
              fontSize: 13,
              color: '#f87171',
            }}>
              {formError}
            </div>
          )}

          <button
            type="submit"
            className="btn btn-accent"
            disabled={submitting}
            style={{ width: '100%', justifyContent: 'center', padding: '11px 0', marginTop: 4 }}
          >
            {submitting ? 'Creating account…' : 'Create account and sign in'}
          </button>
        </form>

        <p style={{ fontSize: 12, color: 'var(--muted)', textAlign: 'center', marginTop: 20 }}>
          Already have an account?{' '}
          <a href="/login" style={{ color: 'var(--accent)' }}>Sign in</a>
        </p>
      </div>
    </div>
  )
}
