import { useEffect, type RefObject } from 'react';
import { configureBrandGsap, type BrandGsap } from './brandGsap';

type NetworkInformation = EventTarget & { saveData?: boolean };

export function useBrandMotion(rootRef: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return undefined;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const data = window.matchMedia('(prefers-reduced-data: reduce)');
    const network = (navigator as Navigator & { connection?: NetworkInformation }).connection;
    let cancelled = false;
    let loading = false;
    let failed = false;
    let gsap: BrandGsap | undefined;
    let revertMedia: (() => void) | undefined;
    let syncVisibility: (() => void) | undefined;
    const eligible = () => !motion.matches && !data.matches && network?.saveData !== true;

    const stopMotion = () => {
      revertMedia?.();
      revertMedia = undefined;
      syncVisibility = undefined;
    };

    const startMotion = (api: BrandGsap) => {
      if (cancelled || !eligible() || revertMedia) return;
      const media = api.matchMedia(root);
      revertMedia = () => media.revert();
      media.add('(prefers-reduced-motion: no-preference)', () => {
        const hero = root.querySelector<HTMLElement>('.overview-hero') ?? root;
        const bounds = hero.getBoundingClientRect();
        let heroVisible = bounds.bottom > 0 && bounds.top < window.innerHeight && bounds.right > 0 && bounds.left < window.innerWidth;
        let heroTimeline: ReturnType<BrandGsap['timeline']> | undefined;
        type Reveal = { visible: boolean; timeline?: ReturnType<BrandGsap['timeline']> };
        const rows = new Map<Element, Reveal>(Array.from(root.querySelectorAll<HTMLElement>('[data-reveal]'), (row) => [row, { visible: false }]));
        let rowObserver: IntersectionObserver | undefined;
        let heroObserver: IntersectionObserver | undefined;
        const context = api.context(() => {
          const rule = root.querySelector('.overview-hero .overview-eyebrow > span');
          const copy = root.querySelector('[data-motion="hero-copy"]');
          const figure = root.querySelector('[data-motion="hero-figure"]');
          heroTimeline = api.timeline({ paused: document.hidden || !heroVisible });
          if (rule) heroTimeline.fromTo(rule, { scaleX: 0.08 }, { scaleX: 1, duration: 0.36, ease: 'power2.out' }, 0);
          if (copy) heroTimeline.fromTo(copy, { y: 12, opacity: 0.92 }, { y: 0, opacity: 1, duration: 0.52, ease: 'power2.out' }, 0);
          if (figure) heroTimeline.fromTo(figure, { y: 12, opacity: 0.92 }, { y: 0, opacity: 1, duration: 0.52, ease: 'power2.out' }, 0.07);
        }, root);

        const updateVisibility = () => {
          if (heroTimeline && heroTimeline.totalProgress() < 1) {
            heroTimeline.paused(document.hidden || !heroVisible);
          }
          rows.forEach((state, row) => {
            if (!state.timeline && state.visible && !document.hidden) {
              context.add(() => {
                state.timeline = api.timeline({ onComplete: () => rowObserver?.unobserve(row) });
                state.timeline.fromTo(row, { y: 16, opacity: 0.88 }, { y: 0, opacity: 1, duration: 0.4, ease: 'power2.out' });
              });
            }
            if (state.timeline && state.timeline.totalProgress() < 1) {
              state.timeline.paused(document.hidden || !state.visible);
            }
          });
        };
        syncVisibility = updateVisibility;

        if ('IntersectionObserver' in window) {
          heroObserver = new IntersectionObserver((entries) => {
            heroVisible = entries.some((entry) => entry.isIntersecting);
            updateVisibility();
          });
          heroObserver.observe(hero);
          if (rows.size > 0) {
            rowObserver = new IntersectionObserver((entries) => {
              entries.forEach((entry) => {
                const state = rows.get(entry.target);
                if (state) state.visible = entry.isIntersecting;
              });
              updateVisibility();
            }, { rootMargin: '0px 0px -15% 0px', threshold: 0.01 });
            rows.forEach((_state, row) => rowObserver?.observe(row));
          }
        }
        return () => {
          heroObserver?.disconnect();
          rowObserver?.disconnect();
          context.revert();
          rows.clear();
          syncVisibility = undefined;
        };
      });
    };

    const syncMotion = () => {
      if (cancelled) return;
      if (!eligible()) {
        stopMotion();
        return;
      }
      if (revertMedia) {
        syncVisibility?.();
        return;
      }
      if (document.hidden || loading || failed) return;
      if (gsap) {
        startMotion(gsap);
        return;
      }
      loading = true;
      import('gsap').then(({ gsap: api }) => {
        // A chunk can finish after unmount. Bound its idle ticker without
        // attaching resources or interrupting another consumer.
        configureBrandGsap(api);
        loading = false;
        gsap = api;
        if (!cancelled && eligible() && !document.hidden) startMotion(api);
      }).catch(() => {
        loading = false;
        failed = true;
        // Content stays at its authored static position if loading fails.
      });
    };

    motion.addEventListener('change', syncMotion);
    data.addEventListener('change', syncMotion);
    network?.addEventListener('change', syncMotion);
    document.addEventListener('visibilitychange', syncMotion);
    syncMotion();
    return () => {
      cancelled = true;
      motion.removeEventListener('change', syncMotion);
      data.removeEventListener('change', syncMotion);
      network?.removeEventListener('change', syncMotion);
      document.removeEventListener('visibilitychange', syncMotion);
      stopMotion();
    };
  }, [rootRef]);
}
