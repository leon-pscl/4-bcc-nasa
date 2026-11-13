import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import {
  CalendarResponseSchema, SummaryResponseSchema, MapResponseSchema,
  HotspotsResponseSchema, CoverageResponseSchema, MethodsResponseSchema,
} from './api/schemas';

const mocks: [string, unknown][] = [
  ['api_calendar.json', CalendarResponseSchema],
  ['api_summary.json', SummaryResponseSchema],
  ['api_map.json', MapResponseSchema],
  ['api_hotspots.json', HotspotsResponseSchema],
  ['api_coverage.json', CoverageResponseSchema],
  ['api_methods.json', MethodsResponseSchema],
];

describe('contract: mock files parse with schemas', () => {
  for (const [file, schema] of mocks) {
    it(file, () => {
      const p = path.join(process.cwd(), 'public', 'mock', file);
      const data = JSON.parse(fs.readFileSync(p, 'utf8'));
      const res = schema.safeParse(data);
      expect(res.success).toBe(true);
    });
  }
});