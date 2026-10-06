// "Apple Inc." + "AAPL" -> "Apple (AAPL)". Every company shown in the UI goes through this,
// so a bare ticker never appears on its own. Falls back to the ticker when the name is unknown.
// "Company" is kept on purpose: stripping it breaks "Deere & Company" and "The Coca-Cola Company".
const SUFFIX = /,?\s+(inc\.?|incorporated|corporation|corp\.?|plc|ltd\.?|limited|n\.v\.|s\.a\.|l\.p\.)$/i;

export function shortName(name: string): string {
  let n = name.trim();
  for (let prev = ""; prev !== n; ) [prev, n] = [n, n.replace(SUFFIX, "").trim()];
  return n;
}

export const company = (name: string | null | undefined, ticker: string) =>
  name ? `${shortName(name)} (${ticker})` : ticker;
