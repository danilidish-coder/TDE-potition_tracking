from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw


def build_icon(target: Path) -> None:
    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Rounded dark-blue tile so the symbol remains legible on light and dark desktops.
    draw.rounded_rectangle((18, 18, 238, 238), radius=48, fill="#0a4f8c")

    center = (128, 128)
    outer = [(66, 72), (190, 72), (66, 184), (190, 184)]

    # Network links.
    for point in outer:
        draw.line((center, point), fill="#8fd0ff", width=12)

    # Network nodes.
    for x, y in outer:
        draw.ellipse((x - 22, y - 22, x + 22, y + 22), fill="#1976c9", outline="#dff3ff", width=5)
    x, y = center
    draw.ellipse((x - 28, y - 28, x + 28, y + 28), fill="#f5f9ff", outline="#dff3ff", width=5)

    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        target,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    build_icon(Path("build_assets") / "position_tracking_network.ico")
