import logging
import pulp

from .models import _extract_status, _series, build_model, solve_model
from .schemas import DispatchInput, DispatchResult, SolveStatus

log = logging.getLogger(__name__)
_SUCCESS = {SolveStatus.OPTIMAL, SolveStatus.FEASIBLE}


def solve_dispatch(inp: DispatchInput, *, time_limit_s: float = 30.0,
                   mip_gap: float = 0.01) -> DispatchResult:
    try:
        model, h = build_model(inp)
        elapsed = solve_model(model, h, time_limit_s=time_limit_s, mip_gap=mip_gap)
        status = _extract_status(model)
        codes = f"status={model.status} sol_status={getattr(model, 'sol_status', None)}"

        if status not in _SUCCESS:
            return DispatchResult(status=status, solve_time_s=elapsed, message=codes)

        n, cap = inp.horizon, inp.battery.capacity_kwh
        return DispatchResult(
            status=status, solve_time_s=elapsed, message=codes,
            objective_eur=float(pulp.value(model.objective)),
            battery_charge_kw=_series(h["batt"].charge.p, n),      # verify names
            battery_discharge_kw=_series(h["batt"].discharge.p, n),
            soc=[e / cap for e in _series(h["batt"].e, n)],
            grid_import_kw=_series(h["grid_in"].p, n),
            grid_export_kw=_series(h["grid_out"].p, n),
            pv_used_kw=_series(h["pv"].p, n),
        )
    except Exception as exc:
        log.exception("dispatch solve crashed")
        return DispatchResult(status=SolveStatus.ERROR, message=f"{type(exc).__name__}: {exc}")