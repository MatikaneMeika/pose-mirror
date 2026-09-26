"""FastAPI server: webcam pose capture + top-k reference matching.

Endpoints:
    GET /             artist UI (dark theme)
    GET /api/stream   MJPEG stream of the camera with skeleton overlay
    GET /api/matches  JSON top-k matches, params: k (default 9), mirror (0/1)
    GET /api/status   {"camera_ok": bool, "index_size": int, ...}
    GET /thumbs/...   static thumbnails from data/index/thumbs/

The webcam runs in a background thread; if no camera is available the
server keeps working (status reports it, stream returns 503, matches
return []).
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .pose import (
    N_LANDMARKS,
    annotate_frame,
    cosine_similarity,
    ensure_model,
    extract_pose,
    normalize_pose,
    project_root,
)

ROOT = project_root()
WEB_DIR = ROOT / "web"

state = {
    "frame_jpeg": None,          # latest annotated JPEG bytes
    "query_vec": None,           # latest normalized pose vector (or None)
    "camera_ok": False,
    "camera_error": None,
    "index_ids": [],
    "index_vectors": None,       # (N, 66) float32
    "manifest": {},
    "lock": threading.Lock(),
}


def load_index(index_dir: Path) -> None:
    emb_path = index_dir / "embeddings.npz"
    manifest_path = index_dir / "manifest.json"
    if emb_path.exists():
        data = np.load(emb_path)
        state["index_ids"] = [str(i) for i in data["ids"]]
        state["index_vectors"] = data["vectors"].astype(np.float32)
    if manifest_path.exists():
        state["manifest"] = json.loads(manifest_path.read_text())
    print(f"[server] index loaded: {len(state['index_ids'])} poses")


def camera_loop() -> None:
    """Background thread: grab frames, estimate pose, annotate."""
    while True:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            with state["lock"]:
                state["camera_ok"] = False
                state["camera_error"] = "no camera found (index 0)"
                state["frame_jpeg"] = None
                state["query_vec"] = None
            time.sleep(5)  # retry periodically (e.g. camera plugged in later)
            continue
        with state["lock"]:
            state["camera_ok"] = True
            state["camera_error"] = None
        print("[server] camera opened")
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                try:
                    landmarks = extract_pose(frame)
                except Exception:  # noqa: BLE001 - never kill the loop
                    landmarks = None
                vec = normalize_pose(landmarks) if landmarks else None
                annotated = annotate_frame(frame, landmarks)
                _, jpeg = cv2.imencode(".jpg", annotated,
                                       [cv2.IMWRITE_JPEG_QUALITY, 80])
                with state["lock"]:
                    state["frame_jpeg"] = jpeg.tobytes()
                    state["query_vec"] = vec
        finally:
            cap.release()
        with state["lock"]:
            state["camera_ok"] = False
            state["camera_error"] = "camera disconnected"
        time.sleep(2)


def match_vector(vec: np.ndarray, k: int) -> list[dict]:
    """Rank the index against a normalized query pose vector."""
    with state["lock"]:
        vectors = state["index_vectors"]
        ids = state["index_ids"]
        manifest = state["manifest"]
    if vectors is None or len(ids) == 0:
        return []
    sims = vectors @ vec  # cosine similarity, vectors are unit norm
    order = np.argsort(sims)[::-1][: max(1, k)]
    results = []
    for idx in order:
        entry_id = ids[int(idx)]
        meta = manifest.get(entry_id, {})
        results.append({
            "id": entry_id,
            "score": round(float(np.clip(sims[int(idx)], -1, 1)) * 100, 1),
            "thumb": f"/thumbs/{entry_id}.jpg",
            "title": meta.get("title", entry_id),
            "author": meta.get("author", ""),
            "license": meta.get("license", ""),
            "source": meta.get("source", ""),
        })
    return results


def top_matches(k: int, mirror: bool) -> list[dict]:
    with state["lock"]:
        vec = state["query_vec"]
    if vec is None:
        return []
    if mirror:
        # Mirror the query pose horizontally. The normalized vector stores
        # ((x - mid_hip_x) / scale) for each joint, so mirroring x -> 1 - x
        # exactly negates the x components; the vector stays unit norm.
        vec = vec.copy()
        vec[0::2] = -vec[0::2]
    return match_vector(vec, k)


class SearchRequest(BaseModel):
    """Remote pose query, e.g. from the phone web client.

    ``landmarks`` uses the same convention as the MediaPipe pose output:
    33 points in normalized image coordinates [0, 1]. Accepted shapes:
    33 ``[x, y]`` pairs, 33 ``[x, y, visibility]`` triples, or a flat
    array of 66 (x, y) / 99 (x, y, visibility) floats.
    """

    landmarks: list = Field(description="33 pose landmarks, see docstring")
    mirror: bool = False
    top_k: int = 9


def parse_landmarks(raw: list) -> list[tuple[float, float, float]] | None:
    """Parse flexible landmark input into [(x, y, visibility)] x 33."""
    try:
        arr = np.asarray(raw, dtype=np.float64)
    except (ValueError, TypeError):
        return None
    if arr.ndim == 1:
        if arr.size == N_LANDMARKS * 2:
            arr = arr.reshape(N_LANDMARKS, 2)
        elif arr.size == N_LANDMARKS * 3:
            arr = arr.reshape(N_LANDMARKS, 3)
        else:
            return None
    if arr.ndim != 2 or arr.shape[0] != N_LANDMARKS or arr.shape[1] not in (2, 3):
        return None
    if arr.shape[1] == 2:
        pts, vis = arr, np.ones(N_LANDMARKS)
    else:
        pts, vis = arr[:, :2], arr[:, 2]
    return [(float(x), float(y), float(v)) for (x, y), v in zip(pts, vis)]


app = FastAPI(title="pose-mirror")


@app.get("/")
def index_page():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/status")
def api_status():
    with state["lock"]:
        return {
            "camera_ok": state["camera_ok"],
            "camera_error": state["camera_error"],
            "index_size": len(state["index_ids"]),
            "pose_detected": state["query_vec"] is not None,
        }


@app.get("/api/matches")
def api_matches(
    k: int = Query(9, ge=1, le=50),
    mirror: int = Query(0, ge=0, le=1),
):
    return JSONResponse(top_matches(k, bool(mirror)))


@app.post("/api/search")
def api_search(req: SearchRequest):
    """Match a client-supplied pose against the index.

    Stateless utility: the caller does pose estimation itself (a script,
    test, or third-party client) and sends only the 33 landmarks; no
    image data crosses the network. It is NOT part of any phone
    architecture -- the mobile app runs fully offline and independently.
    """
    landmarks = parse_landmarks(req.landmarks)
    if landmarks is None:
        return JSONResponse(
            {"detail": "landmarks must be 33 [x, y] pairs (or [x, y, v] "
                       "triples), or a flat array of 66/99 floats"},
            status_code=400,
        )
    vec = normalize_pose(landmarks, mirror_x=req.mirror)
    if vec is None:
        return JSONResponse(
            {"detail": "pose invalid: <50% joints visible or degenerate"},
            status_code=422,
        )
    k = max(1, min(50, req.top_k))
    return JSONResponse(match_vector(vec, k))


@app.get("/api/stream")
def api_stream():
    with state["lock"]:
        ok = state["camera_ok"]
    if not ok:
        return JSONResponse(
            {"detail": "camera unavailable"}, status_code=503
        )

    def gen():
        boundary = b"--frame"
        while True:
            with state["lock"]:
                jpeg = state["frame_jpeg"]
            if jpeg is None:
                time.sleep(0.05)
                continue
            yield (boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n"
                   + jpeg + b"\r\n")
            time.sleep(0.04)  # ~25 fps cap

    return StreamingResponse(
        gen(), media_type="multipart/x-mixed-replace; boundary=frame"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="pose-mirror server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--index", default="data/index")
    parser.add_argument("--no-camera", action="store_true",
                        help="skip webcam capture (index browsing only)")
    args = parser.parse_args()

    import uvicorn

    ensure_model()
    index_dir = Path(args.index)
    if not index_dir.is_absolute():
        index_dir = ROOT / index_dir
    if index_dir.exists():
        load_index(index_dir)
        thumbs = index_dir / "thumbs"
        if thumbs.exists():
            app.mount("/thumbs", StaticFiles(directory=thumbs), name="thumbs")
    else:
        print(f"[server] no index at {index_dir} "
              f"(run build_index first); matches will be empty")
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    if not args.no_camera:
        threading.Thread(target=camera_loop, daemon=True).start()
    else:
        print("[server] camera disabled by --no-camera")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
