"""Download openly-licensed pose reference photos from Wikimedia Commons.

Uses the public Commons API (no key required). Polite by design: a real
User-Agent header and ~1s between requests. Every download is stored next
to a JSON sidecar recording author + license, which ``build_index.py``
picks up into the index manifest.

Example:
    python -m posemirror.crawl_wikimedia --limit 50
    python -m posemirror.crawl_wikimedia --categories "Category:Yoga" --limit 20
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

API_URL = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "pose-mirror/0.1 (open-source art reference tool)"

DEFAULT_CATEGORIES = [
    "Category:Martial arts",
    "Category:People dancing",
    "Category:Yoga as exercise",
    "Category:People running",
    "Category:People jumping",
]

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})


def api(params: dict, retries: int = 3) -> dict:
    params = {"format": "json", "formatversion": 2, **params}
    last_exc = None
    for attempt in range(retries):
        try:
            resp = session.get(API_URL, params=params, timeout=30)
            if resp.status_code == 429:
                # Rate limited: back off longer before retrying.
                time.sleep(30)
                continue
            resp.raise_for_status()
            time.sleep(0.5)  # be polite to the public API
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(2 ** attempt)  # back off, the network may be flaky
    raise last_exc


def iter_category_members(category: str, member_type: str, limit: int,
                          with_imageinfo: bool = False):
    """Yield raw page dicts for members of a category."""
    seen = 0
    cont: dict = {}
    while seen < limit:
        params = {
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": category,
            "gcmtype": member_type,
            "gcmlimit": min(50, limit - seen),
        }
        if with_imageinfo:
            # Batch imageinfo into the generator query: one API call per
            # 50 files instead of one per file.
            params.update({
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": 1280,  # 1280px thumbnail, not the full original
            })
        data = api({**params, **cont})
        pages = data.get("query", {}).get("pages", [])
        if not pages:
            break
        for page in pages:
            yield page
            seen += 1
            if seen >= limit:
                break
        cont = data.get("continue", {})
        if not cont:
            break


def iter_category_files(category: str, limit: int, depth: int = 1,
                        _seen_titles: set | None = None):
    """Yield (title, imageinfo) dicts for files in a category.

    Many Commons categories keep their files in subcategories, so by
    default we also descend one level (``depth=1``). Titles are
    deduplicated across the whole crawl.
    """
    if _seen_titles is None:
        _seen_titles = set()
    yielded = 0
    for page in iter_category_members(category, "file", limit,
                                      with_imageinfo=True):
        info = (page.get("imageinfo") or [{}])[0]
        if not (info.get("thumburl") or info.get("url")):
            continue
        title = page["title"]
        if title in _seen_titles:
            continue
        _seen_titles.add(title)
        yield title, info
        yielded += 1
        if yielded >= limit:
            return
    if depth > 0:
        for sub in iter_category_members(category, "subcat", 50):
            for title, info in iter_category_files(
                    sub["title"], limit - yielded, depth - 1, _seen_titles):
                yield title, info
                yielded += 1
                if yielded >= limit:
                    return


def slugify(text: str) -> str:
    keep = [c if c.isalnum() else "_" for c in text.lower()]
    return "".join(keep).strip("_")[:60] or "misc"


def download(url: str, dest: Path) -> None:
    with session.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                fh.write(chunk)
    time.sleep(1.0)  # rate limit: ~1 download per second


def metadata_from(info: dict) -> dict:
    ext = info.get("extmetadata", {}) or {}
    def val(key: str) -> str:
        return (ext.get(key) or {}).get("value", "")
    return {
        "author": val("Artist"),
        "license": val("LicenseShortName"),
        "license_url": val("LicenseUrl"),
        "description": val("ImageDescription")[:300],
        "source_url": info.get("descriptionurl", ""),
    }


def crawl(categories: list[str], limit: int, out_dir: Path, depth: int = 1) -> int:
    total = 0
    for category in categories:
        dest_dir = out_dir / slugify(category.replace("Category:", ""))
        dest_dir.mkdir(parents=True, exist_ok=True)
        print(f"[crawl] category: {category} -> {dest_dir}")
        for title, info in iter_category_files(category, limit, depth):
            url = info.get("thumburl") or info.get("url")
            name = slugify(title.rsplit(":", 1)[-1].rsplit(".", 1)[0])[:50]
            ext = ".jpg"
            dest = dest_dir / f"{name}{ext}"
            sidecar = dest_dir / f"{name}.json"
            if dest.exists():
                continue
            try:
                download(url, dest)
            except Exception as exc:  # noqa: BLE001 - keep crawling on failures
                print(f"[crawl] SKIP {title}: {exc}")
                continue
            meta = metadata_from(info)
            meta.update({"title": title, "file": dest.name})
            sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
            total += 1
            print(f"[crawl] saved {dest} ({total})")
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl Wikimedia Commons pose photos")
    parser.add_argument("--limit", type=int, default=200,
                        help="max images per category (default: 200)")
    parser.add_argument("--categories", nargs="*", default=DEFAULT_CATEGORIES,
                        help="Commons categories to crawl")
    parser.add_argument("--depth", type=int, default=1,
                        help="subcategory recursion depth (default: 1)")
    parser.add_argument("--out", default="data/raw/wikimedia",
                        help="output directory (default: data/raw/wikimedia)")
    args = parser.parse_args()

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        from .pose import project_root
        out_dir = project_root() / out_dir
    total = crawl(args.categories, args.limit, out_dir, args.depth)
    print(f"[crawl] done, {total} images downloaded")


if __name__ == "__main__":
    main()
