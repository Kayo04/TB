import { getHeartbeat } from "@/lib/queries";
import { formatTs } from "@/lib/format";

export default async function HeartbeatStatus() {
  const heartbeat = await getHeartbeat();

  if (!heartbeat) {
    return <p>Sem heartbeat registado ainda -- o processo nunca escreveu um.</p>;
  }

  const secondsAgo = Math.round((Date.now() - new Date(heartbeat.lastSeenAt).getTime()) / 1000);
  // ~3x the ~60s write cadence -- inferred, not a guaranteed liveness proof,
  // same caveat as CycleHealthPanel's own staleness check. The point of
  // this signal is to catch a wedged process within roughly a minute
  // instead of waiting for a bar to be due (up to an hour away).
  const stale = secondsAgo > 180;

  return (
    <p>
      Última atividade: há {secondsAgo}s ({formatTs(heartbeat.lastSeenAt)})
      {heartbeat.detail && ` -- ${heartbeat.detail}`}
      {stale && (
        <strong style={{ color: "#dc2626" }}> -- pode estar parado (heartbeat atrasado)</strong>
      )}
    </p>
  );
}
