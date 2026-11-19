import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Threshold } from "./api";
import { fmt, metricInfo, statusOf, STATUS_LABEL, timeFmt, type Point } from "./metrics";

const TOKENS = ["--line", "--grid", "--ink-2", "--warn-zone", "--crit-zone", "--paper", "--crit"] as const;
type Tokens = Record<(typeof TOKENS)[number], string>;

/** SVG attributes can't take var(); read the theme tokens and re-read when the scheme flips. */
function useTokens(): Tokens {
  const read = () => {
    const s = getComputedStyle(document.documentElement);
    return Object.fromEntries(TOKENS.map((k) => [k, s.getPropertyValue(k).trim()])) as Tokens;
  };
  const [tokens, setTokens] = useState(read);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => setTokens(read());
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return tokens;
}

function domain(points: Point[], t?: Threshold): [number, number] {
  const vals = points.flatMap((p) => (p.v == null ? [] : [p.v]));
  if (t?.low_warning != null) vals.push(t.low_warning);
  if (t?.high_warning != null) vals.push(t.high_warning);
  if (!vals.length) return [0, 1];
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = (hi - lo || 1) * 0.12;
  return [Math.max(0, lo - pad), hi + pad];
}

function Bands({ t, tok }: { t?: Threshold; tok: Tokens }) {
  if (!t) return null;
  const big = 1e6;
  const zones: [number, number, string][] = [];
  if (t.low_critical != null) zones.push([-big, t.low_critical, tok["--crit-zone"]]);
  if (t.low_warning != null) zones.push([t.low_critical ?? -big, t.low_warning, tok["--warn-zone"]]);
  if (t.high_warning != null) zones.push([t.high_warning, t.high_critical ?? big, tok["--warn-zone"]]);
  if (t.high_critical != null) zones.push([t.high_critical, big, tok["--crit-zone"]]);
  return (
    <>
      {zones.map(([y1, y2, fill]) => (
        <ReferenceArea key={`${y1}-${y2}`} y1={y1} y2={y2} fill={fill} fillOpacity={1} ifOverflow="hidden" strokeWidth={0} />
      ))}
    </>
  );
}

type TipProps = { active?: boolean; payload?: { payload: Point }[]; metric: string; t?: Threshold; withDay: boolean };

function Tip({ active, payload, metric, t, withDay }: TipProps) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  const st = statusOf(p.v, t);
  return (
    <div className="tip">
      <div className="tip-time">{timeFmt(p.t, withDay)}</div>
      <div className="tip-value">
        {p.v == null ? "No valid reading" : `${fmt(p.v, metric)} ${metricInfo(metric)?.unit ?? ""}`}
      </div>
      {p.v != null && st !== "none" && <div className={`tip-status s-${st}`}>{STATUS_LABEL[st]}</div>}
    </div>
  );
}

export function TrendChart({
  points,
  metric,
  threshold,
  height = 260,
  withDay = false,
  syncId,
  mark,
  compact = false,
}: {
  points: Point[];
  metric: string;
  threshold?: Threshold;
  height?: number;
  withDay?: boolean;
  syncId?: string;
  mark?: Point;
  compact?: boolean;
}) {
  const tok = useTokens();
  if (!points.length) return <div className="chart-empty" style={{ height }}>No readings in this period.</div>;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={points} syncId={syncId} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={tok["--grid"]} vertical={false} />
        <Bands t={threshold} tok={tok} />
        <XAxis
          dataKey="t"
          type="number"
          scale="time"
          domain={["dataMin", "dataMax"]}
          tickFormatter={(v: number) => timeFmt(v, withDay)}
          tick={{ fill: tok["--ink-2"], fontSize: 12 }}
          tickLine={false}
          axisLine={{ stroke: tok["--grid"] }}
          minTickGap={48}
          hide={compact}
        />
        <YAxis
          domain={domain(points, threshold)}
          tickFormatter={(v: number) => fmt(v, metric)}
          tick={{ fill: tok["--ink-2"], fontSize: 12 }}
          tickLine={false}
          axisLine={false}
          width={44}
        />
        <Tooltip
          content={<Tip metric={metric} t={threshold} withDay={withDay} />}
          cursor={{ stroke: tok["--ink-2"], strokeWidth: 1, strokeDasharray: "3 3" }}
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="v"
          stroke={tok["--line"]}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, stroke: tok["--paper"], strokeWidth: 2 }}
          isAnimationActive={false}
        />
        {mark?.v != null && (
          <ReferenceDot x={mark.t} y={mark.v} r={5} fill={tok["--crit"]} stroke={tok["--paper"]} strokeWidth={2} />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function Sparkline({ points }: { points: Point[] }) {
  const tok = useTokens();
  if (points.length < 2) return <div className="spark" />;
  return (
    <div className="spark" aria-hidden="true">
      <ResponsiveContainer width="100%" height={36}>
        <LineChart data={points} margin={{ top: 4, right: 0, bottom: 4, left: 0 }}>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <XAxis hide dataKey="t" type="number" domain={["dataMin", "dataMax"]} />
          <Line type="monotone" dataKey="v" stroke={tok["--line"]} strokeWidth={1.5} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
