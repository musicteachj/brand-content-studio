// Global test setup (vitest `setupFiles`): jest-dom matchers + React Testing
// Library auto-cleanup. MSW is started per flow-test file (see test/msw/lifecycle)
// so it never intercepts the legacy createRoot tests that mock the api directly.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// No-op for the createRoot tests (they own their containers); unmounts RTL renders.
afterEach(() => cleanup());
