"""Green Bay display domain from the packaged NOAA/NWS marine zones."""
from functools import lru_cache
import gzip
import json
from pathlib import Path

import numpy as np
from PIL import Image
from rasterio.features import geometry_mask
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling, transform_bounds, transform_geom
from shapely import contains_xy
from shapely.geometry import shape

BOUNDARY = Path(__file__).resolve().parents[1] / "data/xray/green_bay_boundary.geojson"


@lru_cache(maxsize=1)
def boundary():
    return json.loads(BOUNDARY.read_text())


def grid_mask(xy):
    polygon = shape(transform_geom("EPSG:4326", "EPSG:32616", boundary()["geometry"]))
    return contains_xy(polygon, xy[:, 0], xy[:, 1])


def mercator_transform(bounds, width, height):
    (south, west), (north, east) = bounds
    projected = transform_bounds("EPSG:4326", "EPSG:3857", west, south, east, north)
    return from_bounds(*projected, width, height)


def pixel_mask(bounds, width, height):
    polygon = transform_geom("EPSG:4326", "EPSG:3857", boundary()["geometry"])
    return geometry_mask([polygon], out_shape=(height, width),
                         transform=mercator_transform(bounds, width, height), invert=True)


def rebuild_samples(dest, predictions, scene_index, unsupported, shape_, transform):
    """Reproject clipped values into the existing API inspection grid."""
    path = dest / "samples.json.gz"
    with gzip.open(path, "rt") as stream:
        sample = json.load(stream)
    height, width = sample["height"], sample["width"]
    target = mercator_transform(sample["bounds"], width, height)
    valid = np.isfinite(predictions)
    for key, values, nodata in [("values", predictions, np.nan),
                                ("scenes", np.where(valid, scene_index, 0), 0),
                                ("outside_support", valid & unsupported, 0)]:
        output = np.full((height, width), nodata, dtype="float32")
        reproject(values.reshape(shape_).astype("float32"), output, src_transform=transform,
                  src_crs="EPSG:32616", dst_transform=target, dst_crs="EPSG:3857",
                  src_nodata=nodata, dst_nodata=nodata, resampling=Resampling.nearest)
        sample[key] = ([round(float(v), 3) if np.isfinite(v) else None for v in output.ravel()]
                       if key == "values" else output.astype(int).ravel().tolist())
    with gzip.open(path, "wt") as stream:
        json.dump(sample, stream, separators=(",", ":"), allow_nan=False)


def clip_export(dest, metadata):
    """Clip final image pixels and inspection cells, including resampling edges."""
    for layer in metadata["layers"]:
        path = dest / f"{layer['id']}.png"
        with Image.open(path) as image:
            rgba = np.array(image.convert("RGBA"))
        height, width = rgba.shape[:2]
        inside = pixel_mask(layer["bounds"], width, height)
        rgba[~inside, 3] = 0
        Image.fromarray(rgba).save(path)
    path = dest / "samples.json.gz"
    with gzip.open(path, "rt") as stream:
        sample = json.load(stream)
    inside = pixel_mask(sample["bounds"], sample["width"], sample["height"]).ravel()
    for index in np.flatnonzero(~inside):
        sample["values"][index] = None
        sample["scenes"][index] = 0
        sample["outside_support"][index] = 0
    with gzip.open(path, "wt") as stream:
        json.dump(sample, stream, separators=(",", ":"), allow_nan=False)
    west, south, east, north = shape(boundary()["geometry"]).bounds
    (image_south, image_west), (image_north, image_east) = metadata["layers"][0]["bounds"]
    metadata["region"] = {**boundary()["properties"],
        "bounds": [[max(south, image_south), max(west, image_west)],
                   [min(north, image_north), min(east, image_east)]]}
