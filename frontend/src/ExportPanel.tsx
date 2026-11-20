import { useMemo, useState } from "react";
import { API_BASE, type Tank } from "./api";
import { METRICS } from "./metrics";

const day = (offset: number) => {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
};

export function ExportPanel({ tanks }: { tanks: Tank[] }) {
  const [tankIds, setTankIds] = useState<string[]>([]);
  const [metrics, setMetrics] = useState<string[]>(METRICS.map((m) => m.key));
  const [from, setFrom] = useState(day(-7));
  const [to, setTo] = useState(day(0));
  const [layout, setLayout] = useState<"wide" | "long">("wide");
  const [validOnly, setValidOnly] = useState(true);
  const [copied, setCopied] = useState(false);

  const toggle = (list: string[], set: (v: string[]) => void, id: string) =>
    set(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

  const url = useMemo(() => {
    const q = new URLSearchParams();
    tankIds.forEach((t) => q.append("tank_id", t));
    if (metrics.length < METRICS.length) metrics.forEach((m) => q.append("metric", m));
    // dates are local calendar days; send them as UTC instants
    if (from) q.set("start", new Date(`${from}T00:00:00`).toISOString());
    if (to) q.set("end", new Date(`${to}T23:59:59`).toISOString());
    q.set("layout", layout);
    if (validOnly) q.set("valid_only", "true");
    return `${API_BASE}/export/readings.csv?${q}`;
  }, [tankIds, metrics, from, to, layout, validOnly]);

  const fishUrl = useMemo(() => {
    const q = new URLSearchParams();
    tankIds.forEach((t) => q.append("tank_id", t));
    if (from) q.set("start", new Date(`${from}T00:00:00`).toISOString());
    if (to) q.set("end", new Date(`${to}T23:59:59`).toISOString());
    return `${API_BASE}/export/fish-positions.csv?${q}`;
  }, [tankIds, from, to]);

  const invalid =metrics.length === 0 || (from && to && from > to);

  return (
    <section className="panel export" aria-labelledby="export-h">
      <div className="panel-head">
        <h2 id="export-h">Download data</h2>
        <p className="lede">
          Water quality and camera behaviour in one CSV, for analysis in Excel, Python or R.
        </p>
      </div>

      <div className="export-grid">
        <fieldset>
          <legend>Tanks</legend>
          <label className="check">
            <input type="checkbox" checked={tankIds.length === 0} onChange={() => setTankIds([])} />
            All tanks
          </label>
          {tanks.map((t) => (
            <label className="check" key={t.id}>
              <input type="checkbox" checked={tankIds.includes(t.id)} onChange={() => toggle(tankIds, setTankIds, t.id)} />
              {t.name}
            </label>
          ))}
        </fieldset>

        <fieldset>
          <legend>Measurements</legend>
          {METRICS.map((m) => (
            <label className="check" key={m.key}>
              <input type="checkbox" checked={metrics.includes(m.key)} onChange={() => toggle(metrics, setMetrics, m.key)} />
              {m.label}
            </label>
          ))}
        </fieldset>

        <fieldset>
          <legend>Period</legend>
          <label className="field">
            From
            <input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className="field">
            To
            <input type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} />
          </label>
        </fieldset>

        <fieldset>
          <legend>File layout</legend>
          <label className="check">
            <input type="radio" name="layout" checked={layout === "wide"} onChange={() => setLayout("wide")} />
            <span>
              One row per time
              <small>A column for each measurement. Best for comparing oxygen with fish behaviour.</small>
            </span>
          </label>
          <label className="check">
            <input type="radio" name="layout" checked={layout === "long"} onChange={() => setLayout("long")} />
            <span>
              One row per reading
              <small>Includes quality flag and source for every value.</small>
            </span>
          </label>
          <label className="check">
            <input type="checkbox" checked={validOnly} onChange={(e) => setValidOnly(e.target.checked)} />
            Leave out failed readings
          </label>
        </fieldset>
      </div>

      <div className="export-actions">
        <a className={`btn primary${invalid ? " disabled" : ""}`} href={invalid ? undefined : url} aria-disabled={!!invalid} download>
          Download CSV
        </a>
        <button
          className="btn"
          type="button"
          disabled={!!invalid}
          onClick={() => {
            navigator.clipboard?.writeText(url).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            });
          }}
        >
          {copied ? "Link copied" : "Copy link"}
        </button>
        <span className="hint">
          {invalid ? "Pick at least one measurement and a valid period." : "The link always returns fresh data, so it works in scripts too."}
        </span>
      </div>

      <div className="panel-head fish-export">
        <h2>Fish movement data</h2>
        <p className="lede">
          Every position of every fish for the tanks and period above: time, fish, place in the tank (in cm) and body length.
        </p>
      </div>
      <div className="export-actions">
        <a className={`btn primary${from > to ? " disabled" : ""}`} href={from > to ? undefined : fishUrl} download>
          Download fish positions
        </a>
      </div>
    </section>
  );
}
