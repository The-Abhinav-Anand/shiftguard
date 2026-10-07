export function createSceneFrameMonitor() {
  let previousTime: number | null = null;
  let previousFrame: number | null = null;
  let windowTime = 0;
  let windowFrames = 0;
  let slowWindows = 0;

  const settle = () => {
    // Resting time never contributes to a visible animation window.
    previousTime = null;
    previousFrame = null;
  };

  return {
    settle,
    reset() {
      settle();
      windowTime = 0;
      windowFrames = 0;
      slowWindows = 0;
    },
    sample(time: number, frame: number) {
      // Pointer and chapter updates can share one GSAP tick. Count it once.
      if (frame === previousFrame) return false;
      previousFrame = frame;
      const previous = previousTime;
      previousTime = time;
      if (previous === null || time <= previous) return false;

      const interval = time - previous;
      let remaining = interval;
      while (remaining > 0) {
        const portion = Math.min(2_000 - windowTime, remaining);
        windowTime += portion;
        windowFrames += portion / interval;
        remaining -= portion;
        if (windowTime >= 2_000) {
          slowWindows = windowFrames / 2 < 24 ? slowWindows + 1 : 0;
          windowTime = 0;
          windowFrames = 0;
          if (slowWindows >= 2) return true;
        }
      }
      return false;
    },
  };
}
