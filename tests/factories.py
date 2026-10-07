# tests/factories.py
import math

from gridcast.dispatch.schemas import BatteryParams, DispatchInput


def _pv_profile(hours: int, peak_kw: float) -> list[float]:
    """Half-sine between 06:00 and 18:00, zero at night."""
    return [
        peak_kw * math.sin(math.pi * (h - 6) / 12) if 6 <= h <= 18 else 0.0 for h in range(hours)
    ]


def _buy_price(h: int) -> float:
    if 17 <= h < 22:
        return 0.30  # evening peak
    if h >= 22 or h < 6:
        return 0.10  # night
    return 0.20  # daytime shoulder


def make_input(
    *,
    hours: int = 24,
    pv_peak_kw: float = 5.0,
    load_kw: float = 1.0,
    battery: dict | None = None,
    **overrides,
) -> DispatchInput:
    """Valid 24h PV + battery instance. Override any field by keyword."""
    batt = {
        "capacity_kwh": 10.0,
        "p_charge_max_kw": 5.0,
        "p_discharge_max_kw": 5.0,
        "eff_charge": 0.95,
        "eff_discharge": 0.95,
        "soc_min": 0.1,
        "soc_max": 0.9,
        "soc_init": 0.5,
    }
    batt.update(battery or {})

    fields = {
        "dt_h": 1.0,
        "load_kw": [load_kw] * hours,
        "pv_kw": _pv_profile(hours, pv_peak_kw),
        "price_buy": [_buy_price(h % 24) for h in range(hours)],
        "price_sell": [0.05] * hours,
        "grid_import_max_kw": 10.0,
        "grid_export_max_kw": 5.0,
        "battery": BatteryParams(**batt),
    }
    fields.update(overrides)
    return DispatchInput(**fields)
