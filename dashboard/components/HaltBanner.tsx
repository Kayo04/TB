import { getHaltState } from "@/lib/queries";
import { formatTs } from "@/lib/format";

export default async function HaltBanner() {
  const { halted, latestEvent } = await getHaltState();

  if (!halted) {
    return (
      <div style={{ background: "#16a34a", color: "white", textAlign: "center", padding: "6px 16px" }}>
        A correr -- kill switch não está ativo.
      </div>
    );
  }

  return (
    <div
      style={{
        background: "#dc2626",
        color: "white",
        textAlign: "center",
        padding: "6px 16px",
        fontWeight: 700,
      }}
    >
      HALTED desde {formatTs(latestEvent?.created_at ?? null)} -- motivo: {latestEvent?.reason}{" "}
      (via {latestEvent?.triggered_by}). Requer intervenção humana (scripts/clear_halt.py).
    </div>
  );
}
