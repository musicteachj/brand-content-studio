import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFrames, STREAM_INACTIVITY_MS } from "./sse";

function fakeResponse(reader: Partial<ReadableStreamDefaultReader<Uint8Array>>) {
  return { body: { getReader: () => reader } } as unknown as Response;
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("readFrames", () => {
  it("fires onError + cancels when the stream stalls", async () => {
    const cancel = vi.fn();
    const reader = { read: () => new Promise(() => {}), cancel, releaseLock: vi.fn() };
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
      read: () =>
        sent
          ? Promise.resolve({ done: true, value: undefined })
          : ((sent = true), Promise.resolve({ done: false, value: frame })),
      cancel: vi.fn(),
      releaseLock: vi.fn(),
    };
    const onError = vi.fn();
    await readFrames(fakeResponse(reader), { onText: vi.fn(), onMeta: vi.fn(), onError });
    expect(onError).toHaveBeenCalledWith("Generation failed.");
  });
});
