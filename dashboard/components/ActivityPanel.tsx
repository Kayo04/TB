import { getCycleActivity, getHeartbeat } from "@/lib/queries";
import Panel from "./Panel";

const DECISIONS = ["no_transition", "order_submitted", "cycle_failed"] as const;

const DECISION_COLOR: Record<(typeof DECISIONS)[number], string> = {
  no_transition: "var(--text-muted)",
  order_submitted: "var(--cyan)",
  cycle_failed: "var(--critical)",
};

function formatAgo(ts: string | null): string {
  if (!ts) return "--";
  const seconds = Math.round((Date.now() - new Date(ts).getTime()) / 1000);
  if (seconds < 60) return `há ${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `há ${hours}h`;
  return `há ${Math.round(hours / 24)} dias`;
}

export default async function ActivityPanel() {
  const [activity, heartbeat] = await Promise.all([getCycleActivity(), getHeartbeat()]);
  const max = Math.max(1, ...DECISIONS.map((d) => activity.byDecision[d] ?? 0));

  return (
    <Panel title="Atividade">
      {DECISIONS.map((d) => {
        const n = activity.byDecision[d] ?? 0;
        return (
          <div className="cycle-bar-row" key={d}>
            <span className="lbl">{d}</span>
            <span className="cycle-bar-track">
              <span className="cycle-bar-fill" style={{ width: `${(n / max) * 100}%`, background: DECISION_COLOR[d] }} />
            </span>
            <span className="n">{n}</span>
          </div>
        );
      })}
      <div className="kv-list">
        <div>
          Total de ciclos <span className="kv-value">{activity.totalCycles}</span>
        </div>
        <div>
          Último ciclo <span className="kv-value">{formatAgo(activity.lastCycleAt)}</span>
        </div>
        <div>
          A monitorizar desde <span className="kv-value">{formatAgo(activity.monitoringSince)}</span>
        </div>
        <div>
          Duração média de ciclo (24h){" "}
          <span className="kv-value">
            {activity.avgDurationMs24h !== null ? `${Math.round(activity.avgDurationMs24h)} ms` : "--"}
          </span>
        </div>
        <div>
          Heartbeat <span className="kv-value">{heartbeat ? formatAgo(heartbeat.lastSeenAt) : "sem registo"}</span>
        </div>
      </div>
      <p
        style={{
          fontFamily: "var(--mono)",
          fontSize: "0.62rem",
          color: "var(--text-muted)",
          marginTop: "0.8rem",
          marginBottom: 0,
          lineHeight: 1.5,
        }}
      >
        "A monitorizar desde" é a linha mais antiga em run_log -- não é o tempo de vida real do
        processo (não há histórico de restarts nas tabelas atuais).
      </p>
    </Panel>
  );
}
