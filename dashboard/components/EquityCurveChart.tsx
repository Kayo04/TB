import { getEquityCurve } from "@/lib/queries";
import EquityCurveClient from "./EquityCurveClient";

export default async function EquityCurveChart() {
  const rows = await getEquityCurve(500);

  return (
    <div>
      <p style={{ fontSize: "0.85em", color: "#666" }}>
        Curva mark-to-market (dinheiro realizado + posição × preço ao vivo), calculada pelo risk
        layer a cada ciclo -- <strong>não</strong> é uma repetição do motor de backtest (isso
        precisaria do histórico de barras, que não é guardado de propósito).
      </p>
      <EquityCurveClient data={rows} />
    </div>
  );
}
