/** Typed client for the FastAPI service. The API decides who can see what; this only carries the request. */

export type Role = "admin" | "supervisor" | "clerk";

export type Me = {
  id: string;
  email: string;
  memberships: { organization_id: string; role: Role }[];
};

export type Organization = { id: string; name: string; plan: string; role: Role; approval_steps: Role[]; retention_days: number | null };

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
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

  const response = await (context.fetchImpl ?? fetch)(`${context.baseUrl}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!response.ok) throw new ApiError(response.status);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const getMe = (context: ApiContext) => request<Me>(context, "/v1/me");

export const getOrganization = (context: ApiContext) => request<Organization>(context, "/v1/organization");

export type Usage = {
  plan: string;
  month: string;
  limit: number | null;
  remaining: number | null;
  documents: number;
  model_calls: number;
  input_tokens: number;
  output_tokens: number;
};

export const getUsage = (context: ApiContext) => request<Usage>(context, "/v1/usage");

export const listMembers = (context: ApiContext) => request<Member[]>(context, "/v1/organization/members");

export type AuditEvent = {
  actor_id: string | null;
  action: string;
  target: string | null;
  request_id: string | null;
  created_at: string;
};

export const listAuditEvents = (context: ApiContext, limit = 50) =>
  request<AuditEvent[]>(context, `/v1/audit-events?limit=${limit}`);

export const renameOrganization = (context: ApiContext, name: string) =>
  request<{ id: string; name: string }>(context, "/v1/organization", {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });

export type Invitation = { id: string; email: string; role: Role; expires_at: string; expired: boolean };

export const listInvitations = (context: ApiContext) => request<Invitation[]>(context, "/v1/organization/invitations");

export const inviteMember = (context: ApiContext, email: string, role: Role) =>
  request<Invitation>(context, "/v1/organization/invitations", {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });

export const cancelInvitation = (context: ApiContext, id: string) =>
  request<void>(context, `/v1/organization/invitations/${encodeURIComponent(id)}`, { method: "DELETE" });

export type MyInvitation = { id: string; organization_name: string; invited_by: string | null; role: Role; expires_at: string };

export const listMyInvitations = (context: ApiContext) => request<MyInvitation[]>(context, "/v1/invitations");

export const acceptInvitation = (context: ApiContext, id: string) =>
  request<{ organization_id: string; role: Role }>(context, `/v1/invitations/${encodeURIComponent(id)}/accept`, { method: "POST" });

export const declineInvitation = (context: ApiContext, id: string) =>
  request<void>(context, `/v1/invitations/${encodeURIComponent(id)}/decline`, { method: "POST" });

export const changeRole = (context: ApiContext, userId: string, role: Role) =>
  request<{ user_id: string; role: Role }>(context, `/v1/organization/members/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    body: JSON.stringify({ role }),
  });

export const removeMember = (context: ApiContext, userId: string) =>
  request<void>(context, `/v1/organization/members/${encodeURIComponent(userId)}`, { method: "DELETE" });

export type Shipment = { id: string; reference: string; status: string; created_at: string | null };

export type ShipmentDetail = Shipment & {
  documents: { id: string; document_type: string | null; processing_status: string; page_count: number | null }[];
  jobs: { id: string; status: string }[];
};

export type JobDocument = {
  id: string;
  document_type: string | null;
  fields: Record<string, string | number | null>;
  quantity_unit: string | null;
};

export type Job = {
  id: string;
  shipment_id: string;
  status: string;
  attempts: number;
  error_class: string | null;
  timings_ms: Record<string, number> | null;
  entity_counts: Record<string, number> | null;
  check: { status: string; reason: string } | null;
  config_version: string | null;
  documents: JobDocument[];
};

export type JobRow = {
  id: string;
  shipment_id: string;
  reference: string;
  status: string;
  check_status: string | null;
  error_class: string | null;
  attempts: number;
  created_at: string | null;
  finished_at: string | null;
};

export type ExceptionItem = {
  job_id: string;
  shipment_id: string;
  reference: string;
  job_status: string;
  error_class: string | null;
  check_status: string | null;
  reason: string | null;
  created_at: string | null;
  approval: { required: number; approved: number; next_role: Role; submitted: boolean; can_act: boolean; is_last_step: boolean };
  history: { id: string; action: string; reason: string; created_at: string | null }[];
};

export type Analytics = {
  shipments: number;
  jobs_by_status: Record<string, number>;
  checks_by_status: Record<string, number>;
  open_exceptions: number;
  waiting_for_you: number;
};

export type Observability = {
  jobs_measured: number;
  average_latency_ms: number;
  vision_fallback_rate: number;
  latest: {
    job_id: string;
    job_status: string;
    check_status: string | null;
    error_class: string | null;
    timings_ms: Record<string, number>;
    entity_counts: Record<string, number>;
  } | null;
  average_stage_ms: Record<string, number>;
  entities_by_type: Record<string, number>;
  outcomes: Record<string, number>;
  checks_by_status: Record<string, number>;
};

export type ListFilters = { limit?: number; q?: string; status?: string };

function filterQuery({ limit = 50, q, status }: ListFilters): string {
  const query = new URLSearchParams({ limit: String(limit) });
  if (q?.trim()) query.set("q", q.trim());
  if (status) query.set("status", status);
  return query.toString();
}

export const listShipments = (context: ApiContext, filters: ListFilters = {}) =>
  request<Shipment[]>(context, `/v1/shipments?${filterQuery(filters)}`);

