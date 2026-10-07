import { useEffect, useMemo, useRef, useState } from "react";
import type { BudgetCurvePayload, BudgetPoint, MetricName } from "../../api/types";
import { methodLabel, methodStyle } from "./shared";
import "../../styles/budget-volume.css";

type PersistedPoint = {
  point: BudgetPoint;
  budget: number;
  conditionId: string | null;
  value: number | null;
};

type VolumeStatus = "loading" | "ready" | "static" | "error";
type OverlayLabel = {
  key: string;
  text: string;
  x: number;
  y: number;
  kind: "point" | "budget" | "metric";
};

type SaveDataConnection = {
  saveData?: boolean;
  addEventListener?: (type: "change", listener: () => void) => void;
  removeEventListener?: (type: "change", listener: () => void) => void;
};

const INITIAL_ANGLE = 0.72;
const BAR_WIDTH = 0.22;
const BAR_DEPTH = 0.72;
const GRID_NEAR = 1.25;
const GRID_FAR = -1.25;

function exactNumber(value: number): string {
  return String(value);
}

function projectLabel(
  THREE: typeof import("three"),
  camera: import("three").PerspectiveCamera,
  rect: DOMRect,
  key: string,
  text: string,
  x: number,
  y: number,
  z: number,
  kind: OverlayLabel["kind"],
): OverlayLabel {
  const projected = new THREE.Vector3(x, y, z).project(camera);
  return {
    key,
    text,
    x: ((projected.x + 1) / 2) * rect.width,
    y: ((1 - projected.y) / 2) * rect.height,
    kind,
  };
}

