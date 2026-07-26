import { getAllFills } from "@/lib/queries";
import { pairTrades, summarizeTrades } from "@/lib/tradeStats";
import { formatMoney, formatDollar, formatPercent, formatTs, formatNumber } from "@/lib/format";
import ClosedTradesTable from "./ClosedTradesTable";

function signClass(n: number | null): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "";
  return n > 0 ? "pos" : n < 0 ? "neg" : "";
}

export default async function PerformanceSection() {
  const fills = await getAllFills();
  const { closedTrades, openPositions, anomalies } = pairTrades(fills);
  const summary = summarizeTrades(closedTrades);
  const totalFees = fills.reduce((sum, f) => sum + f.fee, 0);

  return (
    <>
      {anomalies.length > 0 && (
        <div className="anomaly-banner">
          <strong>⚠ P&amp;L pode estar incorreto além do ponto assinalado.</strong> A assunção de
          pareamento (fills alternam buy/sell, qty fixa por símbolo) foi violada. Os números abaixo
          refletem só os trades pareados com segurança antes da anomalia -- não foi inventado nenhum
          número para o resto. Ver também os logs do serviço dashboard.
          <ul>
            {anomalies.map((a, i) => (
              <li key={i}>
                {a.symbol} · fill {a.fillId}: {a.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="panel-title" style={{ marginBottom: "0.9rem" }}>
        Desempenho -- desde o início do paper trading
      </div>
      <div className="stat-grid">
        <div className="stat-tile">
          <div className="k">P&amp;L realizado</div>
          <div className={`v ${signClass(summary.totalRealizedPnl)}`}>{formatMoney(summary.totalRealizedPnl)}</div>
          <div className="sub">{summary.totalClosedTrades} trades fechados</div>
        </div>
        <div className="stat-tile">
          <div className="k">Win rate</div>
          <div className="v">{formatPercent(summary.winRate)}</div>
          <div className="sub">
            {summary.wins}W / {summary.losses}L / {summary.breakeven}BE
          </div>
        </div>
        <div className="stat-tile">
          <div className="k">Trade médio</div>
          <div className={`v ${signClass(summary.avgTrade)}`}>{formatMoney(summary.avgTrade)}</div>
          <div className="sub">por round-trip</div>
        </div>
        <div className="stat-tile">
          <div className="k">Melhor trade</div>
          <div className={`v ${signClass(summary.bestTradePnl)}`}>{formatMoney(summary.bestTradePnl)}</div>
          <div className="sub">{summary.bestTrade ? formatTs(summary.bestTrade.exitTs) : "--"}</div>
        </div>
        <div className="stat-tile">
          <div className="k">Pior trade</div>
          <div className={`v ${signClass(summary.worstTradePnl)}`}>{formatMoney(summary.worstTradePnl)}</div>
          <div className="sub">{summary.worstTrade ? formatTs(summary.worstTrade.exitTs) : "--"}</div>
        </div>
        <div className="stat-tile">
          <div className="k">Fees pagas</div>
          <div className="v">{formatDollar(totalFees)}</div>
          <div className="sub">{fills.length} fills</div>
        </div>
      </div>

      {openPositions.length > 0 && (
        <p
          style={{
            fontFamily: "var(--mono)",
            fontSize: "0.72rem",
            color: "var(--text-secondary)",
            marginTop: "-0.4rem",
            marginBottom: "1.1rem",
          }}
        >
          Posição aberta: {openPositions.map((p) => `${p.symbol} @ ${formatNumber(p.entryPrice, 2)}`).join(", ")} --
          não realizada, não incluída no P&amp;L acima.
        </p>
      )}

      <ClosedTradesTable trades={closedTrades} />
    </>
  );
}
