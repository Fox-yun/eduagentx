import { UserDto, UserModel, RegisterResponseDto, RegisterResultModel } from "../schemas/users";

export function mapUserDto(dto: UserDto): UserModel {
  return {
    id: dto.user_id,
    displayName: dto.display_name,
    email: dto.email,
    emailVerified: dto.email_verified,
    onboardingCompleted: dto.onboarding_completed,
    status: dto.status,
    avatarUrl: dto.avatar_url,
    timezone: dto.timezone,
  };
}

export function mapRegisterResponse(dto: RegisterResponseDto): RegisterResultModel {
  return {
    nextStep: dto.next_step,
    user: dto.user ? mapUserDto(dto.user) : null,
  };
}

