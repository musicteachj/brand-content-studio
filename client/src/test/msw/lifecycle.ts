import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server";

/** Call at the top of a flow-test module to start/stop the MSW server around it.
 *  Only `/api/*` requests are enforced (an unhandled one is a real contract gap);
 *  incidental asset loads (fonts, images) are ignored. */
export function setupMswServer() {
  beforeAll(() =>
    server.listen({
      onUnhandledRequest(request, print) {
        if (new URL(request.url).pathname.startsWith("/api/")) print.error();
      },
    }),
  );
  afterEach(() => server.resetHandlers());
  afterAll(() => server.close());
}
