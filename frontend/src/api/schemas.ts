import { z } from 'zod';

export const AreaQuerySchema = z.object({
  bbox: z.array(z.number()).length(4).optional(),
  point: z.array(z.number()).length(2).optional(),
  radius_km: z.number().optional(),
  start: z.string(),
  end: z.string(),
  area_km2: z.number().optional(),
  cover: z.string().optional(),
});

export const CalendarResponseSchema = z.object({
  query: AreaQuerySchema,
  unit: z.string(),
  years: z.array(z.number()),
  values: z.array(z.array(z.number().nullable())),
  partial: z.object({ year: z.number(), month: z.number(), through_day: z.number() }).nullable(),
  monthly_median: z.array(z.number().nullable()),
  monthly_p25: z.array(z.number().nullable()),
  monthly_p75: z.array(z.number().nullable()),
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
    median_same_span: z.number().nullable(), pct_vs_median: z.number().nullable(),
    forest_share: z.number().nullable().optional(),
    median_forest_share: z.number().nullable().optional(),
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
  data_version: z.string(),
});

export const HotspotRowSchema = z.object({
  date_local: z.string(),
  acq_datetime_utc: z.string(),
  latitude: z.number(),
  longitude: z.number(),
  confidence_class: z.string(),
  frp: z.number(),
  daynight: z.string(),
  sensor: z.string().optional(),
  platform: z.string().optional(),
  processing: z.string().optional(),
});

export const HotspotsResponseSchema = z.object({
  page: z.number(),
  page_size: z.number(),
  total: z.number(),
  rows: z.array(HotspotRowSchema),
  rows_note: z.string().nullable().optional(),
  data_version: z.string(),
});

export const OutlookAreaQuerySchema = z.object({
  bbox: z.array(z.number()).length(4).optional(),
  point: z.array(z.number()).length(2).optional(),
  radius_km: z.number().optional(),
  area_km2: z.number().optional(),
});

export const OutlookMonthSchema = z.object({
  year: z.number(),
  month: z.number(),
  lead: z.number(),
  model: z.string(),
  expected: z.number(),
  typical_range: z.array(z.number()).nullable(),
  normal_mean: z.number().nullable(),
  normal_median: z.number().nullable(),
  observed_so_far: z.object({ through_day: z.number(), value: z.number() }).nullable(),
  cells_likely: z.number(),
});

export const OutlookTopCellSchema = z.object({
  lat: z.number(),
  lon: z.number(),
  lead: z.number(),
  p_fire: z.number(),
  expected: z.number(),
});

export const OutlookSeasonSchema = z.object({
  normal_median: z.array(z.number()),
  normal_mean: z.array(z.number()),
  peak_month: z.number(),
  busiest_months: z.array(z.number()),
});

export const OutlookSkillSchema = z.object({
  top10_capture_pct: z.number().nullable(),
  brier: z.number().nullable(),
  test_years: z.array(z.number()),
  big_years: z.record(z.string(), z.number().nullable()).optional(),
});

export const OutlookResponseSchema = z.object({
  query: OutlookAreaQuerySchema,
  issued: z.string(),
  latest_data_date: z.string(),
  unit: z.string(),
  grid_deg: z.number(),
  threshold: z.number(),
  months: z.array(OutlookMonthSchema),
  top_cells: z.array(OutlookTopCellSchema),
  season: OutlookSeasonSchema,
  skill: OutlookSkillSchema.nullable(),
  synthetic: z.boolean(),
  data_version: z.string(),
  coverage_warning: z.string().nullable().optional(),
});

export const OutlookMapCellSchema = z.object({
  lat: z.number(),
  lon: z.number(),
  p_fire: z.number(),
  expected: z.number(),
  mean_clim: z.number(),
});

export const OutlookMapResponseSchema = z.object({
  grid_deg: z.number(),
  issued: z.string(),
  target: z.object({ year: z.number(), month: z.number() }),
  model: z.string(),
  cells: z.array(OutlookMapCellSchema),
  data_version: z.string(),
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
  outlook: z.object({ issued: z.string(), targets: z.array(z.string()) }).optional(),
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

const MetricsSchema = z.object({
  pearson_r: z.number(),
  bias_pct: z.number(),
  median_abs_pct_error: z.number(),
  monthly_viirs: z.array(z.number()),
  monthly_modis: z.array(z.number()),
});

export const MethodsResponseSchema = z.object({
  region: z.string(),
  calibration: z.object({
    k_median: z.number(),
    k_min: z.number(),
    k_max: z.number(),
    count_per_level: z.record(z.string(), z.number()),
  }),
  validation: z.object({
    calibration_years: z.object({ years: z.array(z.number()), metrics: MetricsSchema }),
    validation_years: z.object({ years: z.array(z.number()), metrics: MetricsSchema }),
  }),
  grid: z.object({
    cells: z.record(z.string(), z.number()),
    masked_share_of_fire_pct: z.number().nullable(),
  }).optional(),
  outlook: z.object({
    grid_deg: z.number(),
    mask: z.object({
      nonburnable_classes: z.array(z.number()),
      min_burnable_pct: z.number(),
    }),
    threshold: z.number(),
    p_fire_rule: z.string(),
    model: z.string(),
    issued: z.string().nullable(),
    targets: z.array(z.string()),
    skill: OutlookSkillSchema.nullable(),
  }).optional(),
  data_version: z.string(),
});

const NumArr = z.array(z.number().nullable());
const YearMetrics = z.object({ pearson_r: z.number(), bias_pct: z.number() });

export const SeriesResponseSchema = z.object({
  months: z.array(z.object({ year: z.number(), month: z.number() })),
  aqua: NumArr,
  snpp: NumArr,
  noaa20: NumArr,
  noaa21: NumArr,
  aqua_k: z.number(),
  harmonized: NumArr,
  switch_date: z.string(),
  outage_days: z.number().optional(),
  validation: z.object({
    overlap_years: z.array(z.number()),
    pearson_r: z.number(),
    bias_pct: z.number(),
    per_year: z.record(z.string(), YearMetrics),
    note: z.string().optional(),
    fit_years: z.array(z.number()).optional(),
    in_sample: YearMetrics.optional(),
    held_out_aggregate: YearMetrics.optional(),
    typical_year_error_pct: z.number().optional(),
  }),
  data_version: z.string().optional(),
});

export const ApiErrorSchema = z.object({ error: z.string(), field: z.string().optional() });

export type CalendarResponse = z.infer<typeof CalendarResponseSchema>;
export type SummaryResponse = z.infer<typeof SummaryResponseSchema>;
export type MapResponse = z.infer<typeof MapResponseSchema>;
export type HotspotsResponse = z.infer<typeof HotspotsResponseSchema>;
export type CoverageResponse = z.infer<typeof CoverageResponseSchema>;
export type MethodsResponse = z.infer<typeof MethodsResponseSchema>;
export type SeriesResponse = z.infer<typeof SeriesResponseSchema>;
export type OutlookResponse = z.infer<typeof OutlookResponseSchema>;
export type OutlookMapResponse = z.infer<typeof OutlookMapResponseSchema>;