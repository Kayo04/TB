import { getReconciliationChecks } from "@/lib/queries";
import { formatTs, formatNumber } from "@/lib/format";

export default async function ReconciliationTable() {
  const rows = await getReconciliationChecks(50);

  return (
    <table>
      <thead>
        <tr>
          <th>Verificado em</th>
          <th>Símbolo</th>
          <th>Interno</th>
          <th>Externo</th>
          <th>Diferença</th>
          <th>Divergente</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.check_id} className={r.is_divergent ? "row-bad" : undefined}>
            <td>{formatTs(r.checked_at)}</td>
            <td>{r.symbol}</td>
            <td>{formatNumber(r.internal_position)}</td>
            <td>{formatNumber(r.external_position)}</td>
            <td>{formatNumber(r.difference)}</td>
            <td>{r.is_divergent ? "SIM" : "não"}</td>
          </tr>
        ))}
        {rows.length === 0 && (
          <tr>
            <td colSpan={6}>Sem verificações ainda.</td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
