interface ResourceBarProps {
  label: string
  value: number
  color: string
}

export default function ResourceBar({ label, value, color }: ResourceBarProps) {
  return (
    <div className="resource-bar">
      <div className="resource-bar-header">
        <span>{label}</span>
        <span>{value}%</span>
      </div>
      <div className="resource-bar-track">
        <div className="resource-bar-fill" style={{ width: `${value}%`, background: color }} />
      </div>
    </div>
  )
}
