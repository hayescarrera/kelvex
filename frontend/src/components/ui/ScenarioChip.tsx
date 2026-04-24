interface ScenarioChipProps {
  color: string
  title: string
  desc: string
}

export default function ScenarioChip({ color, title, desc }: ScenarioChipProps) {
  return (
    <div className="scenario-chip" style={{ '--chip-color': color } as any}>
      <h5>{title}</h5>
      <p>{desc}</p>
    </div>
  )
}
