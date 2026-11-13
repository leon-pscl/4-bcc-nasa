import { describe, it, expect } from 'vitest';
import { formatNumber, formatDate } from './format';

describe('format', () => {
  it('numbers', () => { expect(formatNumber(1234)).toBe('1,234'); });
  it('dates', () => { expect(formatDate('2026-11-12')).toContain('2026'); });
});