"""
Carbon and oxygen calculations for RFMS.

This module is plain Python: it imports nothing from Django, so it can be
tested anywhere and reused by views, admin, the API and management commands.
Every assumption is a named constant or a parameter, never a hidden number.
"""
from dataclasses import dataclass
from math import exp, log

# ---------------------------------------------------------------------------
# Constants. Review each against its source before publishing any figures.
# ---------------------------------------------------------------------------
CARBON_FRACTION = 0.47            # share of dry biomass that is carbon (IPCC default)
CO2_PER_CARBON = 44.0 / 12.0      # molecular weight ratio CO2 : C
O2_PER_CO2 = 32.0 / 44.0          # kg O2 released per kg CO2 fixed (photosynthesis)
DEFAULT_WOOD_DENSITY = 0.60       # g/cm3. PLACEHOLDER: use species values
DEFAULT_ROOT_SHOOT = 0.26         # below/above-ground ratio. PLACEHOLDER: confirm
CHAVE_A, CHAVE_B = 0.0673, 0.976  # Chave et al. (2014) pantropical equation


@dataclass(frozen=True)
class GrowthParams:
    """Chapman-Richards growth curve: size = max * (1 - exp(-k * age)) ** shape.

    The defaults are generic and ILLUSTRATIVE. Replace them per species with
    values calibrated on local data before publishing modelled figures.
    """
    dbh_max_cm: float = 60.0
    dbh_k: float = 0.08
    height_max_m: float = 25.0
    height_k: float = 0.10
    shape: float = 1.3


@dataclass(frozen=True)
class TreeCarbon:
    dbh_cm: float
    height_m: float
    agb_kg: float        # above-ground biomass
    bgb_kg: float        # below-ground biomass
    carbon_kg: float
    co2e_kg: float       # CO2 equivalent stored in the tree
    oxygen_kg: float     # O2 released while building that biomass
    method: str          # 'measured' or 'modelled'
    confidence: int      # 0-100


# ---------------------------------------------------------------------------
# Growth model
# ---------------------------------------------------------------------------
def modelled_dbh_cm(age_years, p=GrowthParams()):
    age = max(0.0, age_years)
    return p.dbh_max_cm * (1 - exp(-p.dbh_k * age)) ** p.shape


def modelled_height_m(age_years, p=GrowthParams()):
    age = max(0.0, age_years)
    return p.height_max_m * (1 - exp(-p.height_k * age)) ** p.shape


def age_from_dbh(dbh_cm, p=GrowthParams()):
    """Invert the DBH curve. Used to estimate height when only DBH was measured."""
    if dbh_cm <= 0:
        return 0.0
    ratio = min(dbh_cm / p.dbh_max_cm, 0.999)
    return -log(1 - ratio ** (1 / p.shape)) / p.dbh_k


def height_from_dbh_m(dbh_cm, p=GrowthParams()):
    return modelled_height_m(age_from_dbh(dbh_cm, p), p)


# ---------------------------------------------------------------------------
# Biomass, carbon, oxygen
# ---------------------------------------------------------------------------
def above_ground_biomass_kg(dbh_cm, height_m, wood_density=DEFAULT_WOOD_DENSITY):
    """Chave et al. (2014), equation 4: AGB = 0.0673 * (rho * D^2 * H) ^ 0.976."""
    if dbh_cm <= 0 or height_m <= 0:
        return 0.0
    return CHAVE_A * (wood_density * dbh_cm ** 2 * height_m) ** CHAVE_B


def oxygen_from_co2e(co2e_kg):
    return co2e_kg * O2_PER_CO2


def confidence_score(method, has_height, months_since_measured=None, verified=False):
    """Transparent rules, not a statistical error estimate.

    modelled only            35
    measured DBH only        70
    measured DBH and height  85
    measurement older than 24 months: minus 15
    verified by a reviewer:  plus 10, capped at 95
    """
    if method == 'modelled':
        score = 35
    else:
        score = 85 if has_height else 70
        if months_since_measured is not None and months_since_measured > 24:
            score -= 15
    if verified:
        score += 10
    return min(score, 95)


def tree_carbon(age_years, dbh_cm=None, height_m=None,
                wood_density=None, params=None,
                months_since_measured=None, verified=False,
                root_shoot=DEFAULT_ROOT_SHOOT):
    """Carbon stored in one tree today.

    Uses measured DBH (and height) when given, otherwise the growth model.
    """
    p = params or GrowthParams()
    rho = wood_density or DEFAULT_WOOD_DENSITY

    if dbh_cm and dbh_cm > 0:
        method = 'measured'
        has_height = bool(height_m and height_m > 0)
        dbh = dbh_cm
        height = height_m if has_height else height_from_dbh_m(dbh_cm, p)
    else:
        method = 'modelled'
        has_height = False
        dbh = modelled_dbh_cm(age_years, p)
        height = modelled_height_m(age_years, p)

    agb = above_ground_biomass_kg(dbh, height, rho)
    bgb = agb * root_shoot
    carbon = (agb + bgb) * CARBON_FRACTION
    co2e = carbon * CO2_PER_CARBON

    return TreeCarbon(
        dbh_cm=round(dbh, 1), height_m=round(height, 1),
        agb_kg=round(agb, 1), bgb_kg=round(bgb, 1),
        carbon_kg=round(carbon, 1), co2e_kg=round(co2e, 1),
        oxygen_kg=round(oxygen_from_co2e(co2e), 1),
        method=method,
        confidence=confidence_score(method, has_height, months_since_measured, verified),
    )


def annual_co2e_increment(age_years, wood_density=None, params=None):
    """Modelled CO2e added over the next year (a flux, not a stock)."""
    now = tree_carbon(age_years, wood_density=wood_density, params=params).co2e_kg
    nxt = tree_carbon(age_years + 1, wood_density=wood_density, params=params).co2e_kg
    return round(nxt - now, 1)


def forecast_co2e(age_years, years=5, current=None, wood_density=None, params=None):
    """CO2e stock for each of the next `years` years, as a list starting now.

    If `current` (a TreeCarbon from a measurement) is given, the modelled curve
    is scaled so that year 0 matches the measurement.
    """
    modelled = [tree_carbon(age_years + y, wood_density=wood_density, params=params).co2e_kg
                for y in range(years + 1)]
    if current is not None and modelled[0] > 0:
        scale = current.co2e_kg / modelled[0]
        return [round(v * scale, 1) for v in modelled]
    return modelled
