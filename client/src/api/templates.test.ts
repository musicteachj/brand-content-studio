import { afterEach, describe, expect, it, vi } from "vitest";
import { fillTemplateFromDocument } from "./templates";

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: { post } }));

afterEach(() => vi.clearAllMocks());

describe("fillTemplateFromDocument", () => {
  it("posts the file as multipart and returns the values map", async () => {
    post.mockResolvedValue({ data: { values: { title: "Mapped" } } });
    const file = new File(["hi"], "draft.docx");
    const values = await fillTemplateFromDocument("ws1", "t1", file);
    expect(values).toEqual({ title: "Mapped" });
    const [url, body] = post.mock.calls[0];
    expect(url).toBe("/workspaces/ws1/templates/t1/fill-from-document");
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get("file")).toBe(file);
  });
});
