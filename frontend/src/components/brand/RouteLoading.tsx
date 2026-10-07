import { Brand } from './Brand';

type RouteLoadingProps = { label?: string };

export function RouteLoading({ label = 'Loading page' }: RouteLoadingProps) {
  return (
    <main className="sg-route-loading" role="status" aria-live="polite" aria-label={label}>
      <Brand />
      <div className="sg-route-loading__body">
        <span className="sg-route-loading__registers" aria-hidden="true"><i /><i /><i /></span>
        <p>{label}</p>
      </div>
    </main>
  );
}
