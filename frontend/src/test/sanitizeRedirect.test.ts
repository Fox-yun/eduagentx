import { describe, it, expect } from "vitest";
import { sanitizeRedirect } from "../auth/sanitizeRedirect";

describe("sanitizeRedirect Helper", () => {
  it("should accept valid local absolute paths", () => {
    expect(sanitizeRedirect("/learning-paths/a")).toBe("/learning-paths/a");
    expect(sanitizeRedirect("/")).toBe("/");
    expect(sanitizeRedirect("/auth/login?redirect=%2F")).toBe("/auth/login?redirect=%2F");
  });

  it("should reject null or empty values, falling back to root", () => {
    expect(sanitizeRedirect(null)).toBe("/");
    expect(sanitizeRedirect("")).toBe("/");
  });

  it("should reject protocol-relative malicious paths", () => {
    expect(sanitizeRedirect("//evil.example")).toBe("/");
    expect(sanitizeRedirect("///evil.example")).toBe("/");
  });

  it("should reject absolute external urls", () => {
    expect(sanitizeRedirect("https://evil.example")).toBe("/");
    expect(sanitizeRedirect("http://evil.example/learning-paths")).toBe("/");
  });

  it("should reject malicious schemes", () => {
    expect(sanitizeRedirect("javascript:alert(1)")).toBe("/");
    expect(sanitizeRedirect("data:text/html,<html>")).toBe("/");
  });
});
