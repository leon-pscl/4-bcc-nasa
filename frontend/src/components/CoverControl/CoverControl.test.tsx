import { describe, it, expect } from 'vitest';
import { OPTIONS } from './CoverControl';

const API_VALUES = ['all', 'forest', 'farmland', 'other'];

describe('CoverControl', () => {
  it('every CoverControl value is one of the four API values', () => {
    expect(OPTIONS.map((o) => o.id)).toEqual(API_VALUES);
    OPTIONS.forEach((o) => expect(API_VALUES).toContain(o.id));
  });
});
