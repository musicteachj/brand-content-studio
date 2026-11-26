import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

import { useStreamedGeneration } from "./useStreamedGeneration";
import type { StreamHandlers } from "@/lib/sse";

interface S {
  status: "idle" | "streaming" | "done" | "error";
  text: string;
  gid: string | null;
  error: string | null;
}
const INITIAL: S = { status: "idle", text: "", gid: null, error: null };
type Meta = { generation_id: string };
type Body = { brief: string };

// A controllable fake stream: captures the handlers + signal, resolves on demand.
let handlers: StreamHandlers<Meta> | undefined;
let signal: AbortSignal | undefined;
let resolve: (() => void) | undefined;
function fakeStream(
  _ws: string,
  _body: Body,
  h: StreamHandlers<Meta>,
  s: AbortSignal,
): Promise<void> {
  handlers = h;
  signal = s;
  return new Promise<void>((r) => {
    resolve = r;
  });
}

const CONFIG = {
  initial: INITIAL,
  stream: fakeStream,
  applyText: (s: S, delta: string) => ({ ...s, text: s.text + delta }),
  applyMeta: (s: S, meta: Meta) => ({ ...s, gid: meta.generation_id }),
};

type Hook = ReturnType<typeof useStreamedGeneration<S, Body, Meta>>;
let latest: Hook;
let container: HTMLDivElement;
let root: Root;
function Harness({ ws }: { ws: string }) {
  latest = useStreamedGeneration<S, Body, Meta>(ws, CONFIG);
  return null;
}
function mount(ws = "a") {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root.render(<Harness ws={ws} />));
}

beforeEach(() => {
  handlers = undefined;
  signal = undefined;
  resolve = undefined;
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("useStreamedGeneration", () => {
  it("generate → streaming; applyText/applyMeta accumulate; resolve → done", async () => {
    mount();
    act(() => {
      void latest.generate({ brief: "x" });
    });
    expect(latest.state.status).toBe("streaming");

    act(() => {
      handlers!.onText("Hello ");
      handlers!.onText("world");
    });
    expect(latest.state.text).toBe("Hello world");
    act(() => {
      handlers!.onMeta({ generation_id: "g1" });
    });
    expect(latest.state.gid).toBe("g1");

    await act(async () => {
      resolve!();
    });
    expect(latest.state.status).toBe("done");
  });

  it("onError sets status error + message and does not flip to done", async () => {
    mount();
    act(() => {
      void latest.generate({ brief: "x" });
    });
    act(() => {
      handlers!.onError("boom");
    });
    expect(latest.state.status).toBe("error");
    expect(latest.state.error).toBe("boom");
    await act(async () => {
      resolve!();
    });
    expect(latest.state.status).toBe("error"); // stays error, never "done"
  });

  it("stop aborts the in-flight stream and flips streaming → done", () => {
    mount();
    act(() => {
      void latest.generate({ brief: "x" });
    });
    act(() => {
      latest.stop();
    });
    expect(signal!.aborted).toBe(true);
    expect(latest.state.status).toBe("done");
  });

  it("switching workspace aborts the in-flight stream and resets to idle", () => {
    mount("a");
    act(() => {
      void latest.generate({ brief: "x" });
    });
    expect(latest.state.status).toBe("streaming");
    const inflight = signal!;
    act(() => root.render(<Harness ws="b" />));
    expect(inflight.aborted).toBe(true);
    expect(latest.state.status).toBe("idle");
    expect(latest.state.text).toBe("");
  });
});
