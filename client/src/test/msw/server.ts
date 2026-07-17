import { setupServer } from "msw/node";
import { handlers } from "./handlers";

/** Shared MSW server for the flow tests. Its lifecycle is wired by `useMswServer()`
 *  (see ./lifecycle) so only flow tests intercept the network. */
export const server = setupServer(...handlers);
