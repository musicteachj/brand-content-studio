import { useCallback, useEffect, useRef, useState } from "react";
import type { StreamHandlers } from "@/lib/sse";

export type Status = "idle" | "streaming" | "done" | "error";

/** The status/error fields every generation state carries. */
export interface StreamBaseState {
  status: Status;
  error: string | null;
}

export interface StreamConfig<TState extends StreamBaseState, TBody, TMeta> {
  initial: TState;
  stream: (
    workspaceId: string,
    body: TBody,
    handlers: StreamHandlers<TMeta>,
    signal: AbortSignal,
  ) => Promise<void>;
  applyText: (prev: TState, delta: string) => TState;
  applyMeta: (prev: TState, meta: TMeta) => TState;
  /** Seed the streaming state from the request body. Defaults to
   *  `{ ...initial, status: "streaming" }`. */
  streamingSeed?: (prev: TState, body: TBody) => TState;
}

/** The streaming state machine shared by all four generation hooks (ARCH-04): owns
 *  the AbortController, the workspace-switch abort+reset, `generate` (abort prior →
 *  seed streaming → stream → terminal done/error unless aborted), and `stop`. The
 *  per-domain state shape, stream endpoint, and text/meta reducers are supplied via
 *  `config`, held in a ref so `generate`/effects stay stable across renders. */
export function useStreamedGeneration<TState extends StreamBaseState, TBody, TMeta>(
  workspaceId: string | null,
  config: StreamConfig<TState, TBody, TMeta>,
) {
  const [state, setState] = useState<TState>(config.initial);
  const abortRef = useRef<AbortController | null>(null);
  const configRef = useRef(config);
  configRef.current = config; // always read the latest without destabilizing callbacks

  // Switching workspaces must not leave an in-flight stream writing into the new
  // workspace's view: abort it and reset to a clean slate.
  useEffect(() => {
    setState(configRef.current.initial);
    return () => abortRef.current?.abort();
  }, [workspaceId]);

  const generate = useCallback(
    async (body: TBody) => {
      if (!workspaceId) return;
      const cfg = configRef.current;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setState((s) =>
        cfg.streamingSeed ? cfg.streamingSeed(s, body) : { ...cfg.initial, status: "streaming" },
      );

      let errored = false;
      await cfg.stream(
        workspaceId,
        body,
        {
          onText: (delta) => setState((s) => cfg.applyText(s, delta)),
          onMeta: (meta) => setState((s) => cfg.applyMeta(s, meta)),
          onError: (message) => {
            errored = true;
            setState((s) => ({ ...s, status: "error", error: message }));
          },
        },
        controller.signal,
      );

      if (!controller.signal.aborted) {
        setState((s) => (errored ? s : { ...s, status: "done" }));
      }
    },
    [workspaceId],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setState((s) => (s.status === "streaming" ? { ...s, status: "done" } : s));
  }, []);

  const abort = useCallback(() => abortRef.current?.abort(), []);

  return { state, setState, generate, stop, abort };
}
