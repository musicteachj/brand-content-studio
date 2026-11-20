// The multi-format download row under a generated document (Generate preview, History,
// and the public examples). Each button pulls the pre-rendered file with no model call:
// through the auth-gated workspace route by default, or from `downloadUrl` when given.
// Per-format loading/error state lives here.
import { useState } from "react";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiErrorMessage } from "@/lib/apiError";
import { cn } from "@/lib/utils";
import {
  downloadDocumentFile,
  workspaceDownloadUrl,
  type DocumentDownloadUrl,
} from "@/features/generate/documentDownload";
import type { DocumentFormat, DocumentOutput } from "@/types";

const FORMAT_ORDER: DocumentFormat[] = ["docx", "pdf", "pptx"];
const FORMAT_LABEL: Record<DocumentFormat, string> = { docx: ".docx", pdf: "PDF", pptx: ".pptx" };

interface Props {
  workspaceId: string | null;
  generationId: string;
  output: DocumentOutput;
  /** Where each format downloads from (default: the workspace's authed route). */
  downloadUrl?: DocumentDownloadUrl;
  className?: string;
}

export function DocumentDownloadRow({
  workspaceId,
  generationId,
  output,
  downloadUrl,
  className,
}: Props) {
  const [busy, setBusy] = useState<DocumentFormat | null>(null);
  const [error, setError] = useState<string | null>(null);
  const available = FORMAT_ORDER.filter((f) => output.formats[f]);
  const urlFor =
    downloadUrl ?? (workspaceId ? workspaceDownloadUrl(workspaceId, generationId) : null);

  async function go(fmt: DocumentFormat) {
    if (!urlFor) return;
    setBusy(fmt);
    setError(null);
    try {
      await downloadDocumentFile(urlFor, fmt, output.document.archetype);
    } catch (err) {
      setError(apiErrorMessage(err, "Download failed."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      {available.map((fmt) => (
        <Button
          key={fmt}
          variant="secondary"
          size="sm"
          onClick={() => void go(fmt)}
          loading={busy === fmt}
          disabled={!urlFor || busy !== null}
        >
          <Download className="h-4 w-4" aria-hidden />
          {FORMAT_LABEL[fmt]}
        </Button>
      ))}
      {error && (
        <span role="alert" className="text-xs text-destructive">
          {error}
        </span>
      )}
    </div>
  );
}
