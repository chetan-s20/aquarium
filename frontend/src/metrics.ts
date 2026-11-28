import type { Reading, Threshold } from "./api";

export type MetricKey =
  | "dissolved_oxygen"
  | "temperature"
  | "ph"
  | "turbidity"
  | "ammonium"
  | "fish_activity"
  | "surface_activity";

export const METRICS: { key: MetricKey; label: string; unit: string; digits: number; group: "water" | "camera"; hint: string }[] = [
  { key: "dissolved_oxygen", label: "Oxygen", unit: "mg/L", digits: 1, group: "water", hint: "Oxygen in the water; lowest just before dawn" },
  { key: "temperature", label: "Temperature", unit: "°C", digits: 1, group: "water", hint: "Water temperature" },
  { key: "ph", label: "pH", unit: "", digits: 1, group: "water", hint: "How acidic the water is; 7 is neutral" },
  { key: "turbidity", label: "Cloudiness", unit: "NTU", digits: 0, group: "water", hint: "How cloudy the water is (turbidity)" },
  { key: "ammonium", label: "Ammonia", unit: "mg/L", digits: 2, group: "water", hint: "Waste from fish and feed; more toxic in warm, high-pH water" },
  { key: "fish_activity", label: "Fish activity", unit: "% moving", digits: 1, group: "camera", hint: "Share of the camera view in motion" },
  { key: "surface_activity", label: "Surface activity", unit: "% at surface", digits: 0, group: "camera", hint: "High values can mean fish are gasping for air" },
];

export const metricInfo = (key: string) => METRICS.find((m) => m.key === key);

export type Status = "good" | "warning" | "critical" | "none";

export function statusOf(value: number | null | undefined, t?: Threshold): Status {
  if (value == null) return "none";
  if (!t) return "none";
  if ((t.low_critical != null && value <= t.low_critical) || (t.high_critical != null && value >= t.high_critical)) return "critical";
  if ((t.low_warning != null && value <= t.low_warning) || (t.high_warning != null && value >= t.high_warning)) return "warning";
  return "good";
}

export const STATUS_LABEL: Record<Status, string> = {
  good: "In range",
  warning: "Watch",
  critical: "Act now",
  none: "No limit set",
};

export function fmt(value: number | null | undefined, key: string): string {
  if (value == null) return "—";
  return value.toFixed(metricInfo(key)?.digits ?? 1);
}

export type Point = { t: number; v: number | null };

/** Valid readings for one metric as chart points; invalid/missing become gaps. */
export function series(readings: Reading[], metric: string): Point[] {
  return readings
    .filter((r) => r.metric === metric)
    .map((r) => ({ t: Date.parse(r.observed_at), v: r.quality_status === "valid" ? r.value : null }));
}

export function latestValid(points: Point[]): Point | undefined {
  for (let i = points.length - 1; i >= 0; i--) if (points[i].v != null) return points[i];
  return undefined;
}

export function extremes(points: Point[]) {
  let min: Point | undefined;
  let max: Point | undefined;
  for (const p of points) {
    if (p.v == null) continue;
    if (!min || p.v < min.v!) min = p;
    if (!max || p.v > max.v!) max = p;
  }
  return { min, max };
}

export const timeFmt = (t: number, withDay = false) =>
  new Date(t).toLocaleString(undefined, withDay ? { weekday: "short", hour: "2-digit", minute: "2-digit" } : { hour: "2-digit", minute: "2-digit" });

export function ago(iso: string): string {
  const mins = Math.round((Date.now() - Date.parse(iso)) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
}
