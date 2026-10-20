import { Outlet } from "react-router-dom";
import { useAppearance } from "@/features/settings/useAppearance";
import { SideNav } from "./SideNav";
import { TopBar } from "./TopBar";

/** Authenticated app frame: fixed sidebar + top bar + scrollable content. */
export function AppShell() {
  useAppearance();
  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      {/* Skip the persistent SideNav for keyboard users (A11Y-06, DESIGN.md). */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-modal focus:rounded-md focus:bg-surface focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-foreground focus:shadow-heavy focus:outline-hidden focus:ring-2 focus:ring-ring"
      >
        Skip to content
      </a>
      <SideNav />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main
          id="main-content"
          tabIndex={-1}
          className="flex-1 overflow-y-auto focus:outline-hidden"
        >
          <div className="mx-auto w-full max-w-6xl px-6 py-8 md:px-10 md:py-10">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
