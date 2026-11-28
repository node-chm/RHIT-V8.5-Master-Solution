import warnings
import numpy as np
from scipy.optimize import minimize
import rhit_v9_0_audit_kernel as K
import rhit_v9_fit_controls_c1 as C1
from rhit_v9_jeans_solver import SphericalJeansSolver, NON_EQUILIBRIUM_OUTLIERS

warnings.filterwarnings("ignore")

BENCHMARK_GALAXIES = ["Segue 1", "Draco", "Sculptor", "Leo I", "Fornax"]


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


def eval_cored_with_alpha(jeans, kern, r_half, m_star, params, r_vac_pc, alpha_t):
    log10_m_floor, alpha_shmr, log10_rho_crit = params
    m200 = (10.0 ** log10_m_floor) * (1.0 + ((m_star / 1e6) ** alpha_shmr))
    c200 = 15.0 * ((m200 / 1e9) ** (-0.1))

    rho_tot_est = (kern.nfw_enclosed_mass(r_half, m200, c200) + 0.5 * m_star) / (
        (4.0 / 3.0) * np.pi * (r_half ** 3)
    )
    sym = 1.0 / (1.0 + (rho_tot_est / (10.0 ** log10_rho_crit)) ** 2)
    r_eff = kern.R_TF_MIN_PC + (r_vac_pc - kern.R_TF_MIN_PC) * sym

    r_grid = r_half[:, None] * jeans.u[None, :]
    m_dm = jeans.cored_soliton_nfw_mass(kern, r_grid, r_eff[:, None], m200, c200, alpha_t=alpha_t)
    m_st = jeans.plummer_enclosed_mass(r_grid, r_half[:, None], m_star[:, None])
    sig2 = (jeans.g_astro / r_half) * np.sum((m_dm + m_st) * jeans.kernel_w[None, :], axis=1)
    return np.sqrt(np.maximum(sig2, 1e-12)), r_eff, sym


