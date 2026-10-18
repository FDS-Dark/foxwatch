"""Serve a portable, verified export of the completed spatial holdout research."""
from functools import lru_cache
import json

from settings import DATA_DIR

XRAY_DIR = DATA_DIR / "xray"
EVIDENCE_FILES = {
    "observations": "observations.geojson", "metrics": "metrics.json",
    "results": "results.md", "decision": "decision.md", "segment32": "segment32.geojson",
}


@lru_cache(maxsize=1)
def load_demo():
    return json.loads((XRAY_DIR / "demo.json").read_text(encoding="utf-8"))


def load_holdout_maps():
    path = XRAY_DIR / "holdouts" / "manifest_bay.json"
    if not path.is_file():
        path = XRAY_DIR / "holdouts" / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


class XrayService:
    def metadata(self):
        data = load_demo()
        result = {k: v for k, v in data.items() if k not in ("observations", "cases")}
        result["observation_count"] = len(data["observations"])
        bay_manifest = XRAY_DIR / "bay" / "manifest.json"
        result["bay"] = json.loads(bay_manifest.read_text(encoding="utf-8")) if bay_manifest.is_file() else None
        result["cases"] = [{"id": c["id"], "label": c["label"],
                            "matched_count": len(c["points"]), "total_count": len(c["target_ids"])}
                           for c in data["cases"].values()]
        return result

    def survey(self):
        data = load_demo()
        return {"campaign": data["campaign"], "units": data["units"], "observations": data["observations"]}

    def segment(self, segment_id: int, stage: str):
        data = load_demo()
        case = data["cases"][str(segment_id)]
        observations = {o["id"]: o for o in data["observations"]}
        points = []
        for prediction in case["points"]:
            obs = observations[prediction["id"]]
            point = {k: obs[k] for k in ("id", "lat", "lon", "observed_at")}
            point.update({k: prediction[k] for k in ("distance_km", "scene_id", "lag_hours")})
            if stage != "hidden":
                point["predictions"] = {k: v for k, v in prediction["predictions"].items()
                                        if stage != "location" or k in ("rf_xy", "gp_xy", "idw")}
            if stage == "reveal":
                point["value"] = obs["value"]
            points.append(point)
        result = {"id": segment_id, "label": case["label"], "stage": stage,
                  "units": data["units"], "protocol": data["protocol"],
                  "matched_count": len(points), "total_count": len(case["target_ids"]),
                  "training": [observations[idx] for idx in case["train_ids"]],
                  "target": [{k: observations[idx][k] for k in ("id", "lat", "lon", "observed_at")}
                             for idx in case["target_ids"]], "points": points}
        if stage == "reveal":
            result["metrics"] = case["metrics"]
        if stage != "hidden":
            surfaces = load_holdout_maps()[str(segment_id)]
            result["surfaces"] = {**surfaces, "layers": {
                key: value for key, value in surfaces["layers"].items()
                if stage != "location" or key == "rf_xy"
            }}
        return result

    def investigate(self, question: str, segment_id: int):
        data = load_demo()
        case = data["cases"][str(segment_id)]
        q = question.lower()
        m = case["metrics"]
        citations = ["usgs", "observations", "metrics", "results", "decision"]
        if any(word in q for word in ("why", "improv", "explain", "plume", "satellite", "segment")):
            change = 100 * (1 - m["gp_resid"]["mae"] / m["rf_xy"]["mae"])
            direction = "lower" if change > 0 else "higher"
            answer = [
                f"On segment {segment_id}, the location-only random forest has a mean absolute error of {m['rf_xy']['mae']:.2f} RFU. "
                f"The diagnostic satellite-trend + spatial GP has an error of {m['gp_resid']['mae']:.2f} RFU "
                f"({abs(change):.1f}% {direction}), measured against the same {len(case['points'])} withheld bins.",
                f"The primary location + satellite random forest has an error of {m['rf_xysat']['mae']:.2f} RFU. "
                "It is a different model from the diagnostic GP; the stronger segment-32 result must not be attributed to the primary model.",
                ("A plausible interpretation is that satellite reflectance supplies plume structure that nearby coordinates alone miss. "
                 "The research finds that red-edge brightness also tracks turbidity, so this is not proof of a chlorophyll-specific signal."
                 if segment_id == 32 else
                 "Satellite information does not guarantee a better reconstruction. The research reports overshoot near the river mouth; "
                 "this case should be read alongside segment 32 rather than treating that improvement as universal."),
                "Across 48 hard-holdout folds, the diagnostic GP is worse than the location-only RF in 33 folds. "
                "The primary RF comparison improves pooled error by only 3.4%, with a bootstrap interval that includes zero improvement.",
            ]
        elif any(word in q for word in ("valid", "reliab", "uncertain", "general", "fail", "accur", "bloom")):
            answer = [
                "The evaluation hides contiguous 5 km segments, excludes 1 km of adjacent track and measurements within 1.5 km, "
                "and compares every model on identical satellite-matched bins. Predictions were saved during that evaluation; the app does not train on the reveal.",
                "The primary RF comparison gives 0.609 vs 0.630 RFU pooled MAE. The relative MAE change is −3.4%, "
                "with a 95% fold-bootstrap interval of −7.9% to +3.1%. A general benefit is not established.",
                "The diagnostic GP is worse in 33 of 48 folds. Segment 31 illustrates failure: "
                "2.57 RFU MAE for the satellite-trend GP versus 0.86 for the location-only RF.",
                "Neither fluorescence reconstruction nor a satellite spectral index establishes a harmful bloom. "
                "The satellite-informed uncertainty also failed to reliably identify larger errors.",
            ]
        elif any(word in q for word in ("source", "data", "measur", "time", "unit", "rfu", "boat")):
            lags = [p["lag_hours"] for p in case["points"]]
            answer = [
                f"The replay contains {len(data['observations'])} real 100 m bins from the USGS FLAMe Green Bay survey, "
                f"{data['start']} through {data['end']}. The target is sensor-response-corrected EXO2 chlorophyll fluorescence in RFU.",
                f"Segment {segment_id} contains {len(case['target_ids'])} observation bins; {len(case['points'])} have satellite matches "
                "and participate in the displayed model comparison. Unmatched bins are excluded from the reported errors.",
                f"For these matched bins, signed satellite acquisition minus boat time ranges from {min(lags):.2f} to {max(lags):.2f} hours. "
                "Negative means the satellite passed earlier. Each point identifies its actual scene and observation timestamp.",
                "RFU is relative fluorescence, not chlorophyll concentration in micrograms per liter. "
                "The survey is historical; the map does not describe current bay conditions.",
            ]
        else:
            return {"supported": False, "answer": ["This investigator is limited to the stored FLAMe survey and spatial holdout results. "
                    "Ask about the segment comparison, validation, or measurement sources; no evidence-backed answer is available for that question."],
                    "sources": [], "limitations": [], "mode": "stored_research_evidence"}
        return {"supported": True, "answer": answer, "sources": [s for s in data["sources"] if s["id"] in citations],
                "limitations": data["limitations"][:2], "mode": "stored_research_evidence"}
