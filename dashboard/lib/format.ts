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
