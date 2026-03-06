"""
Driver & Team Price Updater — v2 (Target-Curve Approach)
========================================================

Replaces the v1 exponential repricing that created extreme polarization
(10+ drivers trapped at 1M floor, top 3 absorbing 55%+ of pool).

New approach:
  1. SCORE each driver/team by DEMAND (user picks) + PERFORMANCE (GP points)
  2. RANK by composite score (recalculated EVERY round — no fixed labels)
  3. MAP ranks → target prices via a geometric curve that creates a
     smooth, continuous distribution across the full price range
  4. BLEND current prices toward targets (capped step per round)
  5. APPORTION to integers preserving total price pool exactly

Design principles:
  - BUDGET TENSION: Top driver ~36M ensures users MUST make tough choices.
    With 150M budget for 5 drivers + 2 teams, picking 3 top drivers + 1 top
    team costs ~151M BEFORE the remaining 2 drivers — IMPOSSIBLE.
    Users must choose: 1-2 premium picks + value picks to fill the roster.

  - FULLY DYNAMIC: No fixed groups or labels. Every round, every driver's
    composite score is recomputed from current picks + points.  A back-marker
    who becomes popular can rise 5M/round, reaching top prices within
    6-7 rounds.  Designed for regulation-change seasons where the pecking
    order can shift dramatically mid-season.

  - NO TRAPS: Even the cheapest driver gets a meaningful target (~2M), never
    stuck at 1M floor.  The geometric curve is continuous — there are no hard
    boundaries between price ranges.  Ranks shift freely every round.

  - DEMAND-DOMINANT: User picks drive 65% of price changes, on-track
    performance 35%.  Price reflects what users WANT, not just lap times.

Example distribution (22 drivers, 250M pool, ratio=0.86):
  Rank  1–3:   27–36M    (most in-demand — forces heavy budget sacrifice)
  Rank  4–8:   14–23M    (strong demand — competitive mid picks)
  Rank  9–14:   6–12M    (moderate demand — value plays)
  Rank 15–19:   3–5M     (low demand — budget options)
  Rank 20–22:   2–3M     (least demanded — cheapest)
"""

from f1porra_website.apps.public.models import (
    Season, DriverPoints, TeamPoints, Porra, GrandPrix,
)
from django.db.models import Max
from django.db import transaction
import numpy as np
import pandas as pd
from datetime import date

# =========================================================
# TUNABLES
# =========================================================

# --- Score weights (demand vs. performance) ---
W_PICKS  = 0.65    # User demand (pick frequency) — primary price driver
W_POINTS = 0.35    # On-track performance — secondary signal

# --- Target distribution shape (geometric ratio) ---
# Ratio r determines the spread: rank k target = C·r^k.
# Lower r = steeper spread.  There are NO hard tier boundaries —
# the curve is smooth and every rank gets a unique target price.
# r=1.0 → flat (all equal); r=0.90 → gentle; r=0.85 → steep.
CURVE_RATIO_DRIVERS = 0.86   # top~36M, bottom~2M (18:1) for 22 drivers
CURVE_RATIO_TEAMS   = 0.85   # top~56M, bottom~11M (5:1) for 11 teams

# --- Convergence speed ---
# Fraction of gap (target − current) closed each round.
# 0.50 means ~97% converged in 6 rounds.  High values make prices
# responsive to demand shifts (important for regulation-change seasons).
BLEND_SPEED_DRIVERS = 0.50
BLEND_SPEED_TEAMS   = 0.50

# --- Maximum absolute price change per round ---
# Moderate caps balance responsiveness with stability.
# A driver can swing up to ±5M/round = ±25M over 5 races.
# A full reprice from bottom to top takes ~7 rounds.
MAX_STEP_DRIVERS = 5
MAX_STEP_TEAMS   = 8

# --- Floors & smoothing ---
MIN_PRICE      = 1
PICK_SMOOTHING = 0.5    # Laplace smoothing on raw pick counts
EPS            = 1e-9


# =========================================================
# HELPERS
# =========================================================

def _compute_scores(picks: pd.Series, points: pd.Series,
                    w_picks: float = W_PICKS,
                    w_points: float = W_POINTS) -> tuple:
    """
    Composite demand-performance score for ranking.

    • pick_share uses Laplace smoothing so unpicked items still get a
      small but non-zero share (prevents zero-demand traps).
    • points are shifted so the minimum maps to 1 (handles negative values),
      then normalized to a share.

    Returns (composite, pick_share, points_share) — all pd.Series.
    """
    # Pick share with Laplace smoothing
    p = picks.astype(float) + PICK_SMOOTHING
    pick_share = p / p.sum()

    # Points share: shift so minimum → 1, then normalize
    pts = points.astype(float).fillna(0.0)
    pts_shifted = pts - pts.min() + 1.0          # all positive, min = 1
    points_share = pts_shifted / max(pts_shifted.sum(), EPS)

    composite = w_picks * pick_share + w_points * points_share
    return composite, pick_share, points_share


