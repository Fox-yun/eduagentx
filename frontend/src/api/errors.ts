import type { ZodIssue } from "zod";

export class ApiError extends Error {
  status: number;
  code?: string;
  details?: unknown;
  requestId?: string;

  constructor(message: string, status: number, code?: string, details?: unknown, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

export class ApiSchemaError extends Error {
  issues: ZodIssue[];
  endpoint: string;

  constructor(issues: ZodIssue[], endpoint: string) {
    super("服务返回的数据格式不正确");
    this.name = "ApiSchemaError";
    this.issues = issues;
    this.endpoint = endpoint;
    Object.setPrototypeOf(this, ApiSchemaError.prototype);
  }
}

export class AuthExpiredError extends Error {
  constructor() {
    super("认证已过期，请重新登录");
    this.name = "AuthExpiredError";
    Object.setPrototypeOf(this, AuthExpiredError.prototype);
  }
}
