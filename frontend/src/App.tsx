import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Alert, type Health, type Reading, type Tank, type Threshold } from "./api";
import { Sparkline, TrendChart } from "./charts";
import { ExportPanel } from "./ExportPanel";
import {
  ago,
  extremes,
  fmt,
  latestValid,
  METRICS,
  metricInfo,
  series,
  STATUS_LABEL,
  statusOf,
  timeFmt,
  type MetricKey,
  type Status,
} from "./metrics";

const RANGES = { "24h": { label: "24 hours", hours: 24 }, "7d": { label: "7 days", hours: 168 } } as const;
type RangeKey = keyof typeof RANGES;
const REFRESH_MS = 60_000;
const STALE_MIN = 30;

function StatusMark({ status }: { status: Status }) {
  if (status === "none") return null;
  return (
    <span className={`status s-${status}`}>
      <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
        {status === "good" && <path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />}
        {status === "warning" && <path d="M8 2l6.5 12h-13zM8 6.5v3.5M8 12v.2" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />}
        {status === "critical" && <path d="M5.2 1.5h5.6l3.7 3.7v5.6l-3.7 3.7H5.2l-3.7-3.7V5.2zM8 4.5v4.5M8 11.3v.2" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />}
      </svg>
      {STATUS_LABEL[status]}
    </span>
  );
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [tanks, setTanks] = useState<Tank[]>([]);
  const [tankId, setTankId] = useState("");
  const [range, setRange] = useState<RangeKey>("24h");
  const [readings, setReadings] = useState<Reading[]>([]);
  const [thresholds, setThresholds] = useState<Threshold[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [detail, setDetail] = useState<MetricKey>("temperature");
  const [showResolved, setShowResolved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadedAt, setLoadedAt] = useState<Date | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([api<Health>("/health"), api<Tank[]>("/tanks")])
      .then(([h, t]) => {
        setHealth(h);
        setTanks(t);
        setTankId((cur) => cur || t[0]?.id || "");
      })
      .catch((e: Error) => setError(`Can't reach the monitoring server (${e.message}). Check that the backend is running.`));
  }, []);

  const load = useCallback(async () => {
    if (!tankId) return;
    const start = new Date(Date.now() - RANGES[range].hours * 3600_000).toISOString();
    try {
      const [r, t, a] = await Promise.all([
        api<Reading[]>(`/readings?tank_id=${tankId}&start=${encodeURIComponent(start)}&limit=20000`),
        api<Threshold[]>(`/tanks/${tankId}/thresholds`),
        api<Alert[]>(`/alerts?tank_id=${tankId}&limit=100`),
      ]);
      setReadings(r);
      setThresholds(t);
      setAlerts(a);
      setError(null);
      setLoadedAt(new Date());
    } catch (e) {
      setError(`Couldn't load tank data: ${(e as Error).message}`);
    }
  }, [tankId, range]);

  useEffect(() => {
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  const byMetric = useMemo(() => Object.fromEntries(METRICS.map((m) => [m.key, series(readings, m.key)])), [readings]);
  const limit = (key: string) => thresholds.find((t) => t.metric === key);
  const withDay = range === "7d";
  const tank = tanks.find((t) => t.id === tankId);

  const lastReading = readings.length ? readings[readings.length - 1].observed_at : null;
  const stale = lastReading && loadedAt ? (loadedAt.getTime() - Date.parse(lastReading)) / 60000 > STALE_MIN : false;

  const doPoints = byMetric.dissolved_oxygen ?? [];
  const doNow = latestValid(doPoints);
  const doStatus = statusOf(doNow?.v, limit("dissolved_oxygen"));
  const doExt = extremes(doPoints);

  const activeAlerts = alerts.filter((a) => a.status !== "resolved");
  const resolved = alerts.filter((a) => a.status === "resolved");

  async function generate() {
    setBusy(true);
    try {
      await api(`/simulate/run?tank_id=${tankId}&hours=${RANGES[range].hours}`, { method: "POST", operator: true });
      await load();
    } catch (e) {
      setError(`Couldn't generate readings: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function acknowledge(id: string) {
    try {
      await api(`/alerts/${id}/acknowledge?by=dashboard`, { method: "POST", operator: true });
      await load();
    } catch (e) {
      setError(`Couldn't acknowledge the alert: ${(e as Error).message}`);
    }
  }

  return (
    <div className="shell">
      <header className="top">
        <div className="brand">
          <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">
            <path d="M16 3c5 7 9 11.5 9 16.5a9 9 0 0 1-18 0C7 14.5 11 10 16 3z" fill="var(--line)" />
            <path d="M11 20.5c1.6 1.4 3.2 2.1 5 2.1s3.4-.7 5-2.1" fill="none" stroke="var(--paper)" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          <div>
            <h1>Pond monitor</h1>
            <p className="sub">
              {loadedAt ? `Updated ${loadedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : "Connecting…"}
              {lastReading && <> · last reading {ago(lastReading)}</>}
            </p>
          </div>
        </div>

        <nav className="tanks" aria-label="Tanks">
          {tanks.map((t) => (
            <button key={t.id} className={t.id === tankId ? "tank on" : "tank"} aria-pressed={t.id === tankId} onClick={() => setTankId(t.id)}>
              <span className="tank-name">{t.name}</span>
              <span className="tank-meta">{t.species ?? "Species not set"}</span>
            </button>
          ))}
        </nav>

        <div className="top-actions">
          <div className="seg" role="group" aria-label="Time range">
            {(Object.keys(RANGES) as RangeKey[]).map((k) => (
              <button key={k} className={k === range ? "on" : ""} aria-pressed={k === range} onClick={() => setRange(k)}>
                {RANGES[k].label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {health?.simulation_mode && (
        <div className="notice sim">
          <span>
            <strong>Demo data.</strong> These readings are simulated; no real sensors are connected yet.
          </span>
          <button className="btn small" onClick={generate} disabled={busy || !tankId}>
            {busy ? "Generating…" : "Generate readings up to now"}
          </button>
        </div>
      )}
      {stale && !health?.simulation_mode && (
        <div className="notice warn">No reading for over {STALE_MIN} minutes. Check the probe and gateway power.</div>
      )}
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}

      <main className="grid">
        <section className={`panel hero s-edge-${doStatus}`} aria-labelledby="do-h">
          <div className="hero-read">
            <h2 id="do-h">Dissolved oxygen</h2>
            <div className="big">
              {fmt(doNow?.v, "dissolved_oxygen")}
              <span className="big-unit">mg/L</span>
            </div>
            <StatusMark status={doStatus} />
            <dl className="facts">
              <div>
                <dt>Lowest</dt>
                <dd>
                  {fmt(doExt.min?.v, "dissolved_oxygen")} <small>at {doExt.min ? timeFmt(doExt.min.t, withDay) : "—"}</small>
                </dd>
              </div>
              <div>
                <dt>Highest</dt>
                <dd>
                  {fmt(doExt.max?.v, "dissolved_oxygen")} <small>at {doExt.max ? timeFmt(doExt.max.t, withDay) : "—"}</small>
                </dd>
              </div>
              <div>
                <dt>Keep above</dt>
                <dd>
                  {limit("dissolved_oxygen")?.low_warning ?? "—"} <small>mg/L</small>
                </dd>
              </div>
            </dl>
            <p className="hint">
              Oxygen falls overnight and is lowest just before dawn. Run aerators early when the low point nears the
              shaded band.
            </p>
          </div>
          <div className="hero-chart">
            <TrendChart points={doPoints} metric="dissolved_oxygen" threshold={limit("dissolved_oxygen")} height={300} withDay={withDay} mark={doExt.min} />
            <p className="legend">
              <span className="key warn" /> Watch zone <span className="key crit" /> Act-now zone
              <span className="key dot" /> Lowest point
            </p>
          </div>
        </section>

        <aside className="panel alerts" aria-labelledby="alerts-h">
          <div className="panel-head row">
            <h2 id="alerts-h">Alerts</h2>
            <span className="count">{activeAlerts.length ? `${activeAlerts.length} active` : "All clear"}</span>
          </div>
          {activeAlerts.length === 0 && <p className="empty">Nothing needs attention in {tank?.name ?? "this tank"} right now.</p>}
          <ul className="alert-list">
            {activeAlerts.map((a) => (
              <li key={a.id} className={`alert s-edge-${a.severity}`}>
                <StatusMark status={a.severity} />
                <p className="alert-reason">{a.reason}</p>
                <p className="alert-meta">
                  Since {timeFmt(Date.parse(a.triggered_at), true)}
                  {a.status === "acknowledged" && ` · seen by ${a.acknowledged_by}`}
                </p>
                {a.status === "open" && (
                  <button className="btn small" onClick={() => acknowledge(a.id)}>
                    Mark as seen
                  </button>
                )}
              </li>
            ))}
          </ul>
          {resolved.length > 0 && (
            <>
              <button className="link" onClick={() => setShowResolved(!showResolved)} aria-expanded={showResolved}>
                {showResolved ? "Hide" : "Show"} {resolved.length} resolved
              </button>
              {showResolved && (
                <ul className="alert-list past">
                  {resolved.map((a) => (
                    <li key={a.id} className="alert">
                      <p className="alert-reason">{a.reason}</p>
                      <p className="alert-meta">
                        {timeFmt(Date.parse(a.triggered_at), true)} to {a.resolved_at ? timeFmt(Date.parse(a.resolved_at), true) : "—"}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </aside>

        <section className="readouts" aria-label="Other measurements">
          {METRICS.filter((m) => m.key !== "dissolved_oxygen").map((m) => {
            const pts = byMetric[m.key] ?? [];
            const now = latestValid(pts);
            const ext = extremes(pts);
            const st = statusOf(now?.v, limit(m.key));
            return (
              <button
                key={m.key}
                className={`readout${detail === m.key ? " on" : ""}`}
                onClick={() => setDetail(m.key)}
                aria-pressed={detail === m.key}
              >
                <span className="r-label">{m.label}</span>
                <span className="r-value">
                  {fmt(now?.v, m.key)}
                  <span className="r-unit">{m.unit}</span>
                </span>
                <Sparkline points={pts} />
                <span className="r-foot">
                  {st === "none" ? <span className="r-group">{m.group === "camera" ? "Camera" : "No limit set"}</span> : <StatusMark status={st} />}
                  <span className="r-range">
                    {fmt(ext.min?.v, m.key)}–{fmt(ext.max?.v, m.key)}
                  </span>
                </span>
              </button>
            );
          })}
        </section>

        <section className="panel detail" aria-labelledby="detail-h">
          <div className="panel-head">
            <h2 id="detail-h">{metricInfo(detail)?.label}</h2>
            <p className="lede">{metricInfo(detail)?.hint}. Pick another measurement above to see it here.</p>
          </div>
          <TrendChart points={byMetric[detail] ?? []} metric={detail} threshold={limit(detail)} withDay={withDay} height={380} />
          {limit(detail)?.reference && <p className="source">Limits: {limit(detail)?.reference}</p>}
        </section>

        <section className="panel behaviour" aria-labelledby="beh-h">
          <div className="panel-head">
            <h2 id="beh-h">Oxygen and fish behaviour</h2>
            <p className="lede">
              Same time axis, so you can see how fish respond. When oxygen drops, fish move less and gather at the
              surface.
            </p>
          </div>
          {(["dissolved_oxygen", "fish_activity", "surface_activity"] as const).map((k) => (
            <div className="stack-row" key={k}>
              <div className="stack-label">
                {metricInfo(k)?.label}
                <small>{metricInfo(k)?.unit}</small>
              </div>
              <TrendChart points={byMetric[k] ?? []} metric={k} threshold={limit(k)} height={120} withDay={withDay} syncId="behaviour" compact={k !== "surface_activity"} />
            </div>
          ))}
        </section>

        <ExportPanel tanks={tanks} />
      </main>

      <footer className="foot">
        Limits are general warm-water pond guidance until confirmed for your species. Times shown in your local time zone; stored in UTC.
      </footer>
    </div>
  );
}
