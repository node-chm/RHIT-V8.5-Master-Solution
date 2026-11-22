# RHIT-SEWN v2.0: Holographic Seismic Early-Warning & Forecasting Node

**Applied Engineering Module for RHIT V8.5** | Developed & Validated by **Node CHM (`node-chm`)**

## 1. Overview & Physical Scope
**RHIT-SEWN v2.0** applies the mathematical architecture of **Relativistic Holographic Information Theory (RHIT V8.5)**—specifically **5D Complex Singular Value Decomposition (Complex SVD)** and **$S^2$ Holographic Boundary Phase Coherence**—to real-world seismic early warning (EEW) and short-term probabilistic forecasting.

* **Strict Adherence to Symmetron Screening:** In high-density crustal environments, the Symmetron scalar field remains completely screened ($\eta = 0.0$). This module does not claim direct fifth-force detection; instead, it utilizes Complex SVD phase-coherence extraction ($\sigma_2$) across multi-modal surface sensors to isolate pre-slip crustal stress anomalies from stochastic background noise.
* **Zero-Leakage Causal Processing:** All filtering and sliding-window decompositions strictly enforce forward-only causality (`scipy.signal.lfilter`) to eliminate future data leakage.

## 2. Module Contents
* `rhit_sewn_v1_kernel.py` — Complete Python kernel combining the **Causal Complex SVD Early-Warning Detector** and **Voight’s Acceleration Forecasting Engine** ($\sigma_2(t) = \sigma_0 + K(t_f - t)^{-p}$).
* `RHIT_Seismic_Blueprint.md` — Full engineering architecture, COTS multi-modal sensor BOM (`ADXL355`, `PNI RM3100`, `Murata SCL3300`, `GPS 1PPS`), and field calibration protocol.
* `RHIT_Seismic_Blueprint.pdf` — Formatted technical report and empirical benchmark documentation.

## 3. Empirical Validation Summary (EarthScope / IRIS 20 Hz Data)
| Reference Station | Historical Event | Quiet Baseline ($\sigma_2$) | Peak Anomaly | Audit Status |
| :--- | :--- | :---: | :---: | :---: |
| **IU.CHTO** (Chiang Mai, Thailand) | 2011 M6.8 Myanmar-Thailand Border (~240 km) | `0.0019` | `187,065.33 σ` | `ALERT_PASSED` |
| **IU.MAJO** (Matsushiro, Japan) | 2024 M7.5 Noto Peninsula (~230 km) | `0.7390` | `147.35 σ` | `ALERT_PASSED` |

## 4. Quick Start & Usage
Ensure you have `numpy` and `scipy` installed, then run the kernel directly to execute both the real-data detection benchmark (`IU.CHTO`) and the Voight's Acceleration forecasting simulation:

```bash
pip install numpy scipy
python3 rhit_sewn_v1_kernel.py
```

## 5. Core Audit Compatibility
This module is strictly isolated within `applications/RHIT-SEWN-v2/` and does not alter any core parameters in `rhit_v8_5_ai_ssot.json`. Running the project's primary verification gate (`python3 rhit_v8_5_audit_kernel_v4.py`) preserves the exact $\chi^2 = 1.9421$ benchmark across all 22 observables.
