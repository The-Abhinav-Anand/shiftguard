import { lazy, Suspense, useEffect, useState } from "react";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import { RouteLoading } from "./components/brand/RouteLoading";
import { matchRoute, type RouteMatch } from "./routes";

const Overview = lazy(() => import("./pages/Overview"));
const BenchmarkWorkbench = lazy(() => import("./pages/BenchmarkWorkbench"));
const PlannedWorkspace = lazy(() => import("./pages/PlannedWorkspace"));
const NotFound = lazy(() => import("./pages/NotFound"));

function currentRoute(): RouteMatch {
  return matchRoute(window.location.pathname);
}

function RouteScreen({ route }: { route: RouteMatch }) {
  switch (route.kind) {
    case "overview":
      return <Overview />;
    case "demo":
      return <BenchmarkWorkbench />;
    case "planned":
      return <PlannedWorkspace />;
    case "not-found":
      return <NotFound />;
  }
}

function PageLoading() {
  const [takingLonger, setTakingLonger] = useState(false);

  useEffect(() => {
    const timeout = window.setTimeout(() => setTakingLonger(true), 10_000);
    return () => window.clearTimeout(timeout);
  }, []);

  return (
    <>
      <RouteLoading label={takingLonger ? "This is taking longer than expected" : "Opening this page"} />
      {takingLonger && <button className="route-loading-reload" type="button" onClick={() => window.location.reload()}>Reload page</button>}
    </>
  );
}

export default function App() {
  const [route, setRoute] = useState<RouteMatch>(currentRoute);

  useEffect(() => {
    const updateRoute = () => setRoute(currentRoute());
    window.addEventListener("popstate", updateRoute);
    return () => window.removeEventListener("popstate", updateRoute);
  }, []);

  useEffect(() => {
    document.title = route.title;
  }, [route.title]);

  return (
    <div className="app-root">
      <a className="skip-link" href="#route-content">Skip to main content</a>
      <div id="route-content" tabIndex={-1}>
        <AppErrorBoundary key={route.pathname}>
          <Suspense fallback={<PageLoading />}>
            <RouteScreen route={route} />
          </Suspense>
        </AppErrorBoundary>
      </div>
    </div>
  );
}
