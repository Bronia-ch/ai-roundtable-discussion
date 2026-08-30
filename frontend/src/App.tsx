import { useEffect, useState } from "react";
import { Home } from "./pages/Home";
import { PanelSetup } from "./pages/PanelSetup";
import { Studio } from "./pages/Studio";
import { Result } from "./pages/Result";

function useHashRoute(): string {
  const [route, setRoute] = useState(window.location.hash.replace(/^#/, "") || "/");
  useEffect(() => {
    const onHash = () => setRoute(window.location.hash.replace(/^#/, "") || "/");
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return route;
}

/** hash 路由 → {path, sessionId}：`#/studio?id=s1` → {"/studio", "s1"}。 */
function parseRoute(raw: string): { path: string; sessionId: string | null } {
  const [path, query] = raw.split("?");
  const sessionId = new URLSearchParams(query ?? "").get("id");
  return { path: path || "/", sessionId: sessionId && sessionId.length > 0 ? sessionId : null };
}

export default function App() {
  const { path, sessionId } = parseRoute(useHashRoute());
  if (path === "/panel" && sessionId) return <PanelSetup sessionId={sessionId} />;
  if (path === "/studio" && sessionId) return <Studio sessionId={sessionId} />;
  if (path === "/result" && sessionId) return <Result sessionId={sessionId} />;
  return <Home />;
}
