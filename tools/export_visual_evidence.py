"""Small, non-production CI evidence readable over the existing Git transport."""
import argparse
import json
from pathlib import Path
import shutil

from PIL import Image, ImageDraw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--regressions", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.regressions and (args.regressions / "results.json").is_file():
        results = json.loads((args.regressions / "results.json").read_text(encoding="utf-8"))
        shutil.copy2(args.regressions / "results.json", args.out / "regressions.json")
        for result in results:
            if result["exit_code"]:
                stem = Path(result["test"]).stem
                shutil.copy2(args.regressions / (stem + ".log"), args.out / (stem + ".txt"))
    report = args.source / "report.json"
    if report.is_file():
        shutil.copy2(report, args.out / "report.json")
    # Retain original failure references over Git as well as the short-lived
    # artifact. Thumbnails cannot establish exact pixel/background differences.
    if report.is_file():
        data = json.loads(report.read_text(encoding="utf-8"))
        originals = args.out / "originals"
        for startup in data.get("startup_runs", []):
            if not startup.get("endpoint_flicker_detected"):
                continue
            prefix = f"startup_{startup['run']:02d}"
            for pattern in (f"{prefix}_first.png", f"{prefix}_reference.png",
                            f"{prefix}_desktop_reference.png", f"{prefix}_endpoint_01_*.png"):
                for source in args.source.glob(pattern):
                    originals.mkdir(exist_ok=True)
                    shutil.copy2(source, originals / source.name)
    if report.is_file():
        for toggle in data.get("theme_toggles", []):
            if not toggle.get("endpoint_flicker_detected"):
                continue
            for source in args.source.glob(f"theme_{toggle['toggle']:02d}_*.png"):
                originals.mkdir(exist_ok=True)
                shutil.copy2(source, originals / source.name)
    # Original lossless frames stay in the artifact. These sheets are an index
    # of the most divergent frame plus first/reference frames, not test inputs.
    paths = sorted(set(args.source.glob("*_endpoint_01_*.png")) |
                   set(args.source.glob("*_first.png")) |
                   set(args.source.glob("*_reference.png")))
    for page in range(0, len(paths), 9):
        sheet = Image.new("RGB", (1080, 3 * 260), "#aaaaaa")
        draw = ImageDraw.Draw(sheet)
        for index, path in enumerate(paths[page:page + 9]):
            x, y = index % 3 * 360, index // 3 * 260
            with Image.open(path) as original:
                image = original.convert("RGB")
                image.thumbnail((356, 230))
                sheet.paste(image, (x, y + 28))
            draw.text((x + 3, y + 3), path.name, fill="black")
        sheet.save(args.out / f"contact_{page // 9 + 1:02d}.png")
    (args.out / "provenance.json").write_text(json.dumps({
        "tested_commit": args.commit, "run_id": args.run,
        "report_available": report.is_file(), "indexed_frames": len(paths),
        "note": "Diagnostic thumbnails only; acceptance uses original full-resolution frames."
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
