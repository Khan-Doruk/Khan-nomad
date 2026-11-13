"""Khan-Nomad vented case: open the back cap's thin pocket as a vent and move the
engraved yurt onto the solid part of the plate.

The cap's back plate is 2.2 mm thick except for a ~10 x 12 mm pocket near the top
end that is only 0.4 mm thick (clearance for parts on the back of the board).
That pocket sits right over the board, so it becomes the vent:

  --style window   one rounded window, the whole pocket opened (most airflow, strongest)
  --style arcs     WiFi-arc slots cut through the pocket (looks like the logo's waves)

The yurt is engraved DEPTH mm into the 2.2 mm plate, fully clear of the pocket.

    python tools/case/make_vented_case.py NomadCasev30.stl NomadCasev30_KhanNomad_Vented.stl --style window
"""
import argparse
import math
import os
import sys

import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_yurt_case as myc  # noqa: E402

DEPTH = 0.6
LOGO_SCALE = 0.17           # mm per logo unit (smaller than before so it fits the solid plate)
LOGO_CENTER = (25.4, 61.7)  # bed coordinates, on the 2.2 mm plate below the pocket
THIN = 1.0                  # plate thinner than this (mm) counts as the pocket
GRID = 0.25


def split_parts(mesh):
    parts = sorted(mesh.split(only_watertight=False), key=lambda p: -abs(p.volume))
    return parts[0], parts[1], parts[2:]


def plate_top_map(cap):
    """Height of the first surface seen from above, on a grid over the cap face."""
    (minx, miny, _), (maxx, maxy, _) = cap.bounds
    xs = np.arange(minx, maxx, GRID)
    ys = np.arange(miny, maxy, GRID)
    pts = np.array([[x, y, 50.0] for x in xs for y in ys])
    loc, idx, _ = cap.ray.intersects_location(pts, np.tile([0, 0, -1.0], (len(pts), 1)), multiple_hits=False)
    top = np.full(len(pts), np.nan)
    top[idx] = loc[:, 2]
    return xs, ys, top.reshape(len(xs), len(ys))


def pocket_polygon(cap):
    """The thin pocket as one polygon (largest thin region), inset slightly."""
    xs, ys, top = plate_top_map(cap)
    cells = [box(x, y, x + GRID, y + GRID) for i, x in enumerate(xs) for j, y in enumerate(ys)
             if not np.isnan(top[i, j]) and top[i, j] < THIN]
    thin = unary_union(cells).buffer(0.05).buffer(-0.05)
    parts = sorted(getattr(thin, "geoms", [thin]), key=lambda g: -g.area)
    return parts[0]


def window_vent(pocket):
    # leave a 0.6 mm lip of the 0.4 mm plate so the edge isn't a knife edge, round corners
    return pocket.buffer(-0.6).buffer(-1.0).buffer(1.0)


def arc_vent(pocket):
    """Concentric WiFi-style slots inside the pocket."""
    inner = pocket.buffer(-1.0)
    minx, miny, maxx, maxy = inner.bounds
    # waves radiate toward the cap's top end (small x), centred on the pocket's long axis
    cx, cy = maxx + 2.0, (miny + maxy) / 2
    slots = []
    r = 4.0
    while r < (maxx - minx) + 4:
        pts = [(cx - r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in np.linspace(-50, 50, 40)]
        slots.append(LineString(pts).buffer(0.8, cap_style=1))
        r += 2.8                 # 1.6 mm slot + 1.2 mm bar
    return unary_union(slots).intersection(inner)


def logo_shape():
    old = (myc.CENTER, myc.SCALE)
    myc.CENTER, myc.SCALE = LOGO_CENTER, LOGO_SCALE
    try:
        return myc.logo_on_bed(myc.yurt_logo())
    finally:
        myc.CENTER, myc.SCALE = old


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--style", choices=["window", "arcs"], default="window")
    ap.add_argument("--preview", help="PNG of the cap face with the vent and logo")
    args = ap.parse_args()

    cap, frame, markers = split_parts(trimesh.load(args.src))
    pocket = pocket_polygon(cap)
    vent = window_vent(pocket) if args.style == "window" else arc_vent(pocket)
    logo = logo_shape()
    print("pocket %.0f mm2, vent open area %.0f mm2 (%s)" % (pocket.area, vent.area, args.style))
    lx0, ly0, lx1, ly1 = logo.bounds
    print("logo %.1f x %.1f mm at x %.1f..%.1f" % (lx1 - lx0, ly1 - ly0, lx0, lx1))
    # the logo must sit on the full-thickness plate, well clear of the pocket
    assert logo.distance(pocket) > 0.8, "logo too close to the thin pocket"

    cutters = [myc.extrude(vent, -1.0, 3.0), myc.extrude(logo, -0.5, DEPTH)]
    out_cap = cap
    for c in cutters:
        out_cap = out_cap.difference(c, engine="manifold")
    assert out_cap.is_watertight
    print("cap volume %.1f -> %.1f mm3" % (cap.volume, out_cap.volume))
    trimesh.util.concatenate([out_cap, frame]).export(args.dst)
    print("wrote", args.dst, "(dropped %d marker body)" % len(markers))

    if args.preview:
        from PIL import Image, ImageDraw
        xs, ys, top = plate_top_map(cap)
        k = 14
        img = Image.new("RGB", (int((ys[-1] - ys[0]) * k) + 40, int((xs[-1] - xs[0]) * k) + 40), "#F6EFE3")
        d = ImageDraw.Draw(img)

        def px(x, y):
            return ((y - ys[0]) * k + 20, (x - xs[0]) * k + 20)

        for i, x in enumerate(xs):
            for j, y in enumerate(ys):
                z = top[i, j]
                if np.isnan(z):
                    continue
                X, Y = px(x, y)
                d.rectangle([X, Y, X + GRID * k, Y + GRID * k], fill="#1B3A4B" if z < 2.5 else "#2B5368")
        for g in getattr(logo, "geoms", [logo]):
            d.polygon([px(*c) for c in g.exterior.coords], fill="#3B6A80")
            for h in g.interiors:
                d.polygon([px(*c) for c in h.coords], fill="#1B3A4B")
        for g in getattr(vent, "geoms", [vent]):
            d.polygon([px(*c) for c in g.exterior.coords], fill="#F6EFE3")
        img.save(args.preview)
        print("preview", args.preview)


if __name__ == "__main__":
    main()