def _geometric_targets(n: int, total_pool: float, ratio: float) -> np.ndarray:
    """
    Generate a descending target-price curve via geometric series.

    Item at rank k (0-based) gets  C · r^k  where C is chosen so the
    series sums to *total_pool* exactly.

    Returns np.ndarray of length n (descending order).
    """
    if n <= 0:
        return np.array([])
    if n == 1:
        return np.array([float(total_pool)])
    if abs(ratio - 1.0) < EPS:
        return np.full(n, total_pool / n)

    c = total_pool * (1.0 - ratio) / (1.0 - ratio ** n)
    targets = c * (ratio ** np.arange(n))
    targets *= total_pool / targets.sum()            # fix float drift
    return targets


def _interpolate_target(rank: float, curve: np.ndarray) -> float:
    """Map a (possibly fractional) rank to a target price via linear interpolation."""
    n = len(curve)
    if n == 0:
        return 0.0
    r = rank - 1.0                                   # 0-based
    if r <= 0:
        return float(curve[0])
    if r >= n - 1:
        return float(curve[-1])
    lo, hi = int(np.floor(r)), int(np.ceil(r))
    if lo == hi:
        return float(curve[lo])
    frac = r - lo
    return float(curve[lo] * (1.0 - frac) + curve[hi] * frac)


# =========================================================
# INTEGER APPORTIONMENT
# =========================================================

def _apportion(current: pd.Series, desired_delta: pd.Series,
               target_sum: int, max_step: int,
               min_price: int = MIN_PRICE) -> pd.Series:
    """
    Convert float deltas to integer deltas while:
      • conserving *target_sum* exactly
      • respecting per-item ±max_step cap
      • ensuring every new price >= min_price
    """
    cur = current.astype(int).values
    des = desired_delta.astype(float).values.copy()

    lower = np.maximum(-max_step, min_price - cur)   # can't drop below floor
    upper = np.full_like(cur, max_step)

    des = np.clip(des, lower, upper)

    base = np.floor(des).astype(int)
    need = target_sum - int((cur + base).sum())

    frac = des - base
    can_add = base < upper
    can_sub = base > lower

    if need > 0:
        order = np.argsort(-frac)                    # largest remainder first
        for j in order:
            if need == 0:
                break
            if can_add[j]:
                base[j] += 1
                need -= 1
        # Fallback: relax cap by 1 if pool still unbalanced
        if need > 0:
            for j in np.argsort(-frac):
                if need == 0:
                    break
                base[j] += 1
                need -= 1
    elif need < 0:
        order = np.argsort(frac)                     # smallest remainder first
        for j in order:
            if need == 0:
                break
            if can_sub[j]:
                base[j] -= 1
                need += 1
        # Fallback: relax cap by 1 if pool still unbalanced
        if need < 0:
            for j in np.argsort(frac):
                if need == 0:
                    break
                if cur[j] + base[j] - 1 >= min_price:
                    base[j] -= 1
                    need += 1

    # Safety: enforce min_price
    new_prices = cur + base
    short = new_prices < min_price
    if short.any():
        lift = min_price - new_prices[short]
        base[short] += lift
        surplus = int(lift.sum())
        idx_desc = np.argsort(-base)
        for j in idx_desc:
            if surplus == 0:
                break
            give = min(int(base[j] - lower[j]), surplus)
            if give > 0:
                base[j] -= give
                surplus -= give

    assert (cur + base).sum() == target_sum, \
        f"Apportionment failed: got {(cur + base).sum()}, want {target_sum}"

    return pd.Series(base, index=current.index)


# =========================================================
# REPRICING (unified for drivers & teams)
# =========================================================

def _reprice(df: pd.DataFrame, curve_ratio: float,
             blend_speed: float, max_step: int,
             entity_label: str = "entity") -> pd.DataFrame:
    """
    Core repricing pipeline:
      1. Composite score from picks + points  →  rank
      2. Geometric target curve               →  target price per rank
      3. Blend toward target (capped delta)
      4. Integer apportionment (pool-conserving)
    """
    out = df.copy()
    n = len(out)
    total_pool = int(out["price"].sum())

    # 1 — composite score & rank
    composite, pick_share, points_share = _compute_scores(
        out["Picks"], out["points"],
    )
    out["composite_score"] = composite.values
    out["pick_share"]      = pick_share.values
    out["points_share"]    = points_share.values
    out["Rank"] = pd.Series(composite.values).rank(
        ascending=False, method="average",
    ).values

    # 2 — geometric target curve
    curve = _geometric_targets(n, total_pool, curve_ratio)
    out["TargetPrice"] = out["Rank"].apply(
        lambda r: _interpolate_target(r, curve),
    )

    # 3 — blend toward target (capped)
    current = out["price"].astype(float)
    desired = blend_speed * (out["TargetPrice"] - current)
    desired = np.clip(desired, -max_step, max_step)

    # 4 — integer apportionment
    deltas = _apportion(
        current=out["price"],
        desired_delta=pd.Series(desired.values, index=out.index),
        target_sum=total_pool,
        max_step=max_step,
    )

    out["DeltaFinal"] = deltas.astype(int)
    out["NewPrice"]   = (out["price"].astype(int) + out["DeltaFinal"]).astype(int)

    # Diagnostic output
    print(f"\n{entity_label} repriced (target-curve approach):")
    cols = ["id", "name", "points", "price", "Picks",
            "composite_score", "Rank", "TargetPrice",
            "DeltaFinal", "NewPrice"]
    display_cols = [c for c in cols if c in out.columns]
    print(out[display_cols].to_string(index=False))

    return out


