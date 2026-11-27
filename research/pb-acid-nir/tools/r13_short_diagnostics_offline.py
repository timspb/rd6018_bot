"""R13 offline identifiability demonstration; no physical battery or connection."""
from dataclasses import dataclass
from math import exp, isclose, isfinite

@dataclass(frozen=True)
class CellRestReference:
    rated_ah: float
    soc_start: float
    soc_end: float
    hours: float
    mean_cell_voltage_v: float

    def compute(self):
        if not all(isfinite(x) for x in vars(self).values()):
            raise ValueError("all values must be finite")
        if self.rated_ah <= 0 or self.hours <= 0 or self.mean_cell_voltage_v <= 0:
            raise ValueError("invalid physical quantities")
        if not (0 <= self.soc_end <= self.soc_start <= 1):
            raise ValueError("invalid inferred SOC range")
        delta_ah = self.rated_ah * (self.soc_start - self.soc_end)
        avg_a = delta_ah / self.hours
        if avg_a <= 0:
            return {"delta_ah": 0, "equivalent_a": 0, "equivalent_ohms": None}
        return {"delta_ah": delta_ah, "equivalent_a": avg_a,
                "equivalent_ohms": self.mean_cell_voltage_v / avg_a}

def apparent_voltage(t_hours, delta_u_v=0.080, end_hour=72.0, tau_h=12.0, model="loss"):
    """Two purely synthetic mechanisms with the same terminal U at end_hour.

    The loss model is linear; relaxation is exponential. Neither is calibrated.
    """
    if not (0 <= t_hours <= end_hour and end_hour > 0 and tau_h > 0):
        raise ValueError("invalid time")
    if model == "loss":
        fraction = t_hours / end_hour
    elif model == "relaxation":
        fraction = (1-exp(-t_hours/tau_h))/(1-exp(-end_hour/tau_h))
    else:
        raise ValueError("unknown synthetic mechanism")
    return 12.90 - delta_u_v * fraction

def main():
    model=CellRestReference(rated_ah=35, soc_start=0.575, soc_end=0.133,
                            hours=72, mean_cell_voltage_v=1.997).compute()
    assert isclose(model["delta_ah"], 15.47, rel_tol=0, abs_tol=1e-10)
    assert isclose(model["equivalent_a"], 0.214861111111, abs_tol=1e-9)
    assert isclose(model["equivalent_ohms"], 9.29425, abs_tol=0.01)
    assert isclose(apparent_voltage(0, model="loss"),12.9)
    assert isclose(apparent_voltage(0, model="relaxation"),12.9)
    assert isclose(apparent_voltage(72,model="loss"),12.82)
    assert isclose(apparent_voltage(72,model="relaxation"),12.82)
    assert not isclose(apparent_voltage(12,model="loss"),
                       apparent_voltage(12,model="relaxation"),abs_tol=0.001)
    try:
        CellRestReference(35,0.1,0.4,72,2.0).compute()
        raise AssertionError("Invalid SOC sequence accepted")
    except ValueError:
        pass
    print(f"R13 OFFLINE PASS: 35Ah model lost {model['delta_ah']:.2f}Ah in 72h,"
          f" equivalent {model['equivalent_a']*1000:.1f}mA,"
          f" {model['equivalent_ohms']:.2f}ohm across ONE cell.")
    print("R13 OFFLINE PASS: different synthetic mechanisms have identical U0 and U72;"
          " no diagnosis from one voltage interval.")
    print("No battery I/O, no firmware changes, no fault induction.")
if __name__=="__main__":
    main()