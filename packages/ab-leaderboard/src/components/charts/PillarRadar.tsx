interface PillarRadarProps {
  scores: Record<string, number>;
  size?: number;
}

/**
 * 5-axis radar — one polygon per pillar. Uses currentColor for the fill so
 * callers can theme it via a wrapping `text-…` class.
 */
export function PillarRadar({ scores, size = 200 }: PillarRadarProps): JSX.Element {
  const c = size / 2;
  const r = (size - 40) / 2;
  const labels = Object.keys(scores);
  const vals = Object.values(scores);
  const n = labels.length;

  function pt(value: number, idx: number): [number, number] {
    const angle = (idx / n) * Math.PI * 2 - Math.PI / 2;
    const rr = (value / 100) * r;
    return [c + Math.cos(angle) * rr, c + Math.sin(angle) * rr];
  }
  function polygonPath(ring: number): string {
    return (
      labels
        .map((_, i) => {
          const [x, y] = pt(ring, i);
          return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join(" ") + "Z"
    );
  }
  const valuePath =
    vals.map((v, i) => {
      const [x, y] = pt(v, i);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ") + "Z";

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
      {[25, 50, 75, 100].map((ring) => (
        <path
          key={ring}
          d={polygonPath(ring)}
          fill="none"
          className="stroke-border-soft"
          strokeWidth="0.7"
        />
      ))}
      {labels.map((label, i) => {
        const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
        const x = c + Math.cos(angle) * (r + 12);
        const y = c + Math.sin(angle) * (r + 12) + 3;
        return (
          <g key={label}>
            <line
              x1={c}
              y1={c}
              x2={c + Math.cos(angle) * r}
              y2={c + Math.sin(angle) * r}
              className="stroke-border-soft"
              strokeWidth="0.5"
            />
            <text
              x={x}
              y={y}
              textAnchor={
                Math.abs(Math.cos(angle)) < 0.3 ? "middle" : Math.cos(angle) > 0 ? "start" : "end"
              }
              fontSize="9"
              className="fill-muted-foreground"
            >
              {label}
            </text>
          </g>
        );
      })}
      <path d={polygonPath(100)} fill="none" className="stroke-border" strokeWidth="0.7" />
      <path
        d={valuePath}
        className="fill-accent stroke-accent"
        fillOpacity="0.18"
        strokeWidth="1.4"
      />
      {vals.map((v, i) => {
        const [x, y] = pt(v, i);
        return <circle key={i} cx={x} cy={y} r="2.5" className="fill-accent" />;
      })}
    </svg>
  );
}
