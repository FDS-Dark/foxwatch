"""Shared paths and constants for Phase 2 (satellite covariates). Reuses Phase 1 code from ../../scripts."""
import pathlib
import sys

P2 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P2.parent / "scripts"))

import xray_common as xc  # noqa: E402  (Phase 1 loaders, folds, models, metrics)

DATA = P2 / "data"
OUT = P2 / "outputs"
FIG = P2 / "figures"
EXP = P2 / "exports"
for d in (DATA, OUT, FIG, EXP):
    d.mkdir(exist_ok=True)

STAC = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-c1-l2a"
CAMPAIGN = "GreenBay_2025_Jun"
TARGET = "chl_RFU_exo_tau"
MODEL_VERSION = "xray-bay-p2-0.1.0"
# Survey footprint (from the 100 m bins, padded) used for the STAC query and the raster window, WGS84
AOI = (-88.10, 44.50, -87.50, 45.16)
GRID_RES = 20.0  # common feature grid (native resolution of B05)
BANDS = {"B02": "blue", "B03": "green", "B04": "red", "B05": "rededge1", "B06": "rededge2", "B07": "rededge3",
         "B8A": "nir08", "B11": "swir16"}
MAX_LAG_H = 24.0  # predeclared time-match rule (main experiment)
