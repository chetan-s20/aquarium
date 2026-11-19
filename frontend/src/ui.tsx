import { useEffect, useState, type ReactNode } from "react";
import type { FishStatus, Threshold } from "./api";
import { STATUS_LABEL, type Status } from "./metrics";

/* ---------- routing: #/tank/<id>, #/fish/<id>, #/download ---------- */

export function useRoute(): string[] {
  const read = () => window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => {
      setRoute(read());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

/* ---------- status ---------- */

const ICONS: Record<"good" | "warning" | "critical", ReactNode> = {
  good: <path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />,
  warning: <path d="M8 2l6.5 12h-13zM8 6.5v3.5M8 12v.2" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />,
  critical: <path d="M5.2 1.5h5.6l3.7 3.7v5.6l-3.7 3.7H5.2l-3.7-3.7V5.2zM8 4.5v4.5M8 11.3v.2" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />,
};

export function StatusMark({ status, label }: { status: Status; label?: string }) {
  if (status === "none") return label ? <span className="status s-none">{label}</span> : null;
  return (
    <span className={`status s-${status}`}>
      <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
        {ICONS[status]}
      </svg>
      {label ?? STATUS_LABEL[status]}
    </span>
  );
}

export const FISH_STATUS: Record<FishStatus, { label: string; tone: Status }> = {
  check: { label: "Needs a check", tone: "critical" },
  watch: { label: "Keep an eye on it", tone: "warning" },
  healthy: { label: "Healthy", tone: "good" },
  unknown: { label: "Not enough data yet", tone: "none" },
  removed: { label: "No longer in tank", tone: "none" },
};

export const FishStatusMark = ({ status }: { status: FishStatus }) => (
  <StatusMark status={FISH_STATUS[status].tone} label={FISH_STATUS[status].label} />
);

/* ---------- fish + tank drawings ---------- */

export function FishIcon({ color, size = 40, facing = 1, faded = false }: { color: string | null; size?: number; facing?: number; faded?: boolean }) {
  const c = color ?? "#9aa7ad";
  return (
    <svg viewBox="0 0 48 28" width={size} height={(size * 28) / 48} aria-hidden="true" style={{ opacity: faded ? 0.4 : 1 }}>
      <g transform={facing < 0 ? "translate(48 0) scale(-1 1)" : undefined}>
        <path d="M2 4l10 10L2 24c2-6 2-14 0-20z" fill={c} stroke="rgba(0,0,0,.35)" strokeWidth="1" />
        <ellipse cx="27" cy="14" rx="18" ry="10" fill={c} stroke="rgba(0,0,0,.35)" strokeWidth="1" />
        <path d="M22 5c3 3 3 15 0 18" fill="none" stroke="rgba(0,0,0,.18)" strokeWidth="1.2" />
        <circle cx="37" cy="11.5" r="2.3" fill="#fff" />
        <circle cx="37.6" cy="11.5" r="1.2" fill="#10262a" />
      </g>
    </svg>
  );
}

/** Side view of the tank. Children are positioned with x/y in 0..1 (0,0 = top-left of the water). */
export function TankScene({ children, ratio = 2.4, label }: { children?: ReactNode; ratio?: number; label: string }) {
  return (
    <div className="scene" style={{ aspectRatio: String(ratio) }} role="group" aria-label={label}>
      <svg className="scene-art" viewBox="0 0 240 100" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <linearGradient id="water" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="var(--water-top)" />
            <stop offset="1" stopColor="var(--water-bottom)" />
          </linearGradient>
        </defs>
        <rect width="240" height="100" fill="url(#water)" />
        <path d="M0 2 Q 15 0 30 2 T 60 2 T 90 2 T 120 2 T 150 2 T 180 2 T 210 2 T 240 2" fill="none" stroke="var(--surface-line)" strokeWidth="0.8" />
        <path d="M0 93 Q 30 89 60 92 T 120 91 T 180 93 T 240 90 V100 H0z" fill="var(--sand)" />
        <path d="M20 92 C 18 80 24 74 20 62 M24 92 C 27 82 22 76 27 66" stroke="var(--weed)" strokeWidth="1.6" fill="none" strokeLinecap="round" />
        <path d="M214 92 C 211 78 218 70 213 56 M219 92 C 222 80 216 72 222 64" stroke="var(--weed)" strokeWidth="1.6" fill="none" strokeLinecap="round" />
      </svg>
      <div className="scene-layer">{children}</div>
    </div>
  );
}

/* ---------- day picker ---------- */

export function lastDays(n: number, offsetHours = 5.5): { value: string; label: string }[] {
  const now = new Date(Date.now() + offsetHours * 3600_000);
  return Array.from({ length: n }, (_, i) => {
    const d = new Date(now.getTime() - i * 86400_000).toISOString().slice(0, 10);
    const label = i === 0 ? "Today" : i === 1 ? "Yesterday" : new Date(`${d}T12:00:00`).toLocaleDateString(undefined, { weekday: "long" });
    return { value: d, label };
  });
}

export function DayPicker({ value, onChange, days }: { value: string; onChange: (d: string) => void; days: { value: string; label: string }[] }) {
  return (
    <div className="seg" role="group" aria-label="Day">
      {days.map((d) => (
        <button key={d.value} className={d.value === value ? "on" : ""} aria-pressed={d.value === value} onClick={() => onChange(d.value)}>
          {d.label}
        </button>
      ))}
    </div>
  );
}

/* ---------- water verdict in plain words ---------- */

export type Verdict = { tone: Status; title: string; advice: string };

export function waterVerdict(latest: Record<string, number | undefined>, limits: Threshold[], hasData: boolean): Verdict {
  if (!hasData) return { tone: "none", title: "No recent water readings", advice: "Check that the water probe and its gateway are switched on." };
  const lim = (m: string) => limits.find((t) => t.metric === m);
  const checks: { metric: string; low: [string, string]; high: [string, string] }[] = [
    { metric: "dissolved_oxygen", low: ["Oxygen is low", "Turn on the aerator now and hold back feeding until oxygen recovers."], high: ["Oxygen is very high", "Usually harmless. Check the probe if it stays this way."] },
    { metric: "temperature", low: ["Water is too cold", "Check the heater, or cover the tank at night."], high: ["Water is too warm", "Shade the tank and add aeration: warm water holds less oxygen."] },
    { metric: "ph", low: ["Water is too acidic", "Do a partial water change and check the buffer (lime)."], high: ["Water is too alkaline", "Do a partial water change and check for algae bloom."] },
    { metric: "turbidity", low: ["Water is very clear", "No action needed."], high: ["Water is very cloudy", "Check the filter, cut feeding a little and consider a water change."] },
  ];
  let worst: Verdict | null = null;
  for (const c of checks) {
    const v = latest[c.metric];
    const t = lim(c.metric);
    if (v == null || !t) continue;
    const crit = (t.low_critical != null && v <= t.low_critical) || (t.high_critical != null && v >= t.high_critical);
    const warn = crit || (t.low_warning != null && v <= t.low_warning) || (t.high_warning != null && v >= t.high_warning);
    if (!warn) continue;
    const low = (t.low_warning != null && v <= t.low_warning) || (t.low_critical != null && v <= t.low_critical);
    const [title, advice] = low ? c.low : c.high;
    const tone: Status = crit ? "critical" : "warning";
    if (!worst || (tone === "critical" && worst.tone !== "critical")) worst = { tone, title: crit ? `${title}: act now` : title, advice };
  }
  return worst ?? { tone: "good", title: "Water is healthy", advice: "All readings are in the safe range. No action needed." };
}
