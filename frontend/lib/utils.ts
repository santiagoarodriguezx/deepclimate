import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...values: ClassValue[]) {
  return twMerge(clsx(values));
}

export function formatValue(value: number | null | undefined, digits = 1) {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return new Intl.NumberFormat("es-CO", { maximumFractionDigits: digits }).format(value);
}

export function formatDate(value?: string | null, options?: Intl.DateTimeFormatOptions) {
  const date = parseUtcDate(value);
  if (!date || Number.isNaN(date.getTime())) return "Sin registro";
  return new Intl.DateTimeFormat("es-CO", options ?? {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  }).format(date);
}

export function isRecent(value?: string | null, maxHours = 3) {
  if (!value) return false;
  const parsed = parseUtcDate(value);
  if (!parsed) return false;
  const age = Date.now() - parsed.getTime();
  return Number.isFinite(age) && age >= -5 * 60_000 && age <= maxHours * 3_600_000;
}

export function parseUtcDate(value?: string | null) {
  if (!value) return null;
  const normalized = value.trim().replace(" ", "T");
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized);
  const date = new Date(hasTimezone ? normalized : `${normalized}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function humanLag(seconds?: number | null) {
  if (seconds == null || !Number.isFinite(seconds)) return "Sin datos";
  if (seconds < 3600) return `${Math.max(0, Math.round(seconds / 60))} min`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h`;
  return `${Math.floor(seconds / 86400)} días`;
}
