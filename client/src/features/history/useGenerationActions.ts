import { useCallback, useEffect, useMemo, useState } from "react";
import { downloadCardPng } from "@/features/generate/useCardExport";
import type { BrandProfile, Generation } from "@/types";
import { cardFrom, postText } from "./historyOutputs";

/** Copy-text (posts) + download-PNG (cards) actions, shared by the grid card and
 *  the detail dialog. The PNG download re-exports from the persisted output with
 *  no model call. Transient state resets when the generation changes. */
export function useGenerationActions(gen: Generation | null, brand: BrandProfile | null) {
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  // Memoized so `download`'s dependency is stable across renders. Covers cards
  // and the nested card of a post_pack.
  const card = useMemo(() => (gen ? cardFrom(gen) : null), [gen]);

  // Reset all transient action state when a different generation is opened
  // (the dialog reuses one hook instance across generations).
  useEffect(() => {
    setCopied(false);
    setDownloading(false);
    setDownloadError(null);
  }, [gen?.id]);

  const copyText = useCallback(async () => {
    if (!gen) return;
    await navigator.clipboard.writeText(postText(gen));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [gen]);

  const download = useCallback(async () => {
    if (!card || !brand) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      await downloadCardPng(card, brand);
    } catch (err) {
      setDownloadError((err as Error).message);
    } finally {
      setDownloading(false);
    }
  }, [card, brand]);

  return { card, copied, copyText, downloading, downloadError, download };
}
