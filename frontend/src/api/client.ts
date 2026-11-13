import { z } from 'zod';
import { ApiErrorSchema } from './schemas';

export class ApiError extends Error {
  status: number;
  field?: string;
  constructor(status: number, message: string, field?: string) {
    super(message);
    this.status = status;
    this.field = field;
  }
}

const mockMode = () => {
  if (typeof window === 'undefined') return false;
  return new URLSearchParams(window.location.search).get('mock') === '1'
    || import.meta.env.VITE_USE_MOCKS === 'true';
};

export async function apiFetch<T>(key: string, url: string, schema: z.ZodType<T>): Promise<T> {
  if (mockMode()) {
    const res = await fetch(`/mock/api_${key}.json`);
    if (!res.ok) throw new ApiError(res.status, 'mock not found');
    const data = await res.json();
    return schema.parse(data);
  }
  const res = await fetch(url);
  if (!res.ok) {
    let message = res.statusText;
    let field: string | undefined;
    try {
      const body = await res.json();
      const parsed = ApiErrorSchema.safeParse(body);
      if (parsed.success) { message = parsed.data.error; field = parsed.data.field; }
    } catch { /* ignore */ }
    throw new ApiError(res.status, message, field);
  }
  const data = await res.json();
  return schema.parse(data);
}