from f1porra_website.apps.public.models import Season, DriverPoints, TeamPoints, Porra, GrandPrix
from django.db.models import Max
from django.db import transaction
import numpy as np
import pandas as pd
from datetime import date
from typing import Optional

# ----------------------------
# Tunables
# ----------------------------
# Demand vs delivered value
W_PICKS = 0.5
W_POINTS = 0.5

# Score shaping
SCORE_TEMP = 1.0           # tanh temperature for centered raw score

# Concave step + hard caps
ALPHA = 0.5
K = 0.15
STEP_CAP_DRIVERS = 1.60     # <= this, or assert
STEP_CAP_TEAMS   = 1.90

# Learning rates
ETA_DRIVERS_BASE = 0.12
ETA_TEAMS        = 0.055    # cooled down further

# Cheap-aware ETA for drivers
ETA_P_REF = 10.0
ETA_GAMMA = 0.70
ETA_MIN_MULT = 0.85
ETA_MAX_MULT = 2.00

# Final integer caps per round
MAX_ABS_STEP_DRIVERS = 3
MAX_ABS_STEP_TEAMS   = 6

# Positive-move pick gate (absolute, vs equal-share baseline)
PICK_GATE_TAU_DRIVERS = 0.35
PICK_GATE_TAU_TEAMS   = 0.30

# Rounding bias for drivers (helps cheap/high-score)
CHEAP_PRICE_THR = 5
EXPENSIVE_PRICE_THR = 25
SCORE_BAND = 0.6
WT_SCORE_ADD = 2.0
WT_CHEAP_ADD = 1.0
WT_SCORE_SUB = 2.0
WT_EXPENSIVE_SUB = 1.0

MIN_PRICE = 1
EPS = 1e-9

# ----------------------------
# Helpers
# ----------------------------
def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))

def _safe_share(counts: pd.Series, tau: float) -> pd.Series:
    x = pd.to_numeric(counts, errors='coerce').fillna(0.0).astype(float)
    n = len(x)
    den = x.sum() + tau * n
    if den <= 0:  # degenerate
        return pd.Series([1.0/n]*n, index=counts.index)
    return (x + tau) / den

def _step_size(price: pd.Series, cap: float) -> pd.Series:
    p = pd.to_numeric(price, errors='coerce').fillna(MIN_PRICE).clip(lower=MIN_PRICE).astype(float)
    step = 1.0 + K * np.power(p, ALPHA)
    step = np.minimum(step, cap)
    return step

def _centered_score_by_equal_share(pick_share: pd.Series, tpg_share: pd.Series,
                                   w_picks=W_PICKS, w_points=W_POINTS,
                                   temp=SCORE_TEMP) -> pd.Series:
    """
    Center vs equal-share baseline:
      rel_pick = pick_share * N, rel_tpg = tpg_share * N
      raw = w_picks*(rel_pick-1) + w_points*(rel_tpg-1)
      Score = tanh(raw / temp)
    """
    n = len(pick_share)
    rel_pick = pick_share * n
    rel_tpg  = tpg_share  * n
    raw = w_picks * (rel_pick - 1.0) + w_points * (rel_tpg - 1.0)
    return np.tanh(raw / temp), rel_pick, rel_tpg

def _build_table(df: pd.DataFrame, id_col: str, name_col: str,
                 picks: pd.Series, step_cap: float,
                 pick_gate_tau: float) -> pd.DataFrame:
    out = df.copy()
    out["Picks"] = out[id_col].map(picks).fillna(0).astype(float)
    out["TotalPointsGiven"] = (out["Picks"] * out["points"]).astype(float)

    pick_share = _safe_share(out["Picks"], tau=1.0)
    tpg_share  = _safe_share(out["TotalPointsGiven"], tau=1.0)

    score, rel_pick, rel_tpg = _centered_score_by_equal_share(pick_share, tpg_share)

    # Absolute pick gate for positive moves (vs equal-share baseline)
    gate = _sigmoid((rel_pick - 1.0) / pick_gate_tau)
    score = np.where(score > 0, score * gate, score)

    out["pick_share"] = pick_share
    out["tpg_share"] = tpg_share
    out["rel_pick"] = rel_pick
    out["rel_tpg"] = rel_tpg
    out["Score"] = score
    out["Step"]  = _step_size(out["price"], cap=step_cap)

    # hard assertion: no path should exceed cap
    assert float(out["Step"].max()) <= step_cap + 1e-9, f"Step cap {step_cap} violated!"
    return out

def _eta_per_driver(price: pd.Series) -> pd.Series:
    p = price.astype(float).clip(lower=MIN_PRICE)
    mult = (ETA_P_REF / p) ** ETA_GAMMA
    mult = np.clip(mult, ETA_MIN_MULT, ETA_MAX_MULT)
    return ETA_DRIVERS_BASE * mult

