import { getCycleHealth } from "@/lib/queries";
import { formatTs } from "@/lib/format";

export default async function CycleHealthPanel() {
  const health = await getCycleHealth();
  // ~2.5x the expected hourly cadence -- an inferred signal, not a guaranteed
  // liveness check (Postgres alone can't prove the process is running; a
  // gap this size just means "worth checking `docker compose logs bot`").
  const stale = health.minutesSinceLastCycle !== null && health.minutesSinceLastCycle > 150;

  return (
    <ul>
      <li>
        Último ciclo: {formatTs(health.lastCycleAt)}
        {health.minutesSinceLastCycle !== null && ` (há ${health.minutesSinceLastCycle} min)`}
        {stale && (
          <strong style={{ color: "#dc2626" }}>
            {" "}
            -- pode estar parado (inferido a partir do gap, não uma garantia)
          </strong>
        )}
      </li>
      <li>
        Duração média de ciclo (24h):{" "}
        {health.avgDurationMs !== null ? `${Math.round(health.avgDurationMs)} ms` : "--"}
      </li>
      <li>Ciclos falhados (24h): {health.failedLast24h}</li>
    </ul>
  );
}
