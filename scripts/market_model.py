"""Market normalization and transparent *experimental* point-spread estimates.

Odds are observations, not forecasts. Spread estimates use a fixed 12-point
normal score-margin assumption and Elo win-probability mapping, neither of
which has been fitted or validated. This module must never assert an edge.
"""
from __future__ import annotations

import math
import re
from statistics import NormalDist

SD_POINTS = 12.0
NORMAL = NormalDist()


def american_to_decimal(value):
    """American odds -> decimal price, rejecting missing or invalid prices."""
    try:
        n = float(value)
        if not math.isfinite(n) or (-100 < n < 100):
            return None
        return round(1 + n / 100 if n > 0 else 1 + 100 / abs(n), 6)
    except (ValueError, TypeError):
        return None


def no_vig_probabilities(home_decimal, away_decimal):
    """Return a two-way market's no-vig probs + overround."""
    try:
        h, a = float(home_decimal), float(away_decimal)
        if not (1 < h < 10000 and 1 < a < 10000):
            return None
        ih, ia = 1 / h, 1 / a
        total = ih + ia
        if not (0.8 < total < 1.6):
            return None
        return {
            "home": round(ih / total, 5),
            "away": round(ia / total, 5),
            "overround": round(total - 1, 5),
        }
    except (ValueError, TypeError):
        return None


def home_spread_from_pickcenter(raw_spread, details, home, away):
    """Cross-check the team named in ESPN details against spread's sign.

    ESPN pickcenter spread is home-oriented for standard NBA games, but do
    not rely on that undocumented behavior when details are ambiguous.
    """
    if not isinstance(details, str):
        return None
    match = re.match(r"^\s*([A-Za-z]{2,4})\s*([+-])\s*(\d+(?:\.\d+)?)\s*$", details)
    if not match:
        return None
    team, sign, number = match.groups()
    value = float(number) * (-1 if sign == "-" else 1)
    if team.upper() == home.upper():
        home_line = value
    elif team.upper() == away.upper():
        home_line = -value
    else:
        return None
    # Verify against raw home-team spread where available.
    if isinstance(raw_spread, (float, int)) and abs(float(raw_spread) - home_line) > 0.011:
        return None
    return home_line


def experimental_cover_probability(home_win_probability, home_spread, sd=SD_POINTS):
    """P(home final margin + home spread > 0) under an *unvalidated* model.

    Translate Elo win probability into a normal expected margin with sigma
    = 12 points. Push probability for whole-point spreads is not resolved
    and must be highlighted instead of pretending an exact settlement rate.
    """
    if not isinstance(home_spread, (int, float)):
        return None
    if not isinstance(home_win_probability, (int, float)):
        return None
    if not (0 < home_win_probability < 1 and math.isfinite(home_spread) and sd > 0):
        return None
    clipped = max(0.001, min(0.999, home_win_probability))
    expected_margin = NORMAL.inv_cdf(clipped) * sd
    return round(NORMAL.cdf((expected_margin + home_spread) / sd), 5)


def build_market(pick, game, forecast):
    """Join ESPN pickcenter to ESPN event; reject unidentifiable market line."""
    home, away = game["home"], game["away"]
    hd = american_to_decimal(pick.get("home_moneyline"))
    ad = american_to_decimal(pick.get("away_moneyline"))
    fair = no_vig_probabilities(hd, ad) if hd and ad else None
    spread = home_spread_from_pickcenter(
        pick.get("spread"), pick.get("details"), home, away
    )
    p = forecast.get("home_win_probability") if forecast else None
    home_cover = experimental_cover_probability(p, spread)
    is_integer = spread is not None and float(spread).is_integer()
    return {
        "event_id": str(game["id"]),
        "home": home,
        "away": away,
        "date": game["date"],
        "provider": pick.get("provider") or "Unknown",
        "captured_at_utc": pick.get("captured_at_utc"),
        "rights_status": "review",
        "moneyline": {
            "home_american": pick.get("home_moneyline") if hd else None,
            "away_american": pick.get("away_moneyline") if ad else None,
            "home_decimal": hd,
            "away_decimal": ad,
            "home_no_vig_probability": fair["home"] if fair else None,
            "away_no_vig_probability": fair["away"] if fair else None,
            "overround": fair["overround"] if fair else None,
        },
        "spread": {
            "home_line": spread,
            "away_line": -spread if spread is not None else None,
            "details": pick.get("details"),
            "home_cover_probability_experimental": home_cover,
            "away_cover_probability_experimental":
                round(1 - home_cover, 5) if home_cover is not None and not is_integer else None,
            "whole_point_push_possible": is_integer,
            "method": "Elo normal-margin approximation; fixed sd=12; unvalidated",
        },
        "total": {"line": pick.get("over_under")},
    }
