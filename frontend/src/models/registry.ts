// Every model on /models and /docs, in display order. Flip `enabled` to hide a model's card and
// its Documentation section (dashboard only; backend jobs and the trading pipeline are unaffected).
// The id doubles as the anchor on /docs (`/docs#pulse`).
export const MODELS = [
  { id: "pulse", name: "Pulse", enabled: true },
  { id: "pressure", name: "Pressure", enabled: true },
  { id: "risk-off", name: "Risk-off classifier", enabled: false }, // off until it's trained
  { id: "sector-sentiment", name: "Sector Sentiment", enabled: true },
  { id: "adoption", name: "AI Adoption Index", enabled: true },
  { id: "cross-asset", name: "Cross-Asset Drivers", enabled: true },
] as const;

export type ModelId = (typeof MODELS)[number]["id"];

export const ENABLED_MODELS = MODELS.filter((m) => m.enabled);
export const isEnabled = (id: string) => ENABLED_MODELS.some((m) => m.id === id);
