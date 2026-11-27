"""R12: algebraic identifiability checks only; no device I/O, no SOC estimator."""
from dataclasses import dataclass
from math import isclose

@dataclass(frozen=True)
class State:
    rated_ah: float
    measured_cmax_ah: float
    remaining_ah: float
    def __post_init__(self):
        if not (self.rated_ah > 0 and 0 < self.measured_cmax_ah and 0 <= self.remaining_ah <= self.measured_cmax_ah):
            raise ValueError("Invalid hypothetical battery state")
    @property
    def soc_percent(self):
        return self.remaining_ah * 100.0 / self.measured_cmax_ah
    @property
    def soh_capacity_percent(self):
        return self.measured_cmax_ah * 100.0 / self.rated_ah
    @property
    def remaining_as_nominal_percent(self):
        return self.remaining_ah * 100.0 / self.rated_ah

def integrate_bias_ah(sensor_offset_a: float, hours: float) -> float:
    if hours < 0:
        raise ValueError("Elapsed time cannot be negative")
    return sensor_offset_a * hours

def main():
    a = State(72.0,42.0,21.0)
    b = State(72.0,70.0,21.0)
    assert isclose(a.soc_percent,50)
    assert isclose(a.soh_capacity_percent,58.3333333333333)
    assert isclose(a.remaining_as_nominal_percent,29.1666666666667)
    assert isclose(b.soc_percent,30)
    assert isclose(a.remaining_as_nominal_percent,b.remaining_as_nominal_percent)
    assert isclose(integrate_bias_ah(0.1,7*24),16.8)
    assert isclose(integrate_bias_ah(0.1,7*24)*100/72,23.3333333333333)
    try:
        State(72,35,42)
        raise AssertionError("Invalid state accepted")
    except ValueError:
        pass
    print("R12 OFFLINE PASS: identical remaining Ah can imply SOC 50% or 30%;")
    print("     0.1 A sensor bias over 7 days -> 16.8 Ah integration error (23.3% of 72Ah).")
    print("     These are algebraic examples, not a calibrated SOC/SOH estimator.")

if __name__ == "__main__":
    main()