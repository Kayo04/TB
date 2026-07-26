import type { ReactNode } from "react";

export default function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="panel">
      <div className="panel-title">{title}</div>
      {children}
    </div>
  );
}
