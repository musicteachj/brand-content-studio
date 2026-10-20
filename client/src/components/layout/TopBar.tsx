import { PenLine } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "./ThemeToggle";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

export function TopBar() {
  const navigate = useNavigate();
  return (
    <header className="z-header flex h-16 shrink-0 items-center gap-4 border-b border-border bg-surface px-6 md:px-10">
      <WorkspaceSwitcher />
      <div className="ml-auto flex shrink-0 items-center gap-2">
        <ThemeToggle />
        {/* Icon-only on a phone-width window, so it isn't cut off. */}
        <Button size="sm" onClick={() => navigate("/generate")}>
          <PenLine className="h-4 w-4" aria-hidden />
          <span className="sr-only sm:not-sr-only">New generation</span>
        </Button>
      </div>
    </header>
  );
}
