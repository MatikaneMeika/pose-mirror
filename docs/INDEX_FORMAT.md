# pose-mirror index format

This document describes the on-disk index layout produced by
`python -m posemirror.build_index`. The index is built **once** (on PC)
and reused by every client: the Python server reads `data/index/`
directly, and the future Android (Kotlin) app downloads the same files
from a GitHub Release. Both sides must implement the math below
identically.

**Current version: 1** (see `format.json`, `INDEX_FORMAT_VERSION` in
`src/posemirror/pose.py`). Bump the version on any incompatible change
to the normalization or file layout.

## Files

`data/index/` contains:

| File | Description |
|---|---|
| `embeddings.npz` | Pose vectors. NumPy `.npz` (ZIP) with two arrays: `ids` (`<U6` unicode, shape `(N,)`) and `vectors` (`float32`, shape `(N, 66)`). Row `i` of `vectors` belongs to `ids[i]`. |
| `manifest.json` | Object mapping each id (e.g. `"000013"`) to its metadata entry (schema below). UTF-8. |
| `thumbs/{id}.jpg` | JPEG thumbnail per id, longest side ≤ 320 px, quality 85. |
| `format.json` | Version marker + normalization parameters (machine-readable copy of §Versioning). |
| `skipped.log` | Images that failed indexing and why (informational only). |

### Reading `.npz` without NumPy (for the Kotlin client)

An `.npz` file is a plain ZIP archive containing one `.npy` file per
array (`ids.npy`, `vectors.npy`). The `.npy` v1.0 format is: 6 magic
bytes (`\x93NUMPY`), 2-byte little-endian header length, an ASCII
header dict like `{'descr': '<f4', 'fortran_order': False, 'shape':
(1234, 66)}`, then raw little-endian data. Parse the header, read
`N*66` float32 values row-major.

If that is inconvenient, run the bundled exporter instead:

```bash
python -m posemirror.export_portable --index data/index --out dist/index-v1
```

which produces a dependency-free bundle:

| File | Description |
|---|---|
| `vectors.f32le.bin` | Raw little-endian float32, row-major, `N*66` values, no header. |
| `ids.json` | `["000000", "000001", ...]` UTF-8 array, aligned with the binary rows. |
| `manifest.json` | Copy of the manifest. |
| `format.json` | Copy of the version marker. |
| `thumbs/` | Copy of the thumbnails. |

Zip this directory and attach it to a GitHub Release; clients download
and use it as-is.

## Landmark convention

Poses come from the MediaPipe **PoseLandmarker** (full model), which
outputs **33** landmarks per person. Each landmark is `(x, y,
visibility)` with `x, y` in normalized image coordinates in `[0, 1]`
(origin = top-left). "Left"/"right" below is the **subject's** left/right
(as MediaPipe reports it).

Key indices used by the normalization:

| Index | Joint |
|---|---|
| 0 | nose |
| 11 | left shoulder |
| 12 | right shoulder |
| 13 / 14 | left / right elbow |
| 15 / 16 | left / right wrist |
| 23 | left hip |
| 24 | right hip |
| 25 / 26 | left / right knee |
| 27 / 28 | left / right ankle |

`visibility` is MediaPipe's per-joint visibility score in `[0, 1]`.
A joint counts as *visible* when `visibility >= 0.5`.

## Normalization (pseudocode)

Converts 33 `(x, y, visibility)` landmarks into a 66-dim unit vector.
Uses only basic arithmetic — deliberately portable to Kotlin.

```
function normalize(landmarks): float[66] | null
    # landmarks: 33 x (x, y, v), x/y in [0,1]
    visible = count(v >= 0.5 for each landmark)
    if visible < 17:                      # < 50% of joints
        return null                       # reject pose

    mid_hip      = ((x23 + x24) / 2, (y23 + y24) / 2)
    mid_shoulder = ((x11 + x12) / 2, (y11 + y12) / 2)

    scale = distance(mid_shoulder, mid_hip)
    if scale < 1e-6:
        # fallback: largest distance between any two joints
        scale = max(distance(pi, pj) for all i, j)
    if scale < 1e-6:
        return null                       # degenerate pose

    q = []
    for each joint i in 0..32:
        q.append((xi - mid_hip.x) / scale)  # x components: indices 0,2,4,...
        q.append((yi - mid_hip.y) / scale)  # y components: indices 1,3,5,...

    norm = sqrt(sum(qi * qi))
    if norm < 1e-9:
        return null
    return [qi / norm]                    # 66-dim unit vector (float32)
```

Properties: translation-invariant (mid-hip at origin) and
scale-invariant (shoulder–hip distance). Only x/y are used; the z
(depth) channel is reserved for a future format version.

## Matching (pseudocode)

```
function search(query_vec, index_vecs, k):
    # query_vec: 66-dim unit vector; index_vecs: N x 66 unit vectors
    scores = [dot(query_vec, row) for row in index_vecs]  # cosine similarity
    order  = indices sorted by scores descending
    return [(id[i], clamp(scores[i], -1, 1)) for i in order[0:k]]
```

The server reports `score` as a percentage: `round(score * 100, 1)`.

### Mirror toggle

When the user enables "mirror X", negate every **x component**
(even indices `0, 2, 4, ...`) of the *normalized* query vector before
matching. Because normalization is translation + uniform scale,
mirroring `x -> 1 - x` beforehand negates exactly those components,
so this is exact and the vector stays unit norm (no re-normalization
needed).

## Indexing-time decisions (already baked into the data)

- **Multiple people in one image:** keep the detection with the highest
  mean visibility. There is exactly one vector per image.
- **Low visibility:** images with fewer than 50% of joints visible are
  skipped (logged in `skipped.log`).
- **Degenerate poses** (zero scale/norm) are skipped.

Clients do not need to reimplement these; they only affect how the
distributed index was built.

## `manifest.json` schema

```json
{
  "000013": {
    "file": "wikimedia/martial_arts/some_photo.jpg",
    "source": "https://commons.wikimedia.org/wiki/File:...",
    "author": "Jane Doe",
    "license": "CC BY-SA 4.0",
    "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
    "title": "File:Some photo.jpg",
    "width": 1280,
    "height": 853,
    "indexed_at": "2026-09-26T10:35:00+00:00"
  }
}
```

| Field | Type | Notes |
|---|---|---|
| `file` | string | path relative to `data/raw/` (informational) |
| `source` | string | source page URL, may be empty |
| `author` | string | author/credit, may be empty (HTML stripped? no — raw) |
| `license` | string | short license name, may be empty |
| `license_url` | string | license URL, may be empty |
| `title` | string | display title |
| `width` / `height` | int | original image dimensions |
| `indexed_at` | string | ISO-8601 UTC timestamp |

`author` may contain raw HTML from Commons metadata; clients should
strip tags before display.

## Versioning

- `format.json` carries `index_version` (currently `1`), `vector_dim`
  (`66`), `landmark_count` (`33`), and the normalization parameters.
- Clients must check `index_version` on load and refuse versions they
  do not understand.
- Any change to landmark count, normalization math, visibility
  thresholds, or file layout requires a version bump.

## Portability notes

- All floats are IEEE-754 binary32, little-endian.
- No platform-specific tricks: the algorithm is dot products, square
  roots, and comparisons only.
- Text is UTF-8; ids are zero-padded ASCII (`000000` …).
- The Python server (`server.py`) and the Kotlin app must produce
  bit-comparable-enough vectors from the same landmarks: use float64
  intermediates during normalization, store float32.
