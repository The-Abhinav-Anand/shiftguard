type BrandProps = { dark?: boolean };

export function Brand({ dark = false }: BrandProps) {
  return (
    <a className={dark ? 'sg-brand sg-brand--dark' : 'sg-brand'} href="/" aria-label="SHIFTGUARD home">
      <svg className="sg-brand__mark" viewBox="0 0 64 64" aria-hidden="true" focusable="false">
        <path d="M8 22V8h14M42 8h14v14M8 42v14h14M42 56h14V42" className="sg-brand__bracket" />
        <path d="M20 20h28M20 44h28" className="sg-brand__register" />
        <path d="M16 32h28" className="sg-brand__register-shift" />
      </svg>
      <span className="sg-brand__word">SHIFTGUARD</span>
    </a>
  );
}
