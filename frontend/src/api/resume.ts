import { apiRequest } from "./client";
import { ResumeDataDtoSchema, ResumeDataModel } from "../schemas/resume";
import { mapResumeDto } from "../mappers/resume";

export async function getResume(signal?: AbortSignal): Promise<ResumeDataModel> {
  const dto = await apiRequest("/learning/resume", {
    method: "GET",
    schema: ResumeDataDtoSchema,
    signal,
  });
  return mapResumeDto(dto);
}
