import { useEffect, useState } from "react";

export type Route = { name: "home" } | { name: "job"; id: string } | { name: "all" };

const JOB = /^#\/job\/([0-9a-f-]{36})$/i;

export function parseHash(hash: string): Route {
  const m = JOB.exec(hash);
  if (m) return { name: "job", id: m[1] };
  if (hash === "#/semua") return { name: "all" };
  return { name: "home" };
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const h = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", h);
    return () => window.removeEventListener("hashchange", h);
  }, []);
  return route;
}

export const go = {
  home: () => {
    window.location.hash = "#/";
  },
  job: (id: string) => {
    window.location.hash = `#/job/${id}`;
  },
  all: () => {
    window.location.hash = "#/semua";
  },
};
