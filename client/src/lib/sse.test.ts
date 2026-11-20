import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth";
import { readFrames, STREAM_INACTIVITY_MS, streamTextGeneration } from "./sse";

type Reader = ReadableStreamDefaultReader<Uint8Array>;
type ReadResult = ReadableStreamReadResult<Uint8Array>;

function fakeResponse(reader: Partial<Reader>) {
  return { body: { getReader: () => reader } } as unknown as Response;
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("readFrames", () => {
  it("fires onError + cancels when the stream stalls", async () => {
    const cancel = vi.fn();
    const reader = {
      read: () => new Promise<ReadResult>(() => {}),
      cancel,
      releaseLock: vi.fn(),
    };
    const onError = vi.fn();
    const p = readFrames(fakeResponse(reader), { onText: vi.fn(), onMeta: vi.fn(), onError });
    await vi.advanceTimersByTimeAsync(STREAM_INACTIVITY_MS + 10);
    await p;
    expect(onError).toHaveBeenCalledOnce();
    expect(cancel).toHaveBeenCalled();
  });

  it("type-guards a non-string error frame", async () => {
    const frame = new TextEncoder().encode('data: {"error": 123}\n\n');
    let sent = false;
    const reader = {
      read: (): Promise<ReadResult> =>
        sent
          ? Promise.resolve({ done: true, value: undefined })
          : ((sent = true), Promise.resolve({ done: false, value: frame })),
      cancel: vi.fn(),
      releaseLock: vi.fn(),
    };
    const onError = vi.fn();
    await readFrames(fakeResponse(reader), { onText: vi.fn(), onMeta: vi.fn(), onError });
    expect(onError).toHaveBeenCalledWith("Generation failed.", undefined);
  });

  it("ignores heartbeat comments and keeps the stream alive", async () => {
    const encode = (text: string) => new TextEncoder().encode(text);
    const heartbeat = encode(": keep-alive\n\n");
    // Each read resolves after 10 s, like the server's heartbeat while the model is silent.
    const chunks = [
      encode('data: {"text": "Hello "}\n\n'),
      heartbeat,
      heartbeat,
      heartbeat,
      heartbeat,
      encode('data: {"text": "world"}\n\n'),
      encode("data: [DONE]\n\n"),
    ];
    const reader = {
      read: (): Promise<ReadResult> => {
        const value = chunks.shift();
        return new Promise((resolve) =>
          setTimeout(
            () => resolve(value ? { done: false, value } : { done: true, value: undefined }),
            10_000,
          ),
        );
      },
      cancel: vi.fn(),
      releaseLock: vi.fn(),
    };
    const onText = vi.fn();
    const onError = vi.fn();
    const p = readFrames(fakeResponse(reader), { onText, onMeta: vi.fn(), onError });
    // 40 s of heartbeats only, past STREAM_INACTIVITY_MS, between the two text frames.
    await vi.advanceTimersByTimeAsync(70_000);
    await p;
    expect(STREAM_INACTIVITY_MS).toBeLessThan(40_000);
    expect(onError).not.toHaveBeenCalled();
    expect(reader.cancel).not.toHaveBeenCalled();
    expect(onText.mock.calls).toEqual([["Hello "], ["world"]]);
  });
});

describe("stream errors", () => {
  it("passes the error code from an error frame", async () => {
    const frame = new TextEncoder().encode(
      'data: {"error": "Paused.", "code": "live_ai_paused"}\n\n',
    );
    let sent = false;
    const reader = {
      read: (): Promise<ReadResult> =>
        sent
          ? Promise.resolve({ done: true, value: undefined })
          : ((sent = true), Promise.resolve({ done: false, value: frame })),
      cancel: vi.fn(),
      releaseLock: vi.fn(),
    };
    const onError = vi.fn();
    await readFrames(fakeResponse(reader), { onText: vi.fn(), onMeta: vi.fn(), onError });
    expect(onError).toHaveBeenCalledWith("Paused.", "live_ai_paused");
  });

  it("passes the code from a non-OK response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({ detail: "Slow down.", code: "rate_limited" }, { status: 429 }),
      ),
    );
    const onError = vi.fn();
    await streamTextGeneration(
      "w",
      { brief: "b", tone: "t", length: "l" },
      {
        onText: vi.fn(),
        onMeta: vi.fn(),
        onError,
      },
    );
    expect(onError).toHaveBeenCalledWith("Slow down.", "rate_limited");
    vi.unstubAllGlobals();
  });

  it("a 401 on a stream ends the demo session", async () => {
    useAuthStore
      .getState()
      .setSession("t", { id: "d1", email: "d@x.io", full_name: "D", is_demo: true });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ detail: "ended", code: "demo_ended" }, { status: 401 })),
    );
    await streamTextGeneration(
      "w",
      { brief: "b", tone: "t", length: "l" },
      {
        onText: vi.fn(),
        onMeta: vi.fn(),
        onError: vi.fn(),
      },
    );
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().endedReason).toBe("ended");
    vi.unstubAllGlobals();
  });

  it("a network failure reads as plain advice, not developer text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    const onError = vi.fn();
    await streamTextGeneration(
      "w",
      { brief: "b", tone: "t", length: "l" },
      { onText: vi.fn(), onMeta: vi.fn(), onError },
    );
    expect(onError).toHaveBeenCalledWith("Network error. Check your connection and try again.");
    expect(onError.mock.calls[0]![0]).not.toMatch(/server running/i);
    vi.unstubAllGlobals();
  });
});
