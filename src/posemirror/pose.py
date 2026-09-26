"""Pose estimation and similarity utilities for pose-mirror.

Uses the MediaPipe Tasks ``PoseLandmarker`` model, which is auto-downloaded
into ``models/`` on first run. All public functions are thread-safe.
"""

from __future__ import annotations

import sys
import threading
import urllib.request
from pathlib import Path

import cv2
import numpy as np

# Official MediaPipe model bundle (float16, full variant).
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_full/float16/1/pose_landmarker_full.task"
)
MODEL_NAME = "pose_landmarker_full.task"
USER_AGENT = "pose-mirror/0.1 (open-source art reference tool)"

# MediaPipe PoseLandmarker indices for the 33 body landmarks.
LEFT_HIP, RIGHT_HIP = 23, 24
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
N_LANDMARKS = 33
VISIBILITY_THRESHOLD = 0.5
MIN_VISIBLE_RATIO = 0.5  # skip images with fewer visible joints than this

# Version of the on-disk index layout described in docs/INDEX_FORMAT.md.
# Bump when the normalization or file layout changes in an incompatible way.
INDEX_FORMAT_VERSION = 1

# Skeleton connections drawn on the annotated stream (subset of the full set).
POSE_CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),  # shoulders / arms
    (15, 17), (15, 19), (15, 21), (16, 18), (16, 20), (16, 22),  # hands
    (11, 23), (12, 24), (23, 24),  # torso
    (23, 25), (25, 27), (24, 26), (26, 28),  # legs
    (27, 29), (27, 31), (29, 31), (28, 30), (28, 32), (30, 32),  # feet
    (0, 1), (0, 4), (1, 2), (2, 3), (4, 5), (5, 6),  # head (simple)
]

_lock = threading.Lock()
_landmarker = None


def project_root() -> Path:
    """Return the pose-mirror project root directory.

    When running from a PyInstaller bundle, the "project root" is the
    directory containing the executable -- that is where writable data
    (``models/``, ``data/``) lives. Read-only bundled assets (``web/``)
    come from :func:`resource_path` instead.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resource_path(*parts: str) -> Path:
    """Path to a read-only resource bundled with the application.

    In a PyInstaller bundle this resolves inside the extracted package
    (``sys._MEIPASS``); in a source checkout it resolves under the
    project root.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS, *parts)  # type: ignore[attr-defined]
    return project_root().joinpath(*parts)


def default_model_path() -> Path:
    return project_root() / "models" / MODEL_NAME


def ensure_model(model_path: Path | str | None = None) -> Path:
    """Download the PoseLandmarker bundle into ``models/`` if missing."""
    path = Path(model_path) if model_path else default_model_path()
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[pose-mirror] downloading pose model -> {path}")
    req = urllib.request.Request(MODEL_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp, open(path, "wb") as fh:
        fh.write(resp.read())
    print("[pose-mirror] model download complete")
    return path


def _get_landmarker():
    global _landmarker
    if _landmarker is None:
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        model_path = ensure_model()
        base = python.BaseOptions(model_asset_path=str(model_path))
        options = vision.PoseLandmarkerOptions(
            base_options=base,
            running_mode=vision.RunningMode.IMAGE,
            num_poses=3,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        _landmarker = vision.PoseLandmarker.create_from_options(options)
    return _landmarker


def extract_pose(bgr: np.ndarray) -> list[tuple[float, float, float]] | None:
    """Detect the most prominent person in a BGR image.

    Returns a list of 33 ``(x, y, visibility)`` tuples in normalized
    image coordinates, or ``None`` when no person is detected.
    With multiple people in frame, the detection with the highest mean
    visibility is kept.
    """
    import mediapipe as mp

    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    with _lock:
        result = _get_landmarker().detect(image)
    if not result.pose_landmarks:
        return None

    def mean_visibility(pose) -> float:
        return float(np.mean([lm.visibility for lm in pose]))

    best = max(result.pose_landmarks, key=mean_visibility)
    return [(float(lm.x), float(lm.y), float(lm.visibility)) for lm in best]


def normalize_pose(
    landmarks: list[tuple[float, float, float]], mirror_x: bool = False
) -> np.ndarray | None:
    """Normalize a pose into a unit vector for cosine similarity.

    Steps: translate so the mid-hip (landmarks 23/24 midpoint) is the
    origin, scale by the shoulder-hip distance (falling back to the max
    pairwise joint distance), flatten x/y and L2-normalize.

    Only x/y are used in v1; the z (depth) channel is noted as future
    work in the README. Returns ``None`` when fewer than 50% of the
    body joints are visible or the pose is degenerate.
    """
    pts = np.array([(x, y) for x, y, _ in landmarks], dtype=np.float64)
    vis = np.array([v for _, _, v in landmarks], dtype=np.float64)
    if pts.shape[0] != N_LANDMARKS:
        return None
    if float(np.mean(vis >= VISIBILITY_THRESHOLD)) < MIN_VISIBLE_RATIO:
        return None
    if mirror_x:
        pts[:, 0] = 1.0 - pts[:, 0]

    mid_hip = (pts[LEFT_HIP] + pts[RIGHT_HIP]) / 2.0
    mid_shoulder = (pts[LEFT_SHOULDER] + pts[RIGHT_SHOULDER]) / 2.0
    scale = float(np.linalg.norm(mid_shoulder - mid_hip))
    if scale < 1e-6:
        # Fallback: largest distance between any two joints.
        diff = pts[:, None, :] - pts[None, :, :]
        scale = float(np.max(np.linalg.norm(diff, axis=-1)))
    if scale < 1e-6:
        return None

    vec = ((pts - mid_hip) / scale).reshape(-1)
    norm = float(np.linalg.norm(vec))
    if norm < 1e-9:
        return None
    return (vec / norm).astype(np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two unit pose vectors, in [-1, 1]."""
    return float(np.clip(np.dot(a, b), -1.0, 1.0))


def annotate_frame(
    bgr: np.ndarray, landmarks: list[tuple[float, float, float]] | None
) -> np.ndarray:
    """Draw the detected skeleton onto a copy of the frame."""
    frame = bgr.copy()
    if not landmarks:
        return frame
    h, w = frame.shape[:2]
    pts = [(int(x * w), int(y * h)) for x, y, _ in landmarks]
    for a, b in POSE_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (0, 255, 0), 2, cv2.LINE_AA)
    for x, y in pts:
        cv2.circle(frame, (x, y), 3, (0, 200, 255), -1, cv2.LINE_AA)
    return frame
