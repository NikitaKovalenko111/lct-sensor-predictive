const values = [22, 25, 24, 29, 31, 34, 37, 45, 52, 61, 74, 86]

export function TrendChart() {
  const points = values.map((value, index) => `${(index / (values.length - 1)) * 100},${100 - value}`).join(' ')
  return (
    <div className="trend-chart">
      <div className="trend-chart__labels"><span>12:00</span><span>14:00</span><span>16:00</span></div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Рост совокупного риска за четыре часа">
        <defs><linearGradient id="riskArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#f05a3c" stopOpacity=".34" /><stop offset="1" stopColor="#f05a3c" stopOpacity="0" /></linearGradient></defs>
        <path d={`M ${points} L 100,100 L 0,100 Z`} fill="url(#riskArea)" />
        <polyline points={points} fill="none" stroke="#e54d31" strokeWidth="2.2" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  )
}
