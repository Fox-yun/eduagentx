import { z } from "zod";

export const UserDtoSchema = z.object({
  user_id: z.string(),
  display_name: z.string(),
  email: z.string().email(),
  email_verified: z.boolean(),
  onboarding_completed: z.boolean(),
  status: z.enum(["pending_verification", "active", "locked", "disabled"]),
  avatar_url: z.string().optional().nullable(),
  timezone: z.string().optional().nullable(),
});

export type UserDto = z.infer<typeof UserDtoSchema>;

export interface UserModel {
  id: string;
  displayName: string;
  email: string;
  emailVerified: boolean;
  onboardingCompleted: boolean;
  status: "pending_verification" | "active" | "locked" | "disabled";
  avatarUrl?: string | null;
  timezone?: string | null;
}

export const RegisterResponseSchema = z.discriminatedUnion("next_step", [
  z.object({
    next_step: z.literal("verify_email"),
    user: UserDtoSchema,
  }),
  z.object({
    next_step: z.literal("login"),
    user: UserDtoSchema.nullable().optional(),
  }),
]);

export type RegisterResponseDto = z.infer<typeof RegisterResponseSchema>;

export interface RegisterResultModel {
  nextStep: "verify_email" | "login";
  user: UserModel | null;
}

