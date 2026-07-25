import RunLogTable from "@/components/RunLogTable";
import TradeBlotter from "@/components/TradeBlotter";
import EquityCurveChart from "@/components/EquityCurveChart";
import PositionTable from "@/components/PositionTable";
import ReconciliationTable from "@/components/ReconciliationTable";
import RiskEventsTable from "@/components/RiskEventsTable";
import CycleHealthPanel from "@/components/CycleHealthPanel";
import HeartbeatStatus from "@/components/HeartbeatStatus";

// This page must reflect live database state on every request -- never
// statically cached or ISR'd.
export const dynamic = "force-dynamic";

export default function DashboardPage() {
  return (
    <main>
      <h1>Trading Bot -- Dashboard (paper)</h1>

      <section>
        <h2>O que decidiu</h2>
        <h3>Histórico de ciclos</h3>
        <RunLogTable />
        <h3>Blotter de trades</h3>
        <TradeBlotter />
        <h3>Curva de equity</h3>
        <EquityCurveChart />
      </section>

      <section>
        <h2>Estado ao vivo</h2>
        <h3>Heartbeat</h3>
        <HeartbeatStatus />
        <h3>Posições</h3>
        <PositionTable />
        <p style={{ fontSize: "0.85em", color: "#666" }}>
          Halted/não-halted mostrado na barra do topo.
        </p>
      </section>

      <section>
        <h2>Saúde do sistema</h2>
        <h3>Reconciliação</h3>
        <ReconciliationTable />
        <h3>Histórico do kill-switch</h3>
        <RiskEventsTable />
        <h3>Timing dos ciclos</h3>
        <CycleHealthPanel />
      </section>
    </main>
  );
}
