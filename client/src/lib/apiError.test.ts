import { AxiosError, AxiosHeaders } from "axios";
import { describe, expect, it } from "vitest";
import { apiErrorMessage, withJsonErrorBody } from "./apiError";

function axiosError(status: number, data: unknown): AxiosError {
  const config = { headers: new AxiosHeaders() };
  return new AxiosError("Request failed", "ERR_BAD_REQUEST", config, null, {
    status,
    statusText: "",
    headers: {},
    config,
    data,
  });
}

describe("apiErrorMessage", () => {
  it("prefers the server's detail string", () => {
    const err = axiosError(409, { detail: "A font with that name exists." });
    expect(apiErrorMessage(err, "Couldn't add that font.")).toBe("A font with that name exists.");
  });

  it("falls back for validation lists, empty details, and non-HTTP errors", () => {
    expect(apiErrorMessage(axiosError(422, { detail: [{ msg: "x" }] }), "fallback")).toBe(
      "fallback",
    );
    expect(apiErrorMessage(axiosError(400, { detail: "  " }), "fallback")).toBe("fallback");
    expect(apiErrorMessage(new AxiosError("Network Error", "ERR_NETWORK"), "fallback")).toBe(
      "fallback",
    );
    expect(apiErrorMessage(new Error("boom"), "fallback")).toBe("fallback");
  });

  it("explains a rate limit instead of blaming the file", () => {
    // slowapi answers `{error: …}`; our demo quota answers with a `detail`.
    expect(
      apiErrorMessage(
        axiosError(429, { error: "Rate limit exceeded: 30 per 1 minute" }),
        "Bad file.",
      ),
    ).toMatch(/Too many requests/);
    expect(
      apiErrorMessage(
        axiosError(429, { detail: "The demo's daily limit of AI actions has been reached." }),
        "x",
      ),
    ).toBe("The demo's daily limit of AI actions has been reached.");
  });
});

describe("withJsonErrorBody", () => {
  it("turns a Blob error body back into JSON so the detail is readable", async () => {
    const err = axiosError(
      422,
      new Blob([JSON.stringify({ detail: "Templates may use {{placeholders}} only." })]),
    );
    const caught = await withJsonErrorBody(Promise.reject(err)).catch((e: unknown) => e);
    expect(apiErrorMessage(caught, "fallback")).toBe("Templates may use {{placeholders}} only.");
  });

  it("leaves a non-JSON Blob alone (the fallback applies)", async () => {
    const err = axiosError(502, new Blob(["<html>Bad gateway</html>"]));
    const caught = await withJsonErrorBody(Promise.reject(err)).catch((e: unknown) => e);
    expect(apiErrorMessage(caught, "fallback")).toBe("fallback");
  });
});
