import { useEffect, useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { api, type Tank, type Reading, type Health } from "./api";

type Alert = {
  id: string;
  metric: string;
  severity: string;
  status: string;
  value: number | null;
  reason: string;
  triggered_at: string;
};

const METRICS = ["temperature", "ph", "tds", "turbidity", "dissolved_oxygen"] as const;

function isStale(observedAt: string, minutes = 15): boolean {
  const age = (Date.now() - new Date(observedAt).getTime()) / 60000;
  return age > minutes;
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [tanks, setTanks] = useState<Tank[]>([]);
  const [tankId, setTankId] = useState<string>("");
  const [readings, setReadings] = useState<Reading[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [metric, setMetric] = useState<string>("temperature");
  const [running, setRunning] = useState(false);
  const [alerts, setAlerts] = useState<Alert[]>([]);

  async function loadAlerts() {
    try {
      setAlerts(await api<Alert[]>("/alerts?limit=50"));
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    (async () => {
      try {
        setHealth(await api<Health>("/health"));
        const t = await api<Tank[]>("/tanks");
        setTanks(t);
        if (t.length) setTankId(t[0].id);
        loadAlerts();
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to load");
      }
    })();
  }, []);

  useEffect(() => {
    if (!tankId) return;
    setLoading(true);
    (async () => {
      try {
        const r = await api<Reading[]>(`/readings?tank_id=${tankId}&limit=500`);
        setReadings(r);
        setError(null);
        loadAlerts();
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to load readings");
      } finally {
        setLoading(false);
      }
    })();
  }, [tankId]);

  const latestByMetric = useMemo(() => {
    const map: Record<string, Reading> = {};
    for (const r of readings) {
      if (!map[r.metric] || new Date(r.observed_at) > new Date(map[r.metric].observed_at)) {
        map[r.metric] = r;
      }
    }
    return map;
  }, [readings]);

  const chartData = useMemo(() => {
    return readings
      .filter((r) => r.metric === metric)
      .map((r) => ({
        time: new Date(r.observed_at).toLocaleTimeString(),
        value: r.value,
        quality: r.quality_status,
      }))
      .reverse();
  }, [readings, metric]);

  async function runSim() {
    if (!tankId) return;
    setRunning(true);
    try {
      await api(`/simulate/run?tank_id=${tankId}&count=48&interval_minutes=5`, {
        method: "POST",
        headers: { "X-Operator-Key": import.meta.env.VITE_OPERATOR_KEY ?? "dev-operator-key-change-me" },
      });
      const r = await api<Reading[]>(`/readings?tank_id=${tankId}&limit=500`);
      setReadings(r);
      loadAlerts();
    } catch (e) {
      setError(e instanceof Error ? e.message : "simulation failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <h1>Aquaculture Monitoring</h1>
          <p className="muted">Water-quality dashboard · timestamps in UTC</p>
        </div>
        <div className="topbar-right">
          {health?.simulation_mode && <span className="badge sim">SIMULATED DATA</span>}
          {Object.values(latestByMetric).some((r) => isStale(r.observed_at)) && (
            <span className="badge stale">STALE DATA</span>
          )}
          <select value={tankId} onChange={(e) => setTankId(e.target.value)}>
            {tanks.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
          <button onClick={runSim} disabled={running || !tankId}>
            {running ? "Running…" : "Run simulated data"}
          </button>
        </div>
      </header>

      {error && <div className="banner error">{error}</div>}

      <section className="cards">
        {METRICS.map((m) => {
          const r = latestByMetric[m];
          return (
            <div className="card" key={m}>
              <div className="card-label">{m.replace("_", " ")}</div>
              <div className="card-value">
                {r && r.value !== null ? `${r.value} ${r.unit}` : "—"}
              </div>
              <div className="card-meta">
                {r ? (
                  <>
                    <span className={`quality ${r.quality_status}`}>{r.quality_status}</span>
                    {isStale(r.observed_at) && <span className="stale">stale</span>}
                    <span className="muted">{new Date(r.observed_at).toLocaleString()} UTC</span>
                  </>
                ) : (
                  <span className="muted">no data</span>
                )}
              </div>
            </div>
          );
        })}
      </section>

      <section className="chart-section">
        <div className="chart-header">
          <h2>Historical trend</h2>
          <div className="metric-tabs">
            {METRICS.map((m) => (
              <button
                key={m}
                className={metric === m ? "tab active" : "tab"}
                onClick={() => setMetric(m)}
              >
                {m.replace("_", " ")}
              </button>
            ))}
          </div>
        </div>
        <div className="chart-box">
          {loading ? (
            <p className="muted">Loading…</p>
          ) : chartData.length === 0 ? (
            <p className="muted">No readings. Run simulated data to populate.</p>
          ) : (
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Line type="monotone" dataKey="value" stroke="#0ea5e9" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>

      <section className="alerts">
        <h2>Alert history</h2>
        {alerts.length === 0 ? (
          <p className="muted">No alerts.</p>
        ) : (
          <ul className="alert-list">
            {alerts.map((a) => (
              <li key={a.id} className={`alert ${a.severity} ${a.status}`}>
                <div>
                  <strong>{a.metric}</strong> {a.severity} — {a.reason}
                  <div className="muted">{new Date(a.triggered_at).toLocaleString()} UTC · {a.status}</div>
                </div>
                {a.status === "open" && (
                  <button
                    onClick={async () => {
                      await api(`/alerts/${a.id}/acknowledge?by=operator`, {
                        method: "POST",
                        headers: { "X-Operator-Key": import.meta.env.VITE_OPERATOR_KEY ?? "dev-operator-key-change-me" },
                      });
                      loadAlerts();
                    }}
                  >
                    Acknowledge
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
