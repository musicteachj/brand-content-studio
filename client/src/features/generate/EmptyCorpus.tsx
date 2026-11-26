import { FileText } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";

export function EmptyCorpus() {
  const navigate = useNavigate();
  return (
    <div className="flex min-h-[60vh] animate-fade-in-up flex-col items-center justify-center text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-lg border border-border bg-surface text-muted-foreground shadow-light">
        <FileText className="h-6 w-6" aria-hidden />
      </span>
      <h1 className="mt-5 text-xl font-semibold text-foreground">Ingest assets first</h1>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        This workspace has no retrievable brand corpus yet. Upload brand documents so generation has
        something on-brand to work from.
      </p>
      <Button className="mt-5" onClick={() => navigate("/assets")}>
        Open Asset Manager
      </Button>
    </div>
  );
}
