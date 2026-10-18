from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, Query
from fastapi.responses import FileResponse

from models.xray import XrayQuestion, LiveXrayQuestion
from services.xray import EVIDENCE_FILES, XRAY_DIR, XrayService
import settings
from services.xray_live import LIVE_DIR, live_metadata, load_run_manifest, sample_point
from services.xray_explanations import explain_point

router = APIRouter(prefix="/api/xray", tags=["xray"])


@router.get("/live")
def live(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return live_metadata()


def validate_snapshot(run_id: str):
    import re
    if not re.fullmatch(r"\d{8}T\d{6}Z-[a-f0-9]{8}", run_id):
        raise HTTPException(404, "Unknown map snapshot")
    if settings.XRAY_LIVE_PUBLIC_BASE_URL:
        try:
            load_run_manifest(run_id)
        except Exception:
            raise HTTPException(404, "Map snapshot is unavailable") from None
        return
    if not (LIVE_DIR / run_id / "manifest.json").is_file():
        raise HTTPException(404, "Map snapshot is unavailable")


@router.get("/live/{run_id}/sample")
def live_sample(run_id: str, lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)):
    validate_snapshot(run_id)
    try:
        return sample_point(run_id, lat, lon)
    except FileNotFoundError:
        raise HTTPException(503, "Interactive map values are unavailable") from None


@router.post("/live/{run_id}/explain")
def explain_live(run_id: str, body: LiveXrayQuestion, response: Response):
    validate_snapshot(run_id)
    response.headers["Cache-Control"] = "no-store"
    try:
        return explain_point(run_id, body.lat, body.lon, body.question, body.use_gemini)
    except FileNotFoundError:
        raise HTTPException(503, "Explanation evidence is unavailable for this snapshot") from None


@router.get("/live/{run_id}/{layer_id}")
def live_layer(run_id: str, layer_id: Literal["prediction", "satellite", "support", "age"]):
    validate_snapshot(run_id)
    path = LIVE_DIR / run_id / f"{layer_id}.png"
    if not (path.parent / "manifest.json").is_file() or not path.is_file():
        raise HTTPException(404, "Map snapshot is unavailable")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=31536000, immutable"})


def get_xray_service():
    if not (XRAY_DIR / "demo.json").is_file():
        raise HTTPException(503, "X-Ray research export is unavailable")
    return XrayService()


@router.get("")
def metadata(service: XrayService = Depends(get_xray_service)):
    return service.metadata()


@router.get("/survey")
def survey(service: XrayService = Depends(get_xray_service)):
    return service.survey()


@router.get("/segments/{segment_id}")
def segment(segment_id: int, stage: Literal["hidden", "location", "satellite", "reveal"] = "hidden",
            service: XrayService = Depends(get_xray_service)):
    try:
        return service.segment(segment_id, stage)
    except KeyError:
        raise HTTPException(404, "No packaged holdout case for this segment") from None


@router.post("/investigate")
def investigate(body: XrayQuestion, service: XrayService = Depends(get_xray_service)):
    return service.investigate(body.question.strip(), body.segment_id)


@router.get("/evidence/{source_id}")
def evidence(source_id: str):
    name = EVIDENCE_FILES.get(source_id)
    if name is None:
        raise HTTPException(404, "Unknown research source")
    path = XRAY_DIR / "evidence" / name
    if not path.is_file():
        raise HTTPException(503, "Research source is unavailable")
    return FileResponse(path, media_type="text/plain" if path.suffix == ".md" else "application/json")


@router.get("/layers/{layer_id}")
def layer(layer_id: Literal["satellite", "reconstruction"]):
    path = XRAY_DIR / f"{layer_id}.png"
    if not path.is_file():
        raise HTTPException(503, "Research layer is unavailable")
    return FileResponse(path, media_type="image/png")


@router.get("/holdouts/{segment_id}/{model}")
def holdout_layer(segment_id: int, model: Literal["rf_xy", "rf_xysat", "gp_resid", "extrapolation"], extent: Literal["local", "bay"] = "local"):
    if segment_id not in (17, 31, 32):
        raise HTTPException(404, "Unknown holdout segment")
    suffix = "_bay" if extent == "bay" else ""
    path = XRAY_DIR / "holdouts" / f"{segment_id}_{model}{suffix}.png"
    if not path.is_file():
        raise HTTPException(503, "Holdout map is unavailable")
    return FileResponse(path, media_type="image/png")


@router.get("/bay/{layer_id}")
def bay_layer(layer_id: Literal["rf_xy", "rf_xysat", "extrapolation", "satellite"]):
    path = XRAY_DIR / "bay" / f"{layer_id}.png"
    if not path.is_file():
        raise HTTPException(503, "Bay overview layer is unavailable")
    return FileResponse(path, media_type="image/png")
