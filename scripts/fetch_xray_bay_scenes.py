"""Download adjacent Sentinel-2 COG windows without modifying holdout inputs."""
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import requests

import export_xray_holdout_maps as hold

AOI = (-88.15, 44.45, -86.65, 45.95)
DEST = hold.RESEARCH / "bay_overview"


def fetch(item):
    downloader = hold.module("bay_fetch", "02_fetch_scenes.py")
    downloader.DATA = DEST / "data"
    downloader.OUT = DEST
    downloader.ENV.update(GDAL_HTTP_TIMEOUT="120", GDAL_HTTP_MAX_RETRY="2", GDAL_HTTP_RETRY_DELAY="2")
    downloader.DATA.mkdir(parents=True, exist_ok=True)
    bbox = item["bbox"]
    downloader.AOI = (max(AOI[0], bbox[0]), max(AOI[1], bbox[1]), min(AOI[2], bbox[2]), min(AOI[3], bbox[3]))
    downloader.main([item["id"]])
    return item["id"]


def main():
    inventories = hold.RESEARCH / "outputs/bay_overview"
    inventories.mkdir(parents=True, exist_ok=True)
    for name, date in [("items.json", "2025-07-01"), ("items_june30.json", "2025-06-30")]:
        if not (inventories / name).exists():
            response = requests.post("https://earth-search.aws.element84.com/v1/search", json={
                "collections": ["sentinel-2-c1-l2a"], "bbox": AOI,
                "datetime": f"{date}T00:00:00Z/{date}T23:59:59Z", "limit": 100,
            }, timeout=60)
            response.raise_for_status()
            (inventories / name).write_text(json.dumps(response.json(), indent=2))
    items = json.loads((inventories / "items.json").read_text())["features"]
    items += json.loads((inventories / "items_june30.json").read_text())["features"]
    nearby = inventories / "nearby_items.json"
    if not nearby.exists():
        response = requests.post("https://earth-search.aws.element84.com/v1/search", json={
            "collections": ["sentinel-2-c1-l2a"], "bbox": AOI,
            "datetime": "2025-06-28T00:00:00Z/2025-07-03T23:59:59Z", "limit": 100,
        }, timeout=60)
        response.raise_for_status()
        nearby.write_text(json.dumps(response.json(), indent=2))
    items += json.loads(nearby.read_text())["features"]
    items = list({item["id"]: item for item in items}.values())
    selected = [item for item in items if item["id"] in {
        "S2C_T16TDQ_20250701T165332_L2A", "S2C_T16TDR_20250701T165332_L2A",
        "S2A_T16TER_20250630T164706_L2A",
        "S2B_T16TDR_20250703T164446_L2A", "S2B_T16TER_20250703T164446_L2A",
    }]
    (DEST / "stac_items").mkdir(parents=True, exist_ok=True)
    for item in selected:
        (DEST / "stac_items" / f"{item['id']}.json").write_text(json.dumps(item, indent=2))
    (DEST / "manifest.json").write_text(json.dumps({"aoi": AOI, "items": [item["id"] for item in selected]}, indent=2))
    with ProcessPoolExecutor(max_workers=2) as pool:
        for iid in pool.map(fetch, selected):
            print("Completed", iid, flush=True)


if __name__ == "__main__":
    main()
