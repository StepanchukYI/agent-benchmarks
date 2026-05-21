/**
 * Vitest setup — runs before each test file.
 *
 * Forces `AB_USE_MOCK=1` for the entire test suite. Reason: the hooks in
 * `src/api/hooks.ts` no longer set `placeholderData: mock`, so without this
 * flag tests would see a brief loading state and then a network error
 * (because no server is running under jsdom). With `AB_USE_MOCK=1` every
 * `fetchOrMock` call resolves synchronously to the mock payload, so smoke
 * tests render the data-rich UI without async waiting.
 *
 * If you're adding a test that needs to exercise the loading / empty /
 * error branches, override per-test with `vi.stubEnv("AB_USE_MOCK", "0")`
 * and stub `fetch` accordingly.
 */

import { vi } from "vitest";

vi.stubEnv("AB_USE_MOCK", "1");
