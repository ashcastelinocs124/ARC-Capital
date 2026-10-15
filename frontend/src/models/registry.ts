// Every model, in display order. Flip `enabled` to hide a model's card and its Documentation section
// (dashboard only; backend jobs are unaffected). The id doubles as the anchor on /docs (`/docs#pulse`).
// Since 2026-10-15 the models are admin-only (/admin → Models, data under /api/admin/); `public: true`
// marks the one shown on the public site, Fear & Greed · Sector Sentiment, a card on Radar (/macro).
export const MODELS = [
  { id: "pulse", name: "Pulse", enabled: true, public: false },
  { id: "pressure", name: "Pressure", enabled: true, public: false },
  { id: "risk-off", name: "Risk-off classifier", enabled: false, public: false }, // off until it's trained
  { id: "sector-sentiment", name: "Fear & Greed · Sector Sentiment", enabled: true, public: true },
  { id: "adoption", name: "AI Adoption Index", enabled: true, public: false },
  { id: "cross-asset", name: "Cross-Asset Drivers", enabled: true, public: false },
] as const;

export type ModelId = (typeof MODELS)[number]["id"];

export const ENABLED_MODELS = MODELS.filter((m) => m.enabled);
export const PRIVATE_MODELS = ENABLED_MODELS.filter((m) => !m.public);
export const isEnabled = (id: string) => ENABLED_MODELS.some((m) => m.id === id);
export const isPublic = (id: string) => ENABLED_MODELS.some((m) => m.id === id && m.public);
