export const CSRF_COOKIE_NAME =
  (import.meta.env.VITE_CSRF_COOKIE_NAME as string) || "csrftoken";

export const CSRF_HEADER_NAME =
  (import.meta.env.VITE_CSRF_HEADER_NAME as string) || "X-CSRF-Token";

export function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp("(^| )" + CSRF_COOKIE_NAME + "=([^;]*)"));
  if (match) return decodeURIComponent(match[2]);
  return null;
}

export function shouldAddCsrf(method?: string): boolean {
  if (!method) return false;
  const upperMethod = method.toUpperCase();
  return ["POST", "PUT", "PATCH", "DELETE"].includes(upperMethod);
}
