import type { ClosedTrade } from "@/lib/tradeStats";
import { formatTs, formatNumber, formatMoney } from "@/lib/format";
import Panel from "./Panel";

export default function ClosedTradesTable({ trades }: { trades: ClosedTrade[] }) {
  const rows = [...trades].sort((a, b) => new Date(b.exitTs).getTime() - new Date(a.exitTs).getTime());

  return (
    <Panel title="Trades fechados (round-trip)">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Entrada</th>
              <th>Saída</th>
              <th>Preço entrada</th>
              <th>Preço saída</th>
              <th>Fees</th>
              <th>P&amp;L</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t, i) => (
              <tr key={i}>
                <td>{formatTs(t.entryTs)}</td>
                <td>{formatTs(t.exitTs)}</td>
                <td>{formatNumber(t.entryPrice, 2)}</td>
                <td>{formatNumber(t.exitPrice, 2)}</td>
                <td>{formatNumber(t.entryFee + t.exitFee, 2)}</td>
                <td className={t.bucket}>{formatMoney(t.pnl)}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={6}>Sem trades fechados ainda.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
