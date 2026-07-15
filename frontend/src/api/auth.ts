import { z } from "zod";
import { apiRequest } from "./client";
import { UserDtoSchema, UserModel, RegisterResponseSchema, RegisterResultModel } from "../schemas/users";
import { mapUserDto, mapRegisterResponse } from "../mappers/users";
import { ApiError, AuthExpiredError } from "./errors";
import { clearDesktopSession, isTauriDesktop } from "../desktop/runtime";


export const loginFormSchema = z.object({
  email: z.string().email("请输入有效的邮箱地址"),
  password: z.string().min(1, "请输入密码"),
  rememberMe: z.boolean(),
});

export type LoginFormValues = z.infer<typeof loginFormSchema>;

export const registerFormSchema = z
  .object({
    displayName: z
      .string()
      .min(2, "昵称不能少于2个字符")
      .max(40, "昵称不能超过40个字符"),
    email: z.string().email("请输入有效的邮箱地址"),
    password: z.string().min(10, "密码长度必须在10-128个字符之间").max(128),
    confirmPassword: z.string(),
    acceptTerms: z.literal(true, {
      message: "您必须同意服务条款",
    }),
  })
  .refine((data) => data.password === data.confirmPassword, {
    path: ["confirmPassword"],
    message: "两次输入的密码不一致",
  });

export type RegisterFormValues = z.infer<typeof registerFormSchema>;

export async function getCurrentUser(): Promise<UserModel | null> {
  try {
    const dto = await apiRequest("/auth/me", {
      method: "GET",
      schema: UserDtoSchema,
    });
    return mapUserDto(dto);
  } catch (error) {
    if (
      (error instanceof ApiError && error.status === 401) ||
      error instanceof AuthExpiredError
    ) {
      return null;
    }
    throw error;
  }
}

export async function loginUser(values: LoginFormValues): Promise<UserModel | null> {
  const body = {
    email: values.email,
    password: values.password,
    remember_me: values.rememberMe,
  };
  const dto = await apiRequest("/auth/login", {
    method: "POST",
    body,
    schema: UserDtoSchema,
    skipAuthRefresh: true,
  });
  return mapUserDto(dto);
}

export async function registerUser(
  values: Omit<RegisterFormValues, "confirmPassword" | "acceptTerms">
): Promise<RegisterResultModel> {
  const body = {
    display_name: values.displayName,
    email: values.email,
    password: values.password,
    accept_terms: true,
  };
  const dto = await apiRequest("/auth/register", {
    method: "POST",
    body,
    schema: RegisterResponseSchema,
    skipAuthRefresh: true,
  });
  return mapRegisterResponse(dto);
}

export async function logoutUser(): Promise<void> {
  try {
    await apiRequest("/auth/logout", {
      method: "POST",
      skipAuthRefresh: true,
    });
  } finally {
    if (isTauriDesktop) await clearDesktopSession();
  }
}

export async function verifyEmail(token: string): Promise<UserModel | null> {
  const dto = await apiRequest("/auth/verify-email", {
    method: "POST",
    body: { token },
    schema: UserDtoSchema,
    skipAuthRefresh: true,
  });
  return mapUserDto(dto);
}

export async function resendVerification(): Promise<void> {
  await apiRequest("/auth/resend-verification", {
    method: "POST",
    skipAuthRefresh: true,
  });
}

export async function forgotPassword(email: string): Promise<void> {
  await apiRequest("/auth/forgot-password", {
    method: "POST",
    body: { email },
    skipAuthRefresh: true,
  });
}

export async function resetPassword(token: string, password: string): Promise<void> {
  await apiRequest("/auth/reset-password", {
    method: "POST",
    body: { token, password },
    skipAuthRefresh: true,
  });
}
