#!/usr/bin/env python3
"""Generate the PhotoSleuth logo, app icons and Windows .ico.

The mark: a rounded-square badge carrying a magnifying glass whose lens frames
a camera aperture (the "sleuth inspecting a photo" idea), with a location pin
in the lens to nod at the GPS features.  Everything is drawn at 8x and
downsampled so the curves stay clean at 16px.

Run:  python tools/make_assets.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent.parent / "photosleuth" / "assets"

# Brand palette
INK_TOP = (26, 35, 68)        # deep navy
INK_BOTTOM = (12, 17, 38)     # near-black navy
CYAN = (56, 214, 224)         # lens glow / accent
CYAN_DEEP = (22, 148, 178)
AMBER = (255, 176, 62)        # pin accent
WHITE = (255, 255, 255)

SS = 8  # supersampling factor


def _lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _rounded_rect_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def _vertical_gradient(size: int, top, bottom) -> Image.Image:
    gradient = Image.new("RGB", (1, size))
    pixels = gradient.load()
    for y in range(size):
        pixels[0, y] = _lerp(top, bottom, y / max(1, size - 1))
    return gradient.resize((size, size), Image.BILINEAR)


def _diagonal_sheen(size: int) -> Image.Image:
    """A soft light sweep from the top-left, so the badge is not flat."""
    sheen = Image.new("L", (size, size), 0)
    pixels = sheen.load()
    for y in range(size):
        for x in range(size):
            t = 1.0 - min(1.0, (x + y) / (size * 1.35))
            pixels[x, y] = int(58 * t * t)
    return sheen


def _draw_aperture(draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: float, blades: int = 6) -> None:
    """Six-blade camera iris: shaded wedges around a hexagonal opening."""
    step = 2 * math.pi / blades
    start_angle = -math.pi / 2 - step / 2
    opening = radius * 0.46

    # Blades, each a slightly different shade so the seams read as real edges.
    for index in range(blades):
        a0 = start_angle + index * step
        a1 = a0 + step
        shade = _lerp(CYAN, CYAN_DEEP, index / max(1, blades - 1))
        points = [(cx, cy)]
        steps = 14
        for k in range(steps + 1):
            angle = a0 + (a1 - a0) * (k / steps)
            points.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
        draw.polygon(points, fill=shade + (255,))

    # Blade seams.
    for index in range(blades):
        angle = start_angle + index * step
        draw.line(
            [(cx, cy), (cx + math.cos(angle) * radius, cy + math.sin(angle) * radius)],
            fill=INK_BOTTOM + (110,),
            width=max(1, int(radius * 0.035)),
        )

    # The hexagonal opening in the middle.
    hexagon = [
        (cx + math.cos(start_angle + i * step) * opening,
         cy + math.sin(start_angle + i * step) * opening)
        for i in range(blades)
    ]
    draw.polygon(hexagon, fill=INK_BOTTOM + (255,))


def _draw_pin(draw: ImageDraw.ImageDraw, cx: float, cy: float, height: float) -> None:
    """A map pin sitting in the middle of the aperture."""
    width = height * 0.70
    head_r = width / 2
    head_cy = cy - height * 0.18
    draw.ellipse(
        [cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r],
        fill=AMBER + (255,),
    )
    draw.polygon(
        [
            (cx - head_r * 0.82, head_cy + head_r * 0.55),
            (cx + head_r * 0.82, head_cy + head_r * 0.55),
            (cx, cy + height * 0.52),
        ],
        fill=AMBER + (255,),
    )
    hole = head_r * 0.38
    draw.ellipse(
        [cx - hole, head_cy - hole, cx + hole, head_cy + hole],
        fill=INK_BOTTOM + (255,),
    )


def render_badge(size: int = 512, *, badge: bool = True, detail: bool = True) -> Image.Image:
    """Render the logo at *size* pixels.

    ``detail=False`` drops the pin and the handle highlight, which is what keeps
    the 16px and 20px icons readable.
    """
    s = size * SS
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    if badge:
        plate = _vertical_gradient(s, INK_TOP, INK_BOTTOM).convert("RGBA")
        sheen = _diagonal_sheen(s)
        plate.paste(Image.new("RGBA", (s, s), WHITE + (255,)), (0, 0), sheen)
        canvas.paste(plate, (0, 0), _rounded_rect_mask(s, int(s * 0.22)))

    draw = ImageDraw.Draw(canvas)

    # --- magnifying glass -------------------------------------------------
    lens_cx, lens_cy = s * 0.435, s * 0.415
    lens_r = s * 0.245
    ring = s * 0.062

    # handle, drawn first so the ring overlaps it cleanly
    angle = math.radians(45)
    handle_start = (lens_cx + math.cos(angle) * lens_r * 0.94,
                    lens_cy + math.sin(angle) * lens_r * 0.94)
    handle_end = (lens_cx + math.cos(angle) * (lens_r + s * 0.235),
                  lens_cy + math.sin(angle) * (lens_r + s * 0.235))
    draw.line([handle_start, handle_end], fill=WHITE + (255,), width=int(ring * 1.16))
    draw.ellipse(
        [handle_end[0] - ring * 0.58, handle_end[1] - ring * 0.58,
         handle_end[0] + ring * 0.58, handle_end[1] + ring * 0.58],
        fill=WHITE + (255,),
    )

    # glass interior
    inner_r = lens_r - ring * 0.5
    draw.ellipse(
        [lens_cx - inner_r, lens_cy - inner_r, lens_cx + inner_r, lens_cy + inner_r],
        fill=INK_BOTTOM + (235,),
    )

    if detail:
        _draw_aperture(draw, lens_cx, lens_cy, inner_r * 0.86)
        _draw_pin(draw, lens_cx, lens_cy, inner_r * 0.80)
    else:
        # At 16-24px the iris turns to mush: a plain cyan lens stays readable.
        draw.ellipse(
            [lens_cx - inner_r * 0.86, lens_cy - inner_r * 0.86,
             lens_cx + inner_r * 0.86, lens_cy + inner_r * 0.86],
            fill=CYAN + (255,),
        )

    # lens ring on top
    draw.ellipse(
        [lens_cx - lens_r, lens_cy - lens_r, lens_cx + lens_r, lens_cy + lens_r],
        outline=WHITE + (255,), width=int(ring),
    )

    if detail:
        # specular glint on the glass
        glint = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glint)
        gd.ellipse(
            [lens_cx - inner_r * 0.70, lens_cy - inner_r * 0.76,
             lens_cx - inner_r * 0.14, lens_cy - inner_r * 0.34],
            fill=WHITE + (64,),
        )
        canvas = Image.alpha_composite(canvas, glint)

    return canvas.resize((size, size), Image.LANCZOS)


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="PhotoSleuth">
  <defs>
    <linearGradient id="plate" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#1a2344"/><stop offset="100%" stop-color="#0c1126"/>
    </linearGradient>
    <linearGradient id="sheen" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.22"/>
      <stop offset="60%" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
    <clipPath id="lensClip"><circle cx="223" cy="212" r="113"/></clipPath>
  </defs>

  <rect width="512" height="512" rx="113" fill="url(#plate)"/>
  <rect width="512" height="512" rx="113" fill="url(#sheen)"/>

  <line x1="305" y1="294" x2="396" y2="385" stroke="#ffffff" stroke-width="37" stroke-linecap="round"/>
  <circle cx="223" cy="212" r="113" fill="#0c1126"/>

  <g clip-path="url(#lensClip)">
    <g transform="translate(223 212)">
      <path d="M0 0 L-46.5 -80.54 A93.0 93.0 0 0 1 46.5 -80.54 Z" fill="#38d6e0"/>
      <path d="M0 0 L46.5 -80.54 A93.0 93.0 0 0 1 93.0 0.0 Z" fill="#31c6d6"/>
      <path d="M0 0 L93.0 0.0 A93.0 93.0 0 0 1 46.5 80.54 Z" fill="#2ab5cc"/>
      <path d="M0 0 L46.5 80.54 A93.0 93.0 0 0 1 -46.5 80.54 Z" fill="#24a7c1"/>
      <path d="M0 0 L-46.5 80.54 A93.0 93.0 0 0 1 -93.0 0.0 Z" fill="#1d9db8"/>
      <path d="M0 0 L-93.0 0.0 A93.0 93.0 0 0 1 -46.5 -80.54 Z" fill="#1694b2"/>
      <line x1="0" y1="0" x2="-46.5" y2="-80.54" stroke="#0c1126" stroke-opacity="0.45" stroke-width="3.2"/>
      <line x1="0" y1="0" x2="46.5" y2="-80.54" stroke="#0c1126" stroke-opacity="0.45" stroke-width="3.2"/>
      <line x1="0" y1="0" x2="93.0" y2="0.0" stroke="#0c1126" stroke-opacity="0.45" stroke-width="3.2"/>
      <line x1="0" y1="0" x2="46.5" y2="80.54" stroke="#0c1126" stroke-opacity="0.45" stroke-width="3.2"/>
      <line x1="0" y1="0" x2="-46.5" y2="80.54" stroke="#0c1126" stroke-opacity="0.45" stroke-width="3.2"/>
      <line x1="0" y1="0" x2="-93.0" y2="0.0" stroke="#0c1126" stroke-opacity="0.45" stroke-width="3.2"/>
      <polygon points="-21.39,-37.05 21.39,-37.05 42.78,0.0 21.39,37.05 -21.39,37.05 -42.78,0.0" fill="#0c1126"/>
      <g>
        <circle cx="0" cy="-12" r="25" fill="#ffb03e"/>
        <path d="M-20 2 L20 2 L0 40 Z" fill="#ffb03e"/>
        <circle cx="0" cy="-12" r="9.5" fill="#0c1126"/>
      </g>
    </g>
    <ellipse cx="180" cy="168" rx="54" ry="38" fill="#ffffff" opacity="0.18"
             transform="rotate(-32 180 168)"/>
  </g>

  <circle cx="223" cy="212" r="113" fill="none" stroke="#ffffff" stroke-width="32"/>
</svg>
"""


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)

    (ASSETS / "logo.svg").write_text(SVG, encoding="utf-8")

    # Full-size marks
    render_badge(512).save(ASSETS / "logo.png")
    render_badge(256).save(ASSETS / "logo_256.png")
    render_badge(128).save(ASSETS / "logo_128.png")
    render_badge(1024).save(ASSETS / "logo_1024.png")

    # Transparent glyph (no badge plate) for the About dialog / splash
    render_badge(512, badge=False).save(ASSETS / "mark.png")

    # Windows .ico - small sizes use the simplified mark so they stay legible
    ico_sizes = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
    frames = [render_badge(n, detail=n >= 32) for n in ico_sizes]
    frames[-1].save(
        ASSETS / "photosleuth.ico",
        format="ICO",
        sizes=[(n, n) for n in ico_sizes],
        append_images=frames[:-1],
    )

    # Installer artwork (Inno Setup wants BMPs)
    wizard = Image.new("RGB", (164, 314), INK_BOTTOM)
    wizard.paste(_vertical_gradient(164, INK_TOP, INK_BOTTOM).crop((0, 0, 164, 314)), (0, 0))
    badge = render_badge(120)
    wizard.paste(badge, (22, 96), badge)
    wizard.save(ASSETS / "installer_wizard.bmp")

    banner = Image.new("RGB", (150, 57), (255, 255, 255))
    small = render_badge(48)
    banner.paste(small, (6, 4), small)
    banner.save(ASSETS / "installer_banner.bmp")

    print(f"Assets written to {ASSETS}")
    for path in sorted(ASSETS.glob("*")):
        if path.is_file():
            print(f"  {path.name:<26} {path.stat().st_size:>8,} bytes")


if __name__ == "__main__":
    main()
