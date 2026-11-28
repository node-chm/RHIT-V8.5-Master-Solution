"""
RHIT V9.0 - Spherical Jeans Equation Solver for C1-Smooth Soliton & NFW Halos
File: rhit_v9_jeans_solver.py

Run from repository root (requires numpy, scipy, pandas):
    python3 rhit_v9_jeans_solver.py

Evaluates line-of-sight luminosity-weighted velocity dispersion <sigma_los^2>
via the isotropic spherical Jeans equation (Plummer stellar tracer) for:
1. NFW Halo (Jeans 2p)
2. C1-Smooth Thomas-Fermi Soliton + NFW Halo (Jeans 3p)
Tested on both Full LVDB samples and Clean dSph subsamples (excluding massive
rotation-supported systems and extreme tidally disrupting outliers).
Does not alter any of the 22 fundamental SSOT observables.
"""
import math
import warnings
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
import rhit_v9_0_audit_kernel as K
import rhit_v9_fit_controls_c1 as C1

warnings.filterwarnings("ignore")

# Massive rotation-supported / tidally disrupting systems outside spherical Jeans equilibrium
NON_EQUILIBRIUM_OUTLIERS = {
    "LMC",
    "SMC",
    "M 32",
    "NGC 205",
    "NGC 147",
    "NGC 185",
    "IC 1613",
    "WLM",
    "Sagittarius",
    "Antlia II",
    "Crater II",
    "Bootes III",
    "Tucana III",
}


