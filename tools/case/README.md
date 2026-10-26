# Khan-Nomad case

`NomadCasev30_KhanNomad.stl` (USB-A board) and `NomadCasev30_USB-C_KhanNomad.stl`
(USB-C board) are the original Nomad v30 case with the **steppe yurt logo
engraved into the back cap**, in place of the original tree logo.

Same two parts as the original, same fit: the back cap and the front frame.
Only the cap's outside face changes.

## Printing (Prusa CORE One or any FDM printer)

- Print exactly like the original case: the parts are already laid out
  flat, with the cap's outside face down on the bed. No supports needed for
  the logo.
- The logo is cut **0.6 mm** deep into that face (3 layers at 0.2 mm), so it
  shows as a recessed yurt on the finished cap.
- Use a 0.4 mm nozzle and 0.2 mm layers or finer. The thinnest logo features
  (the WiFi arcs and the band diamonds) are about 0.7-1.1 mm wide.
- A smooth or textured PEI sheet both work; textured gives the face a nice
  matte look.

## Two-colour logo (optional)

The engraving is open to the bed, so a filament change makes the logo a
different colour from the face:

1. Start with the **face colour** (for example dark teal or black).
2. In PrusaSlicer, add a **colour change at 0.6 mm** (right-click the "+" on
   the layer slider at the 0.6 mm layer).
3. When the printer pauses, load the **logo colour** (for example cream or
   white) and continue.

The first 0.6 mm print the face with yurt-shaped holes; the layers above fill
those holes from behind, so the yurt shows in the second colour. The rest of
the case also prints in the second colour. For a teal case with a cream yurt,
add a second change back to teal at 0.8 mm.

## Regenerating

```bash
pip install trimesh manifold3d shapely numpy
python tools/case/make_yurt_case.py NomadCasev30.stl NomadCasev30_KhanNomad.stl --preview logo.png
```

`--depth` changes the engraving depth. The script checks that the logo stays
inside the cap face and that the result is watertight.
