# Gauge tray setup (demo day)

How to set up the 3D-printed gauge tray so the Tello camera can read the flood level in feet.
Background and design: [gauge-water-level-plan.md](gauge-water-level-plan.md). This guide covers the
**160 mm tray** (`data/gauge_tray_160/`). The 200 mm tray (`data/gauge_tray/`) works the same way but
has its own tag sheet and pour table.

## 1. What you need

| Item | Notes |
|---|---|
| Printed gauge tray | `data/gauge_tray_160/gauge_tray.stl`. Matte, light filament is best (white, grey or tan). |
| Tag sheet, printed at 100% | `data/gauge_tray_160/tag_sheet.png`. Use a laser printer or a dry inkjet print on **matte** paper. |
| Scissors or a craft knife, ruler | For cutting the tags and checking the scale. |
| Glue stick or thin double-sided tape | Keep the tags flat. Avoid wet glue that wrinkles paper. |
| Blue food dye | Strong colour. Mix one batch for the whole run (see step 5). |
| Measuring syringe (10-60 mL) or a measuring cup with mL marks | Steps as small as 5 mL. A syringe is much more accurate. |
| A jug or cup of about 250 mL | For the dyed water. |
| Paper towels | For spills. Keep the tray and tags dry before the baseline. |
| DJI Tello, charged | Motors stay off in stand mode; the battery only powers the camera and Wi-Fi. |
| A stand: a book stack, box or phone stand | Props the Tello nose-down about 45 degrees. |
| Laptop with Flood Watch | Backend, console and Tello bridge (step 7). |
| Bright, diffuse light | A window with no direct sun, or ceiling light bounced off a wall. |

## 2. Print and check the tag sheet

1. Regenerate the sheet if the tray was rebuilt (otherwise skip this step):
   `~/tello-env/Scripts/python.exe backend/scripts/gauge_tag_sheet.py --tray data/gauge_tray_160 --check`
   (use `--tray data/gauge_tray` for the 200 mm tray).
2. Print `tag_sheet.png` at **100% / actual size**. Turn off "fit to page", "shrink to fit" and
   "borderless". The PNG stores 600 dpi, so most viewers print it at the right size.
3. Measure the **50.0 mm scale bar** with a ruler. It must read 49.5 to 50.5 mm.
4. Measure a tag's black square. It must be **16.0 mm** (20.0 mm on the 200 mm sheet).
5. If either measurement is off, fix the print settings and print again. Wrong tag size gives a wrong
   camera distance, and every reading after that is off.

## 3. Find the +Y side of the tray

The tray has embossed lettering on two opposite rims:

| Rim | Lettering | Tray side | Tags in those corners |
|---|---|---|---|
| Near you when "FLOOD WATCH" reads upright | **FLOOD WATCH** | low Y (south) | 0 (left), 1 (right) |
| Far side (lettering reads upside down from where you stand) | **GUADALUPE RIVER  KERRVILLE TX** | high Y (north), **+Y** | 3 (left), 2 (right) |

Stand at the FLOOD WATCH rim so the words read normally. **+Y points straight away from you**, toward
the GUADALUPE RIVER rim. +X points to your right. The tag sheet is laid out the same way, seen from
above.

## 4. Stick the tags on the corner pads

Each corner has a square raised pad (20.8 mm) with a shallow pocket in the middle that is just
larger than the tag.

| Tag | Corner (standing at FLOOD WATCH) | Pad centre x, y (mm) |
|---|---|---|
| ID 0 | front left | 10.4, 10.4 (low X, low Y) |
| ID 1 | front right | 149.6, 10.4 (high X, low Y) |
| ID 2 | back right | 149.6, 149.6 (high X, high Y) |
| ID 3 | back left | 10.4, 149.6 (low X, high Y) |

1. **Before cutting**, write a small pencil dot and the ID in the white border at the top edge of
   each tag (the edge nearest the arrow head), well clear of the black square. The arrow is outside
   the cut line, so it won't be on the cut-out tag.
2. Cut each tag out **on the dashed square** (20.8 mm). The white border is the marker's quiet zone,
   so keep it. It lets the camera find the tag on any filament colour.
3. Turn the tag so its **top edge (pencil dot) faces +Y** (toward the GUADALUPE RIVER rim). On every
   pad the dot faces the same way, away from you.
4. Line the paper's two outer edges up with the tray's two outer edges at that corner. The pad
   reaches the tray corner, so this centres the tag on the pad.
5. Glue it flat. No bubbles, curled corners or shiny tape over the black squares.
6. Alternative, for light filament only: cut exactly on the black edge and drop the tag into the
   pocket. Never do this on dark filament, because the tag needs a light border around it.

A paper square over the pocket sits about 0.4 mm higher than the manifest assumes, which has no
practical effect. A tag turned 90 degrees still works because the pose uses tag centres, but it
loses the corner refinement, so get the arrows right.

