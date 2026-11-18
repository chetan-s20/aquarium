const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export type Tank = { id: string; name: string; species: string | null; life_stage: string | null };
export type Reading = {
  id: string;
  tank_id: string;
  sensor_id: string;
  metric: string;
  value: number | null;
  unit: string;
  observed_at: string;
  received_at: string;
  quality_status: string;
  source: string;
};
export type Health = { status: string; simulation_mode: boolean };
