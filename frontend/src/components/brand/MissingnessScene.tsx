import { useEffect, useRef } from 'react';
import type * as ThreeTypes from 'three';
import type { MissingnessChapter } from './SceneFallback';
import { configureBrandGsap } from '../../motion/brandGsap';
import { createSceneFrameMonitor } from '../../motion/sceneFrameMonitor';

export type MissingnessSceneProps = {
  chapter: MissingnessChapter;
  paused: boolean;
  onFirstFrame: () => void;
  onUnavailable: (reason: string) => void;
};

type ThreeModule = typeof import('three');
type Gsap = typeof import('gsap')['gsap'];
type GridPiece = { column: number; row: number; x: number; y: number };
type SceneRuntime = {
  THREE: ThreeModule;
  gsap: Gsap;
  renderer: ThreeTypes.WebGLRenderer;
  scene: ThreeTypes.Scene;
  camera: ThreeTypes.OrthographicCamera;
  group: ThreeTypes.Group;
  ordinary: ThreeTypes.InstancedMesh;
  history: ThreeTypes.InstancedMesh;
  displaced: ThreeTypes.InstancedMesh;
  gaps: ThreeTypes.LineSegments;
  frame: ThreeTypes.LineSegments;
  rails: ThreeTypes.LineSegments;
  pieces: GridPiece[];
  progress: Array<{ value: number }>;
  railProgress: { value: number };
  transform: ThreeTypes.Object3D;
  historyMaterial: ThreeTypes.MeshStandardMaterial;
  displacedMaterials: ThreeTypes.Material[];
  chapterTimeline: ReturnType<Gsap['timeline']> | null;
  pointerTween: ReturnType<Gsap['to']> | null;
  frameRequest: number;
  inView: boolean;
  pageVisible: boolean;
  firstFrameSent: boolean;
  frameMonitor: ReturnType<typeof createSceneFrameMonitor>;
  draw: (animated?: boolean) => void;
};

function settleIfIdle(active: SceneRuntime) {
  if (!active.chapterTimeline?.isActive() && !active.pointerTween?.isActive()) active.frameMonitor.settle();
}

function makeLineGeometry(THREE: ThreeModule, segments: number[][]) {
  const points = new Float32Array(segments.flat());
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(points, 3));
  return geometry;
}

function lineForSquare(x: number, y: number, z: number, half: number) {
  const left = x - half;
  const right = x + half;
  const bottom = y - half;
  const top = y + half;
  return [
    [left, bottom, z, right, bottom, z],
    [right, bottom, z, right, top, z],
    [right, top, z, left, top, z],
    [left, top, z, left, bottom, z],
  ];
}

