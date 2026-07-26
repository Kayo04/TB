export function formatTs(ts: string | null): string {
  if (!ts) return "--";
  return new Date(ts).toLocaleString();
}

export function formatNumber(n: number | string | null, decimals = 4): string {
  if (n === null || n === undefined) return "--";
  const value = typeof n === "string" ? Number(n) : n;
  if (Number.isNaN(value)) return "--";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

// Signed dollar amount for P&L-style figures -- real minus sign (not a
// hyphen), explicit "+" on positive so the sign is never ambiguous at a
// glance in a stat tile.
export function formatMoney(n: number | null, decimals = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "--";
  const sign = n > 0 ? "+" : n < 0 ? "−" : "";
  return `${sign}$${Math.abs(n).toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

// Unsigned dollar amount -- for absolute quantities (equity, fees), where a
// leading "+" would read as noise rather than signal. Use formatMoney
// instead for deltas/P&L, where the sign IS the signal.
export function formatDollar(n: number | null, decimals = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "--";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

export function formatPercent(n: number | null, decimals = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "--";
  return `${(n * 100).toFixed(decimals)}%`;
}