class SphericalJeansSolver:
    """
    Fast vectorized isotropic Spherical Jeans solver for a Plummer stellar tracer
    embedded in a composite (Dark Matter + Stellar) potential:
        <sigma_los^2> = (2 G / I_tot) * int_0^inf [ M_tot(r) * nu_*(r) / r^2 * sqrt(r^2 - R^2) ] ...
    Using the exact Abel-projected kernel for an isotropic Plummer sphere (a_p = r_half):
        sigma_los^2(R) = (2 G / Sigma_*(R)) * int_R^inf [ nu_*(r) * M_tot(r) / r^2 * sqrt(r^2 - R^2) dr ]
    Averaged over the 2D projected light distribution I(R) = L / (pi a_p^2 (1 + R^2/a_p^2)^2),
    swapping the order of integration yields a clean 1D radial integral:
        <sigma_los^2> = (4 G / (3 a_p)) * int_0^inf [ (r / a_p)^3 / (1 + (r / a_p)^2)^3 * (M_tot(r) / r) dr ]
    """

    def __init__(self, g_astro, n_grid=240):
        self.g_astro = g_astro
        # Dimensionless radial integration grid u = r / a_p in log-space [1e-3, 1e3]
        self.u = np.logspace(-3.0, 3.0, n_grid)
        self.du = np.gradient(self.u)
        # Exact isotropic Plummer luminosity-weighted kernel W(u)
        # Satisfies int_0^inf W(u) du = 1/3 for a constant-mass / point-like scaling check
        self.kernel_w = (4.0 / 3.0) * (self.u ** 2) / ((1.0 + self.u ** 2) ** 3) * self.du

    def plummer_enclosed_mass(self, r, a_p, m_star):
        """Enclosed stellar mass M_*(r) = M_* * r^3 / (r^2 + a_p^2)^(3/2)."""
        x = r / a_p
        return m_star * (x ** 3) / ((1.0 + x ** 2) ** 1.5)

    def sigma_los_nfw(self, kern, r_half, m_star, log10_m0, alpha_shmr):
        """Luminosity-weighted <sigma_los> for standard NFW + Plummer stars."""
        m200 = (10.0 ** log10_m0) * ((m_star / 1e5) ** alpha_shmr)
        c200 = 15.0 * ((m200 / 1e9) ** (-0.1))

        # Shape: (N_galaxies, N_grid)
        r_grid = r_half[:, None] * self.u[None, :]
        m_dm = kern.nfw_enclosed_mass(r_grid, m200[:, None], c200[:, None])
        m_st = self.plummer_enclosed_mass(r_grid, r_half[:, None], m_star[:, None])
        m_tot = m_dm + m_st

        # Integral over u = r / r_half: (G / r_half) * sum(W(u) * M_tot(r))
        sig2 = (self.g_astro / r_half) * np.sum(m_tot * self.kernel_w[None, :], axis=1)
        return np.sqrt(np.maximum(sig2, 1e-12))

    def sigma_los_c1_soliton(self, kern, r_half, m_star, log10_m_floor, alpha_shmr, log10_rho_crit, r_vac_pc):
        """Luminosity-weighted <sigma_los> for C1-Smooth Thomas-Fermi Soliton + NFW + Plummer stars."""
        m200 = (10.0 ** log10_m_floor) * (1.0 + ((m_star / 1e6) ** alpha_shmr))
        c200 = 15.0 * ((m200 / 1e9) ** (-0.1))

        # Symmetron density-dependent core modulation evaluated at r_half
        rho_tot_est = (kern.nfw_enclosed_mass(r_half, m200, c200) + 0.5 * m_star) / (
            (4.0 / 3.0) * np.pi * (r_half ** 3)
        )
        sym = 1.0 / (1.0 + (rho_tot_est / (10.0 ** log10_rho_crit)) ** 2)
        r_eff = kern.R_TF_MIN_PC + (r_vac_pc - kern.R_TF_MIN_PC) * sym

        # Shape: (N_galaxies, N_grid)
        r_grid = r_half[:, None] * self.u[None, :]
        m_dm, _ = C1.c1_mass_vec(r_grid, r_eff[:, None], m200[:, None], c200[:, None])
        m_st = self.plummer_enclosed_mass(r_grid, r_half[:, None], m_star[:, None])
        m_tot = m_dm + m_st

        sig2 = (self.g_astro / r_half) * np.sum(m_tot * self.kernel_w[None, :], axis=1)
        return np.sqrt(np.maximum(sig2, 1e-12))



    def nfw_density(self, r, m200, c200):
        rc = 1.36e-7
        r200 = ((3.0 * m200) / (4.0 * np.pi * 200.0 * rc)) ** (1.0 / 3.0)
        rs = r200 / c200
        fc = np.log(1.0 + c200) - c200 / (1.0 + c200)
        rho_s = m200 / (4.0 * np.pi * (rs ** 3) * fc)
        x = r / rs
        return rho_s / (x * ((1.0 + x) ** 2))

    def cored_soliton_nfw_mass(self, kern, r_grid, r_c, m200, c200, alpha_t=3.0):
        r_t = alpha_t * r_c
        rho_nfw_rt = self.nfw_density(r_t, m200[:, None], c200[:, None])
        sol_factor_rt = (1.0 + 0.091 * (alpha_t ** 2)) ** (-8.0)
        rho_c = rho_nfw_rt / sol_factor_rt

        k = 0.091
        sqrt_k = math.sqrt(k)

        def soliton_m_enc(rad):
            y = sqrt_k * (rad / r_c)
            y2 = y ** 2
            denom = (1.0 + y2) ** 7
            term_atan = (33.0 / 14336.0) * np.arctan(y)
            poly = (
                -33.0 * (y ** 13)
                - 231.0 * (y ** 11)
                - 693.0 * (y ** 9)
                - 1155.0 * (y ** 7)
                - 1155.0 * (y ** 5)
                - 693.0 * (y ** 3)
                + 231.0 * y
            ) / (14336.0 * denom)
            integral_y = term_atan + poly
            return 4.0 * np.pi * rho_c * ((r_c / sqrt_k) ** 3) * integral_y

        r_capped = np.minimum(r_grid, r_t)
        m_in = soliton_m_enc(r_capped)
        m_out = np.where(
            r_grid > r_t,
            kern.nfw_enclosed_mass(r_grid, m200[:, None], c200[:, None])
            - kern.nfw_enclosed_mass(r_t, m200[:, None], c200[:, None]),
            0.0,
        )
        return m_in + m_out


