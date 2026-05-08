/** Number/currency/percent formatters matching Bloomberg-terminal conventions. */

export function fmtUSD(value: number | null | undefined, options: { compact?: boolean } = {}): string {
  if (value == null || isNaN(value)) return "—";
  if (options.compact) {
    if (Math.abs(value) >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(2)}B`;
    if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
    if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  }
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });
}

export function fmtPct(value: number | null | undefined, decimals = 2): string {
  if (value == null || isNaN(value)) return "—";
  return `${(value * 100).toFixed(decimals)}%`;
}

export function fmtNum(value: number | null | undefined, decimals = 2): string {
  if (value == null || isNaN(value)) return "—";
  return value.toLocaleString("en-US", { maximumFractionDigits: decimals });
}

export function fmtSignedUSD(value: number | null | undefined): string {
  if (value == null || isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${fmtUSD(value)}`;
}

export function fmtSignedPct(value: number | null | undefined, decimals = 2): string {
  if (value == null || isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${fmtPct(value, decimals)}`;
}

export function fmtRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffMin < 1440) return `${Math.floor(diffMin / 60)}h ago`;
  return `${Math.floor(diffMin / 1440)}d ago`;
}

export function pnlColor(value: number | null | undefined): string {
  if (value == null || isNaN(value) || value === 0) return "text-muted";
  return value > 0 ? "text-success" : "text-danger";
}
