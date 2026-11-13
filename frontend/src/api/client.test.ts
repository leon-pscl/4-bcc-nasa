import { describe, it, expect, vi, afterEach } from 'vitest';
import { apiFetch, ApiError } from './client';
import { z } from 'zod';

const schema = z.object({ ok: z.boolean() });

describe('client', () => {
  afterEach(() => vi.unstubAllGlobals());
  it('non-ok becomes ApiError with status and field', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      json: () => Promise.resolve({ error: 'bad', field: 'start' }),
    }));
    const err = await apiFetch('calendar', '/api/calendar', schema).catch((e) => e as ApiError);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(400);
    expect(err.field).toBe('start');
  });
  it('mock mode reads /mock/api_<name>.json', async () => {
    const prev = window.location.search;
    window.history.replaceState({}, '', '/?mock=1');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ ok: true }) }));
    const res = await apiFetch('calendar', '/api/calendar', schema);
    expect(res).toEqual({ ok: true });
    expect(fetch).toHaveBeenCalledWith('/mock/api_calendar.json');
    window.history.replaceState({}, '', '/' + prev);
  });
});