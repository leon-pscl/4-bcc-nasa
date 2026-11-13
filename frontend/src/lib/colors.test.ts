import { describe, it, expect } from 'vitest';
import { textOn } from './colors';

describe('colors', () => {
  it('textOn', () => {
    expect(textOn('#e31a1c')).toBe('#ffffff');
    expect(textOn('#ffffb2')).toBe('#0f0f0f');
  });
});