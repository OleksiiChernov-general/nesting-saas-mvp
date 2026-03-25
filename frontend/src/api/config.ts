declare global {
  interface Window {
    __APP_CONFIG__?: {
      VITE_API_BASE_URL?: string;
    };
  }
}

function defaultApiBaseUrl(): string {
  if (typeof window !== "undefined" && window.location.origin?.startsWith("http")) {
    return window.location.origin;
  }
  return "";
}

const runtimeApiBaseUrl =
  typeof window !== "undefined" ? window.__APP_CONFIG__?.VITE_API_BASE_URL : undefined;

export const API_BASE_URL = (
  runtimeApiBaseUrl ??
  import.meta.env.VITE_API_BASE_URL ??
  defaultApiBaseUrl()
).replace(/\/$/, "");
