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

export default function App() {
  const route = useHashRoute();
  if (route === "/studio") return <Studio />;
  if (route === "/result") return <Result />;
  if (route === "/panel") return <PanelSetup />;
  return <Home />;
}
