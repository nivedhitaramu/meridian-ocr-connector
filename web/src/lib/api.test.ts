import { describe, expect, it, vi } from "vitest";

import { ApiError, createOrganization, getMe, getOrganization } from "./api";

function respond(status: number, body: unknown = {}) {
  return vi.fn(async () => new Response(JSON.stringify(body), { status }));
}

const context = (fetchImpl: typeof fetch, extra = {}) => ({
  baseUrl: "http://api.test",
  token: "signed-token",
  fetchImpl,
  ...extra,
});

function sent(mock: ReturnType<typeof respond>) {
  const [url, init] = mock.mock.calls[0] as unknown as [string, RequestInit];
  return { url, init, headers: new Headers(init.headers) };
}

describe("api client", () => {
  it("sends the signed-in user's token", async () => {
    const mock = respond(200, { id: "1", email: "a@example.com", memberships: [] });
    await getMe(context(mock));
    const { url, headers } = sent(mock);
    expect(url).toBe("http://api.test/v1/me");
    expect(headers.get("Authorization")).toBe("Bearer signed-token");
  });

  it("sends no Authorization header without a token", async () => {
    const mock = respond(200);
    await getMe(context(mock, { token: null }));
    expect(sent(mock).headers.has("Authorization")).toBe(false);
  });

  it("picks an organization with the header", async () => {
    const mock = respond(200);
    await getOrganization(context(mock, { organizationId: "org-1" }));
    expect(sent(mock).headers.get("X-Organization-Id")).toBe("org-1");
  });

  it("never sends an organization ID in a request body", async () => {
    const mock = respond(201, { id: "1", name: "Fictional Org", role: "admin" });
    await createOrganization(context(mock, { organizationId: "org-1" }), "Fictional Org");
    expect(JSON.parse(sent(mock).init.body as string)).toEqual({ name: "Fictional Org" });
  });

  it.each([401, 403, 404, 500])("turns a %i into an ApiError with that status", async (status) => {
    await expect(getOrganization(context(respond(status)))).rejects.toMatchObject({
      name: ApiError.name,
      status,
    });
  });

  it("never caches, because responses depend on who is signed in", async () => {
    const mock = respond(200);
    await getMe(context(mock));
    expect(sent(mock).init.cache).toBe("no-store");
  });
});
