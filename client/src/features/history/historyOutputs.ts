import type { CardOutput, DocumentOutput, Generation, PostPackOutput, TextOutput } from "@/types";

export function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function postText(gen: Generation): string {
  const out = gen.output as TextOutput;
  return typeof out?.post_text === "string" ? out.post_text : "";
}

function cardOutput(gen: Generation): CardOutput | null {
  const out = gen.output as unknown as CardOutput;
  return gen.type === "card" && out?.template_id ? out : null;
}

/** The renderable card for a generation: a `card` carries it at the top of
 *  `output`; a `post_pack` nests it under `output.card`. */
export function cardFrom(gen: Generation): CardOutput | null {
  if (gen.type === "card") return cardOutput(gen);
  if (gen.type === "post_pack") {
    const out = gen.output as unknown as PostPackOutput;
    return out?.card?.template_id ? out.card : null;
  }
  return null;
}

export function documentOutput(gen: Generation): DocumentOutput | null {
  const out = gen.output as unknown as DocumentOutput;
  return gen.type === "document" && out?.document ? out : null;
}
