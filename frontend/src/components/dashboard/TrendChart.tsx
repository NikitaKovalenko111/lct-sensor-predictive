export function TrendChart({ values, labels }: { values: Array<number | null>; labels: [string, string, string] }) {
  const points = values
    .map((value, index) => value === null ? null : `${(index / Math.max(1, values.length - 1)) * 100},${100 - Math.max(0, Math.min(100, value))}`)
    .filter((point): point is string => point !== null)
    .join(' ')
  const hasLine = points.includes(' ')
  return (
    <div className="trend-chart">
      <div className="trend-chart__labels"><span>{labels[0]}</span><span>{labels[1]}</span><span>{labels[2]}</span></div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Фактическая динамика совокупного риска за четыре часа">
        <defs><linearGradient id="riskArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#f05a3c" stopOpacity=".34" /><stop offset="1" stopColor="#f05a3c" stopOpacity="0" /></linearGradient></defs>
        {hasLine && <path d={`M ${points} L 100,100 L 0,100 Z`} fill="url(#riskArea)" />}
        {hasLine && <polyline points={points} fill="none" stroke="#e54d31" strokeWidth="2.2" vectorEffect="non-scaling-stroke" />}
      </svg>
    </div>
  )
}
