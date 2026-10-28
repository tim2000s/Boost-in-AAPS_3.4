"""Dasiglucagon dose factor relative to native glucagon, from the 30-minute glucose rise.

Source: Hovelmann et al. 2019, Diabetes Obes Metab 21:601 (doi 10.1111/dom.13562), Table 2,
euglycaemia, mean plasma glucose excursion at 30 min (CE30min, mg/dL). For each native dose,
the dasiglucagon dose giving the same rise is found by log-linear interpolation in dose; the
factor is that dose over the native one. Group means only (n = 10 to 17), so no interval.
"""
from math import exp, log

NATIVE = {0.03: 30.1, 0.08: 48.6, 0.2: 70.6}
DASI = {0.03: 38.7, 0.08: 55.9, 0.2: 72.5}


def dasi_dose_for(rise):
    ds = sorted(DASI)
    for a, b in zip(ds, ds[1:]):
        if rise <= DASI[b] or b == ds[-1]:
            slope = (DASI[b] - DASI[a]) / (log(b) - log(a))
            return exp(log(a) + (rise - DASI[a]) / slope)


if __name__ == "__main__":
    for dose, rise in NATIVE.items():
        eq = dasi_dose_for(rise)
        print(f"native {dose} mg, rise {rise} mg/dL: dasiglucagon {eq:.4f} mg, factor {eq / dose:.2f}")
