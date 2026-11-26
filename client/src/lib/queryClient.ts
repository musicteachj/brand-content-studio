import { QueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/auth";

export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});

// Cached data belongs to one session. Doing this on every token change (sign-out, end demo, a
// 401, a new session) means no sign-out path can forget to, and the next visitor on a shared
// browser never sees the last one's History. `clear()` and `removeQueries()` drop the cache
// without telling mounted components, which would keep showing the old data. For a new session,
// canceling in-flight fetches and then resetting drops the data AND notifies observers (active
// queries refetch with the new token). On sign-out there is no token to refetch with (each
// query would 401), so the queries are canceled and removed with no refetch. That is safe
// because every session-scoped query lives under RequireAuth, which unmounts when the session
// ends; the only queries outside it (examples, app status) are public.
useAuthStore.subscribe((state, prev) => {
  if (state.token === prev.token) return;
  void queryClient.cancelQueries();
  if (state.token === null) queryClient.removeQueries();
  else void queryClient.resetQueries();
});
