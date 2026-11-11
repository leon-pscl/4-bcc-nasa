import { z } from 'zod'

export const CalendarSchema = z.object({
  years: z.array(z.number()),
  values: z.array(z.array(z.number().nullable())),
  monthly_median: z.array(z.number()),
  anomaly: z.array(z.array(z.number().nullable())),
})
export type Calendar = z.infer<typeof CalendarSchema>
