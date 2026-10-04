/** Relative age for an attention item. `now` is injected so the result is deterministic. */

export function formatAge(createdAt: string, now: Date): string {
  const created = new Date(createdAt);
  if (Number.isNaN(created.getTime())) {
    return "";
  }
  const diffMs = now.getTime() - created.getTime();
  if (diffMs < 60_000) {
    return "Just now";
  }
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 60) {
    return minutes === 1 ? "1 min ago" : `${minutes} min ago`;
  }
  const hours = Math.floor(diffMs / 3_600_000);
  if (hours < 24) {
    return hours === 1 ? "1 hour ago" : `${hours} hours ago`;
  }
  const days = localCalendarDays(created, now);
  if (days <= 1) {
    return "Yesterday";
  }
  return `${days} days ago`;
}

function localCalendarDays(created: Date, now: Date): number {
  const start = (value: Date) => new Date(value.getFullYear(), value.getMonth(), value.getDate());
  const ms = start(now).getTime() - start(created).getTime();
  return Math.round(ms / 86_400_000);
}
