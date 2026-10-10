# ruff: noqa: N803, N806 - X/Z are the usual design-matrix names
"""Per-asset ridge regression of weekly returns on factor moves, and the attribution it implies.

Contribution of a factor over a window = sum over the window's weeks of beta x that week's move.
Unexplained = actual move - sum of contributions (drift folded in), so the bars always add up.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV

ALPHAS = np.logspace(-2, 3, 20)
WINDOWS = {"1w": 1, "1m": 4, "3m": 13}
MIN_WEEKS = 80

FACTOR_MAP: dict[str, list[str]] = {
    "spx": ["y2", "ry", "inflation", "growth", "nfci", "walcl", "vix", "hy", "usd", "pos"],
    "ief": ["y2", "ry", "be", "inflation", "growth", "vix", "hy", "tp", "pos"],
    "gld": ["y2", "ry", "be", "inflation", "nfci", "walcl", "vix", "hy", "usd", "pos"],
}
# drivers that move together: the fit gets their joint effect right but not the split
GROUPS: dict[str, list[str]] = {
    "rates": ["y2", "ry", "be", "tp"],
    "risk": ["vix", "hy"],
    "liquidity": ["nfci", "walcl"],
}
GROUP_LABELS = {"rates": "Rates", "risk": "Risk appetite", "liquidity": "Liquidity"}
LABELS = {
    "y2": "2y yield",
    "ry": "Real yield",
    "be": "Breakeven",
    "tp": "Term premium",
    "hy": "HY spread",
    "nfci": "NFCI",
    "walcl": "Fed balance sheet",
    "usd": "Dollar",
    "vix": "VIX",
    "inflation": "Inflation surprise",
    "growth": "Growth surprise",
    "pos": "Positioning",
}
UNITS = {
    "y2": "bp",
    "ry": "bp",
    "be": "bp",
    "tp": "bp",
    "hy": "bp",
    "nfci": "pts",
    "walcl": "%",
    "usd": "%",
    "vix": "pts",
    "inflation": "z",
    "growth": "z",
    "pos": "% OI",
}


def columns_for(asset: str) -> list[str]:
    return [f"pos_{asset}" if c == "pos" else c for c in FACTOR_MAP[asset]]


def _base(col: str) -> str:
    return "pos" if col.startswith("pos_") else col


def group_of(col: str) -> str:
    b = _base(col)
    return next((g for g, members in GROUPS.items() if b in members), b)


@dataclass
class Fit:
    beta: pd.Series  # raw units: % return per unit of the factor's move
    intercept: float
    alpha: float


def fit(X: pd.DataFrame, y: pd.Series) -> Fit:
    mu, sd = X.mean(), X.std(ddof=0)
    live = sd > 0
    Z = (X.loc[:, live] - mu[live]) / sd[live]
    r = RidgeCV(alphas=ALPHAS).fit(Z.values, y.values)
    beta = pd.Series(0.0, index=X.columns)
    beta[live] = r.coef_ / sd[live].values
    intercept = float(r.intercept_ - (beta[live] * mu[live]).sum())
    return Fit(beta=beta, intercept=intercept, alpha=float(r.alpha_))


def _clean(X: pd.DataFrame, y: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    ok = y.notna()
    return X.loc[ok].fillna(0.0), y.loc[ok]


def walk_forward_r2(
    X: pd.DataFrame, y: pd.Series, window_weeks: int = 104, n_test: int = 52
) -> float | None:
    X, y = _clean(X, y)
    if len(y) < window_weeks + n_test:
        return None
    preds, actual = [], []
    for t in range(len(y) - n_test, len(y)):
        f = fit(X.iloc[t - window_weeks : t], y.iloc[t - window_weeks : t])
        preds.append(f.intercept + float(X.iloc[t] @ f.beta))
        actual.append(float(y.iloc[t]))
    a, p = np.array(actual), np.array(preds)
    return float(1 - ((a - p) ** 2).sum() / ((a - a.mean()) ** 2).sum())


def _max_pair_corr(corr: pd.DataFrame, cols: list[str]) -> float | None:
    if len(cols) < 2:
        return None
    sub = corr.loc[cols, cols].abs().to_numpy(copy=True)
    np.fill_diagonal(sub, np.nan)
    v = np.nanmax(sub) if not np.isnan(sub).all() else np.nan
    return None if np.isnan(v) else round(float(v), 2)


def explain(asset: str, X: pd.DataFrame, y: pd.Series, window_weeks: int = 104) -> dict:
    cols = columns_for(asset)
    X, y = _clean(X[cols], y)
    if len(y) < MIN_WEEKS:
        raise ValueError(f"{asset}: only {len(y)} usable weeks, need {MIN_WEEKS}")
    Xw, yw = X.iloc[-window_weeks:], y.iloc[-window_weeks:]
    f = fit(Xw, yw)
    corr = Xw.corr()
    windows = {}
    for name, k in WINDOWS.items():
        moves = X.iloc[-k:].sum()
        move = float(y.iloc[-k:].sum())
        contribs = [
            {
                "factor": _base(c),
                "label": LABELS[_base(c)],
                "group": group_of(c),
                "move": round(float(moves[c]), 4),
                "unit": UNITS[_base(c)],
                "beta": float(f.beta[c]),
                "contribution": float(f.beta[c] * moves[c]),
            }
            for c in cols
        ]
        groups = []
        for g in dict.fromkeys(group_of(c) for c in cols):
            members = [c for c in contribs if c["group"] == g]
            groups.append(
                {
                    "group": g,
                    "label": GROUP_LABELS.get(g, LABELS.get(g, g)),
                    "contribution": sum(c["contribution"] for c in members),
                    "members": members,
                    "max_pairwise_corr": _max_pair_corr(
                        corr, [c for c in cols if group_of(c) == g]
                    ),
                }
            )
        unexplained = move - sum(c["contribution"] for c in contribs)
        windows[name] = {
            "move": move,
            "unexplained": unexplained,
            "contributions": contribs,
            "groups": groups,
        }
    history = []
    for t in range(max(0, len(y) - 26), len(y)):
        row = X.iloc[t]
        contrib = {_base(c): float(f.beta[c] * row[c]) for c in cols}
        history.append(
            {
                "week_end": X.index[t].date().isoformat(),
                "move": float(y.iloc[t]),
                "contributions": contrib,
                "unexplained": float(y.iloc[t]) - sum(contrib.values()),
            }
        )
    return {
        "alpha": f.alpha,
        "oos_r2": walk_forward_r2(X, y, window_weeks),
        "windows": windows,
        "history": history,
    }


def summary_line(block: dict, window: str = "1w") -> str:
    groups = sorted(block["windows"][window]["groups"], key=lambda g: -abs(g["contribution"]))[:2]
    parts = [f"{g['label']} {g['contribution']:+.2f} pts" for g in groups]
    return "Biggest drivers: " + ", ".join(parts) + "."
