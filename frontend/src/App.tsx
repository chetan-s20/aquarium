import { useCallback, useEffect, useState } from "react";
import { api, login, type Health, type Tank } from "./api";
import { ExportPanel } from "./ExportPanel";
import { FishPage } from "./FishPage";
import { TankPage } from "./TankPage";
import { useRoute } from "./ui";

type User = { name: string; role: string };

export default function App() {
  const route = useRoute(); // [] | ["tank", id] | ["fish", id] | ["download"]
  const [health, setHealth] = useState<Health | null>(null);
  const [tanks, setTanks] = useState<Tank[]>([]);
  const [lastTankId, setLastTankId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const onError = useCallback((e: string | null) => setError(e), []);

  // Viewing is open; saving anything (alerts, fish notes, demo data) needs an operator login.
  const [user, setUser] = useState<User | null>(null);
  const [showLogin, setShowLogin] = useState(false);
  const [loginName, setLoginName] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api<Health>("/health"), api<Tank[]>("/tanks")])
      .then(([h, t]) => {
        setHealth(h);
        setTanks(t);
      })
      .catch((e: Error) => setError(`Can't reach the monitoring server (${e.message}). Check that the backend is running.`));
    api<User>("/auth/me").then(setUser).catch(() => setUser(null));
  }, []);

  const page = route[0] ?? "tank";
  const routeTankId = page === "tank" ? route[1] : undefined;
  const tank = tanks.find((t) => t.id === (routeTankId ?? lastTankId)) ?? tanks[0];
  useEffect(() => {
    if (routeTankId) setLastTankId(routeTankId);
  }, [routeTankId]);

  async function submitLogin() {
    setLoginError(null);
    try {
      await login(loginName, loginPassword);
      setUser(await api<User>("/auth/me"));
      setShowLogin(false);
      setLoginPassword("");
      setError(null);
    } catch {
      setLoginError("Wrong name or password.");
    }
  }

  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => null);
    setUser(null);
  }

  async function generate() {
    if (!tank) return;
    setBusy(true);
    try {
      await api(`/simulate/run?tank_id=${tank.id}&hours=24`, { method: "POST" });
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setError(`Couldn't update demo data: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="shell">
      <header className="top">
        <a className="brand" href="#/">
          <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">
            <path d="M16 3c5 7 9 11.5 9 16.5a9 9 0 0 1-18 0C7 14.5 11 10 16 3z" fill="var(--line)" />
            <path d="M11 20.5c1.6 1.4 3.2 2.1 5 2.1s3.4-.7 5-2.1" fill="none" stroke="var(--paper)" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          <h1>FISHUT</h1>
        </a>

        <nav className="tanks" aria-label="Tanks">
          {tanks.map((t) => {
            const on = page === "tank" && t.id === tank?.id;
            return (
              <a key={t.id} href={`#/tank/${t.id}`} className={on ? "tank on" : "tank"} aria-current={on ? "page" : undefined}>
                <span className="tank-name">{t.name}</span>
                <span className="tank-meta">{t.species ?? "Species not set"}</span>
              </a>
            );
          })}
        </nav>

        <div className="top-actions">
          <a className={page === "download" ? "btn on-nav" : "btn"} href="#/download" aria-current={page === "download" ? "page" : undefined}>
            Download data
          </a>
          {user ? (
            <span className="who">
              {user.name}
              <button className="link" onClick={logout}>Log out</button>
            </span>
          ) : (
            <button className="btn" onClick={() => setShowLogin(!showLogin)} aria-expanded={showLogin}>
              Log in
            </button>
          )}
        </div>
      </header>

      {showLogin && !user && (
        <form className="notice login" onSubmit={(e) => { e.preventDefault(); void submitLogin(); }}>
          <span>Log in to mark alerts as seen, rename fish and save notes.</span>
          <label className="field">
            Name
            <input value={loginName} onChange={(e) => setLoginName(e.target.value)} autoComplete="username" autoFocus />
          </label>
          <label className="field">
            Password
            <input type="password" value={loginPassword} onChange={(e) => setLoginPassword(e.target.value)} autoComplete="current-password" />
          </label>
          <button className="btn primary" type="submit">Log in</button>
          {loginError && <span className="s-critical" role="alert">{loginError}</span>}
        </form>
      )}

      {health?.simulation_mode && (
        <div className="notice sim">
          <span>
            <strong>Demo data.</strong> Readings and fish movements are simulated; no real sensors or cameras are connected yet.
          </span>
          {page === "tank" && user && (
            <button className="btn small" onClick={generate} disabled={busy || !tank}>
              {busy ? "Updating…" : "Update demo data to now"}
            </button>
          )}
        </div>
      )}
      {error && (
        <div className="notice error" role="alert">
          {error.includes("401") ? "Please log in first: that action needs an operator login." : error}
        </div>
      )}

      {page === "fish" && route[1] ? (
        <FishPage key={route[1]} fishId={route[1]} onError={onError} />
      ) : page === "download" ? (
        <div className="page">
          <ExportPanel tanks={tanks} />
        </div>
      ) : tank ? (
        <TankPage key={tank.id} tank={tank} onError={onError} refreshKey={refreshKey} />
      ) : (
        !error && <p className="empty">Loading tanks…</p>
      )}

      <footer className="foot">
        Health notes compare each fish with its tankmates; they are a prompt to look, not a diagnosis. Water limits are general guidance
        until confirmed for your species.
      </footer>
    </div>
  );
}