export default function BudgetVolume(props: {
  payload: BudgetCurvePayload;
  predictor: string;
  scenario: string;
  method: string;
  metric: MetricName;
}) {
  const selectionKey = `${props.predictor}__${props.scenario}`;
  const metricLabel = props.metric === "brier_score" ? "Brier score" : "Log loss";
  const selectedMethodLabel = methodLabel(props.method);
  const selectedMethodStyle = methodStyle(props.method);
  const persistedPoints = useMemo<PersistedPoint[]>(() => {
    const sequence = props.payload.scenarios[selectionKey]?.[props.method] ?? [];
    return sequence.map((point) => {
      const rawValue = point[props.metric];
      const value = point.available && typeof rawValue === "number" && Number.isFinite(rawValue)
        ? rawValue
        : null;
      return {
        point,
        budget: point.budget,
        conditionId: point.condition_id,
        value,
      };
    });
  }, [props.payload, props.metric, props.method, selectionKey]);

  const hostRef = useRef<HTMLDivElement>(null);
  const drawRef = useRef<(() => void) | null>(null);
  const angleRef = useRef(INITIAL_ANGLE);
  const [status, setStatus] = useState<VolumeStatus>("loading");
  const [staticReason, setStaticReason] = useState("");
  const [labels, setLabels] = useState<OverlayLabel[]>([]);
  const [preferenceRevision, setPreferenceRevision] = useState(0);

  useEffect(() => {
    const host = hostRef.current;
    let disposed = false;
    let renderer: import("three").WebGLRenderer | undefined;
    let scene: import("three").Scene | undefined;
    let camera: import("three").PerspectiveCamera | undefined;
    let geometries: import("three").BufferGeometry[] = [];
    let materials: import("three").Material[] = [];
    let instancedMeshes: import("three").InstancedMesh[] = [];
    let resizeObserver: ResizeObserver | undefined;
    let intersectionObserver: IntersectionObserver | undefined;
    let onWindowResize: (() => void) | undefined;
    let onContextLost: ((event: Event) => void) | undefined;
    let preferenceQueries: MediaQueryList[] = [];
    let preferenceConnection: SaveDataConnection | undefined;
    let onPreferenceChange: (() => void) | undefined;
    let visible = document.visibilityState !== "hidden";
    let onVisibilityChange: (() => void) | undefined;
    let intersecting = true;

    const cleanup = () => {
      disposed = true;
      drawRef.current = null;
      resizeObserver?.disconnect();
      intersectionObserver?.disconnect();
      if (onWindowResize) window.removeEventListener("resize", onWindowResize);
      if (onVisibilityChange) document.removeEventListener("visibilitychange", onVisibilityChange);
      if (onContextLost && renderer) renderer.domElement.removeEventListener("webglcontextlost", onContextLost);
      if (onPreferenceChange) {
        for (const query of preferenceQueries) query.removeEventListener("change", onPreferenceChange);
        preferenceConnection?.removeEventListener?.("change", onPreferenceChange);
      }
      for (const geometry of geometries) geometry.dispose();
      for (const material of materials) material.dispose();
      for (const mesh of instancedMeshes) mesh.dispose();
      if (renderer) {
        renderer.dispose();
        renderer.domElement.remove();
      }
      scene?.clear();
    };

    if (props.method === "all") {
      setStatus("static");
      setStaticReason("The 3D view shows one method at a time. Use the all-methods 2D chart and table for comparison.");
      return cleanup;
    }
    if (!persistedPoints.length) {
      setStatus("static");
      setStaticReason("No persisted budget points are available for this selection. See the chart table below.");
      return cleanup;
    }

    const reducedMotionQuery = typeof window.matchMedia === "function"
      ? window.matchMedia("(prefers-reduced-motion: reduce)")
      : undefined;
    const coarsePointerQuery = typeof window.matchMedia === "function"
      ? window.matchMedia("(pointer: coarse)")
      : undefined;
    preferenceQueries = [reducedMotionQuery, coarsePointerQuery].filter((query): query is MediaQueryList => Boolean(query));
    preferenceConnection = (navigator as Navigator & { connection?: SaveDataConnection }).connection;
    onPreferenceChange = () => setPreferenceRevision((revision) => revision + 1);
    for (const query of preferenceQueries) query.addEventListener("change", onPreferenceChange);
    preferenceConnection?.addEventListener?.("change", onPreferenceChange);
    if (reducedMotionQuery?.matches || preferenceConnection?.saveData || coarsePointerQuery?.matches) {
      setStatus("static");
      setStaticReason("3D rendering is unavailable for the current display preferences. Exact persisted values remain in the chart table below.");
      setLabels([]);
      return cleanup;
    }

    setStatus("loading");
    setStaticReason("");
    setLabels([]);

    const render = async () => {
      try {
        const THREE = await import("three");
        if (disposed || !host) return;

        const activeRenderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: "low-power" });
        renderer = activeRenderer;
        activeRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
        activeRenderer.setClearColor(0xffffff, 0);
        activeRenderer.domElement.setAttribute("aria-hidden", "true");
        activeRenderer.domElement.tabIndex = -1;
        onContextLost = (event) => {
          event.preventDefault();
          if (disposed) return;
          setStaticReason("The 3D display stopped rendering. Exact persisted values remain in the chart table below.");
          cleanup();
          setStatus("error");
        };
        activeRenderer.domElement.addEventListener("webglcontextlost", onContextLost);
        host.replaceChildren(activeRenderer.domElement);

        const activeScene = new THREE.Scene();
        scene = activeScene;
        const activeCamera = new THREE.PerspectiveCamera(38, 1, 0.1, 60);
        camera = activeCamera;
        activeScene.add(new THREE.AmbientLight(0xffffff, 1.55));
        const keyLight = new THREE.DirectionalLight(0xffffff, 2.0);
        keyLight.position.set(-3, 7, 8);
        activeScene.add(keyLight);

        const scores = persistedPoints.flatMap((point) => point.value === null ? [] : [point.value]);
        const minMetric = Math.min(0, ...scores);
        const maxMetric = scores.length ? Math.max(...scores) : 0;
        const scaleMax = Math.max(0, maxMetric);
        const metricRange = scaleMax - minMetric;
        const chartBottom = -1.55;
        const chartTop = 2.65;
        const scoreY = (value: number) => metricRange === 0
          ? chartBottom
          : chartBottom + ((value - minMetric) / metricRange) * (chartTop - chartBottom);
        const budgets = persistedPoints.map((point) => point.budget);
        const minBudget = Math.min(...budgets);
        const maxBudget = Math.max(...budgets);
        const xForBudget = (budget: number) => maxBudget === minBudget
          ? 0
          : -4 + ((budget - minBudget) / (maxBudget - minBudget)) * 8;
        const zeroY = scoreY(0);
        const lineVertices: number[] = [];
        const axisVertices: number[] = [];
        const gridVertices: number[] = [];
        const addSegment = (target: number[], ax: number, ay: number, az: number, bx: number, by: number, bz: number) => {
          target.push(ax, ay, az, bx, by, bz);
        };

        addSegment(axisVertices, -4.25, zeroY, GRID_NEAR, 4.25, zeroY, GRID_NEAR);
        addSegment(axisVertices, -4.25, chartBottom, GRID_NEAR, -4.25, chartTop + 0.18, GRID_NEAR);
        addSegment(axisVertices, -4.25, zeroY, GRID_FAR, -4.25, zeroY, GRID_NEAR);
        for (const budget of budgets) {
          const x = xForBudget(budget);
          addSegment(axisVertices, x, zeroY - 0.08, GRID_NEAR, x, zeroY + 0.08, GRID_NEAR);
          addSegment(gridVertices, x, zeroY, GRID_FAR, x, zeroY, GRID_NEAR);
        }
        addSegment(gridVertices, -4.25, zeroY, GRID_FAR, 4.25, zeroY, GRID_FAR);
        if (maxMetric !== 0) {
          const topY = scoreY(maxMetric);
          addSegment(gridVertices, -4.25, topY, GRID_FAR, 4.25, topY, GRID_FAR);
          addSegment(gridVertices, -4.25, topY, GRID_FAR, -4.25, topY, GRID_NEAR);
        }
        if (minMetric < 0) {
          const lowY = scoreY(minMetric);
          addSegment(gridVertices, -4.25, lowY, GRID_FAR, 4.25, lowY, GRID_FAR);
        }

        const makeLine = (vertices: number[], color: number, opacity: number) => {
          const geometry = new THREE.BufferGeometry();
          geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
          geometries.push(geometry);
          const material = new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity, depthWrite: false });
          materials.push(material);
          return new THREE.LineSegments(geometry, material);
        };
        activeScene.add(makeLine(gridVertices, 0xb9b2ca, 0.42));
        activeScene.add(makeLine(axisVertices, 0x777184, 0.92));

        const scored = persistedPoints.filter((point) => point.value !== null);
        const nonZero = scored.filter((point) => point.value !== 0);
        if (nonZero.length) {
          const barGeometry = new THREE.BoxGeometry(1, 1, 1);
          geometries.push(barGeometry);
          const barMaterial = new THREE.MeshStandardMaterial({ color: selectedMethodStyle.color, roughness: 0.62, metalness: 0.02 });
          materials.push(barMaterial);
          const bars = new THREE.InstancedMesh(barGeometry, barMaterial, nonZero.length);
          instancedMeshes.push(bars);
          bars.instanceMatrix.setUsage(THREE.StaticDrawUsage);
          const matrix = new THREE.Matrix4();
          const position = new THREE.Vector3();
          const scale = new THREE.Vector3();
          nonZero.forEach((point, index) => {
            const endY = scoreY(point.value!);
            const height = Math.abs(endY - zeroY);
            position.set(xForBudget(point.budget), zeroY + (endY - zeroY) / 2, 0);
            scale.set(BAR_WIDTH, height, BAR_DEPTH);
            matrix.compose(position, new THREE.Quaternion(), scale);
            bars.setMatrixAt(index, matrix);
          });
          bars.instanceMatrix.needsUpdate = true;
          activeScene.add(bars);
        }

        const markerGeometry = new THREE.SphereGeometry(0.065, 10, 8);
        geometries.push(markerGeometry);
        const markerMaterial = new THREE.MeshStandardMaterial({ color: 0x9669cf, roughness: 0.5, metalness: 0.02 });
        materials.push(markerMaterial);
        if (scored.length) {
          const markers = new THREE.InstancedMesh(markerGeometry, markerMaterial, scored.length);
          instancedMeshes.push(markers);
          const matrix = new THREE.Matrix4();
          const position = new THREE.Vector3();
          const scale = new THREE.Vector3(1, 1, 1);
          scored.forEach((point, index) => {
            position.set(xForBudget(point.budget), scoreY(point.value!), 0.46);
            matrix.compose(position, new THREE.Quaternion(), scale);
            markers.setMatrixAt(index, matrix);
          });
          markers.instanceMatrix.needsUpdate = true;
          activeScene.add(markers);
        }

        for (let index = 0; index + 1 < persistedPoints.length; index += 1) {
          const left = persistedPoints[index];
          const right = persistedPoints[index + 1];
          if (left.value === null || right.value === null) continue;
          addSegment(
            lineVertices,
            xForBudget(left.budget), scoreY(left.value), 0.47,
            xForBudget(right.budget), scoreY(right.value), 0.47,
          );
        }
        if (lineVertices.length) activeScene.add(makeLine(lineVertices, 0x9669cf, 1));

        const draw = () => {
          if (disposed || !visible || !intersecting || !renderer || !camera || !scene || !host) return;
          const bounds = host.getBoundingClientRect();
          if (bounds.width < 1 || bounds.height < 1) return;
          const width = Math.max(1, Math.floor(bounds.width));
          const height = Math.max(1, Math.min(360, Math.floor(bounds.height)));
          renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
          renderer.setSize(width, height, false);
          camera.aspect = width / height;
          const angle = angleRef.current;
          camera.position.set(Math.sin(angle) * 11.6, 6.6, Math.cos(angle) * 11.6);
          camera.lookAt(0, 0.35, 0);
          camera.updateProjectionMatrix();
          renderer.render(scene, camera);

          const rect = renderer.domElement.getBoundingClientRect();
          const annotations: OverlayLabel[] = [];
          for (const [index, point] of persistedPoints.entries()) {
            const y = point.value === null ? zeroY + 0.18 : scoreY(point.value) + 0.18;
            annotations.push(projectLabel(THREE, camera, rect, `point-${index}`, point.value === null ? "Unscored" : exactNumber(point.value), xForBudget(point.budget), y, 0.58, "point"));
            annotations.push(projectLabel(THREE, camera, rect, `budget-${index}`, exactNumber(point.budget), xForBudget(point.budget), zeroY - 0.16, GRID_NEAR, "budget"));
          }
          const ticks = [...new Set([minMetric, 0, maxMetric])];
          for (const tick of ticks) {
            annotations.push(projectLabel(THREE, camera, rect, `metric-${exactNumber(tick)}`, exactNumber(tick), -4.25, scoreY(tick), GRID_NEAR, "metric"));
          }
          setLabels(annotations);
        };
        drawRef.current = draw;
        onVisibilityChange = () => {
          visible = document.visibilityState !== "hidden";
          if (visible) draw();
        };
        document.addEventListener("visibilitychange", onVisibilityChange);
        if (typeof ResizeObserver !== "undefined") {
          resizeObserver = new ResizeObserver(draw);
          resizeObserver.observe(host);
        } else {
          onWindowResize = draw;
          window.addEventListener("resize", onWindowResize);
        }
        if (typeof IntersectionObserver !== "undefined") {
          intersectionObserver = new IntersectionObserver((entries) => {
            intersecting = entries.some((entry) => entry.isIntersecting);
            if (intersecting) draw();
          });
          intersectionObserver.observe(host);
        }
        setStatus("ready");
        draw();
      } catch {
        if (!disposed) {
          setStaticReason("The persisted chart could not be rendered in 3D. Exact values remain in the chart table below.");
          cleanup();
          setStatus("error");
        }
      }
    };

    void render();
    return cleanup;
  }, [persistedPoints, props.method, preferenceRevision, selectedMethodStyle.color]);

  useEffect(() => {
    if (status === "ready") drawRef.current?.();
  }, [status]);

  const rotate = (amount: number) => {
    angleRef.current += amount;
    drawRef.current?.();
  };
  const resetView = () => {
    angleRef.current = INITIAL_ANGLE;
    drawRef.current?.();
  };

  const unavailableSelection = props.method === "all" || persistedPoints.length === 0;
  const showCanvas = !unavailableSelection && (status === "ready" || status === "loading");
  const scoredValues = persistedPoints.flatMap((point) => point.value === null ? [] : [point.value]);
  const maximumMetric = scoredValues.length ? Math.max(...scoredValues) : 0;
  const fallbackText = props.method === "all"
    ? "The 3D view shows one method at a time. Use the all-methods 2D chart and table for comparison."
    : persistedPoints.length === 0
      ? "No persisted budget points are available for this selection. See the chart table below."
      : status === "loading"
        ? "Preparing the selected persisted budget series…"
        : staticReason || "3D view unavailable. Exact persisted values remain in the chart table below.";

  return (
    <section className="budget-volume" aria-label={`3D ${metricLabel} by label budget`}>
      {!showCanvas && <p className="budget-volume__fallback" role="status">{fallbackText}</p>}
      {!unavailableSelection && (
        <div className={`budget-volume__view${showCanvas ? "" : " budget-volume__view--hidden"}`}>
          {status === "loading" ? (
            <p className="budget-volume__loading" role="status">{fallbackText}</p>
          ) : (
            <div className="budget-volume__toolbar">
              <p className="budget-volume__series"><span className="budget-volume__swatch" style={{ backgroundColor: selectedMethodStyle.color }} />{selectedMethodLabel}</p>
              <div className="budget-volume__controls" role="group" aria-label="3D view controls">
                <button type="button" onClick={() => rotate(-0.18)} aria-label="Rotate view left">Rotate left</button>
                <button type="button" onClick={() => rotate(0.18)} aria-label="Rotate view right">Rotate right</button>
                <button type="button" onClick={resetView}>Reset view</button>
              </div>
            </div>
          )}
          <figure className="budget-volume__figure" aria-label={`${metricLabel} for ${selectedMethodLabel} at persisted target label budgets`}>
            <div className="budget-volume__canvas-wrap">
              <div ref={hostRef} className="budget-volume__canvas" aria-hidden="true" />
              <div className="budget-volume__labels" aria-hidden="true">
                {labels.map((label) => (
                  <span
                    key={label.key}
                    className={`budget-volume__label budget-volume__label--${label.kind}`}
                    style={{ left: label.x, top: label.y }}
                  >{label.text}</span>
                ))}
              </div>
            </div>
            <figcaption className="budget-volume__axes">
              <span>Target label budget</span>
              <span>{metricLabel} · zero baseline · maximum {exactNumber(maximumMetric)}</span>
            </figcaption>
          </figure>
          {status === "ready" && (
            <>
              <div className="budget-volume__legend" aria-label="Chart legend">
                <span><i className="budget-volume__swatch" style={{ backgroundColor: selectedMethodStyle.color }} />Bars: {selectedMethodLabel}</span>
                <span><i className="budget-volume__line-key" />Purple line: adjacent scored points</span>
              </div>
              <p className="budget-volume__note">Only finite values marked available are drawn. Unscored budgets remain gaps in the line.</p>
              <ol className="budget-volume__points" aria-label="Persisted budget values">
                {persistedPoints.map(({ point, budget, conditionId, value }, index) => (
                  <li key={`${budget}-${index}`}>
                    <strong>Budget {exactNumber(budget)}</strong>
                    <span>{value === null ? `Unscored (${point.status || "metric unavailable"})` : `${metricLabel}: ${exactNumber(value)}`}</span>
                    <span>Condition ID: {conditionId ?? "Unavailable"}</span>
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>
      )}
    </section>
  );
}
