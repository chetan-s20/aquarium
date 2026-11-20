import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type FishDetail } from "./api";
import { HourBars } from "./charts";
import { DayPicker, FishIcon, FishStatusMark, lastDays, TankScene } from "./ui";

const fmtTime = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

function compare(value: number, typical: number | undefined, more: string, less: string) {
  if (!typical) return "";
  const r = value / typical;
  if (r > 1.4) return more;
  if (r < 0.7) return less;
  return "about the same as the others";
}

export function FishPage({ fishId, onError }: { fishId: string; onError: (e: string | null) => void }) {
  const days = useMemo(() => lastDays(3), []);
  const [day, setDay] = useState(days[0].value);
  const [data, setData] = useState<FishDetail | null>(null);
  const [view, setView] = useState<"path" | "heat">("path");
  const [at, setAt] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [saved, setSaved] = useState("");

  const load = useCallback(async () => {
    try {
      const d = await api<FishDetail>(`/fish/${fishId}?day=${day}`);
      setData(d);
      setName(d.fish.name);
      setNotes(d.fish.notes ?? "");
      setAt(Math.max(0, d.fish.path.length - 1));
      onError(null);
    } catch (e) {
      onError(`Couldn't load this fish: ${(e as Error).message}`);
    }
  }, [fishId, day, onError]);

  useEffect(() => {
    load();
  }, [load]);

  const path = data?.fish.path ?? [];
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      setAt((i) => {
        if (i >= path.length - 1) {
          setPlaying(false);
          return i;
        }
        return Math.min(path.length - 1, i + Math.max(1, Math.round(path.length / 240)));
      });
    }, 40);
    return () => clearInterval(id);
  }, [playing, path.length]);

  async function save(body: Record<string, string>, message: string) {
    try {
      await api(`/fish/${fishId}`, { method: "PATCH", body: JSON.stringify(body) });
      setSaved(message);
      setEditing(false);
      setTimeout(() => setSaved(""), 2500);
      load();
    } catch (e) {
      onError(`Couldn't save: ${(e as Error).message}`);
    }
  }

  const segs = useSegments(path); // hooks must run on every render, so before the loading return
  if (!data) return <div className="page"><p className="empty">Loading…</p></div>;
  const f = data.fish;
  const g = data.group;
  const cur = path[at];
  const prev = path[Math.max(0, at - 1)];
  const facing = cur && prev && cur.x < prev.x ? -1 : 1;
  const maxHeat = Math.max(...f.heatmap.flat(), 0.0001);

  return (
    <div className="page">
      <a className="back" href={`#/tank/${data.tank_id}`}>
        ← All fish in this tank
      </a>

      <section className={`panel fish-hero st-edge-${f.status}`} aria-labelledby="fish-name">
        <FishIcon color={f.color_hex} size={96} />
        <div className="fish-hero-body">
          {editing ? (
            <form className="rename" onSubmit={(e) => { e.preventDefault(); save({ name }, "Name saved"); }}>
              <label className="field">
                Name
                <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} autoFocus />
              </label>
              <button className="btn primary small" type="submit">Save name</button>
              <button className="btn small" type="button" onClick={() => { setEditing(false); setName(f.name); }}>Cancel</button>
            </form>
          ) : (
            <div className="row">
              <h1 id="fish-name" className="fish-title">{f.name}</h1>
              <button className="link" onClick={() => setEditing(true)}>Rename</button>
            </div>
          )}
          <FishStatusMark status={f.status} />
          <p className="fish-summary">{f.summary}</p>
          {saved && <p className="saved" role="status">{saved}</p>}
        </div>
        <DayPicker value={day} onChange={setDay} days={days} />
      </section>

      <section className="panel" aria-labelledby="noticed-h">
        <h2 id="noticed-h">What we noticed</h2>
        {f.flags.length === 0 ? (
          <p className="ok-line">
            {f.status === "unknown"
              ? "The camera hardly saw this fish on this day, so there's nothing to judge yet."
              : "Nothing unusual. It swims, rests and mixes with the group like the other fish."}
          </p>
        ) : (
          <ul className="flags">
            {f.flags.map((fl) => (
              <li key={fl.text} className={`flag st-edge-${fl.level}`}>
                <strong>{fl.text}</strong>
                <span>{fl.advice}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="two">
        <section className="panel" aria-labelledby="where-h">
          <div className="panel-head row wrap">
            <h2 id="where-h">Where it swam</h2>
            <div className="seg" role="group" aria-label="Map view">
              <button className={view === "path" ? "on" : ""} aria-pressed={view === "path"} onClick={() => setView("path")}>Its route</button>
              <button className={view === "heat" ? "on" : ""} aria-pressed={view === "heat"} onClick={() => setView("heat")}>Favourite spots</button>
            </div>
          </div>
          <TankScene label={`${f.name}'s movements`} ratio={data.tank_length_cm / data.tank_depth_cm}>
            {view === "heat" ? (
              <div className="heat" aria-hidden="true">
                {f.heatmap.flatMap((row, r) =>
                  row.map((v, c) => <span key={`${r}-${c}`} style={{ opacity: Math.min(0.85, (v / maxHeat) * 0.85) }} />),
                )}
              </div>
            ) : (
              <>
                <svg className="route" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">
                  {segs.map((s, i) => (
                    <polyline key={i} points={s.map((p) => `${p.x * 1000},${p.y * 1000}`).join(" ")} />
                  ))}
                </svg>
                {cur && (
                  <span className="scene-fish replay" style={{ left: `${cur.x * 100}%`, top: `${cur.y * 100}%` }}>
                    <FishIcon color={f.color_hex} size={40} facing={facing} />
                  </span>
                )}
              </>
            )}
          </TankScene>
          {view === "path" && path.length > 1 ? (
            <div className="replay-bar">
              <button className="btn small" onClick={() => { if (at >= path.length - 1) setAt(0); setPlaying(!playing); }}>
                {playing ? "Pause" : at >= path.length - 1 ? "Replay the day" : "Play"}
              </button>
              <input
                type="range" min={0} max={path.length - 1} value={at}
                onChange={(e) => { setPlaying(false); setAt(Number(e.target.value)); }}
                aria-label="Time of day"
              />
              <span className="replay-time">{cur ? fmtTime(cur.t) : ""}</span>
            </div>
          ) : (
            <p className="hint">
              {view === "heat" ? `Darker means more time spent there. Mostly ${f.favourite_area}.` : "No movement recorded on this day."}
            </p>
          )}
        </section>

        <section className="panel" aria-labelledby="day-h">
          <h2 id="day-h">Its day, hour by hour</h2>
          <p className="lede">Taller bars mean it was swimming more. Fish normally rest at night.</p>
          <HourBars values={f.hourly_speed_cm_s} />
        </section>
      </div>

      <section className="panel" aria-labelledby="facts-h">
        <h2 id="facts-h">The details</h2>
        <dl className="fact-grid">
          <div>
            <dt>Distance swum</dt>
            <dd>{f.distance_m.toFixed(0)} m</dd>
            <small>{compare(f.distance_m, g.distance_m, "more than most fish here", "less than most fish here")}</small>
          </div>
          <div>
            <dt>Time spent moving</dt>
            <dd>{f.active_pct.toFixed(0)}%</dd>
            <small>
              {f.activity_rank ? `Number ${f.activity_rank} of ${data.tank_size} for activity` : ""}
            </small>
          </div>
          <div>
            <dt>At the surface</dt>
            <dd>{f.surface_pct.toFixed(0)}%</dd>
            <small>Others: {g.surface_pct?.toFixed(0) ?? "—"}%</small>
          </div>
          <div>
            <dt>On the bottom</dt>
            <dd>{f.bottom_pct.toFixed(0)}%</dd>
            <small>Others: {g.bottom_pct?.toFixed(0) ?? "—"}%</small>
          </div>
          <div>
            <dt>Distance to nearest fish</dt>
            <dd>{f.neighbour_cm != null ? `${f.neighbour_cm.toFixed(0)} cm` : "—"}</dd>
            <small>{f.neighbour_cm != null ? compare(f.neighbour_cm, g.neighbour_cm, "further away than usual", "closer than usual") : ""}</small>
          </div>
          <div>
            <dt>Approximate length</dt>
            <dd>{f.size_cm != null ? `${f.size_cm.toFixed(0)} cm` : "—"}</dd>
            <small>Measured from the camera</small>
          </div>
          <div>
            <dt>Seen by the camera</dt>
            <dd>{f.seen_pct.toFixed(0)}%</dd>
            <small>of the day</small>
          </div>
          <div>
            <dt>Last seen</dt>
            <dd>{f.last_seen_at ? fmtTime(f.last_seen_at) : "—"}</dd>
            <small>{f.last_seen_at ? new Date(f.last_seen_at).toLocaleDateString() : ""}</small>
          </div>
        </dl>
      </section>

      <section className="panel" aria-labelledby="notes-h">
        <h2 id="notes-h">Staff notes</h2>
        <p className="lede">Write what you see when you check this fish: spots, fin damage, treatment given.</p>
        <textarea className="notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} maxLength={4000} aria-labelledby="notes-h" />
        <div className="export-actions">
          <button className="btn primary" onClick={() => save({ notes }, "Notes saved")}>Save notes</button>
          {f.in_tank ? (
            <button className="btn" onClick={() => { if (confirm(`Mark ${f.name} as no longer in the tank (sold, moved or died)?`)) save({ status: "removed" }, "Marked as removed"); }}>
              Mark as removed from tank
            </button>
          ) : (
            <button className="btn" onClick={() => save({ status: "in_tank" }, "Back in tank")}>Mark as back in tank</button>
          )}
        </div>
      </section>
    </div>
  );
}

/** Break the route where the fish was out of sight, so we don't draw lines across gaps. */
function useSegments(path: { t: string; x: number; y: number }[]) {
  return useMemo(() => {
    const out: { x: number; y: number }[][] = [];
    let cur: { x: number; y: number }[] = [];
    for (let i = 0; i < path.length; i++) {
      if (i > 0 && Date.parse(path[i].t) - Date.parse(path[i - 1].t) > 10 * 60_000) {
        if (cur.length > 1) out.push(cur);
        cur = [];
      }
      cur.push(path[i]);
    }
    if (cur.length > 1) out.push(cur);
    return out;
  }, [path]);
}
