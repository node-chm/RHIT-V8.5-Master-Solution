import math
import warnings
import numpy as np
from scipy.optimize import minimize
import rhit_v9_0_audit_kernel as K
import rhit_v9_fit_controls_c1 as C1

warnings.filterwarnings("ignore")

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
    def __init__(self, g_astro, n_grid=260):
        self.g_astro = g_astro
        self.u = np.logspace(-3.0, 3.0, n_grid)
        self.du = np.gradient(self.u)
        self.kernel_w = (4.0 / 3.0) * (self.u ** 2) / ((1.0 + self.u ** 2) ** 3) * self.du

    def plummer_enclosed_mass(self, r, a_p, m_star):
        x = r / a_p
        return m_star * (x ** 3) / ((1.0 + x ** 2) ** 1.5)

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

    def sigma_los_nfw(self, kern, r_half, m_star, log10_m0, alpha_shmr):
        m200 = (10.0 ** log10_m0) * ((m_star / 1e5) ** alpha_shmr)
        c200 = 15.0 * ((m200 / 1e9) ** (-0.1))

        r_grid = r_half[:, None] * self.u[None, :]
        m_dm = kern.nfw_enclosed_mass(r_grid, m200[:, None], c200[:, None])
        m_st = self.plummer_enclosed_mass(r_grid, r_half[:, None], m_star[:, None])
        sig2 = (self.g_astro / r_half) * np.sum((m_dm + m_st) * self.kernel_w[None, :], axis=1)
        return np.sqrt(np.maximum(sig2, 1e-12))

    def sigma_los_c1_soliton(self, kern, r_half, m_star, log10_m_floor, alpha_shmr, log10_rho_crit, r_vac_pc):
        m200 = (10.0 ** log10_m_floor) * (1.0 + ((m_star / 1e6) ** alpha_shmr))
        c200 = 15.0 * ((m200 / 1e9) ** (-0.1))

        rho_tot_est = (kern.nfw_enclosed_mass(r_half, m200, c200) + 0.5 * m_star) / (
            (4.0 / 3.0) * np.pi * (r_half ** 3)
        )
        sym = 1.0 / (1.0 + (rho_tot_est / (10.0 ** log10_rho_crit)) ** 2)
        r_eff = kern.R_TF_MIN_PC + (r_vac_pc - kern.R_TF_MIN_PC) * sym

        r_grid = r_half[:, None] * self.u[None, :]
        m_dm, _ = C1.c1_mass_vec(r_grid, r_eff[:, None], m200[:, None], c200[:, None])
        m_st = self.plummer_enclosed_mass(r_grid, r_half[:, None], m_star[:, None])
        sig2 = (self.g_astro / r_half) * np.sum((m_dm + m_st) * self.kernel_w[None, :], axis=1)
        return np.sqrt(np.maximum(sig2, 1e-12))

    def sigma_los_cored_soliton(self, kern, r_half, m_star, log10_m_floor, alpha_shmr, log10_rho_crit, r_vac_pc):
        m200 = (10.0 ** log10_m_floor) * (1.0 + ((m_star / 1e6) ** alpha_shmr))
        c200 = 15.0 * ((m200 / 1e9) ** (-0.1))

        rho_tot_est = (kern.nfw_enclosed_mass(r_half, m200, c200) + 0.5 * m_star) / (
            (4.0 / 3.0) * np.pi * (r_half ** 3)
        )
        sym = 1.0 / (1.0 + (rho_tot_est / (10.0 ** log10_rho_crit)) ** 2)
        r_eff = kern.R_TF_MIN_PC + (r_vac_pc - kern.R_TF_MIN_PC) * sym

        r_grid = r_half[:, None] * self.u[None, :]
        m_dm = self.cored_soliton_nfw_mass(kern, r_grid, r_eff[:, None], m200, c200, alpha_t=3.0)
        m_st = self.plummer_enclosed_mass(r_grid, r_half[:, None], m_star[:, None])
        sig2 = (self.g_astro / r_half) * np.sum((m_dm + m_st) * self.kernel_w[None, :], axis=1)
        return np.sqrt(np.maximum(sig2, 1e-12))


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

    jeans = SphericalJeansSolver(kern.G_ASTRO, n_grid=260)

    print("=" * 92)
    print("RHIT V9.0 SPHERICAL JEANS BENCHMARK: NFW vs. C1-SMOOTH vs. SCHIVE/ROBLES CORED SOLITON")
    print("=" * 92)
    print(f"SSOT Baseline Audit : {audit_summary['status']} (22 Obs chi2 = {audit_summary['total_chi2']}, dof = 4)")
    print(f"5D Derived Coupling : lambda_V9 = {lambda_v9:.6e} | R_TF,vac = {r_vac:.4f} pc")
    print("=" * 92)

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
            fit_cored = fit_best(
                lambda p: kern.asym_chi2(
                    v, jeans.sigma_los_cored_soliton(kern, r, ms, p[0], p[1], p[2], r_vac), em, ep
                ),
                s3,
            )

            models = [
                ("1. NFW Halo (Plummer Jeans)", 2, fit_nfw.fun, fit_nfw.x),
                ("2. C1-Smooth Soliton + NFW (Jeans)", 3, fit_c1.fun, fit_c1.x),
                ("3. Schive/Robles Cored Soliton (Jeans)", 3, fit_cored.fun, fit_cored.x),
            ]
            base_chi2 = models[0][2]

            print(f"\n>>> {ds_name} — {subset_label} (N = {n_obs})")
            print(f"  {'Model (Spherical Jeans)':<40} | {'k':>2} | {'chi2':>9} | {'chi2_red':>8} | {'vs NFW':>8} | {'AIC':>9}")
            print("  " + "-" * 86)
            for m_name, k_p, c2, _ in models:
                c2_red = c2 / (n_obs - k_p)
                vs_str = "Baseline" if k_p == 2 else f"{100.0 * (c2 / base_chi2 - 1.0):+7.2f}%"
                aic = c2 + 2.0 * k_p
                print(f"  {m_name:<40} | {k_p:>2} | {c2:9.2f} | {c2_red:8.3f} | {vs_str:>8} | {aic:9.2f}")
            print(f"  Best-fit C1 params (log10_M_floor, alpha_SHMR, log10_rho_crit): {np.round(fit_c1.x, 4)}")
            print(f"  Best-fit Cored Soliton params (log10_M_floor, alpha_SHMR, log10_rho_crit): {np.round(fit_cored.x, 4)}")


if __name__ == "__main__":
    main()
