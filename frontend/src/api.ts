// Same hostname as the page: the login cookie is SameSite=lax, and localhost vs 127.0.0.1 count as different sites.
export const API_BASE: string = import.meta.env.VITE_API_BASE ?? `http://${window.location.hostname}:8000`;

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: "include" });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ? `${res.status}: ${body.detail}` : `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function login(name: string, password: string): Promise<{ name: string; role: string }> {
  return api("/auth/login", { method: "POST", body: JSON.stringify({ name, password }) });
}

export type Health = { status: string; env: string; simulation_mode: boolean };

export type Tank = {
  id: string;
  name: string;
  species: string | null;
  life_stage: string | null;
  volume_liters: number | null;
  location: string | null;
  length_cm: number | null;
  depth_cm: number | null;
};

export type Reading = {
  id: string;
  tank_id: string;
  sensor_id: string;
  metric: string;
  value: number | null;
  unit: string;
  observed_at: string;
  quality_status: "valid" | "invalid" | "missing" | string;
  source: string;
};

export type Threshold = {
  metric: string;
  low_critical: number | null;
  low_warning: number | null;
  high_warning: number | null;
  high_critical: number | null;
  reference: string | null;
};

export type Alert = {
  id: string;
  tank_id: string;
  metric: string;
  severity: "warning" | "critical";
  status: "open" | "acknowledged" | "resolved";
  value: number | null;
  reason: string;
  triggered_at: string;
  resolved_at: string | null;
  acknowledged_by: string | null;
};

export type FishStatus = "healthy" | "watch" | "check" | "unknown" | "removed";
export type FishFlag = { level: "watch" | "check"; text: string; advice: string };

export type FishRow = {
  id: string;
  name: string;
  color_hex: string | null;
  notes: string | null;
  in_tank: boolean;
  status: FishStatus;
  flags: FishFlag[];
  summary: string;
  first_seen_at: string | null;
  last_seen_at: string | null;
  last_position: { x: number; y: number; heading: number } | null;
  activity_rank: number | null;
  samples: number;
  seen_pct: number;
  distance_m: number;
  active_pct: number;
  avg_speed_cm_s: number;
  surface_pct: number;
  bottom_pct: number;
  neighbour_cm: number | null;
  size_cm: number | null;
  favourite_area: string;
};

export type FishGroup = Partial<Record<"active_pct" | "distance_m" | "surface_pct" | "bottom_pct" | "neighbour_cm", number>>;

export type FishReport = {
  tank_id: string;
  day: string;
  tank_length_cm: number;
  tank_depth_cm: number;
  group: FishGroup;
  fish: FishRow[];
};

export type FishDetail = Omit<FishReport, "fish"> & {
  tank_size: number;
  fish: FishRow & {
    heatmap: number[][];
    hourly_speed_cm_s: (number | null)[];
    path: { t: string; x: number; y: number }[];
  };
};