## 5. Mix the dyed water

- Mix about **250 mL** of water with enough blue dye to look **deep blue in a 2 mm layer**. Try
  10-15 drops per 250 mL and test a few drops on a white plate. If it looks pale there, add more.
- Use one batch for the whole run. Changing the colour partway through confuses the reading.
- Other colours: set `GAUGE_DYE=green` or `red` for the bridge. Blue is the default and contrasts
  best with grey, white and tan filament. Don't use a dye that matches the filament colour.

## 6. Place the camera

The Tello camera points straight forward and cannot tilt. In a hover the bottom edge of the frame
looks only about 21-27 degrees below horizontal (21 degrees at the default fx = 920; the spec FOV
suggests closer to 27). To look down at the tray you have to tilt the whole drone.

### Stand mode (recommended)

| Setting | Value |
|---|---|
| Motors | **Off.** Do not press Take off. Video only. Removing the propellers is safest. |
| Tilt | Nose down about **45 degrees** (35-60 degrees is fine), resting on a book stack or box |
| Distance, camera to tray centre | **300-350 mm** for the 160 mm tray (450 mm at most) |
| Aim | Tray centre in the middle of the frame. **All 4 tags and the whole tray in view**, with a margin |
| Side | Any side works. From the FLOOD WATCH side the tags appear upright. |
| Stability | The camera must not move between the dry baseline and the readings. Tape the stand down. |

Why 300-350 mm: a 16 mm tag is about 49 px wide at 300 mm and 33 px at 450 mm (fx = 920), and at
45 degrees it is foreshortened to about 0.7 of that in one direction. Closer gives sharper tags. The
whole 160 mm tray still fits in the frame at 300 mm.

### Hover mode (lower confidence)

Flying works only at a shallow angle (about 20-25 degrees): the tray sits low in the frame and many
cells behind the terraces and houses are hidden. Expect wider ranges, lower confidence and more None
readings. Use it to show the idea in flight; use stand mode for the numbers.

## 7. Lighting and glare

- Bright, even, diffuse light from the side or behind the camera. No bare bulb or window reflecting
  in the water from the camera's point of view. Check the video: a white streak on the water is glare.
- Matte filament and matte paper. Shiny surfaces flash white and read as "dry" or "changed".
- Keep shadows steady: no one walking between the light and the tray during the run.
- Don't change the lights between the dry baseline and the readings.

## 8. Pour table (160 mm tray)

Volumes come from `data/gauge_tray_160/manifest.json` (`pour_table`). They are **totals from an empty
tray**. "Add" is the amount to add to go from the previous row. 1 ft equals one 2 mm terrace step;
0 ft is the normal river (4.0 mm).

| Level | Water height | Total poured | Add from previous | Crossing (deck 4.6 mm) | Car | Houses flooded (of 10) |
|---|---|---|---|---|---|---|
| 0 ft | 4.0 mm | 5.5 mL | 5.5 mL (from empty) | dry | none | 0 |
| 1 ft | 6.0 mm | 10.3 mL | 4.8 mL | flooded | none | 0 |
| 2 ft | 8.0 mm | 26.8 mL | 16.5 mL | flooded | doors (right at the wheels/doors line) | 4 |
| 3 ft | 10.0 mm | 49.3 mL | 22.5 mL | flooded | windows | 8 |
| 4 ft | 12.0 mm | 76.6 mL | 27.3 mL | flooded | roof | 9 |
| 5 ft | 14.0 mm | 108.6 mL | 32.0 mL | flooded | roof | 9 |
| 6 ft | 16.0 mm | 145.6 mL | 37.0 mL | flooded | roof | 10 |
| 7 ft | 18.0 mm | 184.8 mL | 39.2 mL | flooded | roof | 10 |

**Pour to mid-step for the clearest reading.** The ground is built from flat 2 mm terraces, so at
exactly 6.0 mm the water is flush with the 6 mm terrace top and the camera can't tell 1 ft from 2 ft.
Halfway up a step the pattern is unambiguous. Mid-step totals, computed the same way as the manifest:

| Level | 0.5 ft | 1.5 ft | 2.5 ft | 3.5 ft | 4.5 ft | 5.5 ft | 6.5 ft | 7.5 ft |
|---|---|---|---|---|---|---|---|---|
| Total poured | 7.9 mL | 18.5 mL | 37.9 mL | 62.8 mL | 92.5 mL | 127.0 mL | 165.2 mL | 205.0 mL |

A reading on a mid-step pour should land in the range between the two whole feet, for example
"2.5 ft (2-3)". The 200 mm tray holds about 1.6x as much water. Use the `pour_table` in
`data/gauge_tray/manifest.json`.

## 9. Run sequence

