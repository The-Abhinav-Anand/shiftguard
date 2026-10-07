export type RouteMatch =
  | { kind: "overview"; pathname: "/about"; title: "About SHIFTGUARD" }
  | { kind: "demo"; pathname: "/" | "/demo"; title: "Bank benchmark workbench · SHIFTGUARD" }
  | { kind: "planned"; pathname: "/workspace" | "/workspace/onboarding" | "/workspace/dashboard" | "/workspace/upload"; title: "Private workspaces planned · SHIFTGUARD" }
  | { kind: "not-found"; pathname: string; title: "Page not found · SHIFTGUARD" };

const plannedPaths = new Set([
  "/workspace",
  "/workspace/onboarding",
  "/workspace/dashboard",
  "/workspace/upload",
]);

export function matchRoute(pathname: string): RouteMatch {
  if (pathname === "/" || pathname === "/demo") {
    return { kind: "demo", pathname, title: "Bank benchmark workbench · SHIFTGUARD" };
  }
  if (pathname === "/about") {
    return { kind: "overview", pathname, title: "About SHIFTGUARD" };
  }
  if (plannedPaths.has(pathname)) {
    return { kind: "planned", pathname: pathname as Extract<RouteMatch, { kind: "planned" }>['pathname'], title: "Private workspaces planned · SHIFTGUARD" };
  }
  return { kind: "not-found", pathname, title: "Page not found · SHIFTGUARD" };
}
