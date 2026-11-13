import { z } from 'zod';

export const AreaQuerySchema = z.object({
  bbox: z.array(z.number()).length(4).optional(),
  point: z.array(z.number()).length(2).optional(),
  radius_km: z.number().optional(),
  start: z.string(),
  end: z.string(),
  area_km2: z.number().optional(),
});

export const CalendarResponseSchema = z.object({
  query: AreaQuerySchema,
  unit: z.string(),
  years: z.array(z.number()),
  values: z.array(z.array(z.number().nullable())),
  partial: z.object({ year: z.number(), month: z.number(), through_day: z.number() }).nullable(),
  monthly_median: z.array(z.number()),
  monthly_p25: z.array(z.number()),
  monthly_p75: z.array(z.number()),
  anomaly: z.array(z.array(z.number().nullable())),
  anomaly_pct: z.array(z.array(z.number().nullable())),
  annual_totals: z.array(z.number()),
  partial_years: z.array(z.number()),
  baseline_years: z.array(z.number()),
  baseline_warning: z.string().nullable(),
  coverage_warning: z.string().nullable(),
  synthetic: z.boolean(),
  data_version: z.string(),
});

export const SummaryResponseSchema = z.object({
  total: z.number(),
  peak_month: z.object({ year: z.number(), month: z.number(), value: z.number() }).nullable(),
  peak_year: z.object({ year: z.number(), value: z.number() }).nullable(),
  current_month: z.object({
    year: z.number(), month: z.number(), through_day: z.number(), value: z.number(),
    median_same_span: z.number(), pct_vs_median: z.number(),
  }).nullable(),
  latest_data_date: z.string(),
  synthetic: z.boolean(),
  data_version: z.string(),
});

export const MapCellSchema = z.object({ lat: z.number(), lon: z.number(), value: z.number() });
export const MapResponseSchema = z.object({
  grid_deg: z.number(),
  aggregated_to: z.number().nullable(),
  cells: z.array(MapCellSchema),
  data_version: z.string().optional(),
});

export const HotspotRowSchema = z.object({
  date_local: z.string(),
  acq_time_utc: z.string().optional(),
  time_utc: z.string().optional(),
  latitude: z.number(),
  longitude: z.number(),
  confidence: z.string(),
  frp: z.number(),
  daynight: z.string(),
  sensor: z.string().optional(),
  platform: z.string().optional(),
  processing: z.string().optional(),
}).passthrough();

export const HotspotsResponseSchema = z.object({
  page: z.number(),
  page_size: z.number(),
  total: z.number(),
  rows: z.array(HotspotRowSchema),
  data_version: z.string().optional(),
});

export const CoverageRegionSchema = z.object({
  name: z.string(),
  label: z.string(),
  bbox: z.array(z.number()).length(4),
  countries: z.array(z.string()),
  start: z.string(),
  end: z.string(),
  platforms: z.array(z.string()),
  latest_date: z.string(),
  synthetic: z.boolean(),
});

export const StarterAreaSchema = z.object({
  name: z.string(),
  label: z.string(),
  region: z.string(),
  bbox: z.array(z.number()).length(4),
});

export const CoverageResponseSchema = z.object({
  regions: z.array(CoverageRegionSchema),
  starter_areas: z.array(StarterAreaSchema),
  data_version: z.string(),
});

export const MethodsResponseSchema = z.object({
  region: z.string(),
  calibration: z.object({
    k_median: z.number(),
    k_min: z.number(),
    k_max: z.number(),
    count_per_level: z.record(z.number()),
  }).passthrough(),
  validation: z.object({
    calibration_years: z.object({ years: z.array(z.number()), metrics: z.any() }),
    validation_years: z.object({ years: z.array(z.number()), metrics: z.any() }),
  }).passthrough(),
  data_version: z.string().optional(),
});

export const ApiErrorSchema = z.object({ error: z.string(), field: z.string().optional() });

export type CalendarResponse = z.infer<typeof CalendarResponseSchema>;
export type SummaryResponse = z.infer<typeof SummaryResponseSchema>;
export type MapResponse = z.infer<typeof MapResponseSchema>;
export type HotspotsResponse = z.infer<typeof HotspotsResponseSchema>;
export type CoverageResponse = z.infer<typeof CoverageResponseSchema>;
export type MethodsResponse = z.infer<typeof MethodsResponseSchema>;