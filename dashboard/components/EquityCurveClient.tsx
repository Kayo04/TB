"use client";

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import type { EquitySnapshotRow } from "@/lib/queries";

export default function EquityCurveClient({ data }: { data: EquitySnapshotRow[] }) {
  if (data.length === 0) {
    return <p>Sem snapshots de equity ainda.</p>;
  }

  const chartData = data.map((d) => ({
    ts: new Date(d.recorded_at).toLocaleString(),
    equity: d.total_equity,
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="ts" tick={false} />
        <YAxis />
        <Tooltip />
        <Line type="monotone" dataKey="equity" stroke="#2563eb" dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
