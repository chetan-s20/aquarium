import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Alert, type FishReport, type Reading, type Tank, type Threshold } from "./api";
import { TrendChart } from "./charts";
import { ago, fmt, latestValid, METRICS, metricInfo, series, statusOf, timeFmt, type MetricKey } from "./metrics";
import { DayPicker, FishIcon, FishStatusMark, FISH_STATUS, lastDays, StatusMark, TankScene, waterVerdict } from "./ui";

const REFRESH_MS = 60_000;
const WATER = METRICS.filter((m) => m.group === "water");
const CAMERA = METRICS.filter((m) => m.group === "camera");

export function TankPage({ tank, onError, refreshKey }: { tank: Tank; onError: (e: string | null) => void; refreshKey: number }) {
  const days = useMemo(() => lastDays(3), []);
  const [day, setDay] = useState(days[0].value);
  const [readings, setReadings] = useState<Reading[]>([]);
  const [limits, setLimits] = useState<Threshold[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [report, setReport] = useState<FishReport | null>(null);
  const [dawnDo, setDawnDo] = useState<number | null>(null);
  const [chartMetric, setChartMetric] = useState<MetricKey>("dissolved_oxygen");

  const load = useCallback(async () => {
    const start = new Date(Date.now() - 24 * 3600_000).toISOString();
    try {
      const [r, t, a, f, fc] = await Promise.all([
        api<Reading[]>(`/readings?tank_id=${tank.id}&start=${encodeURIComponent(start)}&limit=20000`),
        api<Threshold[]>(`/tanks/${tank.id}/thresholds`),
        api<Alert[]>(`/alerts?tank_id=${tank.id}&limit=50`),
        api<FishReport>(`/tanks/${tank.id}/fish?day=${day}`),
        api<{ dissolved_oxygen: number | null }>(`/tanks/${tank.id}/forecast`),
      ]);
      setReadings(r);
      setLimits(t);
      setAlerts(a);
      setReport(f);
      setDawnDo(fc.dissolved_oxygen);
      onError(null);
    } catch (e) {
      onError(`Couldn't load ${tank.name}: ${(e as Error).message}`);
    }
  }, [tank, day, onError]);

  useEffect(() => {
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [load, refreshKey]);

  const points = useMemo(() => Object.fromEntries(METRICS.map((m) => [m.key, series(readings, m.key)])), [readings]);
  const latest = Object.fromEntries(WATER.map((m) => [m.key, latestValid(points[m.key] ?? [])?.v ?? undefined]));
  const limit = (k: string) => limits.find((t) => t.metric === k);
  const lastReading = readings.at(-1)?.observed_at;
  const verdict = waterVerdict(latest, limits, readings.length > 0);
  const active = alerts.filter((a) => a.status !== "resolved");
  // Shown only as a heads-up when low: the forecast isn't validated on real nights, so it must never reassure.
  const doLimit = limit("dissolved_oxygen");
  const dawnTone = statusOf(dawnDo, doLimit);

  const fish = report?.fish ?? [];
  const inTank = fish.filter((f) => f.in_tank);
  const counts = (["check", "watch", "healthy"] as const).map((s) => [s, inTank.filter((f) => f.status === s).length] as const);

  async function acknowledge(id: string) {
    try {
      await api(`/alerts/${id}/acknowledge?by=dashboard`, { method: "POST" });
      load();
    } catch (e) {
      onError(`Couldn't mark the alert as seen: ${(e as Error).message}`);
    }
  }

  return (
    <div className="page">
      {/* ---------- water ---------- */}
      <section className={`panel verdict s-edge-${verdict.tone}`} aria-labelledby="water-h">
        <div className="verdict-head">
          <div>
            <h2 id="water-h" className="verdict-title">{verdict.title}</h2>
            <p className="verdict-advice">{verdict.advice}</p>
          </div>
          <p className="sub">{lastReading ? `Last reading ${ago(lastReading)}` : ""}</p>
        </div>

        {(dawnTone === "warning" || dawnTone === "critical") && (
          <p className={`forecast s-edge-${dawnTone}`}>
            <StatusMark status={dawnTone} label="Tonight" /> Oxygen could fall to about {fmt(dawnDo, "dissolved_oxygen")} mg/L
            before dawn (keep it above {doLimit?.low_warning} mg/L). Be ready to run the aerator early.
          </p>
        )}

        <div className="tiles">
          {WATER.map((m) => {
            const st = statusOf(latest[m.key], limit(m.key));
            return (
              <button key={m.key} className={`tile${chartMetric === m.key ? " on" : ""}`} onClick={() => setChartMetric(m.key)} aria-pressed={chartMetric === m.key}>
                <span className="tile-label">{m.label}</span>
                <span className="tile-value">
                  {fmt(latest[m.key], m.key)}
                  <span className="tile-unit">{m.unit}</span>
                </span>
                <StatusMark status={st} label={st === "none" ? "No limit set" : undefined} />
              </button>
            );
          })}
        </div>

        <div className="water-chart">
          <p className="chart-title">
            {metricInfo(chartMetric)?.label} over the last 24 hours
            <small className="chart-note">shaded bands are outside the safe range</small>
          </p>
          <TrendChart points={points[chartMetric] ?? []} metric={chartMetric} threshold={limit(chartMetric)} height={190} />
        </div>

        {active.length > 0 && (
          <ul className="alert-list">
            {active.map((a) => (
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
        )}
      </section>

      {/* ---------- fish ---------- */}
      <section className="panel" aria-labelledby="fish-h">
        <div className="panel-head row wrap">
          <div>
            <h2 id="fish-h">Fish in {tank.name}</h2>
            <p className="lede">
              {inTank.length} fish tracked by the camera.{" "}
              {counts.filter(([, n]) => n).map(([s, n], i) => (
                <span key={s}>
                  {i > 0 && ", "}
                  {n} {s === "check" ? (n === 1 ? "needs a check" : "need a check") : s === "watch" ? "to keep an eye on" : "healthy"}
                </span>
              ))}
              .
            </p>
          </div>
          <DayPicker value={day} onChange={setDay} days={days} />
        </div>

        <TankScene label={`Where the fish in ${tank.name} were last seen`} ratio={(report?.tank_length_cm ?? 120) / (report?.tank_depth_cm ?? 50)}>
          {inTank.map(
            (f) =>
              f.last_position && (
                <a
                  key={f.id}
                  href={`#/fish/${f.id}`}
                  className={`scene-fish st-${f.status}`}
                  style={{ left: `${f.last_position.x * 100}%`, top: `${f.last_position.y * 100}%` }}
                  aria-label={`${f.name}: ${FISH_STATUS[f.status].label}`}
                  title={`${f.name}: ${FISH_STATUS[f.status].label}`}
                >
                  {(f.status === "check" || f.status === "watch") && <span className={`badge b-${f.status}`}>!</span>}
                  <FishIcon
                    color={f.color_hex}
                    size={34}
                    facing={f.last_position.heading}
                    faded={f.flags.some((fl) => fl.text.startsWith("Not seen"))} // old position, not where it is now
                  />
                  <span className="scene-name">{f.name}</span>
                </a>
              ),
          )}
        </TankScene>
        <p className="hint scene-note">
          Where each fish was last seen. Click a fish to see its day. A <span className="badge inline b-check">!</span> marks fish that need attention.
        </p>

        <div className="two camera-charts">
          {CAMERA.map((m) => (
            <div key={m.key}>
              <p className="chart-title">
                {m.label} over the last 24 hours
                <small className="chart-note">{m.hint}</small>
              </p>
              <TrendChart points={points[m.key] ?? []} metric={m.key} height={140} />
            </div>
          ))}
        </div>

        <ul className="fish-grid">
          {fish.map((f) => (
            <li key={f.id}>
              <a href={`#/fish/${f.id}`} className={`fish-card st-${f.status}`}>
                <FishIcon color={f.color_hex} size={52} faded={!f.in_tank} />
                <div className="fish-card-body">
                  <span className="fish-name">{f.name}</span>
                  <FishStatusMark status={f.status} />
                  <span className="fish-line">{f.flags[0]?.text ?? (f.status === "healthy" ? "Behaving normally" : f.status === "unknown" ? "Hardly seen on this day" : "")}</span>
                  {f.samples > 0 && (
                    <span className="fish-facts">
                      Moving {f.active_pct.toFixed(0)}% · swam {f.distance_m.toFixed(0)} m
                    </span>
                  )}
                </div>
              </a>
            </li>
          ))}
        </ul>
        {fish.length === 0 && (
          <p className="empty">No fish tracked yet. Start the camera tracker (ml/track_fish.py) for this tank and fish will appear here.</p>
        )}
      </section>
    </div>
  );
}
