"""Build the public portfolio into dist/ for Cloudflare Pages.

Usage: python build_cloudflare.py --site-url https://jowoohyung-portfolio.pages.dev
The checked-out source files are never changed.
"""

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
ASSET_DIRS = ("css", "js", "img", "video", "content", "portfolio", "_next")
ROOT_FILES = ("index.html", "404.html", "robots.txt", "sitemap.xml")
MAX_ASSET_SIZE = 25 * 1024 * 1024


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-url", default="")
    args = parser.parse_args()
    if DIST.resolve().parent != ROOT.resolve():
        raise RuntimeError("Output directory must stay inside the portfolio checkout")
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    for name in ROOT_FILES:
        shutil.copy2(ROOT / name, DIST / name)
    for name in ASSET_DIRS:
        shutil.copytree(ROOT / name, DIST / name, dirs_exist_ok=True)
    for target in DIST.rglob("*"):
        if target.is_file() and target.stat().st_size >= MAX_ASSET_SIZE:
            raise RuntimeError(f"Asset exceeds Cloudflare Pages' 25 MiB limit: {target}")

    if args.site_url:
        index = DIST / "index.html"
        html = index.read_text(encoding="utf-8")
        html = html.replace("https://1jang2.netlify.app", args.site_url.rstrip("/"))
        index.write_text(html, encoding="utf-8")
        robots = DIST / "robots.txt"
        robots.write_text(robots.read_text(encoding="utf-8").replace("https://1jang2.netlify.app", args.site_url.rstrip("/")), encoding="utf-8")
        sitemap = DIST / "sitemap.xml"
        sitemap.write_text(sitemap.read_text(encoding="utf-8").replace("https://1jang2.netlify.app", args.site_url.rstrip("/")), encoding="utf-8")

    (DIST / "_redirects").write_text("/tools/* /404.html 404!\n/services/* /404.html 404!\n/api/meta-ads/* /404.html 404!\n", encoding="utf-8")
    (DIST / "_headers").write_text("/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n", encoding="utf-8")
    files = [p for p in DIST.rglob("*") if p.is_file()]
    print(f"Built {len(files)} files, {sum(p.stat().st_size for p in files) / 1024 / 1024:.1f} MiB")
    print(f"Largest: {max(files, key=lambda p: p.stat().st_size).relative_to(DIST)}")


if __name__ == "__main__":
    main()
