import type {
  ApiError,
  ApiErrorBody,
  BatchFileDownload,
  BatchFileExportRequest,
  GarminLoginRequest,
  GarminLoginResponse,
  GarminLogoutResponse,
  MarkdownExportRequest,
  MarkdownExportResponse,
  RecentActivitySummary,
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:3567";
const ACCESS_TOKEN_STORAGE_KEY = "garmin_access_token";

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  return "detail" in value;
}

function getApiMessage(status: number, body: ApiErrorBody | undefined): string {
  if (status === 401) {
    return "Session invalide ou expirée. Reconnecte-toi.";
  }

  if (status === 404) {
    return "Activite introuvable.";
  }

  if (status === 429) {
    return "Garmin limite temporairement les requetes. Reessaie dans quelques minutes.";
  }

  if (status === 502) {
    return "Garmin ne repond pas correctement pour le moment.";
  }

  if (typeof body?.detail === "string") {
    return body.detail;
  }

  if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
    return body.detail[0].msg;
  }

  return "La generation Markdown a echoue.";
}

async function parseErrorBody(response: Response): Promise<ApiErrorBody | undefined> {
  try {
    const payload: unknown = await response.json();
    return isApiErrorBody(payload) ? payload : undefined;
  } catch {
    return undefined;
  }
}

function buildApiError(status: number, body: ApiErrorBody | undefined): ApiError {
  return {
    status,
    message: getApiMessage(status, body),
    details: body,
  };
}

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function getStoredAccessToken(): string | null {
  if (!canUseStorage()) {
    return null;
  }

  return window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
}

export function storeAccessToken(token: string): void {
  if (!canUseStorage()) {
    return;
  }

  window.localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token);
}

export function clearStoredAccessToken(): void {
  if (!canUseStorage()) {
    return;
  }

  window.localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
}

function requireAccessToken(): string {
  const token = getStoredAccessToken();
  if (!token) {
    throw buildApiError(401, { detail: "Missing bearer token." });
  }

  return token;
}

async function authorizedFetch(path: string, init: RequestInit): Promise<Response> {
  const token = requireAccessToken();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init.headers ?? {}),
      Authorization: `Bearer ${token}`,
    },
  });

  if (response.status === 401) {
    clearStoredAccessToken();
  }

  return response;
}

async function postMarkdownExport(
  path: string,
  payload: MarkdownExportRequest,
): Promise<MarkdownExportResponse> {
  const response = await authorizedFetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await parseErrorBody(response);
    throw buildApiError(response.status, body);
  }

  return response.json() as Promise<MarkdownExportResponse>;
}

export async function exportMarkdown(
  payload: MarkdownExportRequest,
): Promise<MarkdownExportResponse> {
  return postMarkdownExport("/api/exports/markdown", payload);
}

export async function exportBatchMarkdown(
  payload: MarkdownExportRequest,
): Promise<MarkdownExportResponse> {
  return postMarkdownExport("/api/exports/batch-markdown", payload);
}

function extractFilename(contentDisposition: string | null): string {
  const match = contentDisposition?.match(/filename="([^"]+)"/);
  return match?.[1] ?? "garmin-batch.zip";
}

export async function exportBatchFile(
  payload: BatchFileExportRequest,
): Promise<BatchFileDownload> {
  const response = await authorizedFetch("/api/exports/batch", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await parseErrorBody(response);
    throw buildApiError(response.status, body);
  }

  return {
    blob: await response.blob(),
    filename: extractFilename(response.headers.get("content-disposition")),
  };
}

export async function loginToGarmin(
  payload: GarminLoginRequest,
): Promise<GarminLoginResponse> {
  const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await parseErrorBody(response);
    throw buildApiError(response.status, body);
  }

  return response.json() as Promise<GarminLoginResponse>;
}

export async function logoutFromGarmin(): Promise<GarminLogoutResponse> {
  const response = await authorizedFetch("/api/auth/logout", {
    method: "POST",
  });

  if (!response.ok) {
    const body = await parseErrorBody(response);
    throw buildApiError(response.status, body);
  }

  return response.json() as Promise<GarminLogoutResponse>;
}

export async function getRecentActivities(): Promise<RecentActivitySummary[]> {
  const response = await authorizedFetch("/api/activities/recent", {
    method: "GET",
  });

  if (!response.ok) {
    const body = await parseErrorBody(response);
    throw buildApiError(response.status, body);
  }

  return response.json() as Promise<RecentActivitySummary[]>;
}