# -------------- apportionment --------------
def _apportion_integer_deltas_for_target_sum(current_price: pd.Series,
                                             desired_delta: pd.Series,
                                             target_sum: int,
                                             min_price: int = MIN_PRICE,
                                             per_item_caps: Optional[pd.Series] = None,
                                             weights_add: Optional[pd.Series] = None,
                                             weights_sub: Optional[pd.Series] = None) -> pd.Series:
    cur = pd.to_numeric(current_price, errors='coerce').fillna(min_price).astype(int)
    des = pd.to_numeric(desired_delta, errors='coerce').fillna(0.0).astype(float)

    if per_item_caps is not None:
        cap = per_item_caps.astype(int).clip(lower=0).values
    else:
        cap = np.array([np.iinfo(np.int32).max]*len(cur), dtype=int)

    lower_bound = np.maximum(-cap, (min_price - cur).values)
    upper_bound = cap

    des_clip = np.minimum(np.maximum(des.values, lower_bound), upper_bound)

    base = np.floor(des_clip).astype(int)
    need = int(target_sum) - int((cur.values + base).sum())

    rema = des_clip - base
    can_add = base < upper_bound
    can_sub = base > lower_bound

    if weights_add is None: weights_add = pd.Series(1.0, index=cur.index)
    if weights_sub is None: weights_sub = pd.Series(1.0, index=cur.index)
    w_add = np.maximum(weights_add.values, EPS)
    w_sub = np.maximum(weights_sub.values, EPS)

    if need > 0:
        order = np.argsort(-(rema * w_add))
        for j in order:
            if need == 0: break
            if can_add[j]:
                base[j] += 1
                need -= 1
    elif need < 0:
        order = np.argsort(rema / w_sub)
        for j in order:
            if need == 0: break
            if can_sub[j]:
                base[j] -= 1
                need += 1

    final = base
    new_prices = cur.values + final
    short = (new_prices < min_price)
    if short.any():
        lift = (min_price - new_prices[short])
        final[short] += lift
        need = -int(lift.sum())
        if need != 0:
            idx_desc = np.argsort(-final)
            for j in idx_desc:
                if need == 0: break
                take = min(final[j] - lower_bound[j], max(0, -need))
                final[j] -= take
                need += take

    assert (cur.values + final).sum() == int(target_sum), "Apportionment failed to conserve sum"
    return pd.Series(final, index=cur.index)

# -------------- repricers --------------
def _reprice_drivers(scored: pd.DataFrame, price_col="price") -> pd.DataFrame:
    x = scored.copy()
    x[price_col] = x[price_col].astype(int)

    eta = _eta_per_driver(x[price_col])
    mag = (x["Step"] * x["Score"].abs()).astype(float)
    dirn = np.sign(x["Score"])

    p_float = x[price_col].astype(float) * np.exp(eta * mag * dirn)

    target_sum = float(x[price_col].sum())
    scale = target_sum / max(p_float.sum(), EPS)
    p_target = p_float * scale

    desired = p_target - x[price_col].astype(float)

    per_caps = pd.Series([MAX_ABS_STEP_DRIVERS]*len(x), index=x.index)

    # bias: cheap/high-score get +1 priority; expensive/neg-score yield -1 first
    cheap_bonus = np.clip((CHEAP_PRICE_THR - x[price_col].astype(float)) / CHEAP_PRICE_THR, 0.0, 1.0)
    exp_bonus   = np.clip((x[price_col].astype(float) - EXPENSIVE_PRICE_THR) / EXPENSIVE_PRICE_THR, 0.0, 1.0)
    add_w = 1.0 + WT_CHEAP_ADD*cheap_bonus + WT_SCORE_ADD*np.clip(x["Score"] - SCORE_BAND, 0.0, 1.0)
    sub_w = 1.0 + WT_EXPENSIVE_SUB*exp_bonus + WT_SCORE_SUB*np.clip((-x["Score"]) - SCORE_BAND, 0.0, 1.0)

    deltas = _apportion_integer_deltas_for_target_sum(
        current_price=x[price_col],
        desired_delta=desired,
        target_sum=int(round(target_sum)),
        min_price=MIN_PRICE,
        per_item_caps=per_caps,
        weights_add=add_w,
        weights_sub=sub_w
    )

    x["DeltaFinal"] = deltas.astype(int)
    x["NewPrice"] = (x[price_col] + x["DeltaFinal"]).astype(int)
    x.loc[x["NewPrice"] < MIN_PRICE, "NewPrice"] = MIN_PRICE
    return x

