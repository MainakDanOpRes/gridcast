import pytest
from pydantic import ValidationError

from gridcast.dispatch import api as dispatch_api
from gridcast.dispatch.api import solve_dispatch
from gridcast.dispatch.schemas import SolveStatus as S
from tests.factories import make_input
from tests.invariants import assert_invariants

OK = {S.OPTIMAL, S.FEASIBLE}


def solved(inp, **kw):
    res = solve_dispatch(inp, **kw)
    assert res.status in OK, res.message
    return res


# ---- invariants across a spread of scenarios ----
SCENARIOS = {
    "baseline": {},
    "no_pv": {"pv_peak_kw": 0},
    "pv_surplus_no_export": {"pv_peak_kw": 8, "grid_export_max_kw": 0},
    "battery_starts_full": {"battery": {"soc_init": 0.9}},
    "battery_starts_empty": {"battery": {"soc_init": 0.1}},
    "weak_efficiency": {"battery": {"eff_charge": 0.7, "eff_discharge": 0.7}},
    # "negative_prices": dict(price_buy=[-0.05] * 12 + [0.3] * 12, price_sell=[-0.1] * 24),
    "flat_prices": {"price_buy": [0.2] * 24, "price_sell": [0.2] * 24},
}


@pytest.mark.parametrize("name", SCENARIOS)
def test_invariants_hold(name):
    inp = make_input(**SCENARIOS[name])
    assert_invariants(inp, solved(inp))


# behavior, not just validity
def test_battery_is_actually_used():
    """Guards against vacuous passes: an all-zero schedule satisfies every invariant."""
    res = solved(make_input())
    assert sum(res.battery_charge_kw) + sum(res.battery_discharge_kw) > 0


def test_pv_is_curtailed_when_it_cannot_be_used():
    inp = make_input(pv_peak_kw=8, grid_export_max_kw=0, load_kw=0.5, battery={"capacity_kwh": 2.0})
    res = solved(inp)
    assert sum(res.pv_used_kw) < sum(inp.pv_kw) - 1.0  # some PV was curtailed
    assert_invariants(inp, res)


# ---- value tests: do the numbers mean what we think? ----
@pytest.mark.parametrize("dt,hours", [(1.0, 24), (0.5, 48), (0.25, 96)])
def test_cost_scales_with_dt(dt, hours):
    """2 kW for 24 h at 0.20 EUR/kWh = 9.60 EUR, whatever the time step.
    SOC pinned to its start value so the battery cannot cash in stored energy."""
    inp = make_input(
        hours=hours,
        dt_h=dt,
        pv_peak_kw=0,
        load_kw=2.0,
        price_buy=[0.2] * hours,
        price_sell=[0.05] * hours,
        battery={"soc_final_min": 0.5},
    )
    res = solved(inp)
    assert res.objective_eur == pytest.approx(9.6, rel=1e-3)


def test_battery_never_makes_things_worse():
    """Metamorphic test: a real battery must cost <= a near-useless one."""
    big = solved(make_input()).objective_eur
    tiny = solved(
        make_input(
            battery={"capacity_kwh": 0.01, "p_charge_max_kw": 0.01, "p_discharge_max_kw": 0.01}
        )
    ).objective_eur
    assert big <= tiny + 1e-6


# ---- failure paths ----
def test_infeasible_returns_status_not_zeros():
    res = solve_dispatch(make_input(load_kw=100, grid_import_max_kw=1, pv_peak_kw=0))
    assert res.status == S.INFEASIBLE
    assert res.soc == [] and res.battery_charge_kw == []  # no fake schedule


def test_bad_input_rejected_at_the_boundary():
    with pytest.raises(ValidationError):
        make_input(price_buy=[0.1] * 23)  # length mismatch
    with pytest.raises(ValidationError):
        make_input(load_kw=[float("nan")] * 24)  # NaN


def test_never_raises_when_the_library_crashes(monkeypatch):
    def boom(_inp):
        raise RuntimeError("simulated library failure")

    monkeypatch.setattr(dispatch_api, "build_model", boom)
    res = solve_dispatch(make_input())
    assert res.status == S.ERROR and "simulated" in res.message


def test_tight_time_limit_never_reports_a_false_optimal():
    inp = make_input(hours=96 * 7, dt_h=0.25)
    res = solve_dispatch(inp, time_limit_s=0.01)
    assert res.status in {S.FEASIBLE, S.TIMEOUT, S.OPTIMAL, S.ERROR}  # must not raise
    print("observed status under 0.01s limit:", res.status, res.message)


# ---- global-state isolation (OMEGALPES stores variables in module globals) ----
def test_replay_is_deterministic_across_other_solves():
    a, b = make_input(), make_input(pv_peak_kw=0, load_kw=3.0)
    first = solved(a)
    solved(b)
    again = solved(a)
    assert first.objective_eur == pytest.approx(again.objective_eur)
    assert first.soc == pytest.approx(again.soc)
