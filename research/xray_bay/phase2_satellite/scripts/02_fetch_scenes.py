"""Fetch survey-window subsets of Sentinel-2 L2A COGs (no rendered imagery) onto a common 20 m UTM 16N grid.

10 m bands (B02-B04) are block-averaged 2x2 to the 20 m B05 grid (exact aggregation, no interpolation).
Reflectance = DN * scale + offset from the STAC `raster:bands` metadata (processing baseline 05.11: 1e-4, -0.1);
DN 0 is no-data. SCL (scene classification) and CLD (cloud probability, %) are kept as QA layers.
Output: data/<item_id>_20m.tif (float32 bands B02..B11, then SCL, CLD), data/<item_id>_tci.tif (10 m true colour, for figures)
"""
import json
import sys

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.windows import from_bounds

from p2_common import AOI, BANDS, DATA, GRID_RES, OUT

DEFAULT_IDS = ["S2A_T16TDQ_20250630T164706_L2A", "S2C_T16TDQ_20250701T165332_L2A",
               "S2C_T16TDQ_20250628T164829_L2A", "S2A_T16TDQ_20250703T165928_L2A"]
ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES", GDAL_HTTP_MULTIRANGE="YES",
           GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES", VSI_CACHE="TRUE")


def grid_bounds():
    tr = Transformer.from_crs(4326, 32616, always_xy=True)
    xs, ys = tr.transform([AOI[0], AOI[2], AOI[0], AOI[2]], [AOI[1], AOI[1], AOI[3], AOI[3]])
    snap = 60.0  # S2 tile origins are multiples of 60 m, so 10/20 m pixels align exactly
    return (np.floor(min(xs) / snap) * snap, np.floor(min(ys) / snap) * snap,
            np.ceil(max(xs) / snap) * snap, np.ceil(max(ys) / snap) * snap)


def read(href, bounds, res):
    with rasterio.open(href) as src:
        win = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
        a = src.read(1, window=win, boundless=True, fill_value=0)
        if src.res[0] != res:
            f = int(res / src.res[0])
            h, w = a.shape[0] // f, a.shape[1] // f
            blk = a[: h * f, : w * f].reshape(h, f, w, f).astype(np.float64)
            valid = (blk > 0).all(axis=(1, 3))
            a = np.where(valid, blk.mean(axis=(1, 3)), 0)
        return a


def main(ids):
    b = grid_bounds()
    W, H = int((b[2] - b[0]) / GRID_RES), int((b[3] - b[1]) / GRID_RES)
    transform = from_origin(b[0], b[3], GRID_RES, GRID_RES)
    with rasterio.Env(**ENV):
        for iid in ids:
            item = json.loads((OUT / "stac_items" / f"{iid}.json").read_text())
            out = DATA / f"{iid}_20m.tif"
            if out.exists():
                print("exists", out.name)
                continue
            layers, names = [], []
            for band, key in BANDS.items():
                a = item["assets"][key]
                rb = a["raster:bands"][0]
                dn = read(a["href"], b, GRID_RES)
                refl = np.where(dn > 0, dn * rb["scale"] + rb["offset"], np.nan).astype(np.float32)
                layers.append(refl[:H, :W])
                names.append(band)
                print(iid, band, "scale", rb["scale"], "offset", rb["offset"], "native", a.get("gsd"))
            for key, name in [("scl", "SCL"), ("cloud", "CLD")]:
                layers.append(read(item["assets"][key]["href"], b, GRID_RES)[:H, :W].astype(np.float32))
                names.append(name)
            prof = dict(driver="GTiff", width=W, height=H, count=len(layers), dtype="float32", crs="EPSG:32616",
                        transform=transform, compress="deflate", nodata=np.nan, tiled=True)
            with rasterio.open(out, "w", **prof) as dst:
                for i, (L, n) in enumerate(zip(layers, names), 1):
                    dst.write(L, i)
                    dst.set_band_description(i, n)
                dst.update_tags(stac_item=iid, datetime_utc=item["properties"]["datetime"],
                                collection="sentinel-2-c1-l2a", source="Element 84 Earth Search",
                                processing_baseline=item["properties"].get("s2:processing_baseline"),
                                note="bottom-of-atmosphere reflectance (Sen2Cor L2A), land-oriented; not water-leaving reflectance")
            # 10 m true colour for figures, decimated to 20 m by GDAL averaging
            with rasterio.open(item["assets"]["visual"]["href"]) as src:
                win = from_bounds(*b, transform=src.transform)
                tci = src.read(window=win, out_shape=(3, H, W), resampling=Resampling.average, boundless=True)
            with rasterio.open(DATA / f"{iid}_tci.tif", "w", **{**prof, "count": 3, "dtype": "uint8", "nodata": 0}) as dst:
                dst.write(tci)
            print("wrote", out.name, (H, W))


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_IDS)
