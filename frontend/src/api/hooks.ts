import { useQuery } from '@tanstack/react-query';
import { apiFetch } from './client';
import {
  CalendarResponseSchema, SummaryResponseSchema, MapResponseSchema,
  HotspotsResponseSchema, CoverageResponseSchema, MethodsResponseSchema, SeriesResponseSchema,
} from './schemas';
import { buildQueryParams, isQueryValid } from './params';
import type { AppState } from '../state/urlState';

export function useCoverage() {
  return useQuery({
    queryKey: ['coverage'],
    queryFn: () => apiFetch('coverage', '/api/coverage', CoverageResponseSchema),
  });
}

export function useQueryParams(state: Pick<AppState, 'area' | 'start' | 'end'> | null | undefined) {
  const { data: coverage } = useCoverage();
  const valid = !!state && isQueryValid(state, coverage);
  const params = valid && state ? buildQueryParams(state) : '';
  return { params, valid, coverage };
}

export function useCalendar(params: string) {
  return useQuery({
    queryKey: ['calendar', params],
    queryFn: () => apiFetch('calendar', `/api/calendar?${params}`, CalendarResponseSchema),
    enabled: params.length > 0,
  });
}

export function useSummary(params: string) {
  return useQuery({
    queryKey: ['summary', params],
    queryFn: () => apiFetch('summary', `/api/summary?${params}`, SummaryResponseSchema),
    enabled: params.length > 0,
  });
}

export function useMap(params: string, month?: string) {
  const q = month ? `${params}&month=${month}` : params;
  return useQuery({
    queryKey: ['map', params, month ?? ''],
    queryFn: () => apiFetch('map', `/api/map?${q}`, MapResponseSchema),
    enabled: params.length > 0,
  });
}

export function useHotspots(params: string, page: number, allSensors: boolean) {
  const q = `${params}&page=${page}&page_size=100&all_sensors=${allSensors ? 1 : 0}`;
  return useQuery({
    queryKey: ['hotspots', params, page, allSensors],
    queryFn: () => apiFetch('hotspots', `/api/hotspots?${q}`, HotspotsResponseSchema),
    enabled: params.length > 0,
  });
}

export function useMethods(region: string) {
  return useQuery({
    queryKey: ['methods', region],
    queryFn: () => apiFetch('methods', `/api/methods?region=${encodeURIComponent(region)}`, MethodsResponseSchema),
    enabled: region.length > 0,
  });
}

export function useSeries(params: string) {
  return useQuery({
    queryKey: ['series', params],
    queryFn: () => apiFetch('series', `/api/series?${params}`, SeriesResponseSchema),
    enabled: params.length > 0,
  });
}