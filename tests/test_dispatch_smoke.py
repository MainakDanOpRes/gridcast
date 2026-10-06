# tests/test_dispatch_smoke.py
from gridcast.dispatch.api import solve_dispatch
from gridcast.dispatch.schemas import SolveStatus
from tests.factories import make_input


def test_solves_and_discharges_in_the_evening():
    inp = make_input()
    res = solve_dispatch(inp)

    assert res.status in {SolveStatus.OPTIMAL, SolveStatus.FEASIBLE}
    assert len(res.soc) == inp.horizon
    assert sum(res.battery_discharge_kw[17:22]) > 0   # evening peak at 0.30