def main():
    kern = K.RHITV90IntegratedAuditKernel()
    _, audit_summary = kern.self_audit()
    res = kern.evaluate()
    g_n = res["metrics"]["G_N"]["pred"]
    kern.G_ASTRO = g_n * kern.MSUN_KG / (kern.PC_M * 1e6)
    r_vac, lambda_v9 = C1.derive_r_tf_vac_pc(kern, res)

    jeans = SphericalJeansSolver(kern.G_ASTRO, n_grid=260)

    print("=" * 92)
    print("RHIT V9.0 - TRANSITION ALPHA_T SENSITIVITY SCAN & 5 BENCHMARK GALAXIES (SPHERICAL JEANS)")
    print("=" * 92)
    print(f"SSOT Audit Status : {audit_summary['status']} (22 Obs chi2 = {audit_summary['total_chi2']}, dof = 4)")
    print(f"5D Derived Scales : lambda_V9 = {lambda_v9:.6e} | R_TF,vac = {r_vac:.4f} pc")
    print("=" * 92)

    s2 = [[8.5, 0.3], [7.8, 0.35], [9.2, 0.3]]
    s3 = [[m, 0.35, rho] for m in (7.8, 8.5, 9.0) for rho in (-1.5, -0.8, -0.2)]
    alpha_grid = [2.5, 2.75, 3.0, 3.25, 3.5, 4.0]

    mw_path = C1.resolve_lvdb_path("dwarf_mw.csv")
    all_path = C1.resolve_lvdb_path("dwarf_all.csv")

    df_mw_full = kern.prepare_lvdb_dataset(mw_path)
    df_mw_clean = df_mw_full[~df_mw_full["name"].isin(NON_EQUILIBRIUM_OUTLIERS)].reset_index(drop=True)
    df_all_full = kern.prepare_lvdb_dataset(all_path)
    df_all_clean = df_all_full[~df_all_full["name"].isin(NON_EQUILIBRIUM_OUTLIERS)].reset_index(drop=True)

    scan_targets = [
        ("MW Full (N=46)", df_mw_full),
        ("MW Clean dSph (N=40)", df_mw_clean),
        ("LV_All Clean dSph (N=82)", df_all_clean),
    ]

    print("\n[PART 1] SENSITIVITY SCAN OVER TRANSITION RATIO alpha_t = r_t / r_c in [2.5, 4.0]")
    for ds_label, df in scan_targets:
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
        base_c2 = fit_nfw.fun
        base_aic = base_c2 + 4.0

        print(f"\n  >>> {ds_label} | NFW Jeans Baseline: chi2 = {base_c2:.2f}, AIC = {base_aic:.2f}")
        print(f"  {'alpha_t':>8} | {'chi2':>9} | {'chi2_red':>8} | {'vs NFW':>8} | {'AIC':>9} | {'Delta AIC':>9}")
        print("  " + "-" * 64)
        for a_t in alpha_grid:
            fit_a = fit_best(
                lambda p: kern.asym_chi2(
                    v, eval_cored_with_alpha(jeans, kern, r, ms, p, r_vac, a_t)[0], em, ep
                ),
                s3,
            )
            c2 = fit_a.fun
            c2_red = c2 / (n_obs - 3)
            pct = 100.0 * (c2 / base_c2 - 1.0)
            aic = c2 + 6.0
            d_aic = aic - base_aic
            print(f"  {a_t:8.2f} | {c2:9.2f} | {c2_red:8.3f} | {pct:+7.2f}% | {aic:9.2f} | {d_aic:+9.2f}")

    print("\n" + "=" * 92)
    print("[PART 2] 5 BENCHMARK MILKY WAY DWARF GALAXIES (SPHERICAL JEANS AT alpha_t = 3.0)")
    print("=" * 92)

    for fit_regime, df_ref in [("Fitted on MW Full (N=46)", df_mw_full), ("Fitted on MW Clean dSph (N=40)", df_mw_clean)]:
        r_ref = df_ref["rhalf_sph_physical"].values
        v_ref = df_ref["vlos_sigma"].values
        em_ref = df_ref["vlos_sigma_em"].values
        ep_ref = df_ref["vlos_sigma_ep"].values
        ms_ref = df_ref["m_star_msun"].values

        p_nfw = fit_best(
            lambda p: kern.asym_chi2(v_ref, jeans.sigma_los_nfw(kern, r_ref, ms_ref, p[0], p[1]), em_ref, ep_ref),
            s2,
        ).x
        p_cored = fit_best(
            lambda p: kern.asym_chi2(
                v_ref, eval_cored_with_alpha(jeans, kern, r_ref, ms_ref, p, r_vac, 3.0)[0], em_ref, ep_ref
            ),
            s3,
        ).x

        r_all = df_mw_full["rhalf_sph_physical"].values
        ms_all = df_mw_full["m_star_msun"].values
        sig_nfw_all = jeans.sigma_los_nfw(kern, r_all, ms_all, p_nfw[0], p_nfw[1])
        sig_cor_all, reff_all, sym_all = eval_cored_with_alpha(
            jeans, kern, r_all, ms_all, p_cored, r_vac, 3.0
        )

        print(f"\n  >>> {fit_regime}")
        print(
            f"  {'Galaxy':<10} | {'r_1/2(pc)':>9} | {'R_TF_eff':>8} | {'Sym_f':>6} | "
            f"{'Obs(km/s)':>13} | {'NFW Jeans':>9} | {'Cored Jeans':>11}"
        )
        print("  " + "-" * 78)
        for gname in BENCHMARK_GALAXIES:
            idx = df_mw_full.index[df_mw_full["name"] == gname][0]
            obs_str = f"{df_mw_full.loc[idx, 'vlos_sigma']:.2f} (-{df_mw_full.loc[idx, 'vlos_sigma_em']:.2f}/+{df_mw_full.loc[idx, 'vlos_sigma_ep']:.2f})"
            print(
                f"  {gname:<10} | {r_all[idx]:>9.2f} | {reff_all[idx]:>8.2f} | {sym_all[idx]:>6.3f} | "
                f"{obs_str:>13} | {sig_nfw_all[idx]:>9.2f} | {sig_cor_all[idx]:>11.2f}"
            )


if __name__ == "__main__":
    main()
