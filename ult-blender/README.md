# Roblox Ult — Blender recreation

A shot-for-shot rebuild of the reference ult (7.7 s) with a Roblox R6 avatar, ending on an impact-frame sequence.
Everything is procedural: run the script and Blender builds the whole thing.

| File | What it is |
|---|---|
| `RobloxUlt.blend` | The finished scene: 15 sets, cameras auto-cutting via timeline markers, compositor VFX, SFX in the sequencer |
| `ult_build.py` | Rebuilds `RobloxUlt.blend` from scratch. Tweak and re-run it. |
| `ult_sfx.py` / `ult_sfx.wav` | Synthesized SFX track (no samples, royalty-free), timed to every cut |
| `preview/RobloxUlt_preview.mp4` | 960×540 preview render with sound |
| `preview/compare_side_by_side.mp4` | Reference (left) vs this recreation (right) |

## Render it
1. Open `RobloxUlt.blend` in Blender **4.2 or newer** (built and tested on 5.2 LTS).
2. Render ▸ Render Animation (Ctrl+F12). Output goes to `render/` next to the .blend as MP4 with audio.
   * EEVEE at 1920×1080 / 30 fps / 32 samples. Raise the samples for a cleaner result.
   * For **60 fps**: set `FPS = 60` at the top of `ult_build.py` and re-run it. Every key is placed in seconds, so timing stays identical.

## Rebuild / tweak
Scripting tab ▸ open `ult_build.py` ▸ Run Script (this wipes the current file and rebuilds it), or:
```
blender --background --python ult_build.py -- --out RobloxUlt.blend
```
Handy knobs at the top of the script: `FPS`, `RES`, `EEVEE_SAMPLES`, `EMIT` (overall glow brightness), and the palette (`BLUE`, `PINK`, …).
Shot timings live in `SHOTS`. Poses live in `POSES`.

## Shot list
| Time | Shot | VFX |
|---|---|---|
| 0.00 | Arena wide shot, spear held | floating particles, floor energy line, grid floor |
| 0.22 | Hologram face close-up | pixel-block dissolve, data cubes, glitch bars, lightning |
| 0.67 | Ink splash | over-exposed silhouette on an animated ink blob |
| 0.83 | Glitch close-up | heavy band displacement + RGB split + shake |
| 0.92 | Pink duotone flash | compositor duotone |
| 1.00 | Afterimage clones | ghost clones, falling pixels, square grid |
| 1.47 | Over the shoulder, spear raised | square tunnel opening |
| 1.63 | Infinite twisting square tunnel | 4-point star glints on the spear |
| 1.97 | Diamond portal + crescent | 150 cubes blasting outward |
| 2.40 | Smirk close-up | energy ribbons |
| 2.72 | Dash through cubes | motion blur |
| 2.83 | Flash explosion | radial rays, exposure punch |
| 3.00 | Hyperspace | radial streaking blocks, starburst |
| 3.47 | Crescent flare | fade to dark |
| 3.62 | Flight through the block tunnel to the core | wisps, debris, follow-cam, shake |
| 6.00 | Final slash | pink vertical line, blue-white beam, whiteout |
| 6.40 | **Impact frames** | B/W flips every 2 frames, red frame, speed wedges, shockwave, shake |
| 7.20 | Colour returns | final blast, fade to black |

## The compositor (`ULT_Compositor` node group)
Bloom ▸ Streaks ▸ Glitch (noise-driven horizontal band displacement) ▸ RGB split ▸ Flash exposure ▸ Pink duotone ▸ Impact (hard threshold B/W, invert, red) ▸ Vignette ▸ Fade.
These Value nodes are keyframed, so edit them in the Graph Editor: `GlitchAmount`, `RGBSplit`, `Flash`, `Duotone`, `Impact`, `ImpactInvert`, `ImpactRed`, `Fade`.

## Using YOUR Roblox avatar
The rig matches Roblox R6 Motor6D pivots (1 Blender unit = 1 stud):
`<Shot>_Av_Root` (hip) ▸ `_Torso` ▸ `_Head`, `_ArmL`, `_ArmR`; `_Root` ▸ `_LegL`, `_LegR`. The spear is parented to `_ArmR`.
1. In Roblox Studio, right-click your character ▸ **Export Selection** (.obj).
2. Import it into Blender. Split it into parts and parent each part to the matching `_Torso` / `_Head` / `_Arm*` / `_Leg*` object (Ctrl+P ▸ Object, Keep Transform).
3. Hide the original blocky meshes. The animation carries over, because it lives on the pivot objects.

## Notes
* This is a **Blender render** in the Roblox-animation style, the usual way these ult edits are made. Roblox Studio itself can't play compositor effects (bloom, glitch, impact frames). To put the moves in-game, use the poses as a reference for Roblox's Animation Editor, or rig the avatar with the official Roblox Blender plugin and export the keyframes.
* The original game audio is copyrighted, so `ult_sfx.wav` is newly synthesized SFX hit-matched to the reference timing. To add music, drop it into the sequencer under the SFX strip.
