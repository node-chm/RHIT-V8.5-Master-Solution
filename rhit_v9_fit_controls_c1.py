"""
RHIT V9.0 - control tests A/B and C1-smooth soliton comparison (fit.py)

Run from the repo root (needs numpy, scipy, pandas):
    python3 fit.py
Expects in the working directory:
    rhit_v9_0_audit_kernel.py, rhit_v9_0_ai_ssot.json,
    data/dwarf_mw.csv, data/dwarf_all.csv

Models: NFW (2p); control A = NFW + floor-SHMR (2p); original Hybrid V9 (3p);
control B = Hybrid with R_TF,vac = 12 pc (3p); C1-smooth soliton (3p).
Also scans R_TF,vac from 12 to 3000 pc. Does not modify the kernel.
"""
import numpy as np, sys, os, math, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
from scipy.optimize import minimize, brentq
import rhit_v9_0_audit_kernel as K

kern = K.RHITV90IntegratedAuditKernel()
res = kern.evaluate()
G_N = res["metrics"]["G_N"]["pred"]
kern.G_ASTRO = G_N*kern.MSUN_KG/(kern.PC_M*1e6)
R_VAC = 320.3682
RMIN = kern.R_TF_MIN_PC
nfw = kern.nfw_enclosed_mass

# ---------- vectorised C1 matching (validated against Gemini's brentq version) ----------
def solve_x_vec(ratio):
    lo=np.full_like(ratio,1e-4); hi=np.full_like(ratio,np.pi-1e-4)
    f=lambda x:(x*np.cos(x)-np.sin(x))/np.sin(x)+(1+3*(x/np.pi)*ratio)/(1+(x/np.pi)*ratio)
    for _ in range(60):
        mid=0.5*(lo+hi); pos=f(mid)>0
        lo=np.where(pos,mid,lo); hi=np.where(pos,hi,mid)
    return 0.5*(lo+hi)

def c1_mass_vec(r, r_core, M200, c200, alpha_t=None):
    rc=1.36e-7
    r200=((3*M200)/(4*np.pi*200*rc))**(1/3); rs=r200/c200
    fc=np.log(1+c200)-c200/(1+c200); rho_s=M200/(4*np.pi*rs**3*fc)
    xm=solve_x_vec(r_core/rs); rm=xm/np.pi*r_core; um=rm/rs
    rho_c=rho_s/(um*(1+um)**2)*xm/np.sin(xm)
    x=np.pi*np.minimum(r,rm)/r_core
    Min=4*np.pi*rho_c*(r_core/np.pi)**3*(np.sin(x)-x*np.cos(x))
    Mout=np.where(r>rm, nfw(r,M200,c200)-nfw(rm,M200,c200), 0.0)
    return Min+Mout, rm

# validation vs scalar brentq
def solve_scalar(r_core,r_s):
    ratio=r_core/r_s
    return brentq(lambda x:(x*np.cos(x)-np.sin(x))/np.sin(x)+(1+3*(x/np.pi)*ratio)/(1+(x/np.pi)*ratio),1e-4,np.pi-1e-4)
if __name__ == "__main__":
    rt=np.logspace(-3,3,50); err=max(abs(solve_x_vec(rt)-np.array([solve_scalar(x,1.0) for x in rt])))
    print(f"vectorised solver vs brentq max |dx| = {err:.2e}")


def resolve_lvdb_path(filename):
    p = Path(filename)
    if p.exists():
        return str(p)
    p_data = Path("data") / p.name
    if p_data.exists():
        return str(p_data)
    p_ws_data = Path("RHIT_Workspace") / "data" / p.name
    if p_ws_data.exists():
        return str(p_ws_data)
    return str(p)

def derive_r_tf_vac_pc(kern, eval_res=None):
    if eval_res is None:
        eval_res = kern.evaluate()
    scales = eval_res["derived_scales"]
    u_ir = scales["u_IR"]
    delta_h = scales["delta_H"]
    g_n = eval_res["metrics"]["G_N"]["pred"]
    m_eff_ev = eval_res["roadmap"]["scalar_dm_mass_eV"]
    m_eff_kg = (m_eff_ev * 1e-9) * kern.GEV_TO_KG
    k_geom_5d = 4.0 + 2.0 * delta_h - (1.0 / (2.0 * math.pi))
    lambda_v9 = math.exp(k_geom_5d * u_ir)
    r_tf_m = math.pi * math.sqrt((lambda_v9 * (kern.HBAR ** 3)) / (8.0 * math.pi * g_n * (m_eff_kg ** 4) * kern.C))
    r_tf_vac_pc = r_tf_m / (kern.MPC_TO_M * 1e-6)
    return r_tf_vac_pc, lambda_v9

