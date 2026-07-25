import { getRecentRunLog } from "@/lib/queries";
import { formatTs } from "@/lib/format";

export default async function RunLogTable() {
  const rows = await getRecentRunLog(50);

  return (
    <table>
      <thead>
        <tr>
          <th>Bar</th>
          <th>Símbolo</th>
          <th>Sinal</th>
          <th>Decisão</th>
          <th>Estado da ordem</th>
          <th>Halted</th>
          <th>Duração (ms)</th>
          <th>Motivo</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.run_log_id} className={r.decision === "cycle_failed" ? "row-bad" : undefined}>
            <td>{formatTs(r.bar_ts)}</td>
            <td>{r.symbol}</td>
            <td>{r.signal ?? "--"}</td>
            <td>{r.decision}</td>
            <td>{r.order_status ?? "--"}</td>
            <td>{r.halted_after ? "sim" : "não"}</td>
            <td>{r.cycle_duration_ms}</td>
            <td>{r.reason ?? "--"}</td>
          </tr>
        ))}
        {rows.length === 0 && (
          <tr>
            <td colSpan={8}>Sem ciclos registados ainda.</td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
