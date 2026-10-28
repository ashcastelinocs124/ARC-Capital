// Chart and SVG colors that follow the light/dark theme. SVG presentation attributes accept var(), so
// recharts props can take these directly; the variables themselves live in src/index.css.
const v = (name: string) => `rgb(var(--c-${name}))`;
export const C = {
  accent: v("accent"),
  text: v("text"),
  text2: v("text-2"),
  muted: v("muted"),
  muted2: v("muted-2"),
  grid: v("surface-3"),
  border: v("border"),
  borderStrong: v("border-strong"),
  success: v("success"),
  danger: v("danger"),
  warning: v("warning"),
  soft: v("surface-2"),
  soft2: v("accent-soft-2"),
  surface: v("surface"),
  inflation: v("cat-inflation"),
  jobs: v("cat-jobs"),
  ai: v("cat-ai"),
  earnings: v("cat-earnings"),
  // AI Demand & Capex: one color per company, keyed by ticker
  co: {
    MSFT: v("co-msft"), GOOGL: v("co-googl"), AMZN: v("co-amzn"), META: v("co-meta"), ORCL: v("co-orcl"),
    CRWV: v("co-crwv"), NBIS: v("co-nbis"), IREN: v("co-iren"), private: v("co-private"),
  } as Record<string, string>,
};
