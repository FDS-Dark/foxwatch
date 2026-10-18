"""Download the USGS FLAMe data release (doi:10.5066/P1XHRFKZ) from ScienceBase.

File list is resolved from the ScienceBase item JSON at run time so URLs are not hard-coded.
Writes to data/raw/ and records a manifest with sizes and SHA-256 hashes.
"""
import hashlib
import json
import pathlib
import sys
import urllib.request

ITEM_ID = "672e5378d34ea9e450891ffe"  # target of https://doi.org/10.5066/P1XHRFKZ
ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
NATURAL_EARTH = ["ne_10m_lakes", "ne_10m_lakes_north_america"]
MANUAL_HELP = f"""
FLAMe_data.csv is stored in ScienceBase cloud storage and is only served through the login-gated
ScienceBase File Manager (the public 'download all' zip contains a 0-byte placeholder). Download it manually:
  1. https://sciencebase.usgs.gov/manager/item/{ITEM_ID}  (sign in with a free login.gov/ScienceBase account)
  2. select FLAMe_data.csv -> Download -> follow the temporary link
  3. save as {RAW / 'FLAMe_data.csv'}  (expected size 191,928,255 bytes)
"""


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    item_url = f"https://www.sciencebase.gov/catalog/item/{ITEM_ID}?format=json"
    with urllib.request.urlopen(item_url) as r:
        item = json.load(r)
    manifest = {"doi": "10.5066/P1XHRFKZ", "sciencebase_item": item_url, "title": item["title"], "files": []}
    for f in item["files"]:
        dest = RAW / f["name"]
        uri = f.get("downloadUri") or f["url"]
        if not dest.exists() or dest.stat().st_size != f["size"]:
            if f.get("pathOnDisk") == "__s3__":
                print(f"cannot fetch {f['name']} anonymously.{MANUAL_HELP}", file=sys.stderr)
                continue
            print(f"downloading {f['name']} ({f['size'] / 1e6:.1f} MB)")
            urllib.request.urlretrieve(uri, dest)
        sha = hashlib.sha256(dest.read_bytes()).hexdigest()
        manifest["files"].append({"name": f["name"], "size": dest.stat().st_size, "sha256": sha, "url": uri})
    ne = RAW / "naturalearth"
    ne.mkdir(exist_ok=True)
    for n in NATURAL_EARTH:
        uri = f"https://naciscdn.org/naturalearth/10m/physical/{n}.zip"
        dest = ne / f"{n}.zip"
        if not dest.exists():
            urllib.request.urlretrieve(uri, dest)
        manifest["files"].append({"name": f"naturalearth/{n}.zip", "size": dest.stat().st_size,
                                  "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(), "url": uri})
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
