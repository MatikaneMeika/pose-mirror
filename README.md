# pose-mirror 🧍

Strike a pose in front of your webcam — get matching reference images for drawing.

`pose-mirror` is a local-first, open-source tool for artists. It watches your
webcam, estimates your body pose in real time, and searches an indexed library
of reference photos for the most similar poses. No cloud, no account, no
tracking — everything runs on your own machine.

[中文说明](README.zh-CN.md)

## Download (Windows, no Python needed)

Grab `pose-mirror.exe` from the
[Releases page](https://github.com/MatikaneMeika/pose-mirror/releases),
put it in its own folder, and double-click it. On first launch it downloads
the pose model (~9 MB) next to the exe; afterwards it runs fully offline.
Then open http://127.0.0.1:8000 in your browser.

> Want the exe built for a new version? It is produced automatically by
> GitHub Actions whenever a `v*` tag is pushed (see
> `.github/workflows/build.yml`).

## Mobile app (Android)

There is a native Android client:
[pose-mirror-android](https://github.com/MatikaneMeika/pose-mirror-android).
It runs fully offline and independently — CameraX + MediaPipe PoseLandmarker
on your phone, searching the same portable index format. The two apps never
talk to each other; the only thing they share is the index file layout
(`docs/INDEX_FORMAT.md`).

## Quickstart

**Windows:** double-click `install.bat`.
**Linux/macOS:** run `bash setup.sh`.

The script checks Python 3.10+, creates `.venv`, installs everything, and
prints the next three commands. In short:

```bash
# fetch openly-licensed reference photos (Wikimedia Commons)
.venv/bin/python -m posemirror.crawl_wikimedia --limit 50

# build the pose index (downloads the MediaPipe model on first run)
.venv/bin/python -m posemirror.build_index

# serve the app, then open http://127.0.0.1:8000
.venv/bin/python -m posemirror.server
```

(On Windows use `.venv\Scripts\python` instead of `.venv/bin/python`.)

Stand where the camera can see your full body, strike a pose, and watch the
right-hand grid update with the closest reference photos. Click any thumbnail
to enlarge it.

## How it works

```
webcam frame ──▶ MediaPipe PoseLandmarker ──▶ 33 landmarks
                        │
                        ▼
              normalize: mid-hip → origin,
              scale by shoulder–hip distance,
              flatten x/y → 66-dim unit vector
                        │
                        ▼
        cosine similarity vs indexed vectors ──▶ top-k matches
```

- **Pose estimation**: MediaPipe Tasks `PoseLandmarker` (full model, IMAGE
  running mode). The model bundle is auto-downloaded to `models/` on first
  run and is gitignored — it is never committed.
- **Normalization** (`src/posemirror/pose.py`): translation-invariant
  (mid-hip at origin) and scale-invariant (shoulder–hip distance; falls back
  to max pairwise joint distance). Only x/y are used in v1; the z (depth)
  channel is future work.
- **Matching**: cosine similarity between unit vectors. Multi-person images
  keep the detection with the highest mean visibility; images with fewer
  than 50% of joints visible are skipped during indexing.
- **Mirror toggle**: flips the query pose horizontally before matching —
  useful when the reference faces the opposite direction.
- **Server**: FastAPI + a background OpenCV capture thread. The browser UI is
  plain HTML/JS with no ML and no CDN dependency: an MJPEG `<img>` for the
  annotated stream plus polling of `/api/matches`.

## Data sources

| Source | Method | License handling |
|---|---|---|
| Wikimedia Commons | `crawl_wikimedia` — polite API client (real User-Agent, ~1 req/s) | author + license recorded per image into the index manifest |
| quickposes.com | manual download (no stable public API; see module docstring) → `data/raw/quickposes/` | for personal study use |
| Your own photos | drop into `data/raw/` (any subfolders) | yours |

All downloaded images live under `data/` and are gitignored. **Never commit
downloaded images or the model to the repo.**

## Project layout

```
pose-mirror/
├── src/posemirror/
│   ├── pose.py             # model download, extraction, normalization, similarity
│   ├── crawl_wikimedia.py  # Commons API crawler (polite, licensed metadata)
│   ├── crawl_quickposes.py # documented stub → manual download workflow
│   ├── build_index.py      # scan data/raw/** → embeddings.npz + manifest + thumbs
│   │                       # + format.json (index format v1, see docs/INDEX_FORMAT.md)
│   ├── export_portable.py  # index → dependency-free bundle for GitHub Releases
│   └── server.py           # FastAPI: / (UI), /api/stream, /api/matches, /api/search, /api/status
├── web/                    # dark artist-friendly UI (no build step, responsive)
├── docs/
│   └── INDEX_FORMAT.md     # portable index spec shared with the Android client
├── data/                   # gitignored: raw images + index
└── models/                 # gitignored: MediaPipe bundle
```

## API

- `GET /` — UI
- `GET /api/stream` — MJPEG camera stream with skeleton overlay (503 if no camera)
- `GET /api/matches?k=9&mirror=0` — JSON top-k matches
- `POST /api/search` — JSON body `{"landmarks": [[x,y],...] (33 pairs),
  "mirror": false, "top_k": 9}`; stateless matching for a client-supplied
  pose (scripts, tests, third-party clients). No image data crosses the
  network. Not part of the mobile architecture.
- `GET /api/status` — `{"camera_ok": bool, "index_size": int, ...}`
- `GET /thumbs/{id}.jpg` — static thumbnails

## Roadmap

- [ ] Android app (native, Kotlin): CameraX + MediaPipe Tasks PoseLandmarker
      for Android. Fully offline and independent — no connection to the PC
      whatsoever. It reuses the exact same index data: build once on PC,
      export with `python -m posemirror.export_portable`, attach the bundle
      to a GitHub Release, and have the app download it. The normalization
      and matching math is specified in `docs/INDEX_FORMAT.md` (plain
      pseudocode, no exotic dependencies) so the Kotlin side can mirror it
      line by line.
- [ ] Use the z (depth) channel in the pose vector (requires index format v2).
- [ ] VIDEO running mode with tracking for smoother live matching.
- [ ] Optional text/keyword search over the manifest.

## Contributing

PRs welcome. Keep it pure-Python, no JS ML, no CDN dependency. Code comments
and docstrings in English. Run `python -m py_compile` on changed files.
