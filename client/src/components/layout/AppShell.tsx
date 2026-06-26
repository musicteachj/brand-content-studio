import { Outlet } from "react-router-dom";
import { useAppearance } from "@/features/settings/useAppearance";
import { SideNav } from "./SideNav";
import { TopBar } from "./TopBar";

/** Authenticated app frame: fixed sidebar + top bar + scrollable content. */
export function AppShell() {
  useAppearance();
  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      <SideNav />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-6xl px-6 py-8 md:px-10 md:py-10">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
