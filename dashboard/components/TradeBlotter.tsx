import { getRecentFills } from "@/lib/queries";
import { formatTs, formatNumber } from "@/lib/format";

export default async function TradeBlotter() {
  const rows = await getRecentFills(50);

  return (
    <table>
      <thead>
        <tr>
          <th>Executado em</th>
          <th>Símbolo</th>
          <th>Lado</th>
          <th>Qty</th>
          <th>Preço</th>
          <th>Fee</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.fill_id}>
            <td>{formatTs(r.filled_ts)}</td>
            <td>{r.symbol}</td>
            <td>{r.side}</td>
            <td>{formatNumber(r.qty)}</td>
            <td>{formatNumber(r.price, 2)}</td>
            <td>{formatNumber(r.fee, 4)}</td>
          </tr>
        ))}
        {rows.length === 0 && (
          <tr>
            <td colSpan={6}>Sem execuções ainda.</td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
