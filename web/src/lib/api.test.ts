// @vitest-environment jsdom
// Unit tests for the lib/api fetch wrapper. We mock global.fetch and assert
// on the request init that our wrapper produces.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, auth, readCsrfCookie } from "./api";

function mockFetchOk(payload: unknown, init: { status?: number } = {}) {
  const body = JSON.stringify(payload);
  global.fetch = vi.fn(async () =>
    new Response(body, {
      status: init.status ?? 200,
      headers: { "Content-Type": "application/json" },
    }),
  ) as unknown as typeof fetch;
}

beforeEach(() => {
  // Wipe localStorage + cookies between tests.
  window.localStorage.clear();
  document.cookie.split(";").forEach((c) => {
    const name = c.split("=")[0]?.trim();
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api wrapper", () => {
  it("sends X-Role / X-Actor + credentials:include on GET", async () => {
    mockFetchOk({ items: [], total: 0, page: 1, page_size: 20 });
    await api.listRuns(1, 20);
    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>;
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/dashboard/runs?page=1&page_size=20");
    expect(init.credentials).toBe("include");
    expect(init.headers).toMatchObject({ "X-Role": "viewer" });
    // CSRF must NOT be sent on safe methods.
    expect(init.headers).not.toHaveProperty("X-CSRF-Token");
  });

  it("attaches X-CSRF-Token from the cookie on POST", async () => {
    document.cookie = "proline_csrf=abc123.def; path=/";
    expect(readCsrfCookie()).toBe("abc123.def");
    mockFetchOk({ actor: "u@x", role: "viewer" });
    await auth.login({ email: "u@x", password: "p", role: "viewer" });
    const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>;
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(init.headers["X-CSRF-Token"]).toBe("abc123.def");
    expect(init.credentials).toBe("include");
  });

  it("throws ApiError with parsed envelope on 4xx", async () => {
    global.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({
          error_code: "FORBIDDEN",
          message: "nope",
          mcp_context_id: null,
          retryable: false,
        }),
        { status: 403, headers: { "Content-Type": "application/json" } },
      ),
    ) as unknown as typeof fetch;

    await expect(api.getRun("x")).rejects.toMatchObject({
      name: "ApiError",
      status: 403,
    });
    try {
      await api.getRun("x");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      expect((e as ApiError).envelope?.error_code).toBe("FORBIDDEN");
    }
  });
});
