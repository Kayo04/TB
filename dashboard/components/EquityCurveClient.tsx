"use client";

import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import type { EquitySnapshotRow } from "@/lib/queries";

export default function EquityCurveClient({ data }: { data: EquitySnapshotRow[] }) {
  if (data.length === 0) {
    return <p style={{ color: "var(--text-secondary)" }}>Sem snapshots de equity ainda.</p>;
  }

  const chartData = data.map((d) => ({
    ts: new Date(d.recorded_at).toLocaleString(),
    equity: d.total_equity,
  }));

  return (
    <div className="equity-chart">
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.32} />
              <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
          <XAxis dataKey="ts" tick={false} axisLine={{ stroke: "rgba(255,255,255,0.1)" }} tickLine={false} />
          <YAxis
            tick={{ fill: "#8fa3ad", fontFamily: "var(--mono)", fontSize: 11 }}
            axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
            tickLine={false}
            width={70}
            domain={["auto", "auto"]}
          />
          <Tooltip
            contentStyle={{
              background: "#0a0e14",
              border: "1px solid rgba(34,211,238,0.3)",
              borderRadius: 2,
              fontFamily: "var(--mono)",
              fontSize: 12,
            }}
            labelStyle={{ color: "#8fa3ad" }}
            itemStyle={{ color: "#22d3ee" }}
          />
          <Area
            type="monotone"
            dataKey="equity"
            stroke="#22d3ee"
            strokeWidth={2}
            fill="url(#equityFill)"
            dot={false}
            activeDot={{ r: 4, fill: "#22d3ee", stroke: "#0a0e14", strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
