export type BrandGsap = typeof import('gsap')['gsap'];

export function configureBrandGsap(gsap: BrandGsap) {
  // Used only at optional marketing imports. GSAP's own idle check preserves
  // active timelines and other ticker listeners; do not force shared sleep.
  gsap.config({ autoSleep: 1 });
}
