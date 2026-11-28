"""R20-A02: deterministic sensitivity arithmetic. Offline research only; no device I/O."""
from math import sqrt, isclose

Z95 = 1.96

def paired_change_sigma(single_measurement_sigma, correlation=0.0):
    assert single_measurement_sigma >= 0
    assert -1.0 <= correlation <= 1.0
    return single_measurement_sigma * sqrt(2.0 * (1.0 - correlation))

def did_sigma(single_measurement_sigma, correlation=0.0):
    # Independent groups, each with its own pre/post pair; rho within each pair.
    return sqrt(2.0) * paired_change_sigma(single_measurement_sigma, correlation)

def halfwidth_95(sigma):
    return Z95 * sigma

def synthetic_case(nominal_ah=72.0, hypothetical_standard_fraction=0.02):
    assert nominal_ah > 0 and hypothetical_standard_fraction >= 0
    sigma = nominal_ah * hypothetical_standard_fraction
    return {
        "sigma_one_Ah": sigma,
        "pre_post_95_Ah": halfwidth_95(paired_change_sigma(sigma)),
        "did_one_per_arm_95_Ah": halfwidth_95(did_sigma(sigma)),
    }

if __name__ == "__main__":
    x = synthetic_case()
    assert isclose(x["sigma_one_Ah"], 1.44, abs_tol=1e-12)
    assert isclose(x["pre_post_95_Ah"], 1.96 * 1.44 * sqrt(2), rel_tol=1e-12)
    assert isclose(x["did_one_per_arm_95_Ah"], 1.96 * 2 * 1.44, rel_tol=1e-12)
    assert isclose(paired_change_sigma(1.44, correlation=1), 0.0, abs_tol=1e-12)
    assert paired_change_sigma(1.44, correlation=-0.5) > paired_change_sigma(1.44, correlation=0)
    assert x["pre_post_95_Ah"] > 3.0 and x["pre_post_95_Ah"] < 8.0
    print("R20_A02_ANALYTIC_PASS")
    print("HYPOTHETICAL_NOT_MEASURED sigma_one_Ah=%.4f prepost_95_halfwidth_Ah=%.4f did_95_halfwidth_Ah=%.4f" % (x["sigma_one_Ah"],x["pre_post_95_Ah"],x["did_one_per_arm_95_Ah"]))
    print("NO_REFERENCE_CAPACITY_INFERRED_NO_CHARGER_CONTROL")
