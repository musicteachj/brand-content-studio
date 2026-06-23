import { PenLine } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "./ThemeToggle";

export function TopBar() {
  const navigate = useNavigate();
  return (
    <header className="z-header flex h-16 shrink-0 items-center gap-4 border-b border-border bg-surface px-6 md:px-10">
      <div className="flex flex-col leading-none">
        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
          Workspace
        </span>
        <span className="mt-1 text-sm font-medium text-foreground">Verdure Materials</span>
      </div>
      <div className="ml-auto flex items-center gap-2">
        <ThemeToggle />
        <Button size="sm" onClick={() => navigate("/generate")}>
          <PenLine className="h-4 w-4" aria-hidden />
          New generation
        </Button>
      </div>
    </header>
  );
}
