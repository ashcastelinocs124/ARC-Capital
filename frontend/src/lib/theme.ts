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
  soft: v("surface-2"),
  soft2: v("accent-soft-2"),
  surface: v("surface"),
};
