"""Shared data preparation, models and spatial cross-validation for X-Ray the Bay."""
import os
import pathlib
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
FIG = ROOT / "figures"
OUT = ROOT / "outputs"
EPSG = 32616
MODEL_VERSION = "xray-bay-0.1.0"
N_JOBS = int(os.environ.get("XRAY_JOBS", "-1"))  # set with OMP_NUM_THREADS when running configs in parallel

UNITS = {
    "chl_RFU_exo_tau": "RFU",
    "bga_RFU_exo_tau": "RFU",
    "turb_FNU_tau": "FNU",
    "specCond_tau": "uS/cm",
    "temp_exo_tau": "degC",
    "fdom_QSU_exo_tau": "QSU",
}
LABELS = {
    "chl_RFU_exo_tau": "Chlorophyll-a fluorescence (EXO2, RFU)",
    "bga_RFU_exo_tau": "Phycocyanin fluorescence (EXO2, RFU)",
    "turb_FNU_tau": "Turbidity (EXO2, FNU)",
    "specCond_tau": "Specific conductance (EXO2, uS/cm)",
    "temp_exo_tau": "Water temperature (EXO2, degC)",
    "fdom_QSU_exo_tau": "fDOM (EXO2, QSU)",
}
# Optical variables are right-skewed; models that learn a mapping work in log(v + 1).
# The offset is a fixed physical constant, not estimated from data, so held-out values never leak into it.
LOG_TARGETS = {"chl_RFU_exo_tau", "bga_RFU_exo_tau", "turb_FNU_tau", "fdom_QSU_exo_tau"}


def fwd(v, target):
    return np.log(np.clip(v, -0.9, None) + 1.0) if target in LOG_TARGETS else np.asarray(v, float)


def inv(t, target):
    return np.exp(t) - 1.0 if target in LOG_TARGETS else np.asarray(t, float)


def water_polygon(names=("Lake Michigan",)):
    g = gpd.read_file(f"zip://{RAW / 'naturalearth' / 'ne_10m_lakes.zip'}")
    return g[g["name"].isin(names)].to_crs(EPSG).union_all()


