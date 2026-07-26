import CommandHeader from "@/components/CommandHeader";
import PerformanceSection from "@/components/PerformanceSection";
import EquityCurveChart from "@/components/EquityCurveChart";
import ActivityPanel from "@/components/ActivityPanel";
import TradeBlotter from "@/components/TradeBlotter";
import PositionTable from "@/components/PositionTable";
import ReconciliationTable from "@/components/ReconciliationTable";
import RiskEventsTable from "@/components/RiskEventsTable";
import RunLogTable from "@/components/RunLogTable";
import StrategyExplained from "@/components/StrategyExplained";
import Panel from "@/components/Panel";

// This page must reflect live database state on every request -- never
// statically cached or ISR'd.
export const dynamic = "force-dynamic";

export default function DashboardPage() {
  return (
    <main>
      <CommandHeader />

      <section>
        <h2>Desempenho</h2>
        <PerformanceSection />
      </section>

      <section>
        <h2>Curva &amp; atividade</h2>
        <div className="grid-2">
          <EquityCurveChart />
          <ActivityPanel />
        </div>
      </section>

      <section>
        <h2>Estado ao vivo</h2>
        <Panel title="Blotter de trades (todos os fills)">
          <TradeBlotter />
        </Panel>
        <Panel title="Posições">
          <PositionTable />
        </Panel>
      </section>

      <section>
        <h2>Saúde do sistema</h2>
        <div className="grid-2">
          <Panel title="Reconciliação">
            <ReconciliationTable />
          </Panel>
          <Panel title="Histórico do kill-switch">
            <RiskEventsTable />
          </Panel>
        </div>
        <Panel title="Histórico de ciclos">
          <RunLogTable />
        </Panel>
      </section>

      <section>
        <StrategyExplained />
      </section>

      <footer className="page-footer">trading-bot &middot; dashboard read-only (dashboard_ro)</footer>
    </main>
  );
}
