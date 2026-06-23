import { z } from "zod";

export function createCursorPageSchema<T extends z.ZodTypeAny>(itemSchema: T) {
  return z.object({
    items: z.array(itemSchema),
    next_cursor: z.string().nullable(),
    total: z.number().int().nonnegative().optional(),
  });
}

export interface CursorPage<T> {
  items: T[];
  nextCursor: string | null;
  total?: number;
}

