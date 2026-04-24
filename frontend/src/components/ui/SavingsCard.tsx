import { TrendingDown } from 'lucide-react'

interface SavingsCardProps {
  title: string
  desc: string
  savings: string
  color: string
}

export default function SavingsCard({ title, desc, savings, color }: SavingsCardProps) {
  return (
    <div className="savings-card" style={{ '--card-accent': color } as any}>
      <div className="savings-card-icon"><TrendingDown size={18} /></div>
      <h4>{title}</h4>
      <p>{desc}</p>
      <div className="savings-card-value">~{savings} <span>demand reduction</span></div>
    </div>
  )
}
