export function inr(value: number | undefined | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "₹0";
  const rounded = Math.round(value);
  return `₹${rounded.toLocaleString("en-IN")}`;
}

export function pct(value: number | undefined | null, digits = 1): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "–";
  return `${(value * 100).toFixed(digits)}%`;
}

export function daysUntil(dateStr: string, now: Date = new Date()): number {
  const target = new Date(`${dateStr}T00:00:00Z`);
  const nowUtc = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const ms = target.getTime() - nowUtc.getTime();
  return Math.ceil(ms / 86_400_000);
}

export function formatDate(dateStr: string | undefined | null): string {
  if (!dateStr) return "–";
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function formatDateTime(dateStr: string | undefined | null): string {
  if (!dateStr) return "–";
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  return d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