export const listJobs = (context: ApiContext, filters: ListFilters = {}) => request<JobRow[]>(context, `/v1/jobs?${filterQuery(filters)}`);

export const getShipment = (context: ApiContext, id: string) =>
  request<ShipmentDetail>(context, `/v1/shipments/${encodeURIComponent(id)}`);

export const createShipment = (context: ApiContext, reference: string) =>
  request<Shipment>(context, "/v1/shipments", { method: "POST", body: JSON.stringify({ reference }) });

export const uploadDocument = (context: ApiContext, shipmentId: string, file: Blob) => {
  const body = new FormData();
  body.set("file", file, "upload"); // the real filename stays out of the request
  return request<{ id: string }>(context, `/v1/shipments/${encodeURIComponent(shipmentId)}/documents`, { method: "POST", body });
};

export const startJob = (context: ApiContext, shipmentId: string, idempotencyKey: string) =>
  request<{ id: string; status: string }>(context, `/v1/shipments/${encodeURIComponent(shipmentId)}/jobs`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
  });

export const getJob = (context: ApiContext, id: string) => request<Job>(context, `/v1/jobs/${encodeURIComponent(id)}`);

export const listExceptions = (context: ApiContext) => request<ExceptionItem[]>(context, "/v1/exceptions");

export const addReview = (
  context: ApiContext,
  jobId: string,
  review: { action: "resolve" | "follow_up"; reason: string; corrected_quantity: number | null },
) => request<{ id: string }>(context, `/v1/jobs/${encodeURIComponent(jobId)}/reviews`, { method: "POST", body: JSON.stringify(review) });

export const submitForApproval = (context: ApiContext, jobId: string, reason: string) =>
  request<{ id: string }>(context, `/v1/jobs/${encodeURIComponent(jobId)}/submit`, { method: "POST", body: JSON.stringify({ reason }) });

export const setApprovalSteps = (context: ApiContext, steps: Role[]) =>
  request<{ approval_steps: Role[] }>(context, "/v1/organization/approval-steps", { method: "PATCH", body: JSON.stringify({ steps }) });

export type ApiKey = { id: string; name: string; prefix: string; created_at: string | null; last_used_at: string | null; revoked_at: string | null };
export type Webhook = { id: string; url: string; created_at: string | null };
export type Delivery = { id: string; endpoint_id: string; job_id: string; status: string; attempts: number; response_code: number | null; created_at: string | null };

export const listApiKeys = (context: ApiContext) => request<ApiKey[]>(context, "/v1/api-keys");

export const createApiKey = (context: ApiContext, name: string) =>
  request<ApiKey & { key: string }>(context, "/v1/api-keys", { method: "POST", body: JSON.stringify({ name }) });

export const rotateApiKey = (context: ApiContext, id: string) =>
  request<ApiKey & { key: string }>(context, `/v1/api-keys/${encodeURIComponent(id)}/rotate`, { method: "POST" });

export const revokeApiKey = (context: ApiContext, id: string) =>
  request<void>(context, `/v1/api-keys/${encodeURIComponent(id)}`, { method: "DELETE" });

export const listWebhooks = (context: ApiContext) => request<Webhook[]>(context, "/v1/webhooks");

export const addWebhook = (context: ApiContext, url: string) =>
  request<Webhook & { secret: string }>(context, "/v1/webhooks", { method: "POST", body: JSON.stringify({ url }) });

export const removeWebhook = (context: ApiContext, id: string) =>
  request<void>(context, `/v1/webhooks/${encodeURIComponent(id)}`, { method: "DELETE" });

export const listDeliveries = (context: ApiContext) => request<Delivery[]>(context, "/v1/webhooks/deliveries");

export type Trends = {
  days: number;
  daily: { date: string; jobs: number; mismatches: number; manual_review: number; failed: number }[];
  suppliers: { name: string; shipments: number; mismatches: number }[];
  checks: number;
  corrected_checks: number;
};

export const getTrends = (context: ApiContext, days = 30) => request<Trends>(context, `/v1/analytics/trends?days=${days}`);

export const setRetention = (context: ApiContext, days: number | null) =>
  request<{ retention_days: number | null }>(context, "/v1/organization/retention", { method: "PATCH", body: JSON.stringify({ days }) });

export type IntakeItem = {
  id: string;
  batch_id: string;
  status: string;
  document_type: string | null;
  reference: string | null;
  reason: string | null;
  shipment_id: string | null;
  created_at: string | null;
};

export const listIntake = (context: ApiContext) => request<IntakeItem[]>(context, "/v1/intake");

export const uploadBatch = (context: ApiContext, files: Blob[]) => {
  const body = new FormData();
  for (const file of files) body.append("files", file, "upload"); // real filenames stay out of the request
  return request<{ batch_id: string; files: number }>(context, "/v1/intake", { method: "POST", body });
};

export const assignIntake = (context: ApiContext, id: string, reference: string) =>
  request<IntakeItem>(context, `/v1/intake/items/${encodeURIComponent(id)}/assign`, { method: "POST", body: JSON.stringify({ reference }) });

export const discardIntake = (context: ApiContext, id: string) =>
  request<void>(context, `/v1/intake/items/${encodeURIComponent(id)}`, { method: "DELETE" });

export const getAnalytics = (context: ApiContext) => request<Analytics>(context, "/v1/analytics/summary");

export const getObservability = (context: ApiContext) => request<Observability>(context, "/v1/observability/summary");

export const createOrganization = (context: ApiContext, name: string) =>
  request<Pick<Organization, "id" | "name" | "role">>(context, "/v1/organizations", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
