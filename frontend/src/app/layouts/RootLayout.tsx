import { Outlet } from "react-router-dom";
import { Navbar } from "../components/Navbar";

/**
 * The one root layout every route renders inside (frontend plan §A/§O —
 * "designed so later stages can add features without restructuring").
 * Later stages that need a *different* chrome for a specific section
 * (e.g. the live-interview route hiding the normal nav) can nest a
 * further layout under this one — this file itself should stay stable.
 */
export function RootLayout() {
  return (
    <div className="flex min-h-svh flex-col bg-slate-50">
      <Navbar />
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  );
}