def load_observations(campaign, target, bin_m=100.0, water_buffer_m=1000.0, lat_max=None, lat_min=None):
    """One campaign, one target, restricted to the water body and thinned to along-track bins.

    The boat logs ~1 Hz, i.e. a few metres apart; those rows are not independent, so they are
    aggregated (median) into `bin_m` along-track bins. Stationary sampling stops collapse to one bin.
    """
    df = pd.read_parquet(PROC / "flame_core.parquet")
    df = df[(df["id"] == campaign) & df[target].notna()].sort_values("DateTime_UTC").copy()
    if lat_max is not None:
        df = df[df.latitude <= lat_max]
    if lat_min is not None:
        df = df[df.latitude >= lat_min]
    poly = water_polygon().buffer(water_buffer_m)
    inside = gpd.GeoSeries(gpd.points_from_xy(df.x, df.y), crs=EPSG).within(poly).values
    df = df[inside]
    step = np.hypot(np.diff(df.x, prepend=df.x.iloc[0]), np.diff(df.y, prepend=df.y.iloc[0]))
    step[step > 2000] = 0  # GPS jumps / day breaks do not add along-track distance
    df["along_m"] = np.cumsum(step)
    df["bin"] = (df["along_m"] // bin_m).astype(int)
    obs = df.groupby("bin").agg(
        x=("x", "median"), y=("y", "median"), lon=("longitude", "median"), lat=("latitude", "median"),
        t_utc=("DateTime_UTC", "min"), along_m=("along_m", "median"), value=(target, "median"),
        n_raw=(target, "size"),
    ).reset_index(drop=True)
    return obs, len(df)


def make_blocks(obs, block_km):
    """Contiguous along-track segments of ~block_km; each is one held-out unit."""
    return (obs["along_m"] // (block_km * 1000)).astype(int).values


def fold_split(obs, blocks, b, along_buffer_m, spatial_buffer_m=0.0):
    """Indices of test (block b) and train (everything else minus buffers).

    along_buffer_m removes the same-track neighbours either side of the held-out segment.
    spatial_buffer_m (hard mode) also removes any other track passing within that distance,
    e.g. a crossing transect or a return leg.
    """
    test = np.where(blocks == b)[0]
    a0, a1 = obs.along_m.values[test].min(), obs.along_m.values[test].max()
    a = obs.along_m.values
    keep = (blocks != b) & ((a < a0 - along_buffer_m) | (a > a1 + along_buffer_m))
    if spatial_buffer_m > 0:
        d, _ = cKDTree(obs[["x", "y"]].values[test]).query(obs[["x", "y"]].values)
        keep &= d > spatial_buffer_m
    return test, np.where(keep)[0]


def coord_features(xy, n_angles=8):
    """x, y plus oblique (rotated) coordinates - lets tree models cut along non-axis directions."""
    x, y = xy[:, 0] / 1000.0, xy[:, 1] / 1000.0
    feats = [x, y]
    for k in range(1, n_angles):
        th = np.pi * k / n_angles
        feats.append(x * np.cos(th) + y * np.sin(th))
    return np.column_stack(feats)


# ---------------------------------------------------------------- models
def predict_nn(xy_tr, v_tr, xy_te):
    d, i = cKDTree(xy_tr).query(xy_te)
    return v_tr[i], d


def predict_idw(xy_tr, v_tr, xy_te, k=12, power=2.0):
    d, i = cKDTree(xy_tr).query(xy_te, k=k)
    w = 1.0 / np.maximum(d, 1.0) ** power
    return (w * v_tr[i]).sum(1) / w.sum(1)


def fit_rf(xy_tr, t_tr, seed=0):
    m = RandomForestRegressor(n_estimators=300, min_samples_leaf=3, max_features=0.5, n_jobs=N_JOBS, random_state=seed)
    return m.fit(coord_features(xy_tr), t_tr)


def predict_rf(m, xy):
    X = coord_features(xy)
    per_tree = np.stack([t.predict(X) for t in m.estimators_])
    return per_tree.mean(0), per_tree.std(0)


def fit_hgb(xy_tr, t_tr, seed=0):
    m = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=10,
                                      l2_regularization=1.0, random_state=seed)
    return m.fit(coord_features(xy_tr), t_tr)


@dataclass
class GPModel:
    gp: GaussianProcessRegressor
    mu: float
    sd: float

    def predict(self, xy, return_cov=False):
        out = self.gp.predict(xy / 1000.0, return_std=not return_cov, return_cov=return_cov)
        m, s = out
        if return_cov:
            return m * self.sd + self.mu, s * self.sd**2
        return m * self.sd + self.mu, s * self.sd


def fit_gp(xy_tr, t_tr, n_max=1200, seed=0, kernel=None):
    """Exact GP (Matern 3/2 + white noise) on a random subsample of the training bins, coordinates in km.

    With kernel given (already fitted), hyperparameters are frozen - used for fast refits.
    """
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(xy_tr), size=min(n_max, len(xy_tr)), replace=False)
    mu, sd = t_tr[idx].mean(), t_tr[idx].std() + 1e-9
    if kernel is None:
        kernel = ConstantKernel(1.0, (1e-2, 1e2)) * Matern(length_scale=5.0, length_scale_bounds=(0.2, 100.0), nu=1.5) \
            + WhiteKernel(0.05, (1e-4, 1.0))
        gp = GaussianProcessRegressor(kernel=kernel, normalize_y=False, n_restarts_optimizer=1, random_state=seed)
    else:
        gp = GaussianProcessRegressor(kernel=kernel, optimizer=None, normalize_y=False)
    gp.fit(xy_tr[idx] / 1000.0, (t_tr[idx] - mu) / sd)
    return GPModel(gp, mu, sd)


def metrics(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    e = p - y
    ss = ((y - y.mean()) ** 2).sum()
    return {
        "n": int(len(y)),
        "MAE": float(np.abs(e).mean()),
        "RMSE": float(np.sqrt((e**2).mean())),
        "R2": float(1 - (e**2).sum() / ss) if ss > 0 else None,
        "bias": float(e.mean()),
    }
