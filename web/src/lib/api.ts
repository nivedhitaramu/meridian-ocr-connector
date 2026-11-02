/** Typed client for the FastAPI service. The API decides who can see what; this only carries the request. */

export type Role = "admin" | "supervisor" | "clerk";

export type Me = {
  id: string;
  email: string;
  memberships: { organization_id: string; role: Role }[];
};

export type Organization = { id: string; name: string; plan: string; role: Role };

export type Member = { user_id: string; email: string; role: Role };

export class ApiError extends Error {
  constructor(readonly status: number) {
    super(`API request failed with status ${status}`);
    this.name = "ApiError";
  }
}

export type ApiContext = {
  baseUrl: string;
  token: string | null;
  organizationId?: string;
  fetchImpl?: typeof fetch;
};

async function request<T>(context: ApiContext, path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (context.token) headers.set("Authorization", `Bearer ${context.token}`);
  if (context.organizationId) headers.set("X-Organization-Id", context.organizationId);
  if (init.body) headers.set("Content-Type", "application/json");

  const response = await (context.fetchImpl ?? fetch)(`${context.baseUrl}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!response.ok) throw new ApiError(response.status);
  return (await response.json()) as T;
}

export const getMe = (context: ApiContext) => request<Me>(context, "/v1/me");

export const getOrganization = (context: ApiContext) => request<Organization>(context, "/v1/organization");

export const listMembers = (context: ApiContext) => request<Member[]>(context, "/v1/organization/members");

export const createOrganization = (context: ApiContext, name: string) =>
  request<Pick<Organization, "id" | "name" | "role">>(context, "/v1/organizations", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
