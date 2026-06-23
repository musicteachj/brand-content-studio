import { useState } from "react";
import { NavLink } from "react-router-dom";
import {
  Files,
  LayoutDashboard,
  LayoutGrid,
  LogOut,
  PanelLeft,
  PanelLeftClose,
  PenLine,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { Brand } from "@/components/Brand";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/generate", label: "Generate", icon: PenLine },
  { to: "/history", label: "History", icon: LayoutGrid },
  { to: "/assets", label: "Assets", icon: Files },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function SideNav() {
  const [collapsed, setCollapsed] = useState(false);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const initials = (user?.full_name ?? "Demo User")
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <aside
      className={cn(
        "z-drawer flex shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-200 ease-out",
        collapsed ? "w-[68px]" : "w-64",
      )}
    >
      <div className="flex h-16 items-center justify-between px-4">
        <Brand collapsed={collapsed} />
      </div>

      <nav className="flex flex-1 flex-col gap-0.5 px-3 pt-2">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              cn(
                "group flex items-center gap-3 rounded-md border-l-[3px] py-2.5 pr-3 text-sm transition-colors",
                collapsed ? "pl-[14px]" : "pl-3",
                isActive
                  ? "border-accent bg-surface-variant font-medium text-foreground"
                  : "border-transparent text-muted-foreground hover:bg-surface-variant hover:text-foreground",
              )
            }
          >
            <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
            {!collapsed && <span className="truncate">{label}</span>}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-border p-3">
        <div className={cn("flex items-center gap-3", collapsed && "justify-center")}>
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-variant font-mono text-[11px] font-medium text-foreground">
            {initials}
          </span>
          {!collapsed && (
            <div className="flex min-w-0 flex-1 flex-col leading-tight">
              <span className="truncate text-sm font-medium text-foreground">
                {user?.full_name ?? "Demo User"}
              </span>
              {user?.is_demo && (
                <span className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                  Demo session
                </span>
              )}
            </div>
          )}
          {!collapsed && (
            <button
              type="button"
              onClick={logout}
              aria-label="Sign out"
              className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-surface-variant hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <LogOut className="h-[18px] w-[18px]" aria-hidden />
            </button>
          )}
        </div>

        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "mt-3 flex w-full items-center gap-3 rounded-md px-2.5 py-2 text-muted-foreground transition-colors hover:bg-surface-variant hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            collapsed && "justify-center",
          )}
        >
          {collapsed ? (
            <PanelLeft className="h-[18px] w-[18px]" aria-hidden />
          ) : (
            <>
              <PanelLeftClose className="h-[18px] w-[18px]" aria-hidden />
              <span className="text-sm">Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
