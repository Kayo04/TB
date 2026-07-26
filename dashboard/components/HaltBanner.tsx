import { getHaltState } from "@/lib/queries";
import { formatTs } from "@/lib/format";

export default async function HaltBanner() {
  const { halted, latestEvent } = await getHaltState();

  if (!halted) {
    return <div className="banner banner--ok">● A correr -- kill switch não está ativo.</div>;
  }

  return (
    <div className="banner banner--halt">
      ⚠ HALTED desde {formatTs(latestEvent?.created_at ?? null)} -- motivo: {latestEvent?.reason}{" "}
      (via {latestEvent?.triggered_by}). Requer intervenção humana (scripts/clear_halt.py).
    </div>
  );
}
