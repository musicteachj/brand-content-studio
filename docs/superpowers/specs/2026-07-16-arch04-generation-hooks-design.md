# ARCH-04 — Consolidate the generation hooks (+ fix the un-pick-image bug)

**Date:** 2026-07-16
**Audit item:** ARCH-04 (Medium) — "The generation-hook fork has already produced a live user-visible bug."
**Branch:** `feat/arch04-generation-hooks`

## Problem

`client/src/features/generate/` has four streaming-generation hooks —
`useTextGeneration`, `useDocumentGeneration`, `useCardGeneration`,
`usePostPackGeneration`. They repeat two cross-cutting concerns:

1. **The streaming state machine** (all four): an `AbortController` ref, a
   workspace-switch abort+reset effect, a `generate` orchestration
   (abort prior → new controller → seed streaming → stream with
   `onText`/`onMeta`/`onError` → terminal `done` unless aborted/errored), and
   `stop`.
2. **Card image selection** (card + post-pack, ~57 byte-identical lines):
   `selectUnsplash`, `selectUpload`, the idempotent "PATCH the picked image onto
   the generation" effect, and the workspace reset.

### The bug — and what the audit got slightly wrong

The audit states card mode can un-pick an image while post-pack cannot. Tracing
the code shows the reality is worse and simpler: `useCardGeneration` **defines
and returns `clearImage` (and `reset`), but nothing in the client consumes
either** (verified by grep). `CardPreview` only offers "Add an image" /
"Change image" (open the picker); `ImagePickerPanel` has select tiles but no
deselect. So **neither** mode lets a user remove a chosen image — card mode
merely carries an unused method. Extracting a shared hook alone would give
post-pack the *same dead method*; it would not fix anything a user can see.

## Goals

- Remove the duplication the audit names, via two well-bounded hooks.
- **Actually close the capability gap**: a working "Remove image" control in
  **both** card and post-pack modes.
- Preserve the exact return contract every `GeneratePage` consumer depends on,
  so the blast radius stays inside `features/generate/`.

## Non-goals

- Persisting image removal. `clearImage` stays **client-only** (matches today's
  semantics): it un-picks locally so the user can export image-less or choose
  another, but does not PATCH `{image: null}`. A card re-opened from History
  still shows its saved image. Persisting the removal needs
  "had-an-image-then-removed" tracking + a null-PATCH path — a separate,
  higher-risk concern, deferred.
- Splitting `GeneratePage.tsx` (that is ARCH-06, out of scope here).

## Design

### `useStreamedGeneration<TState, TBody, TMeta>(workspaceId, config)`

Owns the streaming state machine for **all four** hooks. Holds `status`/`error`,
the `AbortController` ref, the workspace-switch abort+reset effect, and exposes
`state`, `setState`, `generate(body)`, `stop()`, `abort()`.

Per-domain variation is a config of pure reducers, held in a ref so `generate`
and the effect stay stable (deps `[workspaceId]`, as today):

```ts
interface StreamConfig<TState, TBody, TMeta> {
  initial: TState;                                   // TState extends { status: Status; error: string | null }
  stream: (workspaceId: string, body: TBody,
           handlers: StreamHandlers<TMeta>, signal: AbortSignal) => Promise<void>;
  applyText: (prev: TState, delta: string) => TState;
  applyMeta: (prev: TState, meta: TMeta) => TState;
  streamingSeed?: (prev: TState, body: TBody) => TState; // default {...initial, status: "streaming"}
}
```

`generate` mirrors the current skeleton exactly: abort prior, new controller,
`setState(streamingSeed ?? {...initial, status:"streaming"})`, stream with the
three handlers (`onError` sets `status:"error"` + message and flags `errored`),
then `if (!signal.aborted) setState(done unless errored)`.

### `useCardImageSelection(workspaceId, generationId)`

Owns the image concern for card + post-pack. State: `image`, `imageDataUrl`,
`imageError`. Methods: `selectUnsplash(photo)`, `selectUpload(url, key)`,
`clearImage()`, `hydrate(generationId, image)` (seed from History without
re-PATCHing — records the persisted key first), `reset()`. Internally runs the
idempotent persist effect (PATCH `{image}` onto the generation once both
`generationId` and `image` exist, keyed on `generationId:imageKey`) and an epoch
ref to drop stale async `fetchImageDataUrl` writes after a workspace/gen change.

Because image now lives **outside** the stream state, it survives a regenerate
automatically and re-attaches to the new generation id — same behavior as today,
less code.

### The four hooks become thin compositions

- `useTextGeneration` / `useDocumentGeneration` = `useStreamedGeneration` + a
  2-line config, returning `{ ...state, generate, stop }` — identical shape.
  (Document passes `streamingSeed` to keep `archetype` from the body.)
- `useCardGeneration` / `usePostPackGeneration` = `useStreamedGeneration` +
  `useCardImageSelection`, returning `{ ...state, ...img, generate,
  loadGeneration, stop, reset }`. `loadGeneration` calls `abort()`,
  `setState(done snapshot)`, and `img.hydrate(gen.id, image)`. Post-pack gains
  `clearImage` and `reset` for free.

### UX fix — the "Remove image" control

`CardPreview` gains an optional `onClearImage?: () => void`. In the finishing-
actions row, when `hasImage` is true (template uses an image; status streaming/
done), a subtle ghost "Remove" button (icon `ImageMinus`/`X`) sits next to
"Change image". `CardMode` and `PostPackMode` both pass
`onClearImage={gen.clearImage}`. No image → no Remove button.

## Testing

- **Regression net:** existing `useCardGeneration.test.tsx` and
  `usePostPackGeneration.test.tsx` stay green (adapt a test only if it reaches
  into now-moved internals — never change behavior to fit).
- **New:** `useCardImageSelection.test.tsx` (select → single persist PATCH;
  `clearImage` → image null + no PATCH; `hydrate` suppresses the initial PATCH),
  and a `CardPreview` test (Remove shows only with an image and calls
  `onClearImage`).
- **Behaviors preserved (checklist):** regenerate keeps the image + re-PATCHes
  onto the new id; History load sets `done` without re-PATCH and fetches bytes;
  workspace switch aborts+resets; idempotent PATCH; stale-async guards;
  `onError → status:"error"`.

## Verification

- **Live verify in the browser**, both post and card modes: generate → pick an
  image → Remove (clears) → pick another → regenerate (image persists) → export.
- Client gate: `npm run typecheck` / `lint` / `build` / `test`.
- `/code-review` + `/security-review`, then owner PR approval into `dev`.

## Risk

Medium — delicate stateful hooks with async + effects. Mitigated by the
preserved return contract (blast radius inside `features/generate/`), the
existing hook tests, and browser live-verify.
