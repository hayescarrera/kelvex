import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import KelvexLogo from '../components/ui/KelvexLogo'
import { ArrowLeft } from 'lucide-react'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      await api.requestPasswordReset(email.trim().toLowerCase())
    } catch {
      // Swallow errors — we don't expose whether the email exists
    } finally {
      setLoading(false)
      setSubmitted(true)
    }
  }

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

  return (
    <div style={containerStyle}>
      <div style={cardStyle}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <KelvexLogo size={32} />
        </div>

        {submitted ? (
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 40, marginBottom: 16 }}>📬</div>
            <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>Check your email</h1>
            <p style={{ color: 'var(--muted)', fontSize: 14, lineHeight: 1.6, marginBottom: 24 }}>
              If <strong>{email}</strong> is associated with a Kelvex account, you'll receive a password reset link shortly.
            </p>
            <Link to="/login" style={{ color: 'var(--accent)', fontSize: 14 }}>
              Back to sign in
            </Link>
          </div>
        ) : (
          <>
            <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>Forgot your password?</h1>
            <p style={{ color: 'var(--muted)', fontSize: 14, lineHeight: 1.5, marginBottom: 28 }}>
              Enter your email and we'll send you a reset link.
            </p>

            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 6 }}>Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  required
                  autoFocus
                  style={{ width: '100%' }}
                />
              </div>

              <button
                type="submit"
                className="btn btn-accent"
                disabled={loading}
                style={{ width: '100%', justifyContent: 'center', padding: '11px 0' }}
              >
                {loading ? 'Sending…' : 'Send reset link'}
              </button>
            </form>

            <Link
              to="/login"
              style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--muted)', fontSize: 13, marginTop: 20, justifyContent: 'center', textDecoration: 'none' }}
            >
              <ArrowLeft size={13} /> Back to sign in
            </Link>
          </>
        )}
      </div>
    </div>
  )
}
