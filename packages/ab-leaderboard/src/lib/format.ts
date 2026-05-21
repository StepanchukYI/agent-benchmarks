/** Display formatters. Pure functions, locale-stable. */

export function fmtMoney(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n < 0.01) return "$" + n.toFixed(4);
  if (n < 1) return "$" + n.toFixed(3);
  return "$" + n.toFixed(2);
}

export function fmtScore(n: number | null | undefined): string {
  return n == null ? "—" : n.toFixed(1);
}

export function fmtDelta(n: number | null | undefined): string {
  if (n == null) return "—";
  const sign = n > 0 ? "+" : "";
  return sign + n.toFixed(1);
}

export function fmtPct(n: number | null | undefined, digits = 1): string {
  if (n == null) return "—";
  return n.toFixed(digits) + "%";
}

export function fmtCompact(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "k";
  return n.toString();
}

export function deltaArrow(n: number | null | undefined): "▲" | "▼" | "·" {
  if (n == null || Math.abs(n) < 0.05) return "·";
  return n > 0 ? "▲" : "▼";
}

export function deltaTone(n: number | null | undefined): "up" | "dn" | "flat" {
  if (n == null || Math.abs(n) < 0.05) return "flat";
  return n > 0 ? "up" : "dn";
}

export function fmtIsoRelative(iso: string, now: Date = new Date()): string {
  const t = new Date(iso).getTime();
  const diffMs = now.getTime() - t;
  const min = Math.round(diffMs / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return min + "m ago";
  const hr = Math.round(min / 60);
  if (hr < 24) return hr + "h ago";
  const d = Math.round(hr / 24);
  if (d < 7) return d + "d ago";
  return new Date(iso).toISOString().slice(0, 10);
}

/** Short SHA — 7 hex chars max. */
export function shortSha(sha: string): string {
  return sha.slice(0, 7);
}
