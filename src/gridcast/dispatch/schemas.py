from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, Field, model_validator

Finite = Annotated[float, Field(allow_inf_nan=False)]
NonNegFinite = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class SolveStatus(StrEnum):
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"  # solution found, optimality not proven (time limit)
    INFEASIBLE = "infeasible"
    TIMEOUT = "timeout"  # no solution found within the limit
    ERROR = "error"  # solver/library failure, not a model property


class BatteryParams(BaseModel):
    capacity_kwh: float = Field(gt=0)
    p_charge_max_kw: float = Field(gt=0)
    p_discharge_max_kw: float = Field(gt=0)
    eff_charge: float = Field(gt=0, le=1)
    eff_discharge: float = Field(gt=0, le=1)
    soc_min: float = Field(ge=0, le=1, default=0.1)
    soc_max: float = Field(ge=0, le=1, default=0.9)
    soc_init: float = Field(ge=0, le=1, default=0.5)
    soc_final_min: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        if not self.soc_min < self.soc_max:
            raise ValueError("soc_min must be < soc_max")
        if not self.soc_min <= self.soc_init <= self.soc_max:
            raise ValueError("soc_init must lie within [soc_min, soc_max]")
        if self.soc_final_min is not None and not (
            self.soc_min <= self.soc_final_min <= self.soc_max
        ):
            raise ValueError("soc_final_min must lie within [soc_min, soc_max]")
        return self


class DispatchInput(BaseModel):
    dt_h: float = Field(gt=0, le=1, default=1.0)
    load_kw: list[NonNegFinite]
    pv_kw: list[NonNegFinite]  # forecast = max available PV power
    price_buy: list[Finite]  # EUR/kWh
    price_sell: list[Finite]  # EUR/kWh
    grid_import_max_kw: float = Field(gt=0)
    grid_export_max_kw: float = Field(ge=0)
    battery: BatteryParams

    @model_validator(mode="after")
    def _check_lengths(self) -> Self:
        lengths = {len(self.load_kw), len(self.pv_kw), len(self.price_buy), len(self.price_sell)}
        if len(lengths) != 1 or 0 in lengths:
            raise ValueError("load, pv and price series must be non-empty and equal length")
        return self

    @property
    def horizon(self) -> int:
        return len(self.load_kw)


class DispatchResult(BaseModel):
    status: SolveStatus
    message: str = ""
    objective_eur: float | None = None
    solve_time_s: float | None = None
    battery_charge_kw: list[float] = []
    battery_discharge_kw: list[float] = []
    soc: list[float] = []  # fraction of capacity, length = horizon
    grid_import_kw: list[float] = []
    grid_export_kw: list[float] = []
    pv_used_kw: list[float] = []
