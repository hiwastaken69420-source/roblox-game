# roblox-game

## UltQ: press **Q** to ult

A cinematic ultimate. When you press Q:
- **You** get the full cinematic, played on your own avatar. That's 17 camera cuts recreating the reference ult: hologram glitch close-up, ink splash, pink flash, afterimage clones, the infinite square tunnel with star glints, the crescent portal, hyperspace, the flight through the block tunnel and the slash. It finishes with black/white **impact frames**.
- **Everyone else** sees a charging aura around you, the slash line and a shockwave at the impact.

Controller: **Y**. Mobile: an on-screen **ULT** button.

**Your weapon:** the cinematic clones your character as it is at the moment you cast, so equip your weapon before you press Q and it appears in every shot. There's no built-in weapon.

### Install (no plugins needed)
1. Open your place in Roblox Studio.
2. Drag **`UltQ.rbxmx`** (in this repo) into the Studio window.
3. Move the inserted **UltQ** script into **ServerScriptService**.
4. Press Play, then press **Q**.

The UltQ script sets everything else up at runtime:
- the `UltQShared` modules in ReplicatedStorage
- the `UltQRemote` RemoteEvent
- a client script for every player

### Install with Rojo (optional)
`default.project.json` maps `src/UltQ` to `ServerScriptService.UltQ`. Run `rojo serve` and connect from the Rojo Studio plugin.
After editing `src/`, run `python tools/build_rbxmx.py` to rebuild `UltQ.rbxmx`.

### Sound
Roblox only plays audio that's been uploaded to Roblox:
1. Go to Creator Hub > Development Items > Audio > upload `ult-blender/ult_sfx.wav`.
2. Paste the ID into `ServerScriptService > UltQ > Shared > Config`, e.g. `SoundId = "rbxassetid://123456789"`.

### Settings (`Shared/Config`)
| Setting | Default | What it does |
|---|---|---|
| `Key` | `Q` | Cast key |
| `Cooldown` | `12` | Seconds between casts (server-enforced) |
| `LockMovement` | `true` | Freezes the caster during the ult |
| `Damage` / `DamageRadius` | `0` / `25` | Damage dealt to nearby Humanoids at the impact (6.4 s). 0 = off |
| `SoundId` | `""` | Uploaded `ult_sfx.wav` |
| `VideoId` | `""` | Optional: play a pre-rendered video of the Blender version full-screen instead of the real-time cinematic |
| `Density` | `1` | Lower it (0.3–1) for fewer VFX parts on weak devices |

### How it works
| File | Role |
|---|---|
| `src/UltQ/init.server.lua` | Installer, cooldown, movement lock, optional damage, broadcasts casts |
| `src/UltQ/UltQClient.client.lua` | Q / Y / mobile button input, plays the cinematic or the world FX |
| `Shared/Cinematic.lua` | Scripted camera, Lighting (bloom / colour grade), flash / glitch / fade overlay; restores everything afterwards |
| `Shared/Shots.lua` | The 15 shot sets (built from neon parts far above the map, local-only) |
| `Shared/Rig.lua` | Clones your avatar (and your equipped weapon) as an "actor" and poses it through its Motor6Ds (R6 + R15, no animation upload needed) |
| `Shared/WorldFx.lua` | What other players see |
| `Shared/Kit.lua` | Part, keyframe and Blender-to-Roblox coordinate helpers |

### Blender version
`ult-blender/` holds the original Blender recreation that these shots were ported from:
- `RobloxUlt.blend`: the full scene. Open it and press Ctrl+F12 to render.
- `ult_build.py`: rebuilds the scene from scratch.
- `ult_sfx.wav` / `ult_sfx.py`: the synthesized SFX track and the script that makes it.
- `preview/`: the preview render, plus a side-by-side with the reference clip.
