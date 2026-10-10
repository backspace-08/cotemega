#!/usr/bin/env python3
"""Batch-convert card PNGs to size-capped JPEGs.

For each input PNG, pick the highest JPEG quality (4:2:0, progressive, optimized)
whose encoded size stays within --target-kb, and write ``<name>.jpg`` next to it.
After converting, update ``filename`` in ``characters.json`` (and re-upload to R2).

Requires Pillow. Run with the project venv:

    ./venv/bin/python scripts/cards_to_jpeg.py data/epic/*.png
    ./venv/bin/python scripts/cards_to_jpeg.py data --recursive --target-kb 300
    ./venv/bin/python scripts/cards_to_jpeg.py data --recursive --delete-source
"""

import argparse
import io
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("Pillow is required: pip install Pillow")

SUBSAMPLING = {0: "4:4:4", 1: "4:2:2", 2: "4:2:0"}


def encode(image: Image.Image, quality: int, subsampling: int) -> bytes:
    buf = io.BytesIO()
    image.save(
        buf,
        "JPEG",
        quality=quality,
        subsampling=subsampling,
        optimize=True,
        progressive=True,
    )
    return buf.getvalue()


def best_jpeg(image: Image.Image, target: int, max_q: int, min_q: int, subsampling: int):
    """Highest quality whose size <= target; falls back to min_q if even that is too big.

    JPEG size grows with quality, so binary-search the quality.
    """
    lo, hi = min_q, max_q
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        data = encode(image, mid, subsampling)
        if len(data) <= target:
            best = (mid, data)
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None:
        return min_q, encode(image, min_q, subsampling)
    return best


def iter_pngs(paths, recursive: bool):
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            yield from sorted(path.rglob("*.png") if recursive else path.glob("*.png"))
        else:
            yield path


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert card PNGs to size-capped JPEGs.")
    parser.add_argument("paths", nargs="+", help="PNG files and/or directories")
    parser.add_argument("--target-kb", type=int, default=300, help="max file size in KB (default 300)")
    parser.add_argument("--max-quality", type=int, default=90)
    parser.add_argument("--min-quality", type=int, default=55)
    parser.add_argument("--subsampling", type=int, default=2, choices=[0, 1, 2],
                        help="chroma subsampling: 0=4:4:4, 1=4:2:2, 2=4:2:0 (default)")
    parser.add_argument("--recursive", action="store_true", help="scan directories recursively")
    parser.add_argument("--delete-source", action="store_true", help="remove the PNG after a successful convert")
    parser.add_argument("--dry-run", action="store_true", help="report sizes without writing files")
    args = parser.parse_args()

    target = args.target_kb * 1024
    files = [f for f in iter_pngs(args.paths, args.recursive) if f.exists() and f.suffix.lower() == ".png"]
    if not files:
        sys.exit("no PNG files found")

    print(f"target <= {args.target_kb} KB, subsampling {SUBSAMPLING[args.subsampling]}, "
          f"quality {args.min_quality}-{args.max_quality}\n")
    converted = 0
    for src in files:
        try:
            image = Image.open(src).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            print(f"  {src}: FAILED to open ({exc})")
            continue
        quality, data = best_jpeg(image, target, args.max_quality, args.min_quality, args.subsampling)
        dst = src.with_suffix(".jpg")
        kb = len(data) / 1024
        over = "" if len(data) <= target else "  (> target, min quality reached)"
        print(f"  {src.name} -> {dst.name}: q{quality}, {kb:.0f} KB{over}")
        if not args.dry_run:
            dst.write_bytes(data)
            if args.delete_source:
                src.unlink()
            converted += 1

    if args.dry_run:
        print("\n(dry run: nothing written)")
    else:
        print(f"\nconverted {converted} file(s). Update 'filename' in characters.json and re-upload to R2.")


if __name__ == "__main__":
    main()
