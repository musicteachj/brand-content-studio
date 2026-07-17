import { useRef, useState } from "react";
import { FileText, FileUp, Sparkles, Trash2, Upload } from "lucide-react";
import {
  fillTemplateFromDocument,
  renderTemplate,
  useAiFillTemplate,
  useDeleteTemplate,
  useTemplates,
  useUploadTemplate,
} from "@/api/templates";
import { DemoNotice } from "@/components/DemoNotice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useActiveWorkspace } from "@/features/workspace/useActiveWorkspace";
import { useAuthStore } from "@/stores/auth";
import type { Template } from "@/types";
import { emptyValues, mergeFilled } from "./templateForm";

export function TemplatesPage() {
  const { workspaceId } = useActiveWorkspace();
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const { data: templates } = useTemplates(workspaceId);
  const upload = useUploadTemplate(workspaceId);
  const del = useDeleteTemplate(workspaceId);
  const fileRef = useRef<HTMLInputElement>(null);
  const [active, setActive] = useState<Template | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError(null);
    try {
      await upload.mutateAsync(file);
    } catch {
      setError("Couldn’t upload — use a .docx or .pptx under 10 MB.");
    }
  }

  return (
    <div className="flex max-w-3xl flex-col gap-8">
      <header className="animate-fade-in-up">
        <p className="eyebrow text-[11px]">Templates</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-heading text-foreground">
          On-brand templates
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Upload a branded .docx or .pptx with {"{{placeholders}}"} — fill it with your own text (or
          an AI draft) and download a file in your template’s exact styling.
        </p>
      </header>

      {isDemo && (
        <DemoNotice message="You're exploring as a demo — uploading and deleting templates is disabled so the seeded workspace stays intact." />
      )}

      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">Your templates</h2>
          <input
            ref={fileRef}
            type="file"
            accept=".docx,.pptx"
            className="hidden"
            onChange={onFile}
          />
          <Button
            size="sm"
            variant="secondary"
            onClick={() => fileRef.current?.click()}
            loading={upload.isPending}
            disabled={isDemo}
            title={isDemo ? "Disabled in the demo" : undefined}
          >
            <Upload className="h-4 w-4" aria-hidden />
            Upload template
          </Button>
        </div>
        {error && <span className="text-xs text-destructive">{error}</span>}
        {(templates ?? []).length === 0 ? (
          <div className="rounded-lg border border-dashed border-border bg-surface p-8 text-center text-sm text-muted-foreground">
            No templates yet. Upload a branded .docx or .pptx to start.
          </div>
        ) : (
          <ul className="flex flex-col divide-y divide-border rounded-xl border border-border bg-surface">
            {(templates ?? []).map((t) => (
              <li key={t.id} className="flex items-center gap-3 px-4 py-3">
                <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                <div className="flex min-w-0 flex-col leading-tight">
                  <span className="truncate text-sm font-medium text-foreground">{t.name}</span>
                  <span className="eyebrow">
                    {t.format} · {t.placeholders.length} field
                    {t.placeholders.length === 1 ? "" : "s"}
                  </span>
                </div>
                <div className="ml-auto flex items-center gap-1">
                  <Button size="sm" onClick={() => setActive(t)}>
                    Use
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => del.mutate(t.id)}
                    disabled={isDemo}
                    title={isDemo ? "Disabled in the demo" : "Delete"}
                    aria-label="Delete template"
                    className="hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {active && (
        <FillPanel
          key={active.id}
          workspaceId={workspaceId}
          template={active}
          onClose={() => setActive(null)}
        />
      )}
    </div>
  );
}

function FillPanel({
  workspaceId,
  template,
  onClose,
}: {
  workspaceId: string | null;
  template: Template;
  onClose: () => void;
}) {
  const aiFill = useAiFillTemplate(workspaceId);
  const [values, setValues] = useState<Record<string, string>>(() =>
    emptyValues(template.placeholders),
  );
  const [brief, setBrief] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const docRef = useRef<HTMLInputElement>(null);
  const [fillingFromDoc, setFillingFromDoc] = useState(false);

  async function fillFromDocument(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !workspaceId) return;
    setFillingFromDoc(true);
    setError(null);
    try {
      const filled = await fillTemplateFromDocument(workspaceId, template.id, file);
      setValues(mergeFilled(template.placeholders, filled));
    } catch {
      setError("Couldn’t read that document. Use a .docx, .pptx, .pdf, .txt, or .md under 10 MB.");
    } finally {
      setFillingFromDoc(false);
    }
  }

  async function draftWithAI() {
    if (!brief.trim()) return;
    setError(null);
    try {
      const filled = await aiFill.mutateAsync({ templateId: template.id, brief });
      setValues(mergeFilled(template.placeholders, filled));
    } catch {
      setError("AI draft failed — fill the fields yourself or try again.");
    }
  }

  async function download() {
    if (!workspaceId) return;
    setDownloading(true);
    setError(null);
    try {
      await renderTemplate(workspaceId, template, values);
    } catch {
      setError("Couldn’t render the file. Try again.");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <section className="flex flex-col gap-4 rounded-xl border border-border bg-surface p-5 shadow-light">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Fill “{template.name}”</h2>
        <Button size="sm" variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>

      {template.placeholders.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          This template has no {"{{placeholders}}"} — downloading returns it unchanged.
        </p>
      ) : (
        <>
          <div className="flex flex-col gap-2 rounded-lg border border-dashed border-border bg-surface-variant/40 p-3.5">
            <Label htmlFor="tpl-brief">Draft with AI (optional)</Label>
            <Textarea
              id="tpl-brief"
              rows={2}
              placeholder="e.g. a welcome letter for a new hempcrete supplier"
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
            />
            <div>
              <Button
                size="sm"
                variant="secondary"
                onClick={draftWithAI}
                loading={aiFill.isPending}
              >
                <Sparkles className="h-4 w-4" aria-hidden />
                Draft with AI
              </Button>
            </div>
            <div className="flex flex-wrap items-center gap-2 border-t border-border pt-2.5">
              <input
                ref={docRef}
                type="file"
                accept=".docx,.pptx,.pdf,.txt,.md,.markdown"
                className="hidden"
                onChange={fillFromDocument}
              />
              <Button
                size="sm"
                variant="ghost"
                onClick={() => docRef.current?.click()}
                loading={fillingFromDoc}
              >
                <FileUp className="h-4 w-4" aria-hidden />
                Fill from a document
              </Button>
              <span className="text-[11px] text-muted-foreground">
                Content is mapped and condensed to fit the template.
              </span>
            </div>
          </div>

          <div className="flex flex-col gap-3">
            {template.placeholders.map((p) => (
              <div key={p} className="flex flex-col">
                <Label htmlFor={`f-${p}`}>{p}</Label>
                <Input
                  id={`f-${p}`}
                  value={values[p] ?? ""}
                  onChange={(e) => setValues((v) => ({ ...v, [p]: e.target.value }))}
                />
              </div>
            ))}
          </div>
        </>
      )}

      {error && <span className="text-xs text-destructive">{error}</span>}
      <div>
        <Button onClick={download} loading={downloading}>
          Download {template.format.toUpperCase()}
        </Button>
      </div>
    </section>
  );
}
