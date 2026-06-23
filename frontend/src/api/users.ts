import { apiRequest } from "./client";
import { UserDtoSchema, UserModel } from "../schemas/users";
import { mapUserDto } from "../mappers/users";

export interface OnboardingForm {
  role: "student" | "teacher" | "professional" | "self_learner" | "other";
  learningInterests: string[];
  preferredLanguage: string;
  weeklyHours: number;
  learningPreferences: Array<"project_based" | "theory_first" | "practice_first" | "case_based">;
  useDiagnostic: boolean;
  useKnowledgeBase: boolean;
}

export async function submitOnboarding(values: OnboardingForm): Promise<UserModel> {
  const body = {
    role: values.role,
    learning_interests: values.learningInterests,
    preferred_language: values.preferredLanguage,
    weekly_hours: values.weeklyHours,
    learning_preferences: values.learningPreferences,
    use_diagnostic: values.useDiagnostic,
    use_knowledge_base: values.useKnowledgeBase,
  };

  const dto = await apiRequest("/users/me/onboarding", {
    method: "POST",
    body,
    schema: UserDtoSchema,
  });

  return mapUserDto(dto);
}

export interface ProfileUpdateForm {
  displayName: string;
  avatarUrl?: string;
  timezone?: string;
}

export async function updateProfile(values: ProfileUpdateForm): Promise<UserModel> {
  const body = {
    display_name: values.displayName,
    avatar_url: values.avatarUrl,
    timezone: values.timezone,
  };

  const dto = await apiRequest("/users/me/profile", {
    method: "PUT",
    body,
    schema: UserDtoSchema,
  });

  return mapUserDto(dto);
}

export interface PasswordChangeForm {
  oldPassword?: string;
  newPassword?: string;
}

export async function changePassword(values: PasswordChangeForm): Promise<void> {
  const body = {
    old_password: values.oldPassword,
    new_password: values.newPassword,
  };

  await apiRequest("/users/me/password", {
    method: "PUT",
    body,
  });
}

import { IsoDateTimeSchema } from "../schemas/common";
import { createCursorPageSchema, CursorPage } from "../schemas/pagination";

export interface DeviceSession {
  id: string;
  device: string;
  ipAddress: string;
  lastActiveAt: string;
  isCurrent: boolean;
}

import { z } from "zod";

export const DeviceSessionSchema = z.object({
  id: z.string(),
  device: z.string(),
  ip_address: z.string(),
  last_active_at: IsoDateTimeSchema,
  is_current: z.boolean(),
});

export const DeviceSessionsResponseSchema = createCursorPageSchema(DeviceSessionSchema);

export async function getDeviceSessions(): Promise<CursorPage<DeviceSession>> {
  const dtos = await apiRequest("/users/me/sessions", {
    method: "GET",
    schema: DeviceSessionsResponseSchema,
  });

  return {
    items: dtos.items.map((dto) => ({
      id: dto.id,
      device: dto.device,
      ipAddress: dto.ip_address,
      lastActiveAt: dto.last_active_at,
      isCurrent: dto.is_current,
    })),
    nextCursor: dtos.next_cursor,
    total: dtos.total,
  };
}

export async function revokeDeviceSession(sessionId: string): Promise<void> {
  await apiRequest(`/users/me/sessions/${sessionId}`, {
    method: "DELETE",
  });
}
