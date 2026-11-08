---
tags: [floodwatch, experiment, drone-vision, tabletop]
updated: 2026-11-08
---

# 2026-11-08 Tabletop synthetic accuracy

These are pre-print checks of the [[Tabletop Model]].
- **Frames:** rendered from the CAD heightmap at 960×720 with the Tello 82.6° diagonal FOV, from 380 mm above the tray. (The first sweep below wrongly used 82.6° as horizontal.)
- **Pose:** solved by PnP from the four tag corners plus 0.3 px noise.
- **Water mask:** dilated by 1 px, a systematic bias.
- **Truth:** the bathtub fill.

## Results (`scripts/run_tabletop --source synth`, after review fixes)

Settings:
- The camera uses the Tello 82.6° diagonal FOV, which is about 70° horizontal at 960×720.
- Each row uses a fresh noise seed.
- A tag is used only if it is fully in frame.
- A pose is rejected unless it has at least 2 tags and a reprojection RMS of 1.5 px or less.

| True rise | cp-0154 bridge (steep bluff) | cp-0043 Park St (gentle) |
|---|---|---|
| 3 m | 4.44 [1.7, 7.2] | no level (dry, correct) |
| 9 m | 9.61 [2.6, 16.6] | no level (dry, correct) |
| 12 m | 12.63 [5.5, 19.7] | 12.06 [11.5, 12.6] |
| 13 m | 13.97 [-0.6, 28.6] | 13.12 [12.5, 13.8] |

Photo-like JPEG frames went through the real path at a 12 m rise: ArUco detection, +0.5 px pixel-centre convention, PnP with the RMS gate, and the HSV dye mask.
- 5 of 5 frames got a pose.
- cp-0154 read 11.87 m and cp-0043 read 12.03 m.
- Park St road depth was 130.2 in against 129.2 in true.
- Frames rendered with a wrong focal length were all rejected by the reprojection gate (0/5 posed) instead of giving a confident wrong number.

**This is a self-consistency check, not field accuracy.** The frames come from the same heightmap the pipeline measures against. Print error, lens distortion, refraction and the meniscus appear only as assumed sigmas. The physical pour run is the real test.

## What the sweep taught us

- **The error is mask bias × GSD × slope, not PnP.** It barely changes when tag noise goes from 0.15 to 0.3 px.

| | 960 px | 1920 px |
|---|---|---|
| Bridge, mean absolute error | 2.0 m | 0.64 m |
| Park St, mean absolute error | 0.33 m | 0.16 m |

- **Window-only rendering was wrong.** Rays slipped under terrain just outside the window and read as water. Render against the whole tray.
- **The flat water plane was wrong.** A level tray only wets cells connected to the river; use the bathtub fill.
- **Walls must be blockers.** Building blocks and the rim produced edges up to +3.7 m until they were labelled `building`.
- **Real truth is tiny.** 3 m of rise = 1.65 mm = 4.3 mL. Surface tension will matter on the real print; see the runbook (dish soap, caliper as the primary truth).