1. **Start Flood Watch.** Backend: `cd backend && uv run uvicorn app.main:app --reload`. Frontend:
   `cd frontend && npm run dev`, then open the ops console (`/console`).
2. **Start the Tello bridge.** `~/tello-env/Scripts/python.exe backend/scripts/tello_dashboard.py`
   (or the `Tello dashboard` shortcut), then connect the laptop Wi-Fi to `TELLO-XXXXXX`. The bridge
   dashboard is at http://127.0.0.1:8765.
3. **Set up the tray and camera** as in steps 3-7. Check the live video: all 4 tags are visible and
   the tray is sharp.
4. **Capture the dry baseline BEFORE pouring anything** (the tray must be completely dry and empty).
   Click **Capture dry baseline** on the water gauge card: either the bridge HUD (http://127.0.0.1:8765)
   or the console Live drone panel. The card shows **Dry baseline captured** and its Dry baseline
   field changes to **Captured**. If it is refused the card shows **Baseline refused:** and the reason,
   for example "tray already has water; capture the baseline dry" (dry the tray and press again) or
   too few tags visible. "loading the gauge model, try again in a moment" right after the bridge
   starts just means press again in a few seconds.
5. Click **Start**. The reading updates about twice a second and is smoothed over the last 8 frames
   (about 4 seconds). If the card dims and says **Last reading Ns ago**, the reader stopped or is
   failing (the reason shows on the card): the number is old, not live.
6. **Pour** to a level from the table. Pour slowly into the river channel, then **take your hand and
   the syringe out of the frame** and wait about 5 seconds for the water and the reading to settle.
7. **Read the gauge card:** level in ft with its range, car level, crossing, houses flooded and
   confidence. Compare with the pour table.
   A mid-step pour reads 2.5 ft with a 2 to 3 ft range. Water at or below the normal river reads
   "0 ft" with **At or below normal pool**. If Dry baseline shows **Camera moved, using dye only**, the
   camera was bumped: the reading still works from the dye colour, at lower confidence.
8. Repeat steps 6-7 for higher levels. Click **Stop** when done.
9. Afterwards: empty and dry the tray fully. Dye stains or leftover droplets mean you need a new
   baseline next time, and only after the tray is fully dry.

Endpoints, if you need them directly: bridge `GET /gauge/status`, `POST /gauge/baseline`,
`POST /gauge/start`, `POST /gauge/stop`, `GET /gauge/overlay.jpg` (overlay with wet cells tinted).
Backend: `/api/live-drone/gauge` (status), `POST /api/live-drone/gauge/{baseline|start|stop}`,
`/api/live-drone/gauge/overlay.jpg`. `{"gauge": "offline"}` means the bridge isn't running.

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "No tags found" or fewer than 3 tags | Tag out of frame, glare on the tag, too far, blurry, hand in the way | Check that all 4 tags are in the video. Move closer (300 mm). Remove shiny tape. Angle the light away from the paper. |
| Tags found but pose rejected (high reprojection error) | Sheet printed at the wrong scale, tag curled, tag on the wrong corner | Re-check the 50 mm bar. Flatten the tags. Check the IDs against the table in step 4. |
| Dry baseline shows "Camera moved, using dye only" | Stand bumped, drone slid, or someone touched the tray | Put everything back, or empty and dry the tray and capture a new baseline. |
| "Baseline refused: tray already has water; capture the baseline dry" | Water or dye already in the tray | Empty and dry the tray fully, then press **Capture dry baseline** again. |
| Card dimmed, "Last reading Ns ago" | Reading stopped, or the reader is failing on every frame | Press **Start** again; read the reason on the card (often glare or tags out of view). |
| Reads too high | Glare or reflections read as change, shadow from a hand or arm | Kill the glare (step 7). Keep hands out of frame. Wait for the smoothing to settle. |
| Reads too low | Dye too light, so thin water on terraces looks dry | Add dye (deep blue in a 2 mm layer). The baseline stays valid if the camera has not moved. |
| Reading flips between two whole feet | Water exactly at a terrace top | Pour to mid-step (the 0.5 ft table). |
| Reading is None with a reason | Weak evidence: tags hidden, too few visible cells, flat score, or no baseline in a dim scene | Read the reason on the card. Usually: move closer, raise the angle to 45 degrees, improve light, capture a baseline. |
| Low confidence in hover mode | Shallow angle, so terraces and houses hide the waterline | Expected. Use stand mode for the numbers. |
| Water level lower than the pour table says | Tray leaks through the print layers, or spilled outside the channel | Check under the tray for wet spots. Seal the underside, or test with plain water first and dry fully before the baseline. |
| Console card says offline | Bridge not running, or the laptop is off the Tello Wi-Fi | Start the bridge (step 9.2). Check http://127.0.0.1:8765. |
