import { useCoverage } from '../../api/hooks';

export default function SyntheticBanner() {
  const { data } = useCoverage();
  const synthetic = data?.regions?.some((r) => r.synthetic) ?? true;
  if (!synthetic) return null;
  return (
    <div role="status" style={{ background: 'var(--ink)', color: '#fff', fontSize: 13, padding: '9px 32px' }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, letterSpacing: '0.08em' }}>SYNTHETIC DATA</span>{' '}
      Example values for development. These are not real fire counts.
    </div>
  );
}