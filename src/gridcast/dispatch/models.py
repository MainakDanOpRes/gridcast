import time as _time
from typing import Any
import pulp

from omegalpes.energy.energy_nodes import EnergyNode
from omegalpes.energy.units.consumption_units import FixedConsumptionUnit, VariableConsumptionUnit
from omegalpes.energy.units.production_units import FixedProductionUnit, VariableProductionUnit
from omegalpes.energy.units.storage_units import StorageUnit
from omegalpes.general.optimisation.model import OptimisationModel
from omegalpes.general.optimisation.elements import Objective
from omegalpes.energy.energy_types import elec
from omegalpes.general.time import TimeUnit

from .schemas import DispatchInput, SolveStatus

# --------------------------------------------------------------------------
# Status adapter: pure function of solver codes, testable without a solver
# --------------------------------------------------------------------------
def status_from_codes(status: int | None, sol_status: int | None) -> SolveStatus:
    """Map PuLP (status, sol_status) to our enum. Unknown/contradictory -> ERROR."""
    if status == pulp.LpStatusInfeasible or sol_status == pulp.LpSolutionInfeasible:
        return SolveStatus.INFEASIBLE
    if status == pulp.LpStatusOptimal:
        if sol_status == pulp.LpSolutionIntegerFeasible:
            return SolveStatus.FEASIBLE  # time/gap limit hit, optimality unproven
        if sol_status in (pulp.LpSolutionOptimal, None):
            return SolveStatus.OPTIMAL
        return SolveStatus.ERROR  # "optimal" but no solution: contradictory
    if status == pulp.LpStatusNotSolved:
        return SolveStatus.TIMEOUT  # stopped without an incumbent
    return SolveStatus.ERROR  # unbounded, undefined, unknown codes
 
 
def _extract_status(model: OptimisationModel) -> SolveStatus:
    return status_from_codes(model.status, getattr(model, "sol_status", None))

# --------------------------------------------------------------------------
# Model construction
# --------------------------------------------------------------------------

def build_model(inp: DispatchInput):
    b = inp.battery
    t = TimeUnit(periods=inp.horizon, dt=inp.dt_h)

    load = FixedConsumptionUnit(time=t, name="load", p=inp.load_kw)
    pv = VariableProductionUnit(time=t, name="pv", p_min=0, p_max=inp.pv_kw)
    grid_in = VariableProductionUnit(time=t, name="grid_in", 
                                     p_min=0, p_max=inp.grid_import_max_kw)
    grid_out = VariableConsumptionUnit(time=t, name="grid_out", 
                                       p_min=0, p_max=inp.grid_export_max_kw)

    batt = StorageUnit(time=t, name="battery", 
                       pc_max=b.p_charge_max_kw, pd_max=b.p_discharge_max_kw,
                       eff_c=b.eff_charge, eff_d=b.eff_discharge,
                       soc_min=b.soc_min, soc_max=b.soc_max,
                       e_0=b.soc_init*b.capacity_kwh,
                       capacity=b.capacity_kwh,
                       e_f=None if b.soc_final_min is None else b.soc_final_min*b.capacity_kwh)

    grid_in._add_operating_cost(inp.price_buy)
    grid_in.minimize_operating_cost()
    grid_out._add_operating_cost(inp.price_sell)
    grid_out.minimize_operating_cost(weight = -1)

    node = EnergyNode(time=t, name="bus", energy_type=elec)

    node.connect_units(load, pv, grid_in, grid_out, batt)

    model = OptimisationModel(time=t, name="dispatch")
    model.add_nodes(node)
    return model,  {"pv": pv, "grid_in": grid_in, "grid_out": grid_out, "batt": batt}

    


# --------------------------------------------------------------------------
# Reading results
# --------------------------------------------------------------------------
def _series(quantity: Any, horizon: int) -> list[float]:
    """Read a solved Quantity as a list of floats (works for list or int-keyed dict).
 
    Only call this AFTER checking the solve status: on a failed solve, quantities
    still hold their initial zeros and would look like a valid schedule.
    """
    vals = [quantity.value[t] for t in range(horizon)]
    if any(v is None for v in vals):  # varValue is None if var never entered the LP
        raise ValueError("solved quantity contains None")
    return [float(v) for v in vals]
 
 
# --------------------------------------------------------------------------
# Solving
# --------------------------------------------------------------------------
def solve_model(
    model: OptimisationModel,
    handles: dict[str, Any],
    *,
    time_limit_s: float,
    mip_gap: float,
) -> float:
    """Solve with solver-enforced limits. Returns elapsed seconds.
 
    PULP_CBC_CMD is deprecated in PuLP 4 (we pin pulp<4). Migration path:
    `pulp[cbc]` + COIN_CMD, changed here only.
    """
    solver = pulp.PULP_CBC_CMD(timeLimit=time_limit_s, gapRel=mip_gap, msg=False)
    t0 = _time.perf_counter()
    model.solve_and_update(solver=solver)  # swallows failures: always check status
    return _time.perf_counter() - t0