export function MissingnessScene({ chapter, paused, onFirstFrame, onUnavailable }: MissingnessSceneProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const runtimeRef = useRef<SceneRuntime | null>(null);
  const chapterRef = useRef(chapter);
  const pausedRef = useRef(paused);
  const firstFrameRef = useRef(onFirstFrame);
  const unavailableRef = useRef(onUnavailable);
  chapterRef.current = chapter;
  pausedRef.current = paused;
  firstFrameRef.current = onFirstFrame;
  unavailableRef.current = onUnavailable;

  useEffect(() => {
    const mountNode = hostRef.current;
    if (mountNode === null) return undefined;
    const host: HTMLDivElement = mountNode;
    let cancelled = false;
    let didFail = false;
    let runtime: SceneRuntime | null = null;
    let resizeObserver: ResizeObserver | null = null;
    let intersectionObserver: IntersectionObserver | null = null;
    let pointerEnabled = false;
    let looseRenderer: ThreeTypes.WebGLRenderer | null = null;
    let contextLostListener: ((event: Event) => void) | null = null;
    const ownedGeometries: ThreeTypes.BufferGeometry[] = [];
    const ownedMaterials: ThreeTypes.Material[] = [];

    const teardown = () => {
      const contextCanvas = runtime?.renderer ?? looseRenderer;
      if (contextLostListener && contextCanvas) contextCanvas.domElement.removeEventListener('webglcontextlost', contextLostListener);
      contextLostListener = null;
      if (runtime) {
        if (runtime.frameRequest) cancelAnimationFrame(runtime.frameRequest);
        runtime.chapterTimeline?.kill();
        runtime.pointerTween?.kill();
        runtime.gsap.killTweensOf(runtime.group.rotation);
        runtime.scene.remove(runtime.group);
        runtime.renderer.dispose();
        runtime.renderer.domElement.remove();
        runtimeRef.current = null;
        runtime = null;
      }
      if (looseRenderer) {
        looseRenderer.dispose();
        looseRenderer.domElement.remove();
        looseRenderer = null;
      }
      ownedGeometries.forEach((geometry) => geometry.dispose());
      ownedMaterials.forEach((material) => material.dispose());
      ownedGeometries.length = 0;
      ownedMaterials.length = 0;
      resizeObserver?.disconnect();
      intersectionObserver?.disconnect();
      resizeObserver = null;
      intersectionObserver = null;
      host.removeEventListener('pointermove', onPointerMove);
      host.removeEventListener('pointerleave', onPointerReset);
      host.removeEventListener('blur', onPointerReset);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('blur', onPointerReset);
    };

    const fail = (reason: string) => {
      if (didFail || cancelled) return;
      didFail = true;
      teardown();
      unavailableRef.current(reason);
    };

    const canDraw = () => Boolean(runtime && runtime.inView && runtime.pageVisible && !cancelled && !didFail);

    const renderNow = (animated = false) => {
      const active = runtime;
      if (!active || !canDraw()) return;
      try {
        if (active.renderer.getContext().isContextLost()) {
          fail('The WebGL context was lost.');
          return;
        }
        active.renderer.render(active.scene, active.camera);
      } catch {
        fail('The 3D renderer stopped.');
        return;
      }
      if (active.renderer.info.render.calls > 12 || active.renderer.info.render.triangles > 20_000) {
        fail('The illustration exceeded its rendering budget.');
        return;
      }
      if (animated && !pausedRef.current && active.frameMonitor.sample(performance.now(), active.gsap.ticker.frame)) {
        fail('3D was switched off because rendering was slow.');
        return;
      }
      if (!active.firstFrameSent) {
        active.firstFrameSent = true;
        firstFrameRef.current();
      }
    };

    const scheduleRender = () => {
      if (!runtime || runtime.frameRequest || !canDraw()) return;
      runtime.frameRequest = requestAnimationFrame(() => {
        if (runtime) runtime.frameRequest = 0;
        renderNow();
      });
    };

    const updateMatrices = (active: SceneRuntime) => {
      active.pieces.forEach((piece, index) => {
        const progress = active.progress[piece.row - 2].value;
        active.transform.position.set(piece.x + progress * 0.28, piece.y, progress * 0.72);
        active.transform.updateMatrix();
        active.displaced.setMatrixAt(index, active.transform.matrix);
      });
      active.displaced.instanceMatrix.needsUpdate = true;
      active.rails.scale.x = active.railProgress.value;
      active.gaps.visible = chapterRef.current > 1 || active.progress.some((item) => item.value > 0.001);
      active.rails.visible = active.railProgress.value > 0.001;
    };

    function onPointerMove(event: PointerEvent) {
      const active = runtime;
      if (!active || !pointerEnabled || event.pointerType !== 'mouse' || pausedRef.current || !canDraw()) return;
      const rect = host.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const nx = Math.max(-1, Math.min(1, ((event.clientX - rect.left) / rect.width - 0.5) * 2));
      const ny = Math.max(-1, Math.min(1, ((event.clientY - rect.top) / rect.height - 0.5) * 2));
      settleIfIdle(active);
      active.pointerTween?.kill();
      active.pointerTween = active.gsap.to(active.group.rotation, {
        x: ny * 0.052,
        y: nx * 0.087,
        duration: 0.3,
        overwrite: 'auto',
        onUpdate: () => renderNow(true),
        onComplete: () => settleIfIdle(active),
      });
      if (!active.inView || !active.pageVisible) active.pointerTween.pause();
    }

    function onPointerReset() {
      const active = runtime;
      if (!active) return;
      settleIfIdle(active);
      active.pointerTween?.kill();
      active.pointerTween = null;
      if (pausedRef.current || !canDraw()) {
        active.group.rotation.x = 0;
        active.group.rotation.y = 0;
        if (canDraw()) scheduleRender();
        return;
      }
      active.pointerTween = active.gsap.to(active.group.rotation, {
        x: 0,
        y: 0,
        duration: 0.3,
        overwrite: 'auto',
        onUpdate: () => renderNow(true),
        onComplete: () => settleIfIdle(active),
      });
      if (!active.inView || !active.pageVisible) active.pointerTween.pause();
    }

    function syncPlayback() {
      if (!runtime) return;
      const visible = runtime.inView && runtime.pageVisible;
      if (visible && !pausedRef.current) {
        if (runtime.chapterTimeline && runtime.chapterTimeline.totalProgress() < 1) runtime.chapterTimeline.resume();
        if (runtime.pointerTween && runtime.pointerTween.totalProgress() < 1) runtime.pointerTween.resume();
      } else {
        runtime.chapterTimeline?.pause();
        runtime.pointerTween?.pause();
        runtime.frameMonitor.reset();
        if (runtime.frameRequest) cancelAnimationFrame(runtime.frameRequest);
        runtime.frameRequest = 0;
      }
      if (visible) scheduleRender();
    }

    function onVisibilityChange() {
      if (!runtime) return;
      runtime.pageVisible = !document.hidden;
      syncPlayback();
    }

    const prepare = async () => {
      try {
        const gsapLoad = import('gsap').then(({ gsap }) => {
          configureBrandGsap(gsap);
          return gsap;
        });
        const [THREE, gsap] = await Promise.all([import('three'), gsapLoad]);
        if (cancelled) return;
        const width = Math.max(1, host.clientWidth);
        const height = Math.max(1, host.clientHeight);
        const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'low-power' });
        looseRenderer = renderer;
        renderer.setClearColor(0x000000, 0);
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.LinearToneMapping;
        renderer.toneMappingExposure = 1;
        renderer.domElement.setAttribute('aria-hidden', 'true');
        renderer.domElement.setAttribute('tabindex', '-1');

        const scene = new THREE.Scene();
        const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 30);
        camera.position.set(5.2, 3.6, 7.5);
        camera.lookAt(0, 0, 0.1);
        const group = new THREE.Group();
        group.rotation.z = -8 * Math.PI / 180;
        scene.add(group);

        const boxGeometry = new THREE.BoxGeometry(0.24, 0.24, 0.16);
        ownedGeometries.push(boxGeometry);
        const plateGeometry = new THREE.BoxGeometry(3.72, 3.08, 0.035);
        ownedGeometries.push(plateGeometry);
        const ordinaryMaterial = new THREE.MeshStandardMaterial({ color: '#9EAC9A', roughness: 0.78, metalness: 0.08 });
        ownedMaterials.push(ordinaryMaterial);
        const historyMaterial = new THREE.MeshStandardMaterial({ color: '#182922', roughness: 0.78, metalness: 0.08 });
        ownedMaterials.push(historyMaterial);
        const displacedSideMaterial = new THREE.MeshStandardMaterial({ color: '#B84224', roughness: 0.78, metalness: 0.08 });
        ownedMaterials.push(displacedSideMaterial);
        const plateMaterial = new THREE.MeshStandardMaterial({ color: '#F4F1E9', roughness: 0.9, metalness: 0.02 });
        ownedMaterials.push(plateMaterial);
        const forestLineMaterial = new THREE.LineBasicMaterial({ color: '#11271F' });
        ownedMaterials.push(forestLineMaterial);
        const accentLineMaterial = new THREE.LineBasicMaterial({ color: '#B84224' });
        ownedMaterials.push(accentLineMaterial);

        const plate = new THREE.Mesh(plateGeometry, plateMaterial);
        plate.position.set(0, 0, -0.2);
        group.add(plate);

        const ordinaryGrid: GridPiece[] = [];
        const remainingHistory: GridPiece[] = [];
        const withdrawnGrid: GridPiece[] = [];
        for (let row = 0; row < 8; row += 1) {
          for (let column = 0; column < 10; column += 1) {
            const piece = { column, row, x: (column - 4.5) * 0.34, y: (3.5 - row) * 0.34 };
            if (column < 7) ordinaryGrid.push(piece);
            else if (row >= 2 && row <= 5) withdrawnGrid.push(piece);
            else remainingHistory.push(piece);
          }
        }

        const ordinary = new THREE.InstancedMesh(boxGeometry, ordinaryMaterial, ordinaryGrid.length);
        const history = new THREE.InstancedMesh(boxGeometry, historyMaterial, remainingHistory.length);
        const displacedMaterials = [displacedSideMaterial, displacedSideMaterial, displacedSideMaterial, displacedSideMaterial, ordinaryMaterial, ordinaryMaterial];
        const displaced = new THREE.InstancedMesh(boxGeometry, historyMaterial, withdrawnGrid.length);
        const transform = new THREE.Object3D();
        ordinaryGrid.forEach((piece, index) => {
          transform.position.set(piece.x, piece.y, 0);
          transform.updateMatrix();
          ordinary.setMatrixAt(index, transform.matrix);
        });
        remainingHistory.forEach((piece, index) => {
          transform.position.set(piece.x, piece.y, 0);
          transform.updateMatrix();
          history.setMatrixAt(index, transform.matrix);
        });
        withdrawnGrid.forEach((piece, index) => {
          transform.position.set(piece.x, piece.y, 0);
          transform.updateMatrix();
          displaced.setMatrixAt(index, transform.matrix);
        });
        group.add(ordinary, history, displaced);

        const gapSegments = withdrawnGrid.flatMap((piece) => lineForSquare(piece.x, piece.y, 0.085, 0.13));
        const gapsGeometry = makeLineGeometry(THREE, gapSegments);
        ownedGeometries.push(gapsGeometry);
        const gaps = new THREE.LineSegments(gapsGeometry, accentLineMaterial);
        gaps.visible = false;
        group.add(gaps);

        const frameSegments: number[][] = [];
        const edgeX = 1.86;
        const edgeY = 1.54;
        const mark = 0.17;
        for (const sx of [-1, 1]) {
          for (const sy of [-1, 1]) {
            const x = sx * edgeX;
            const y = sy * edgeY;
            frameSegments.push([x, y, -0.17, x - sx * mark, y, -0.17]);
            frameSegments.push([x, y, -0.17, x, y - sy * mark, -0.17]);
          }
        }
        const frameGeometry = makeLineGeometry(THREE, frameSegments);
        ownedGeometries.push(frameGeometry);
        const frame = new THREE.LineSegments(frameGeometry, forestLineMaterial);
        group.add(frame);

        const railSegments: number[][] = [];
        for (const y of [-1.69, -1.77, -1.85]) railSegments.push([-0.74, y, 0.09, 0.74, y, 0.09]);
        const railsGeometry = makeLineGeometry(THREE, railSegments);
        ownedGeometries.push(railsGeometry);
        const rails = new THREE.LineSegments(railsGeometry, forestLineMaterial);
        rails.scale.x = 0;
        rails.visible = false;
        group.add(rails);

        scene.add(new THREE.HemisphereLight('#F4F1E9', '#9EAC9A', 2.0));
        const key = new THREE.DirectionalLight('#FFFFFF', 2.5);
        key.position.set(-3, 5, 6);
        scene.add(key);
        const fill = new THREE.DirectionalLight('#FFFFFF', 0.7);
        fill.position.set(4, 1, 2);
        scene.add(fill);

        runtime = {
          THREE,
          gsap,
          renderer,
          scene,
          camera,
          group,
          ordinary,
          history,
          displaced,
          historyMaterial,
          displacedMaterials,
          gaps,
          frame,
          rails,
          pieces: withdrawnGrid,
          progress: Array.from({ length: 4 }, () => ({ value: 0 })),
          railProgress: { value: 0 },
          transform: new THREE.Object3D(),
          chapterTimeline: null,
          pointerTween: null,
          frameRequest: 0,
          inView: true,
          pageVisible: !document.hidden,
          firstFrameSent: false,
          frameMonitor: createSceneFrameMonitor(),
          draw: renderNow,
        };
        runtimeRef.current = runtime;
        looseRenderer = null;
        host.appendChild(renderer.domElement);
        if ('IntersectionObserver' in window) {
          const bounds = host.getBoundingClientRect();
          runtime.inView = bounds.bottom > 0 && bounds.top < window.innerHeight && bounds.right > 0 && bounds.left < window.innerWidth;
        }

        const resize = () => {
          if (!runtime) return;
          const widthNow = Math.max(1, host.clientWidth);
          const heightNow = Math.max(1, host.clientHeight);
          const maxDpr = widthNow < 768 ? 1.25 : 1.5;
          const pixelLimitDpr = Math.sqrt(1_500_000 / (widthNow * heightNow));
          const dpr = Math.min(window.devicePixelRatio || 1, maxDpr, pixelLimitDpr);
          renderer.setPixelRatio(dpr);
          renderer.setSize(widthNow, heightNow, false);
          const aspect = widthNow / heightNow;
          const verticalSpan = heightNow > widthNow ? 6.0 : 5.2;
          camera.left = -verticalSpan * aspect / 2;
          camera.right = verticalSpan * aspect / 2;
          camera.top = verticalSpan / 2;
          camera.bottom = -verticalSpan / 2;
          camera.updateProjectionMatrix();
          scheduleRender();
        };

        const lostContext = (event: Event) => {
          event.preventDefault();
          fail('The WebGL context was lost.');
        };
        contextLostListener = lostContext;
        renderer.domElement.addEventListener('webglcontextlost', contextLostListener, { once: true });
        pointerEnabled = window.matchMedia('(pointer: fine)').matches;
        if (pointerEnabled) {
          host.addEventListener('pointermove', onPointerMove, { passive: true });
          host.addEventListener('pointerleave', onPointerReset, { passive: true });
          host.addEventListener('blur', onPointerReset);
          window.addEventListener('blur', onPointerReset);
        }
        document.addEventListener('visibilitychange', onVisibilityChange);
        resizeObserver = new ResizeObserver(resize);
        resizeObserver.observe(host);
        if ('IntersectionObserver' in window) {
          intersectionObserver = new IntersectionObserver((entries) => {
            if (!runtime) return;
            runtime.inView = entries.some((entry) => entry.isIntersecting);
            syncPlayback();
          }, { threshold: 0 });
          intersectionObserver.observe(host);
        }
        resize();
        const active = runtime;
        const target = chapterRef.current;
        active.progress.forEach((item) => { item.value = target > 1 ? 1 : 0; });
        active.railProgress.value = target === 3 ? 1 : 0;
        active.displaced.material = target > 1 ? active.displacedMaterials : active.historyMaterial;
        updateMatrices(active);
        if (target === 3) { active.rails.visible = true; active.rails.scale.x = 1; }
        if (pausedRef.current) {
          active.group.rotation.x = 0;
          active.group.rotation.y = 0;
        }
        scheduleRender();
      } catch {
        if (!cancelled) fail('The 3D illustration is unavailable in this browser.');
      }
    };

    void prepare();
    return () => {
      cancelled = true;
      teardown();
    };
  }, []);

  useEffect(() => {
    const active = runtimeRef.current;
    if (!active) return;
    settleIfIdle(active);
    active.chapterTimeline?.kill();
    active.chapterTimeline = null;
    const target = chapter > 1 ? 1 : 0;
    const targetRail = chapter === 3 ? 1 : 0;
    active.displaced.material = target > 0 ? active.displacedMaterials : active.historyMaterial;
    if (paused) {
      active.frameMonitor.reset();
      if (active.frameRequest) cancelAnimationFrame(active.frameRequest);
      active.frameRequest = 0;
      active.pointerTween?.kill();
      active.pointerTween = null;
      active.progress.forEach((item) => { item.value = target; });
      active.railProgress.value = targetRail;
      active.pieces.forEach((piece, index) => {
        const amount = target;
        active.transform.position.set(piece.x + amount * 0.28, piece.y, amount * 0.72);
        active.transform.updateMatrix();
        active.displaced.setMatrixAt(index, active.transform.matrix);
      });
      active.displaced.instanceMatrix.needsUpdate = true;
      active.gaps.visible = target > 0;
      active.rails.visible = targetRail > 0;
      active.rails.scale.x = targetRail;
      if (active.inView && active.pageVisible) active.draw();
      return;
    }
    const timeline = active.gsap.timeline({ onUpdate: () => {
      active.pieces.forEach((piece, index) => {
        const amount = active.progress[piece.row - 2].value;
        active.transform.position.set(piece.x + amount * 0.28, piece.y, amount * 0.72);
        active.transform.updateMatrix();
        active.displaced.setMatrixAt(index, active.transform.matrix);
      });
      active.displaced.instanceMatrix.needsUpdate = true;
      active.rails.scale.x = active.railProgress.value;
      active.gaps.visible = chapter > 1 || active.progress.some((item) => item.value > 0.001);
      active.rails.visible = chapter === 3 || active.railProgress.value > 0.001;
      active.draw(true);
    } });
    active.chapterTimeline = timeline;
    active.progress.forEach((item, row) => timeline.to(item, { value: target, duration: 0.48, ease: 'power2.inOut' }, row * 0.035));
    timeline.to(active.railProgress, { value: targetRail, duration: 0.32, ease: 'power2.inOut' }, 0);
    timeline.eventCallback('onComplete', () => {
      if (chapter === 1) active.gaps.visible = false;
      settleIfIdle(active);
    });
    if (!active.inView || !active.pageVisible) timeline.pause();
  }, [chapter, paused]);

  return <div className="sg-missingness-renderer" ref={hostRef} aria-hidden="true" />;
}
