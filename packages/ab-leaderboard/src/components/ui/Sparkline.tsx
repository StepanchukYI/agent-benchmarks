interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  strokeWidth?: number;
  fill?: boolean;
  /** ARIA-label for screen readers, e.g. "30-day correctness trend". */
  ariaLabel?: string;
}

export function Sparkline({
  data,
  width = 64,
  height = 18,
  color = "currentColor",
  strokeWidth = 1.4,
  fill = false,
  ariaLabel,
}: SparklineProps): JSX.Element | null {
  if (data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const step = width / (data.length - 1);
  const pts = data.map<[number, number]>((v, i) => [
    i * step,
    height - ((v - min) / range) * (height - 2) - 1,
  ]);
  const dPath = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
  const areaPath = fill ? `${dPath} L ${width},${height} L 0,${height} Z` : "";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role={ariaLabel ? "img" : undefined}
      aria-label={ariaLabel}
      className="inline-block align-middle"
    >
      {fill && <path d={areaPath} fill={color} opacity="0.12" />}
      <path d={dPath} stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
