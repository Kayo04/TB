import { getPositions } from "@/lib/queries";
import { formatNumber } from "@/lib/format";

export default async function PositionTable() {
  const rows = await getPositions();
  const nonZero = rows.filter((r) => r.position !== 0);

  return (
    <table>
      <thead>
        <tr>
          <th>Símbolo</th>
          <th>Posição</th>
        </tr>
      </thead>
      <tbody>
        {nonZero.map((r) => (
          <tr key={r.symbol}>
            <td>{r.symbol}</td>
            <td>{formatNumber(r.position)}</td>
          </tr>
        ))}
        {nonZero.length === 0 && (
          <tr>
            <td colSpan={2}>Flat em todos os símbolos.</td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
