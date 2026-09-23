import { useCallback, useEffect, useState } from "react";

/* Hash routing, deliberately dependency-free. It survives refresh, supports the
   browser back button, and needs no server rewrite rules. */

export function currentRoute(): string {
  const raw = window.location.hash.replace(/^#\/?/, "");
  return raw || "";
}

export function navigate(route: string) {
  const next = route.replace(/^\/+/, "");
  if (currentRoute() === next) return;
  window.location.hash = `/${next}`;
}

export function useRoute(): [string, (route: string) => void] {
  const [route, setRoute] = useState(currentRoute);

  useEffect(() => {
    const onChange = () => {
      setRoute(currentRoute());
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const go = useCallback((next: string) => navigate(next), []);
  return [route, go];
}
