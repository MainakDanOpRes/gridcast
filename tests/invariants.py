from gridcast.dispatch.schemas import DispatchInput, DispatchResult

TOL = 1e-4


def assert_invariants(inp: DispatchInput, res: DispatchResult) -> None:
    n, b, dt = inp.horizon, inp.battery, inp.dt_h
    cap = b.capacity_kwh

    # For each of these result fields, make sure its list contains
    # exactly one value for every time step before we start processing the time steps.
    for name in (
        "battery_charge_kw",
        "battery_discharge_kw",
        "soc",
        "grid_import_kw",
        "grid_export_kw",
        "pv_used_kw",
    ):
        assert len(getattr(res, name)) == n, f"{name} has wrong length"

    for k in range(n):
        # power balance at the bus
        supply = res.pv_used_kw[k] + res.grid_import_kw[k] + res.battery_discharge_kw[k]
        demand = inp.load_kw[k] + res.grid_export_kw[k] + res.battery_charge_kw[k]
        assert abs(supply - demand) < TOL, f"balance broken at k = {k}"

        # soc bounds
        assert b.soc_min - TOL <= res.soc[k] <= b.soc_max + TOL, f"SOC out of bounds at k={k}"

        # no simultaneous charge and discharge
        assert min(res.battery_charge_kw[k], res.battery_discharge_kw[k]) < TOL

        # Physical limits
        assert res.pv_used_kw[k] <= inp.pv_kw[k] + TOL, "PV exceeds forecast"
        assert res.grid_import_kw[k] <= inp.grid_import_max_kw + TOL
        assert res.grid_export_kw[k] <= inp.grid_export_max_kw + TOL
        assert res.battery_charge_kw[k] <= b.p_charge_max_kw + TOL
        assert res.battery_discharge_kw[k] <= b.p_discharge_max_kw + TOL

    # SOC dynamics
    assert abs(res.soc[0] - b.soc_init) < TOL, "initial SOC not respected"
    for k in range(n - 1):
        expected = (
            res.soc[k]
            + dt
            * (
                b.eff_charge * res.battery_charge_kw[k]
                - res.battery_discharge_kw[k] / b.eff_discharge
            )
            / cap
        )
        assert abs(res.soc[k + 1] - expected) < TOL, f"SOC dynamics broken at k={k}"
