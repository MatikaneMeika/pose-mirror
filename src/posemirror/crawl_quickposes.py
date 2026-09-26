"""Quickposes.com adapter -- currently a documented stub.

Findings (checked 2026-09-26): quickposes.com serves its pose image library
through JavaScript-driven gallery pages (e.g. /en/gestures/random). The HTML
returned to a plain HTTP client contains no stable image list, no public
JSON API, and no documented bulk-download endpoint. Writing a scraper
against its dynamic frontend would be fragile and could break at any time,
so this module intentionally does NOT ship a hacky crawler.

Manual alternative (fully supported):
    1. Open https://quickposes.com in your browser.
    2. Use the Challenges / Timed practice / Random gestures pages and save
       the reference photos you like (right-click -> Save image).
    3. Drop them into ``data/raw/quickposes/`` (any subfolders are fine).
    4. Run ``python -m posemirror.build_index`` -- it scans ``data/raw/**``
       recursively, no crawler required.

If quickposes.com ever publishes a stable API or data dump, implement
``crawl(limit, out_dir)`` here following the pattern in
``crawl_wikimedia.py`` (real User-Agent, <= 1 request/second, license
metadata recorded per file).
"""

from __future__ import annotations

MANUAL_STEPS = """\
quickposes.com has no stable public API for its image library, so automated
crawling is not implemented. Manual download is supported instead:

  1. Open https://quickposes.com in your browser.
  2. Browse Challenges / Timed practice / Random gestures and save the
     reference photos you like (right-click -> Save image).
  3. Place them under data/raw/quickposes/ (subfolders are fine).
  4. Run: python -m posemirror.build_index

build_index.py scans data/raw/** recursively, so no crawler is needed.
"""


def crawl(limit: int = 200, out_dir: str = "data/raw/quickposes") -> int:  # noqa: ARG001
    """Not implemented -- see module docstring for the manual workflow."""
    raise NotImplementedError(MANUAL_STEPS)


def main() -> None:
    raise NotImplementedError(MANUAL_STEPS)


if __name__ == "__main__":
    main()
