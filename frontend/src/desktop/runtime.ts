import { ApiError } from "../api/errors";

export const isTauriDesktop =
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export interface DesktopConfig {
  serverUrl: string | null;
  downloadDir: string;
  rememberSession: boolean;
  configured: boolean;
  version: string;
}

export interface NativeMultipartPart {
  name: string;
  value?: string;
  filename?: string;
  contentType?: string;
  bytesBase64?: string;
}

export interface NativeApiRequest {
  path: string;
  method: string;
  headers: Record<string, string>;
  body?: string;
  multipart?: NativeMultipartPart[];
  timeoutMs?: number;
}

export interface NativeApiResponse {
  status: number;
  headers: Record<string, string>;
  body: string;
}

interface NativeErrorPayload {
  code?: string;
  message?: string;
  status?: number;
}

async function invokeDesktop<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  const { invoke } = await import("@tauri-apps/api/core");
  try {
    return await invoke<T>(command, args);
  } catch (error) {
    const payload = (typeof error === "object" && error !== null ? error : {}) as NativeErrorPayload;
    const message = payload.message || (error instanceof Error ? error.message : String(error));
    const apiError = new ApiError(message, payload.status ?? 0, payload.code ?? "DESKTOP_ERROR");
    if ((apiError.code || "").startsWith("NETWORK_")) {
      window.dispatchEvent(new CustomEvent("eduagentx:network-error", { detail: apiError }));
    }
    throw apiError;
  }
}

export function getDesktopConfig(): Promise<DesktopConfig> {
  return invokeDesktop<DesktopConfig>("get_desktop_config");
}

export function configureDesktopServer(serverUrl: string): Promise<DesktopConfig> {
  return invokeDesktop<DesktopConfig>("configure_server", { serverUrl });
}

export function chooseDownloadDirectory(): Promise<string | null> {
  return invokeDesktop<string | null>("choose_download_directory");
}

export function resetDownloadDirectory(): Promise<string> {
  return invokeDesktop<string>("reset_download_directory");
}

export function clearDesktopSession(): Promise<void> {
  return invokeDesktop<void>("clear_desktop_session");
}

export function nativeApiRequest(request: NativeApiRequest): Promise<NativeApiResponse> {
  return invokeDesktop<NativeApiResponse>("native_api_request", { request });
}

export interface DesktopDownloadResult {
  path: string;
  filename: string;
}

export function nativeDownloadResource(
  path: string,
  suggestedFilename: string,
  saveAs = false,
): Promise<DesktopDownloadResult | null> {
  return invokeDesktop<DesktopDownloadResult | null>("native_download_resource", {
    path,
    suggestedFilename,
    saveAs,
  });
}

export function cacheDesktopResource(path: string, cacheKey: string, extension: string): Promise<string> {
  return invokeDesktop<string>("cache_resource", { path, cacheKey, extension });
}

export function openDesktopFile(path: string): Promise<void> {
  return invokeDesktop<void>("open_file", { path });
}

export async function toDesktopAssetUrl(path: string): Promise<string> {
  const { convertFileSrc } = await import("@tauri-apps/api/core");
  return convertFileSrc(path);
}

export function showDesktopNotification(title: string, body: string): Promise<void> {
  if (!isTauriDesktop) return Promise.resolve();
  return invokeDesktop<void>("show_system_notification", { title, body });
}

export function completeDesktopBootstrap(): Promise<void> {
  if (!isTauriDesktop) return Promise.resolve();
  return invokeDesktop<void>("complete_desktop_bootstrap");
}

export async function formDataToNativeParts(formData: FormData): Promise<NativeMultipartPart[]> {
  const parts: NativeMultipartPart[] = [];
  for (const [name, value] of formData.entries()) {
    if (value instanceof File) {
      const bytes = new Uint8Array(await value.arrayBuffer());
      let binary = "";
      for (let offset = 0; offset < bytes.length; offset += 0x8000) {
        binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
      }
      parts.push({
        name,
        filename: value.name,
        contentType: value.type || "application/octet-stream",
        bytesBase64: btoa(binary),
      });
    } else {
      parts.push({ name, value: String(value) });
    }
  }
  return parts;
}

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}
