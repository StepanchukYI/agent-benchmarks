/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly AB_API_BASE_URL?: string;
  /** Force-prefer mock data over live endpoints. `"1"` to enable. */
  readonly AB_USE_MOCK?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
