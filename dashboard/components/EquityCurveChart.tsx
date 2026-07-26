import { getEquityCurve } from "@/lib/queries";
import EquityCurveClient from "./EquityCurveClient";
import Panel from "./Panel";

export default async function EquityCurveChart() {
  const rows = await getEquityCurve(500);

  return (
    <Panel title="Curva de equity">
      <EquityCurveClient data={rows} />
      <p
        style={{
          fontFamily: "var(--mono)",
          fontSize: "0.66rem",
          color: "var(--text-muted)",
          marginTop: "0.6rem",
          marginBottom: 0,
          lineHeight: 1.5,
        }}
      >
        Mark-to-market (dinheiro realizado + posição × preço ao vivo), calculada pelo risk layer a
        cada ciclo -- <strong style={{ color: "var(--text-secondary)" }}>não</strong> é uma
        repetição do motor de backtest.
      </p>
    </Panel>
  );
}