def fit_best(loss_fn, starts):
    best_res = None
    for s in starts:
        res = minimize(
            loss_fn,
            s,
            method="Nelder-Mead",
            options={"maxiter": 6000, "xatol": 1e-6, "fatol": 1e-6},
        )
        if best_res is None or res.fun < best_res.fun:
            best_res = res
    return best_res


def main():
    kern = K.RHITV90IntegratedAuditKernel()
    _, audit_summary = kern.self_audit()
    res = kern.evaluate()
    g_n = res["metrics"]["G_N"]["pred"]
    kern.G_ASTRO = g_n * kern.MSUN_KG / (kern.PC_M * 1e6)
    r_vac, lambda_v9 = C1.derive_r_tf_vac_pc(kern, res)

    jeans = SphericalJeansSolver(kern.G_ASTRO, n_grid=240)

    print("=" * 88)
    print("RHIT V9.0 SPHERICAL JEANS KINEMATIC SOLVER (C1-SMOOTH SOLITON VS. NFW)")
    print("=" * 88)
    print(f"SSOT Baseline Audit : {audit_summary['status']} (22 Obs chi2 = {audit_summary['total_chi2']}, dof = 4)")
    print(f"5D Derived Coupling : lambda_V9 = {lambda_v9:.6e} | R_TF,vac = {r_vac:.4f} pc")
    print("=" * 88)

    s2 = [[8.5, 0.3], [7.8, 0.35], [9.2, 0.3]]
    s3 = [[m, 0.35, rho] for m in (7.8, 8.5, 9.0) for rho in (-1.5, -0.8, -0.2)]

    datasets = [
        ("Milky Way Satellites", C1.resolve_lvdb_path("dwarf_mw.csv")),
        ("Local Volume Superset", C1.resolve_lvdb_path("dwarf_all.csv")),
    ]

    for ds_name, csv_path in datasets:
        df_full = kern.prepare_lvdb_dataset(csv_path)
        df_clean = df_full[~df_full["name"].isin(NON_EQUILIBRIUM_OUTLIERS)].reset_index(drop=True)

        for subset_label, df in [("Full Sample", df_full), ("Clean dSph Sample", df_clean)]:
            r = df["rhalf_sph_physical"].values
            v = df["vlos_sigma"].values
            em = df["vlos_sigma_em"].values
            ep = df["vlos_sigma_ep"].values
            ms = df["m_star_msun"].values
            n_obs = len(df)

            fit_nfw = fit_best(
                lambda p: kern.asym_chi2(v, jeans.sigma_los_nfw(kern, r, ms, p[0], p[1]), em, ep),
                s2,
            )
            fit_c1 = fit_best(
                lambda p: kern.asym_chi2(
                    v, jeans.sigma_los_c1_soliton(kern, r, ms, p[0], p[1], p[2], r_vac), em, ep
                ),
                s3,
            )

            chi2_nfw = fit_nfw.fun
            chi2_c1 = fit_c1.fun
            red_nfw = chi2_nfw / (n_obs - 2)
            red_c1 = chi2_c1 / (n_obs - 3)
            delta_pct = 100.0 * (chi2_c1 / chi2_nfw - 1.0)
            aic_nfw = chi2_nfw + 4.0
            aic_c1 = chi2_c1 + 6.0

            print(f"\n>>> {ds_name} — {subset_label} (N = {n_obs})")
            print(f"  {'Model (Spherical Jeans)':<36} | {'k':>2} | {'chi2':>9} | {'chi2_red':>8} | {'vs NFW':>8} | {'AIC':>9}")
            print("  " + "-" * 82)
            print(f"  {'NFW Halo (Plummer Jeans)':<36} | {2:>2} | {chi2_nfw:9.2f} | {red_nfw:8.3f} | {'Baseline':>8} | {aic_nfw:9.2f}")
            print(f"  {'C1-Smooth Soliton + NFW (Jeans)':<36} | {3:>2} | {chi2_c1:9.2f} | {red_c1:8.3f} | {delta_pct:+7.2f}% | {aic_c1:9.2f}")
            print(f"  Best-fit C1 Jeans params (log10_M_floor, alpha_SHMR, log10_rho_crit): {np.round(fit_c1.x, 4)}")


if __name__ == "__main__":
    main()
