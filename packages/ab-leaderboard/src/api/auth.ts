/**
 * Auth surface: GitHub OAuth device flow + session token storage.
 *
 * Flow (RFC 8628):
 *   1. GET /auth/github/client-id          → fetch effective client_id
 *   2. POST /auth/github/device-start      → {device_code, user_code, verification_uri, interval, expires_in}
 *   3. Open verification_uri in a new tab; display user_code for the user to enter
 *   4. POST /auth/github/device-poll every `interval` seconds
 *      - 200 {access_token, github_login, expires_at} → success: store token
 *      - 200 {error: "authorization_pending"}         → keep polling
 *      - 200 {error: "slow_down"}                     → bump interval by 5s
 *      - 200 {error: "expired_token" | "access_denied"} → abort
 *
 * The server proxies the GitHub calls and mints its OWN session token (hashed
 * in DB); the device flow we expose here is end-to-end against the server.
 */

import { ApiError, apiFetch, endpoints, setStoredToken } from "./client";

export interface DeviceCodeResponse {
  device_code: string;
  user_code: string;
  verification_uri: string;
  interval: number;
  expires_in: number;
}

export interface DevicePollSuccess {
  access_token: string;
  github_login: string;
  expires_at: string;
}

export interface DevicePollPending {
  error: "authorization_pending" | "slow_down" | "expired_token" | "access_denied";
  [key: string]: unknown;
}

export type DevicePollResponse = DevicePollSuccess | DevicePollPending;

export interface MeResponse {
  id: string;
  github_id: string;
  handle: string;
  avatar_url: string | null;
}

export async function fetchClientId(): Promise<string> {
  const { client_id } = await apiFetch<{ client_id: string }>(endpoints.authClientId());
  return client_id;
}

export async function startDeviceFlow(clientId: string): Promise<DeviceCodeResponse> {
  return apiFetch<DeviceCodeResponse>(endpoints.authDeviceStart(), {
    method: "POST",
    body: JSON.stringify({ client_id: clientId }),
  });
}

export async function pollDeviceFlow(
  clientId: string,
  deviceCode: string,
): Promise<DevicePollResponse> {
  return apiFetch<DevicePollResponse>(endpoints.authDevicePoll(), {
    method: "POST",
    body: JSON.stringify({ client_id: clientId, device_code: deviceCode }),
  });
}

export async function fetchMe(): Promise<MeResponse | null> {
  try {
    return await apiFetch<MeResponse>(endpoints.me());
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return null;
    throw err;
  }
}

/** Drive the full device flow to completion. Resolves with token + login or throws. */
export async function runDeviceFlow(
  onUserCode: (resp: DeviceCodeResponse) => void,
  options: { sleep?: (ms: number) => Promise<void>; signal?: AbortSignal } = {},
): Promise<DevicePollSuccess> {
  const sleep = options.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const clientId = await fetchClientId();
  const code = await startDeviceFlow(clientId);
  onUserCode(code);

  let intervalSec = Math.max(code.interval || 5, 5);
  const deadline = Date.now() + (code.expires_in || 900) * 1000;

  // eslint-disable-next-line no-constant-condition
  while (true) {
    if (options.signal?.aborted) throw new Error("device flow aborted by user");
    if (Date.now() > deadline) throw new Error("device flow expired");
    await sleep(intervalSec * 1000);
    const resp = await pollDeviceFlow(clientId, code.device_code);
    if ("access_token" in resp && typeof resp.access_token === "string" && resp.access_token) {
      const success = resp as DevicePollSuccess;
      setStoredToken(success.access_token);
      return success;
    }
    if ("error" in resp) {
      const err = (resp as DevicePollPending).error;
      if (err === "authorization_pending") continue;
      if (err === "slow_down") {
        intervalSec += 5;
        continue;
      }
      throw new Error(`device flow failed: ${err}`);
    }
  }
}

export function signOut(): void {
  setStoredToken(null);
}
