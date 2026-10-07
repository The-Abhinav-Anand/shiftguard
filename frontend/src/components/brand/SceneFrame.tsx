import { useEffect, useRef, useState } from 'react';
import type { ComponentType } from 'react';
import { SceneFallback } from './SceneFallback';
import type { MissingnessChapter } from './SceneFallback';
import type { MissingnessSceneProps } from './MissingnessScene';

type PreferenceState = { reduced: boolean; eligible: boolean; desktop: boolean };
type NetworkInformation = EventTarget & { saveData?: boolean };

const chapterNames: Record<MissingnessChapter, string> = {
  1: 'Inputs',
  2: 'Missing block',
  3: 'Compare evidence',
};

export function SceneFrame() {
  const frameRef = useRef<HTMLElement>(null);
  const [chapter, setChapter] = useState<MissingnessChapter>(1);
  const [preferences, setPreferences] = useState<PreferenceState>({ reduced: false, eligible: false, desktop: false });
  const [nearViewport, setNearViewport] = useState(false);
  const [manualRequest, setManualRequest] = useState(false);
  const [retry, setRetry] = useState(0);
  const [Scene, setScene] = useState<ComponentType<MissingnessSceneProps> | null>(null);
  const [sceneState, setSceneState] = useState<'idle' | 'loading' | 'loaded' | 'ready' | 'failed'>('idle');
  const [paused, setPaused] = useState(false);
  const [unavailableReason, setUnavailableReason] = useState('');
  const attemptedRef = useRef<number | null>(null);

  useEffect(() => {
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const coarse = window.matchMedia('(pointer: coarse)');
    const reducedData = window.matchMedia('(prefers-reduced-data: reduce)');
    const network = (navigator as Navigator & { connection?: NetworkInformation }).connection;
    const read = () => {
      const reduced = motion.matches;
      const saveData = network?.saveData === true || reducedData.matches;
      setPreferences({
        reduced,
        eligible: !reduced && !saveData,
        desktop: window.matchMedia('(min-width: 768px) and (pointer: fine)').matches && !coarse.matches,
      });
    };
    read();
    motion.addEventListener('change', read);
    coarse.addEventListener('change', read);
    reducedData.addEventListener('change', read);
    network?.addEventListener('change', read);
    window.addEventListener('resize', read, { passive: true });
    return () => {
      motion.removeEventListener('change', read);
      coarse.removeEventListener('change', read);
      reducedData.removeEventListener('change', read);
      network?.removeEventListener('change', read);
      window.removeEventListener('resize', read);
    };
  }, []);

  useEffect(() => {
    if (!preferences.eligible || !preferences.desktop || !frameRef.current) return;
    if (!('IntersectionObserver' in window)) {
      setNearViewport(true);
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setNearViewport(true);
        observer.disconnect();
      }
    }, { rootMargin: '120px' });
    observer.observe(frameRef.current);
    return () => observer.disconnect();
  }, [preferences.desktop, preferences.eligible]);

  const requested = preferences.desktop ? nearViewport : manualRequest;
  useEffect(() => {
    if (!requested || !preferences.eligible || attemptedRef.current === retry) return;
    attemptedRef.current = retry;
    let current = true;
    setSceneState('loading');
    setUnavailableReason('');
    import('./MissingnessScene').then((module) => {
      if (!current) return;
      setScene(() => module.MissingnessScene);
      setSceneState('loaded');
    }).catch(() => {
      if (!current) return;
      setScene(null);
      setSceneState('failed');
      setUnavailableReason('The 3D illustration could not be loaded.');
    });
    return () => { current = false; };
  }, [preferences.eligible, requested, retry]);

  useEffect(() => {
    if (preferences.eligible) return;
    attemptedRef.current = null;
    setScene(null);
    setSceneState('idle');
    setManualRequest(false);
    setPaused(false);
  }, [preferences.eligible]);

  useEffect(() => {
    if (preferences.desktop || manualRequest) return;
    if (sceneState === 'loaded' || sceneState === 'ready') {
      attemptedRef.current = null;
      setScene(null);
      setSceneState('idle');
      setPaused(false);
    }
  }, [manualRequest, preferences.desktop, sceneState]);

  const active = sceneState === 'loaded' || sceneState === 'ready';
  const retryScene = () => {
    setScene(null);
    setSceneState('idle');
    setRetry((value) => value + 1);
    setManualRequest(true);
    setNearViewport(true);
  };

  return (
    <figure className="sg-scene" ref={frameRef} aria-labelledby="sg-scene-caption">
      <div className="sg-scene__visual" data-chapter={chapter}>
        <div className={sceneState === 'ready' ? 'sg-scene__fallback sg-scene__fallback--hidden' : 'sg-scene__fallback'}>
          <SceneFallback chapter={chapter} />
        </div>
        {Scene && active && (
          <div className={sceneState === 'ready' ? 'sg-scene__canvas sg-scene__canvas--ready' : 'sg-scene__canvas'}>
            <Scene
              chapter={chapter}
              paused={paused || preferences.reduced}
              onFirstFrame={() => setSceneState('ready')}
              onUnavailable={(reason) => {
                setScene(null);
                setSceneState('failed');
                setUnavailableReason(reason);
              }}
            />
          </div>
        )}
        <span className="sg-scene__coordinate" aria-hidden="true">SG / 01—03</span>
      </div>
      <div className="sg-scene__html-labels" aria-label="Illustration regions">
        <span>Ordinary features</span><span>History inputs</span>
      </div>
      {chapter === 3 && <div className="sg-scene__rail-labels" aria-label="Equal comparison rails"><span>Raw</span><span>Source</span><span>Target</span></div>}
      <div className="sg-scene__controls">
        <div className="sg-scene__chapter-controls" role="group" aria-label="Illustration chapters">
          {([1, 2, 3] as const).map((value) => (
            <button key={value} type="button" aria-label={`${value} ${chapterNames[value]}`} aria-pressed={chapter === value} onClick={() => setChapter(value)}>
              <span>{String(value).padStart(2, '0')}</span>{chapterNames[value]}
            </button>
          ))}
        </div>
        <p className="sg-scene__chapter-status" aria-live="polite">Chapter {chapter}: {chapterNames[chapter]}</p>
      </div>
      <figcaption className="sg-scene__caption" id="sg-scene-caption">
        <span>Concept illustration — not experiment data.</span>
        <span aria-hidden="true">THE MISSINGNESS REGISTER</span>
      </figcaption>
      {sceneState === 'loading' && <p className="sg-scene__status" role="status">Preparing illustration.</p>}
      {sceneState === 'failed' && (
        <p className="sg-scene__status" role="status">
          Static illustration. {unavailableReason || '3D is unavailable.'}
          <button type="button" onClick={retryScene}>Try 3D again</button>
        </p>
      )}
      {sceneState === 'ready' && (
        <button className="sg-scene__pause" type="button" aria-pressed={paused} onClick={() => setPaused((value) => !value)}>
          {paused ? 'Resume illustration' : 'Pause illustration'}
        </button>
      )}
      {!preferences.desktop && preferences.eligible && sceneState === 'idle' && (
        <button className="sg-scene__activate" type="button" onClick={() => setManualRequest(true)}>View 3D illustration</button>
      )}
      {preferences.reduced && <p className="sg-scene__status">Static illustration shown because reduced motion is enabled.</p>}
    </figure>
  );
}
