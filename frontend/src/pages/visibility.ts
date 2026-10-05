import { STATIC } from "@/api/client";

// Pages left out of the public (VITE_STATIC=1) build; the private build shows everything.
// Remove a path here to publish it, and add its endpoints back in scripts/export_snapshot.py.
const PRIVATE_ONLY = ["/portfolio", "/risk", "/research"];

export const pageEnabled = (path: string) => !STATIC || !PRIVATE_ONLY.includes(path);
export const HOME = pageEnabled("/portfolio") ? "/portfolio" : "/models";
