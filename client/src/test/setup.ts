// Global test setup (vitest `setupFiles`): jest-dom matchers + React Testing
// Library auto-cleanup. MSW is started per flow-test file (see test/msw/lifecycle)
// so it never intercepts the legacy createRoot tests that mock the api directly.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// No-op for the createRoot tests (they own their containers); unmounts RTL renders.
afterEach(() => cleanup());

// jsdom has no matchMedia. Default to a wide desktop window that never changes;
// a test that cares about width stubs its own (see SideNav.test.tsx). Some test
// files run in Node, with no window at all.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (media: string) =>
    ({
      matches: false,
      media,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}
