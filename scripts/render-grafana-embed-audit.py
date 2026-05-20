#!/usr/bin/env python3
"""Render all public Grafana embeds into page-level contact sheets."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

DEFAULT_VAULT_ROOT = Path("/mnt/iris/verdify-vault/website")
DEFAULT_OUTPUT_DIR = Path(tempfile.gettempdir()) / "verdify-grafana-embed-audit"
EMBED_RE = re.compile(r"https://graphs\.verdify\.ai/d-solo/([^/?#\s\"<>)]*)/?[^\s\"<>)]*")


@dataclass(frozen=True)
class Embed:
    page: str
    uid: str
    panel_id: str
    title: str
    source_url: str
    render_url: str
    output_name: str


def page_slug(page: str) -> str:
    stem = page.replace("/", "__").replace(".md", "")
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", stem).strip("-") or "index"


def render_url(source_url: str, width: int, height: int, stamp: str, base_url: str | None) -> str:
    parsed = urlparse(source_url)
    path = parsed.path.replace("/d-solo/", "/render/d-solo/")
    if base_url:
        base = urlparse(base_url)
        parsed = parsed._replace(scheme=base.scheme, netloc=base.netloc)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["theme"] = "light"
    query["width"] = str(width)
    query["height"] = str(height)
    query["audit"] = stamp
    return urlunparse(parsed._replace(path=path, query=urlencode(query), fragment=""))


def discover_embeds(vault_root: Path, width: int, height: int, stamp: str, base_url: str | None) -> list[Embed]:
    embeds: list[Embed] = []
    seen: set[tuple[str, str]] = set()
    for path in sorted(vault_root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        page = str(path.relative_to(vault_root))
        page_prefix = page_slug(page)
        for index, match in enumerate(EMBED_RE.finditer(text), start=1):
            source_url = match.group(0)
            parsed = urlparse(source_url)
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            panel_id = query.get("panelId")
            if not panel_id:
                continue
            key = (page, source_url)
            if key in seen:
                continue
            seen.add(key)
            uid = match.group(1)
            title = f"{uid} panel {panel_id}"
            digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:8]
            output_name = f"{page_prefix}__{index:02d}__{uid}__{panel_id}__{digest}.png"
            embeds.append(
                Embed(
                    page=page,
                    uid=uid,
                    panel_id=panel_id,
                    title=title,
                    source_url=source_url,
                    render_url=render_url(source_url, width, height, stamp, base_url),
                    output_name=output_name,
                )
            )
    return embeds


def render_embed(embed: Embed, output_dir: Path, timeout: int, retries: int, delay: float) -> dict[str, object]:
    output_path = output_dir / embed.output_name
    result = None
    if delay > 0:
        time.sleep(delay)
    for attempt in range(retries + 1):
        result = subprocess.run(
            [
                "curl",
                "-sS",
                "-L",
                "--max-time",
                str(timeout),
                "-w",
                "%{http_code}",
                "-o",
                str(output_path),
                embed.render_url,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        size = output_path.stat().st_size if output_path.exists() else 0
        if result.returncode == 0 and result.stdout.strip() == "200" and size > 1_000:
            break
        if result.stdout.strip() == "429" and attempt < retries:
            time.sleep(10 * (attempt + 1))
    size = output_path.stat().st_size if output_path.exists() else 0
    assert result is not None
    return {
        **asdict(embed),
        "output_path": str(output_path),
        "http_code": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "bytes": size,
        "ok": result.returncode == 0 and result.stdout.strip() == "200" and size > 1_000,
    }


def write_contact_sheet(page: str, renders: list[dict[str, object]], output_dir: Path) -> str | None:
    pngs = [str(render["output_path"]) for render in renders if render.get("ok")]
    if not pngs:
        return None
    sheet = output_dir / "contact-sheets" / f"{page_slug(page)}.png"
    sheet.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "montage",
            *pngs,
            "-label",
            "%t",
            "-geometry",
            "560x260+18+28",
            "-background",
            "#F4F7F4",
            "-tile",
            "2x",
            str(sheet),
        ],
        check=True,
    )
    return str(sheet)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-root", type=Path, default=DEFAULT_VAULT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--width", type=int, default=900)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--delay", type=float, default=1.5, help="seconds to wait before each render request")
    parser.add_argument("--base-url", help="optional Grafana base URL for rendering, e.g. http://172.27.0.2:3000")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for child in args.output_dir.glob("*.png"):
        child.unlink()
    sheet_dir = args.output_dir / "contact-sheets"
    if sheet_dir.exists():
        for child in sheet_dir.glob("*.png"):
            child.unlink()

    embeds = discover_embeds(args.vault_root, args.width, args.height, str(int(time.time())), args.base_url)
    print(f"rendering {len(embeds)} embeds from {args.vault_root}", flush=True)
    results: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(render_embed, embed, args.output_dir, args.timeout, args.retries, args.delay)
            for embed in embeds
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            status = "ok" if result["ok"] else "FAIL"
            print(
                f"{status} {result['page']} {result['title']} bytes={result['bytes']} code={result['http_code']}",
                flush=True,
            )

    results.sort(key=lambda item: (str(item["page"]), str(item["output_name"])))
    (args.output_dir / "manifest.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    by_page: dict[str, list[dict[str, object]]] = {}
    for result in results:
        by_page.setdefault(str(result["page"]), []).append(result)
    sheets = [
        sheet
        for page, page_results in sorted(by_page.items())
        if (sheet := write_contact_sheet(page, page_results, args.output_dir))
    ]

    failures = [result for result in results if not result.get("ok")]
    print(f"wrote {len(sheets)} contact sheets to {sheet_dir}", flush=True)
    if failures:
        print(f"{len(failures)} render failures; see {args.output_dir / 'manifest.json'}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
