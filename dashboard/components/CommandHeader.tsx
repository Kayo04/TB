import { getRecentRunLog, getPositions, getHeartbeat, getLatestEquity, getStrategyName } from "@/lib/queries";
import { formatDollar, formatNumber } from "@/lib/format";

export default async function CommandHeader() {
  const [recentLog, positions, heartbeat, equity, strategyName] = await Promise.all([
    getRecentRunLog(1),
    getPositions(),
    getHeartbeat(),
    getLatestEquity(),
    getStrategyName(),
  ]);

  const symbol = recentLog[0]?.symbol ?? positions.find((p) => p.position !== 0)?.symbol ?? "--";
  const position = positions.find((p) => p.symbol === symbol);
  const isLong = !!position && position.position !== 0;

  const secondsAgo = heartbeat ? Math.round((Date.now() - new Date(heartbeat.lastSeenAt).getTime()) / 1000) : null;
  const stale = secondsAgo === null || secondsAgo > 180;

  return (
    <div className="command-header">
      <div>
        <h1>
          TRADING&#8209;BOT <span className="accent">// {symbol}</span>
        </h1>
        <div className="command-sub">{strategyName ?? "sem estratégia registada ainda"}</div>
      </div>
      <div className="status-cluster">
        <span className={`chip ${isLong ? "chip--long" : "chip--flat"}`}>
          {isLong ? `LONG · ${formatNumber(position!.position, 2)}` : "FLAT"}
        </span>
        <span className="heartbeat-readout">
          <span className={`pulse-dot ${stale ? "pulse-dot--stale" : ""}`} />
          {secondsAgo !== null ? `heartbeat há ${secondsAgo}s` : "sem heartbeat ainda"}
        </span>
        <div className="equity-readout">
          <div className="label">Equity (mark-to-market)</div>
          <div className="value">{equity ? formatDollar(equity.totalEquity) : "--"}</div>
        </div>
      </div>
    </div>
  );
}