def _reprice_teams(scored: pd.DataFrame, price_col="price") -> pd.DataFrame:
    x = scored.copy()
    x[price_col] = x[price_col].astype(int)

    mag = (x["Step"] * x["Score"].abs()).astype(float)
    dirn = np.sign(x["Score"])

    p_float = x[price_col].astype(float) * np.exp(ETA_TEAMS * mag * dirn)

    target_sum = float(x[price_col].sum())
    scale = target_sum / max(p_float.sum(), EPS)
    p_target = p_float * scale

    desired = p_target - x[price_col].astype(float)
    per_caps = pd.Series([MAX_ABS_STEP_TEAMS]*len(x), index=x.index)

    deltas = _apportion_integer_deltas_for_target_sum(
        current_price=x[price_col],
        desired_delta=desired,
        target_sum=int(round(target_sum)),
        min_price=MIN_PRICE,
        per_item_caps=per_caps
    )

    x["DeltaFinal"] = deltas.astype(int)
    x["NewPrice"] = (x[price_col] + x["DeltaFinal"]).astype(int)
    x.loc[x["NewPrice"] < MIN_PRICE, "NewPrice"] = MIN_PRICE
    return x

# -------------- main --------------
def update_points():
    current_year = date.today().year
    try:
        current_season = Season.objects.get(year=current_year)
    except Season.DoesNotExist:
        print("No current season found.")
        return

    current_gp_n = DriverPoints.objects.filter(season=current_season).aggregate(
        max_nround=Max('gp__nround')
    )['max_nround']
    if current_gp_n is None:
        print("No GP points found for current season.")
        return

    next_gp = GrandPrix.objects.filter(season=current_season, nround__gt=current_gp_n).order_by('nround').first()
    if next_gp is None:
        print("No next GP found (maybe end of season). No price update written.")
        return

    driver_df = pd.DataFrame(
        DriverPoints.objects.filter(season=current_season, gp__nround=current_gp_n)
        .values('driver_id','driver__name','points','price')
    )
    team_df = pd.DataFrame(
        TeamPoints.objects.filter(season=current_season, gp__nround=current_gp_n)
        .values('team_id','team__name','points','price')
    )
    if driver_df.empty or team_df.empty:
        print("Empty driver/team table; aborting.")
        return

    driver_picks_qs = Porra.objects.filter(season=current_season, gp__nround=current_gp_n)\
                                   .values_list('driver1','driver2','driver3','driver4','driver5')
    team_picks_qs   = Porra.objects.filter(season=current_season, gp__nround=current_gp_n)\
                                   .values_list('team1','team2')

    driver_flat = [d for row in driver_picks_qs for d in row if d is not None]
    team_flat   = [t for row in team_picks_qs for t in row if t is not None]

    driver_pick_counts = pd.Series(driver_flat, dtype="Int64").value_counts()
    team_pick_counts   = pd.Series(team_flat, dtype="Int64").value_counts()

    drivers_scored = _build_table(
        df=driver_df.rename(columns={'driver_id':'id','driver__name':'name'}),
        id_col='id', name_col='name', picks=driver_pick_counts,
        step_cap=STEP_CAP_DRIVERS, pick_gate_tau=PICK_GATE_TAU_DRIVERS
    )
    teams_scored = _build_table(
        df=team_df.rename(columns={'team_id':'id','team__name':'name'}),
        id_col='id', name_col='name', picks=team_pick_counts,
        step_cap=STEP_CAP_TEAMS, pick_gate_tau=PICK_GATE_TAU_TEAMS
    )

    drivers_final = _reprice_drivers(drivers_scored, price_col='price')
    teams_final   = _reprice_teams(teams_scored,   price_col='price')

    # sanity
    assert int(drivers_final["NewPrice"].sum()) == int(driver_df["price"].sum()), "Driver pool not conserved"
    assert int(teams_final["NewPrice"].sum()) == int(team_df["price"].sum()), "Team pool not conserved"
    assert (drivers_final["NewPrice"] >= MIN_PRICE).all(), "Driver below floor"
    assert (teams_final["NewPrice"] >= MIN_PRICE).all(), "Team below floor"

    # Debug heads (so you can *see* the gate acting)
    print("Drivers repriced:")
    print(drivers_final[["id","name","points","price","Picks","TotalPointsGiven","rel_pick","rel_tpg","Score","Step","DeltaFinal","NewPrice"]])
    print("Teams repriced:")
    print(teams_final[["id","name","points","price","Picks","TotalPointsGiven","rel_pick","rel_tpg","Score","Step","DeltaFinal","NewPrice"]])

    with transaction.atomic():
        for _, r in drivers_final.iterrows():
            DriverPoints.objects.update_or_create(
                season=next_gp.season, driver_id=int(r["id"]), gp=next_gp,
                defaults={'price': int(r["NewPrice"])}
            )
        for _, r in teams_final.iterrows():
            TeamPoints.objects.update_or_create(
                season=next_gp.season, team_id=int(r["id"]), gp=next_gp,
                defaults={'price': int(r["NewPrice"])}
            )

    print("Driver and Team updates completed (equal-share centered + absolute pick gate + step caps).")
