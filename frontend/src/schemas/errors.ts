import { z } from "zod";

export const ApiErrorDtoSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.unknown().optional(),
    request_id: z.string().nullable(),
  }),
});

export type ApiErrorDto = z.infer<typeof ApiErrorDtoSchema>;
