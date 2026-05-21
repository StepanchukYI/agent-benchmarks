const DEFAULT_BASE_URL = "http://localhost:8000/api/v1";

function getBaseUrl(): string {
  return import.meta.env.AB_API_BASE_URL ?? DEFAULT_BASE_URL;
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const base = getBaseUrl().replace(/\/$/, "");
  const suffix = path.startsWith("/") ? path : `/${path}`;
  const response = await fetch(`${base}${suffix}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`API ${response.status} ${response.statusText} for ${suffix}`);
  }
  return response;
}
