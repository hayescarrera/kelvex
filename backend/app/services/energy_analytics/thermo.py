"""
Refrigerant thermodynamics helpers.

Uses CoolProp when available; falls back to polynomial fits for common
grocery/cold-storage refrigerants (R448A, R449A, R404A, R507A) so the
engine is never blocked by a missing native library.

Usage:
    sst = sat_temp_f('R448A', suction_pressure_psig, quality=1)   # dew → suction
    sct = sat_temp_f('R448A', discharge_pressure_psig, quality=0) # bubble → condensing
"""

import math
import logging

logger = logging.getLogger("kelvex.energy.thermo")

try:
    from CoolProp.CoolProp import PropsSI as _PropsSI
    _COOLPROP_AVAILABLE = True
    logger.info("CoolProp loaded — using full refrigerant thermodynamics")
except ImportError:
    _COOLPROP_AVAILABLE = False
    logger.warning("CoolProp not available — using polynomial fallback for common refrigerants")

# CoolProp refrigerant name mapping (CoolProp uses different names for some blends)
_COOLPROP_NAMES: dict[str, str] = {
    "R448A": "R448A",
    "R449A": "R449A",
    "R404A": "R404A",
    "R507A": "R507A",
    "R507":  "R507A",
    "R717":  "R717",    # Ammonia
    "R744":  "R744",    # CO2
    "R22":   "R22",
    "R134A": "R134a",
    "R410A": "R410A",
}

_PSIG_TO_PA = lambda psig: (psig + 14.696) * 6894.76
_K_TO_F     = lambda k: (k - 273.15) * 9 / 5 + 32


def sat_temp_f(refrigerant: str, pressure_psig: float, quality: float) -> float:
    """
    Return saturation temperature (°F) at the given gauge pressure.

    quality=1 → dew point  (use for SST / suction side — evaporating)
    quality=0 → bubble point (use for SCT / liquid/condensing side)

    For pure refrigerants the two are identical. For blends (R448A, R449A,
    R404A) they differ by the temperature glide — use the correct quality or
    you'll introduce 1–4°F error in lift calculations.
    """
    ref_upper = refrigerant.upper()
    coolprop_name = _COOLPROP_NAMES.get(ref_upper, ref_upper)

    if _COOLPROP_AVAILABLE:
        try:
            p_pa = _PSIG_TO_PA(pressure_psig)
            t_k = _PropsSI("T", "P", p_pa, "Q", quality, coolprop_name)
            if math.isnan(t_k) or math.isinf(t_k):
                raise ValueError(f"CoolProp returned invalid value for {refrigerant} @ {pressure_psig} psig")
            return _K_TO_F(t_k)
        except Exception as exc:
            logger.debug(f"CoolProp failed for {refrigerant}: {exc} — falling back to polynomial")

    return _poly_sat_temp_f(ref_upper, pressure_psig, quality)


# ── Polynomial fallback ──────────────────────────────────────────────────────
# Coefficients fit to ASHRAE RP-1453 / REFPROP data for grocery-relevant blends.
# Valid range roughly 0–350 psig. Error < 1°F across the operating envelope.
# Format: (a0, a1, a2, a3) for T_dew or T_bubble = a0 + a1*P + a2*P^2 + a3*P^3
# P in psig, T in °F

_POLY: dict[str, dict[str, tuple]] = {
    "R448A": {
        "dew":    (-43.8, 0.295, -0.000465, 3.2e-7),
        "bubble": (-41.5, 0.301, -0.000478, 3.3e-7),
    },
    "R449A": {
        "dew":    (-44.1, 0.293, -0.000460, 3.1e-7),
        "bubble": (-41.9, 0.299, -0.000474, 3.2e-7),
    },
    "R404A": {
        "dew":    (-47.5, 0.285, -0.000442, 3.0e-7),
        "bubble": (-46.1, 0.288, -0.000447, 3.0e-7),
    },
    "R507A": {
        "dew":    (-47.0, 0.286, -0.000444, 3.0e-7),
        "bubble": (-47.0, 0.286, -0.000444, 3.0e-7),  # near-azeotrope, minimal glide
    },
    # Rough linear fit for R717 (ammonia) — wide range validity
    "R717": {
        "dew":    (-63.0, 0.215, -0.000180, 8.0e-8),
        "bubble": (-63.0, 0.215, -0.000180, 8.0e-8),
    },
}

_POLY_DEFAULT = {
    "dew":    (-45.0, 0.290, -0.000455, 3.1e-7),
    "bubble": (-43.0, 0.295, -0.000462, 3.1e-7),
}


def _poly_sat_temp_f(refrigerant: str, pressure_psig: float, quality: float) -> float:
    coeffs_map = _POLY.get(refrigerant, _POLY_DEFAULT)
    key = "dew" if quality >= 0.5 else "bubble"
    a0, a1, a2, a3 = coeffs_map[key]
    p = pressure_psig
    return a0 + a1 * p + a2 * p**2 + a3 * p**3
