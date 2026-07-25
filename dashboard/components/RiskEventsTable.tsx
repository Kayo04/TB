import { getRiskEvents } from "@/lib/queries";
import { formatTs } from "@/lib/format";

export default async function RiskEventsTable() {
  const rows = await getRiskEvents(50);

  return (
    <table>
      <thead>
        <tr>
          <th>Quando</th>
          <th>Tipo</th>
          <th>Motivo</th>
          <th>Disparado por</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.event_id} className={r.event_type === "halt" ? "row-bad" : undefined}>
            <td>{formatTs(r.created_at)}</td>
            <td>{r.event_type}</td>
            <td>{r.reason}</td>
            <td>{r.triggered_by}</td>
          </tr>
        ))}
        {rows.length === 0 && (
          <tr>
            <td colSpan={4}>Nunca houve halt ou clear.</td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
