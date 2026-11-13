import { useCoverage } from '../../api/hooks';
import styles from './SyntheticBanner.module.css';

export default function SyntheticBanner() {
  const { data, isLoading } = useCoverage();
  if (isLoading || !data) return null;
  const synthetic = data.regions.some((r) => r.synthetic);
  if (!synthetic) return null;
  return (
    <div role="status" className={styles.banner}>
      <span className={styles.label}>SYNTHETIC DATA</span>{' '}
      Example values for development. These are not real fire counts.
    </div>
  );
}