# =========================================================
# MAIN ENTRY POINT
# =========================================================

def update_points(season_year: int = None, gp_nround: int = None):
    """
    Read current-GP picks + points, compute new prices, write to next GP.

    Called after each GP is completed.  Preserves total price pool exactly.

    Optional overrides (useful for testing / backfill):
      season_year  – force a specific season instead of current year
      gp_nround    – force a specific GP round instead of latest
    """
    year = season_year or date.today().year
    try:
        current_season = Season.objects.get(year=year)
    except Season.DoesNotExist:
        print(f"No season found for year {year}.")
        return

    if gp_nround is not None:
        current_gp_n = gp_nround
    else:
        current_gp_n = DriverPoints.objects.filter(
            season=current_season,
        ).aggregate(max_nround=Max("gp__nround"))["max_nround"]

    if current_gp_n is None:
        print("No GP points found for current season.")
        return

    next_gp = GrandPrix.objects.filter(
        season=current_season, nround__gt=current_gp_n,
    ).order_by("nround").first()
    if next_gp is None:
        print("No next GP found (end of season). No price update.")
        return

    # ---- load data ----
    driver_df = pd.DataFrame(
        DriverPoints.objects.filter(
            season=current_season, gp__nround=current_gp_n,
        ).values("driver_id", "driver__name", "points", "price")
    )
    team_df = pd.DataFrame(
        TeamPoints.objects.filter(
            season=current_season, gp__nround=current_gp_n,
        ).values("team_id", "team__name", "points", "price")
    )
    if driver_df.empty or team_df.empty:
        print("Empty driver/team table; aborting.")
        return

    driver_df.rename(
        columns={"driver_id": "id", "driver__name": "name"}, inplace=True,
    )
    team_df.rename(
        columns={"team_id": "id", "team__name": "name"}, inplace=True,
    )

    # Handle NULL points (seeded but unplayed GPs)
    driver_df["points"] = driver_df["points"].fillna(0)
    team_df["points"]   = team_df["points"].fillna(0)

    # ---- count picks ----
    driver_picks_qs = (
        Porra.objects.filter(
            season=current_season, gp__nround=current_gp_n,
        ).values_list("driver1", "driver2", "driver3", "driver4", "driver5")
    )
    team_picks_qs = (
        Porra.objects.filter(
            season=current_season, gp__nround=current_gp_n,
        ).values_list("team1", "team2")
    )

    driver_flat = [d for row in driver_picks_qs for d in row if d is not None]
    team_flat   = [t for row in team_picks_qs   for t in row if t is not None]

    driver_pick_counts = pd.Series(driver_flat, dtype="Int64").value_counts()
    team_pick_counts   = pd.Series(team_flat,   dtype="Int64").value_counts()

    driver_df["Picks"] = (
        driver_df["id"].map(driver_pick_counts).fillna(0).astype(float)
    )
    team_df["Picks"] = (
        team_df["id"].map(team_pick_counts).fillna(0).astype(float)
    )

    # ---- reprice ----
    drivers_final = _reprice(
        driver_df, CURVE_RATIO_DRIVERS,
        BLEND_SPEED_DRIVERS, MAX_STEP_DRIVERS,
        entity_label="Drivers",
    )
    teams_final = _reprice(
        team_df, CURVE_RATIO_TEAMS,
        BLEND_SPEED_TEAMS, MAX_STEP_TEAMS,
        entity_label="Teams",
    )

    # ---- sanity checks ----
    assert int(drivers_final["NewPrice"].sum()) == int(driver_df["price"].sum()), \
        "Driver pool not conserved!"
    assert int(teams_final["NewPrice"].sum()) == int(team_df["price"].sum()), \
        "Team pool not conserved!"
    assert (drivers_final["NewPrice"] >= MIN_PRICE).all(), "Driver below floor!"
    assert (teams_final["NewPrice"] >= MIN_PRICE).all(), "Team below floor!"

    # ---- persist to next GP ----
    with transaction.atomic():
        for _, r in drivers_final.iterrows():
            DriverPoints.objects.update_or_create(
                season=next_gp.season, driver_id=int(r["id"]), gp=next_gp,
                defaults={"price": int(r["NewPrice"])},
            )
        for _, r in teams_final.iterrows():
            TeamPoints.objects.update_or_create(
                season=next_gp.season, team_id=int(r["id"]), gp=next_gp,
                defaults={"price": int(r["NewPrice"])},
            )

    print(
        f"\nPrices written for {next_gp} "
        f"(pool: drivers={int(driver_df['price'].sum())}M, "
        f"teams={int(team_df['price'].sum())}M)"
    )
