# Intensity-class calibration experiment (`k-intensity`, 2026-11-14)

Question: is the phase-rate bias (quiet years −2% to −4%, 2020 at −8.6%) reduced by
fitting k separately for high- and low-intensity cell-days?

Method: 2013–2017 fit (`CALIBRATION_YEARS`), 2018–2021 held out (`VALIDATION_YEARS`),
region-wide outage days excluded on both sides, terciles from the calibration years
(Aqua+SNPP pooled), shrinkage m=30 per the D14 hierarchy.

Baseline (current k): 2018 −4.36, 2019 −2.71, 2020 −8.58, 2021 −2.45 → spread (max−min) 6.13.

Variants evaluated on the held-out years:

| Variant | 2018 | 2019 | 2020 | 2021 | spread (max−min) | spread (max|bias|−min|bias|) |
|---|---|---|---|---|---|---|
| FRP tercile, 3 bands (low ≤ 4.58, mid ≤ 13.69) | +1.69 | −9.44 | −10.65 | −3.22 | 12.34 | 8.96 |
| Two classes: high vs rest | +1.82 | −1.17 | −6.83 | +1.11 | 8.65 | 5.72 |
| `n_detections` density (1 = single, ≥ 2 = cluster) | −8.21 | −5.92 | −11.28 | −4.64 | 7.16 | 6.65 |

Band-split ratios over the calibration years: low ≈ 1,278,119 SNPP vs 4,278 Aqua
(k ≈ 297 region-wide — clearly Pathological extrapolation), mid ≈ 5.6, high ≈ 1.76.
The low band is nearly invisible to Aqua (0.3% of SNPP low cell-days), so any low-band
correction is a huge amplification of a thin sample.

Conclusion: **no merge-worthy gain.** The tercile and density variants are worse; the
two-class variant's "win" (5.72) exists only under the |bias| reading, flips 2018's sign,
and does not survive the plain max−min reading (6.13 → 8.65). The residual bias in 2020 is
not explained by detection-efficiency scaling with fire intensity; likely remaining causes
are specific to that outage window (diminished Aqua performance Aug–Sep 2020).

If another angle is wanted: fit k per month with April–August only (drop the rest from the
fit) or drop 2020 entirely from the fit set, and check spread again. Or just accept
validation years as reported.