# ---------- models ----------
def sig_nfw(p,r,ms):            return kern.pred_sigma_nfw(r,ms,p[0],p[1])
def sig_nfw_floor(p,r,ms):
    M200=(10**p[0])*(1+((ms/1e6)**p[1])); c200=15*(M200/1e9)**-0.1
    return np.sqrt(kern.G_ASTRO*(nfw(r,M200,c200)+0.5*ms)/(3*r))
def sig_hyb(p,r,ms,Rvac=R_VAC): return kern.pred_sigma_hybrid_v9(r,ms,p[0],p[1],p[2],Rvac)[0]
def sig_c1(p,r,ms,Rvac=R_VAC):
    M200=(10**p[0])*(1+((ms/1e6)**p[1])); c200=15*(M200/1e9)**-0.1
    rho_tot=(nfw(r,M200,c200)+0.5*ms)/((4/3)*np.pi*r**3)
    sym=1/(1+(rho_tot/10**p[2])**2); Reff=RMIN+(Rvac-RMIN)*sym
    M,_=c1_mass_vec(r,Reff,M200,c200)
    return np.sqrt(kern.G_ASTRO*(M+0.5*ms)/(3*r))

def best(sigfun,v,em,ep,r,ms,starts):
    b=None
    for s in starts:
        o=minimize(lambda p:kern.asym_chi2(v,sigfun(p,r,ms),em,ep),s,method="Nelder-Mead",options={"maxiter":6000,"xatol":1e-6,"fatol":1e-6})
        if b is None or o.fun<b.fun: b=o
    return b

S2=[[8.5,0.3],[7.8,0.35],[9.0,0.3]]
S3=[[m,0.35,rho] for m in (7.8,8.5) for rho in (-1.0,-0.5)]

for label,path in [("MW N=46",resolve_lvdb_path("dwarf_mw.csv")),("LV N=94",resolve_lvdb_path("dwarf_all.csv"))]:
    df=kern.prepare_lvdb_dataset(path)
    r=df["rhalf_sph_physical"].values; v=df["vlos_sigma"].values
    em=df["vlos_sigma_em"].values; ep=df["vlos_sigma_ep"].values; ms=df["m_star_msun"].values
    N=len(df); print(f"\n===== {label} (N={N}) =====")
    rows=[]
    def rec(name,k,o): rows.append((name,k,o.fun,o.x))
    rec("NFW (kernel baseline, 2p)",2,best(sig_nfw,v,em,ep,r,ms,S2))
    rec("NFW + floor-SHMR  (control A, 2p)",2,best(sig_nfw_floor,v,em,ep,r,ms,S2))
    rec("Hybrid V9, R_vac=320.37 (kernel, 3p)",3,best(sig_hyb,v,em,ep,r,ms,S3))
    rec("Hybrid V9, R_vac=12 pc (control B, no lambda scale)",3,best(lambda p,r,ms:sig_hyb(p,r,ms,RMIN),v,em,ep,r,ms,S3))
    rec("C1-smooth soliton, R_vac=320.37 (3p)",3,best(sig_c1,v,em,ep,r,ms,S3))
    base=rows[0][2]
    print(f"{'model':55s} {'k':>2s} {'chi2':>9s} {'vs NFW':>8s} {'AIC':>9s}")
    for n,k,c,x in rows:
        print(f"{n:55s} {k:2d} {c:9.2f} {100*(c/base-1):+7.2f}% {c+2*k:9.2f}")
    print("  best-fit params (M_floor/M0, alpha, [rho_crit]):")
    for n,k,c,x in rows: print("   ",n[:40].ljust(40),np.round(x,3))

    # does the derived scale matter? scan R_vac for hybrid + C1
    print("  scan over R_TF,vac (3-param refit each):   R_vac:  hybrid chi2 | C1 chi2")
    for Rv in [12,50,100,200,320.37,500,1000,3000]:
        h=best(lambda p,r,ms:sig_hyb(p,r,ms,Rv),v,em,ep,r,ms,S3).fun
        c=best(lambda p,r,ms:sig_c1(p,r,ms,Rv),v,em,ep,r,ms,S3).fun
        print(f"      {Rv:8.2f}  {h:9.2f} | {c:9.2f}")
