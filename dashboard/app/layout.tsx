import type { Metadata } from "next";
import PaperModeBanner from "@/components/PaperModeBanner";
import HaltBanner from "@/components/HaltBanner";
import AutoRefresh from "@/components/AutoRefresh";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trading Bot Dashboard (paper)",
};

// HaltBanner queries Postgres live. Without this, Next tries to statically
// prerender routes that use this layout (including the auto-generated
// /_not-found page) at BUILD time, before any real DATABASE_URL exists --
// force-dynamic on the layout itself (not just page.tsx) covers every route
// that inherits it, not only the one page that set its own dynamic export.
export const dynamic = "force-dynamic";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt">
      <body>
        <PaperModeBanner />
        <HaltBanner />
        <AutoRefresh />
        {children}
      </body>
    </html>
  );
}
