"""Engrave the Khan-Nomad yurt logo into the Nomad case's back cap.

The original case STL has three bodies: the back cap (printed upside down, its
outside face on the bed at z=0), the front frame, and a 0.01 mm "tree" marker
sheet sitting at z=0.3 inside the cap (a colour-change marker, not geometry).

This script removes the tree marker and cuts the yurt logo DEPTH mm into the
cap's outside face, in the same spot and pointing the same way as the tree.
The engraving is open to the bed, so it prints on any single-colour printer.
For a two-colour logo, change filament after the first DEPTH mm (see README).

Usage:
    python tools/case/make_yurt_case.py NomadCasev30.stl NomadCasev30_KhanNomad.stl
    python tools/case/make_yurt_case.py NomadCasev30.stl out.stl --preview logo.png

Needs: trimesh, manifold3d, shapely, numpy (pip install trimesh manifold3d shapely).
"""
import argparse
import math

import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

DEPTH = 0.6          # mm engraved into the outside face (3 layers at 0.2 mm)
SCALE = 0.19         # mm per logo unit (logo.svg viewBox is 120 x 120)
CENTER = (20.0, 61.7)  # bed coordinates: the old tree logo's spot, centred on the face
LOGO_CENTER = (60.0, 58.5)  # centre of the yurt drawing in logo units


def arc(cx, cy, r, a0, a1, n=48):
    pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
           for a in np.linspace(a0, a1, n)]
    return LineString(pts)


def quad(p0, p1, p2, n=64):
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2 = map(np.array, (p0, p1, p2))
    return [tuple(v) for v in (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2]


def yurt_logo():
    """The yurt as one 2D shape in logo units (y down, like the SVG).

    'Ink' is the part that gets engraved. The pattern band, door and roof crown
    stay un-engraved so they read as details, like in logo.svg.
    """
    # WiFi arcs above the crown (logo.svg: centre 60,40; radii 8/14/20; 3.6 stroke)
    waves = unary_union([arc(60, 40, r, -135, -45).buffer(1.8, cap_style=1) for r in (8, 14, 20)])
    # roof dome: M22 66 Q60 26 98 66 Z
    roof = Polygon(quad((22, 66), (60, 26), (98, 66)))
    crown = affinity.scale(Point(60, 46).buffer(1), 6, 2.6)  # the roof's crown ring
    roof = roof.difference(crown)
    # walls, separated from the roof by a small gap so the two shapes read apart
    wall = box(28, 68.5, 92, 94)
    band = box(28, 68.5, 92, 74)   # starts at the wall top: a thinner wall strip would not print
    diamonds = unary_union([Polygon([(x, 71.25 - 3), (x + 3, 71.25), (x, 71.25 + 3), (x - 3, 71.25)])
                            for x in (37, 49, 71, 83)])
    door = box(53, 78, 67, 94.5)
    wall = wall.difference(band).union(diamonds).difference(door)
    ground = box(14, 96.5, 106, 99.5)
    return unary_union([waves, roof, wall, ground])


def logo_on_bed(logo):
    """Map logo units to bed mm: the yurt's 'up' points to -x like the old tree."""
    lx, ly = LOGO_CENTER
    cx, cy = CENTER
    # logo (u, v) with v down -> bed x = cx + (v - ly)*s, bed y = cy + (u - lx)*s
    m = [0, SCALE, SCALE, 0, cx - ly * SCALE, cy - lx * SCALE]   # shapely affine [a,b,d,e,xoff,yoff]
    return affinity.affine_transform(logo, m)


def extrude(shape, z0, z1):
    polys = list(shape.geoms) if shape.geom_type == "MultiPolygon" else [shape]
    meshes = [trimesh.creation.extrude_polygon(p, z1 - z0) for p in polys if p.area > 1e-6]
    mesh = trimesh.util.concatenate(meshes)
    mesh.apply_translation([0, 0, z0])
    return mesh


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--depth", type=float, default=DEPTH)
    ap.add_argument("--preview", help="write a PNG of the engraving outline")
    args = ap.parse_args()

    mesh = trimesh.load(args.src)
    parts = sorted(mesh.split(only_watertight=False), key=lambda p: -abs(p.volume))
    cap, frame = parts[0], parts[1]
    dropped = [p for p in parts[2:]]
    print("bodies:", len(parts), "-> keeping cap + frame, dropping", len(dropped), "marker body(ies)")

    shape = logo_on_bed(yurt_logo())
    minx, miny, maxx, maxy = shape.bounds
    print("logo on bed: x %.1f..%.1f  y %.1f..%.1f  (%.1f x %.1f mm)" % (minx, maxx, miny, maxy, maxx - minx, maxy - miny))

    # sanity: the logo must sit inside the cap's outside face
    face = cap.section(plane_origin=[0, 0, 0.05], plane_normal=[0, 0, 1])
    face2d, to3d = face.to_2D()
    face_poly = unary_union(face2d.polygons_full)
    face_poly = affinity.affine_transform(face_poly, [to3d[0, 0], to3d[0, 1], to3d[1, 0], to3d[1, 1], to3d[0, 3], to3d[1, 3]])
    inset = face_poly.buffer(-1.0)
    assert inset.contains(shape), "logo would run off the cap face"

    cutter = extrude(shape, -0.5, args.depth)
    cap_cut = cap.difference(cutter, engine="manifold")
    print("cap volume %.1f -> %.1f mm3 (removed %.1f)" % (cap.volume, cap_cut.volume, cap.volume - cap_cut.volume))
    assert cap_cut.is_watertight, "result is not watertight"

    out = trimesh.util.concatenate([cap_cut, frame])
    out.export(args.dst)
    print("wrote", args.dst, len(out.faces), "triangles")

    if args.preview:
        from PIL import Image, ImageDraw
        k = 20  # px per mm
        fminx, fminy, fmaxx, fmaxy = face_poly.bounds
        img = Image.new("RGB", (int((fmaxy - fminy) * k) + 40, int((fmaxx - fminx) * k) + 40), "#F6EFE3")
        d = ImageDraw.Draw(img)

        def px(x, y):  # draw with logo 'up' (-x on the bed) pointing up in the image
            return ((y - fminy) * k + 20, (x - fminx) * k + 20)

        def draw(poly, fill, outline=None):
            d.polygon([px(*c) for c in poly.exterior.coords], fill=fill, outline=outline)
            for hole in poly.interiors:
                d.polygon([px(*c) for c in hole.coords], fill="#1B3A4B")

        for p in getattr(face_poly, "geoms", [face_poly]):
            d.polygon([px(*c) for c in p.exterior.coords], fill="#1B3A4B")
        for p in getattr(shape, "geoms", [shape]):
            draw(p, "#F4E9D4")
        img.save(args.preview)
        print("preview", args.preview)


if __name__ == "__main__":
    main()
