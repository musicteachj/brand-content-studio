import { QueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/auth";

export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});

// Cached data belongs to one session. Doing this on every token change (sign-out, end demo, a
// 401, a new session) means no sign-out path can forget to, and the next visitor on a shared
// browser never sees the last one's History. `clear()` would drop the cache without telling
// mounted components, which would keep showing the old data; cancelling in-flight fetches and
// then resetting drops the data AND notifies observers (active queries refetch).
useAuthStore.subscribe((state, prev) => {
  if (state.token === prev.token) return;
  void queryClient.cancelQueries();
  void queryClient.resetQueries();
});
