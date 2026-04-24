import { Component, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          minHeight: '50vh', padding: '40px 20px', textAlign: 'center',
        }}>
          <div style={{
            width: 48, height: 48, borderRadius: '50%', background: 'var(--danger-bg)',
            color: 'var(--danger)', display: 'flex', alignItems: 'center', justifyContent: 'center',
            marginBottom: 16,
          }}>
            <AlertTriangle size={22} />
          </div>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>
            Something went wrong
          </h2>
          <p style={{ fontSize: 13, color: 'var(--text-tertiary)', maxWidth: 400, marginBottom: 16, lineHeight: 1.5 }}>
            An unexpected error occurred. Try refreshing the page or navigating back.
          </p>
          {this.state.error && (
            <pre style={{
              fontSize: 11, color: 'var(--text-muted)', background: 'var(--bg-tertiary)',
              padding: '8px 12px', borderRadius: 'var(--radius-md)', marginBottom: 16,
              maxWidth: 500, overflow: 'auto', textAlign: 'left',
            }}>
              {this.state.error.message}
            </pre>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn-secondary" onClick={this.handleReset}>Try Again</button>
            <button className="btn-primary" onClick={() => window.location.href = '/'}>Go Home</button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
