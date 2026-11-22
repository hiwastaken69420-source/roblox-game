--!strict
-- UltQ configuration. Edit these values in Studio (ReplicatedStorage > UltQShared > Config
-- is a runtime copy; edit the one inside ServerScriptService > UltQ > Shared).

local Config = {
	-- Input
	Key = Enum.KeyCode.Q,              -- keyboard key
	GamepadKey = Enum.KeyCode.ButtonY, -- controller button
	MobileButton = true,               -- show an on-screen "ULT" button on touch devices

	-- Timing
	Duration = 7.7,     -- length of the cinematic (seconds)
	Cooldown = 12,      -- seconds between casts (enforced on the server)
	HitTime = 6.4,      -- when the impact lands (seconds after cast)

	-- Gameplay (all optional)
	LockMovement = true, -- freeze the caster while the ult plays
	Damage = 0,          -- damage dealt to other Humanoids at HitTime (0 = off)
	DamageRadius = 25,   -- studs around the caster

	-- Audio: upload ult-blender/ult_sfx.wav to Roblox (Creator Hub > Audio),
	-- then paste the id here, e.g. "rbxassetid://1234567890". Empty = silent.
	SoundId = "",
	Volume = 1,

	-- Optional "exact" mode: upload ult-blender/preview/RobloxUlt_preview.mp4 (or your own 1080p
	-- Blender render) as a Roblox Video asset and paste its id here. When set, pressing Q plays
	-- that pre-rendered video full-screen instead of the real-time in-engine cinematic.
	VideoId = "",

	-- Visual quality: lower this (0.3 - 1) on low-end devices to spawn fewer VFX parts.
	Density = 1,
}

return Config
