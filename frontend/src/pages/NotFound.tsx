import { useNavigate } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'

export default function NotFound() {
  const navigate = useNavigate()
  return (
    <div className="page-container">
      <div className="empty-state" style={{ marginTop: 80 }}>
        <div className="empty-icon"><AlertTriangle size={28} /></div>
        <h3>Page not found</h3>
        <p>The page you&apos;re looking for doesn&apos;t exist or has been moved.</p>
        <button className="btn-primary" onClick={() => navigate('/')}>Back to Fleet Overview</button>
      </div>
    </div>
  )
}
