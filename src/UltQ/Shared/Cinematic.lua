-- Cinematic: plays the ult for the local player.
-- Builds the 15 shot sets far above the map (local-only parts), drives a scripted camera
-- through the cut list, and layers the compositor-style post effects (bloom, flashes, glitch
-- bars, pink duotone, B/W impact frames, fade) using Lighting effects + a ScreenGui overlay.

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local Lighting = game:GetService("Lighting")
local StarterGui = game:GetService("StarterGui")
local SoundService = game:GetService("SoundService")

local Kit = require(script.Parent.Kit)
local Shots = require(script.Parent.Shots)
local Config = require(script.Parent.Config)

local Cinematic = {}

local STAGE_BASE = CFrame.new(0, 4000, 0)
local SET_SPACING = 450

-- Post timelines (ported from the Blender compositor keys) ---------------------------------
local EXPOSURE = Kit.track({
	{ 0.0, 0, "const" }, { 0.22, 1.2 }, { 0.27, 0, "const" }, { 0.67, 0.8 }, { 0.75, 0.2, "const" },
	{ 0.83, 0, "const" }, { 1.0, 1.4 }, { 1.08, 0, "const" }, { 1.97, 1.0 }, { 2.05, 0, "const" },
	{ 2.79, 0.3 }, { 2.83, 1.6 }, { 3.0, 1.2 }, { 3.08, 0, "const" }, { 3.47, 1.5 }, { 3.55, -0.5 },
	{ 3.62, -2.0 }, { 3.80, 0, "const" }, { 5.6, 0 }, { 6.0, 1.5 }, { 6.1, 0.2 }, { 6.28, 1.0 },
	{ 6.37, 4.0, "const" }, { 6.40, 0, "const" }, { 7.20, 0 }, { 7.25, 1.0 }, { 7.40, 0, "const" },
})
local GLITCH = Kit.track({
	{ 0.0, 0, "const" }, { 0.22, 90, "const" }, { 0.29, 0, "const" }, { 0.43, 60, "const" }, { 0.47, 0, "const" },
	{ 0.60, 40, "const" }, { 0.63, 0, "const" }, { 0.67, 120, "const" }, { 0.70, 0, "const" }, { 0.83, 160, "const" },
	{ 0.86, 70, "const" }, { 0.89, 140, "const" }, { 0.92, 0, "const" }, { 1.43, 60, "const" }, { 1.47, 0, "const" },
	{ 1.94, 50, "const" }, { 1.97, 0, "const" }, { 2.70, 80, "const" }, { 2.76, 0, "const" }, { 3.60, 90, "const" },
	{ 3.66, 0, "const" }, { 5.97, 120, "const" }, { 6.0, 0, "const" }, { 6.05, 150, "const" }, { 6.12, 0, "const" },
	{ 7.40, 140, "const" }, { 7.47, 0, "const" },
})
local BLOOM = Kit.track({
	{ 0.0, 1.0, "const" }, { 2.83, 2.0, "const" }, { 3.0, 1.0, "const" }, { 6.0, 1.8, "const" }, { 6.40, 1.0, "const" }, { 7.25, 2.2, "const" },
})
local FADE = Kit.track({ { 0, 0 }, { 7.45, 0 }, { 7.70, 1 } })

local function overlayFrame(parent: Instance, name: string, color: Color3, z: number): Frame
	local f = Instance.new("Frame")
	f.Name = name
	f.BorderSizePixel = 0
	f.BackgroundColor3 = color
	f.BackgroundTransparency = 1
	f.Size = UDim2.fromScale(1, 1)
	f.ZIndex = z
	f.Parent = parent
	return f
end

local function hideCoreGui()
	local states = {}
	for _, ty in Enum.CoreGuiType:GetEnumItems() do
		if ty ~= Enum.CoreGuiType.All then
			local ok, on = pcall(StarterGui.GetCoreGuiEnabled, StarterGui, ty)
			states[ty] = ok and on
		end
	end
	pcall(StarterGui.SetCoreGuiEnabled, StarterGui, Enum.CoreGuiType.All, false)
	return function()
		for ty, on in states do
			pcall(StarterGui.SetCoreGuiEnabled, StarterGui, ty, on)
		end
	end
end

local function hideOtherGuis(gui: Instance)
	local hidden = {}
	local pg = Players.LocalPlayer:FindFirstChildOfClass("PlayerGui")
	if pg then
		for _, g in pg:GetChildren() do
			if g:IsA("ScreenGui") and g ~= gui and g.Enabled then
				g.Enabled = false
				table.insert(hidden, g)
			end
		end
	end
	return function()
		for _, g in hidden do
			if g.Parent then
				g.Enabled = true
			end
		end
	end
end

-- Optional: play a pre-rendered video instead (Config.VideoId)
function Cinematic.playVideo(gui: ScreenGui, onDone: () -> ())
	local restoreCore = hideCoreGui()
	local restoreGuis = hideOtherGuis(gui)
	local vf = Instance.new("VideoFrame")
	vf.Size = UDim2.fromScale(1, 1)
	vf.BackgroundColor3 = Color3.new(0, 0, 0)
	vf.BorderSizePixel = 0
	vf.Video = Config.VideoId
	vf.Volume = Config.Volume
	vf.ZIndex = 50
	vf.Parent = gui
	local done = false
	local function finish()
		if done then
			return
		end
		done = true
		vf:Destroy()
		restoreCore()
		restoreGuis()
		onDone()
	end
	vf.Ended:Connect(finish)
	task.spawn(function()
		local t = 0
		while not vf.IsLoaded and t < 5 and not done do
			t += task.wait(0.05)
		end
		if not done then
			vf:Play()
		end
	end)
	task.delay(Config.Duration + 6, finish)
end

function Cinematic.play(character: Model, gui: ScreenGui, onDone: () -> ())
	if Config.VideoId ~= "" then
		Cinematic.playVideo(gui, onDone)
		return
	end
	local cam = workspace.CurrentCamera
	local saved = { type = cam.CameraType, subject = cam.CameraSubject, fov = cam.FieldOfView }

	-- lighting ---------------------------------------------------------------------------
	local LIGHT_PROPS = { "Ambient", "OutdoorAmbient", "Brightness", "ClockTime", "FogEnd", "FogStart", "FogColor",
		"ExposureCompensation", "EnvironmentDiffuseScale", "EnvironmentSpecularScale", "GlobalShadows" }
	local savedLight = {}
	for _, k in LIGHT_PROPS do
		savedLight[k] = (Lighting :: any)[k]
	end
	local disabled = {}
	for _, e in Lighting:GetChildren() do
		if e:IsA("PostEffect") and e.Enabled then
			e.Enabled = false
			table.insert(disabled, e)
		end
	end
	local atmosphere = Lighting:FindFirstChildOfClass("Atmosphere")
	if atmosphere then
		atmosphere.Parent = nil
	end
	Lighting.Ambient = Color3.fromRGB(16, 22, 48)
	Lighting.OutdoorAmbient = Color3.fromRGB(16, 22, 48)
	Lighting.Brightness = 0
	Lighting.ClockTime = 0
	Lighting.FogStart = 0
	Lighting.FogEnd = 100000
	Lighting.ExposureCompensation = 0
	Lighting.EnvironmentDiffuseScale = 0
	Lighting.EnvironmentSpecularScale = 0.4
	Lighting.GlobalShadows = false

	local bloom = Instance.new("BloomEffect")
	bloom.Name = "UltQBloom"
	bloom.Size = 40
	bloom.Threshold = 0.8
	bloom.Parent = Lighting
	local cc = Instance.new("ColorCorrectionEffect")
	cc.Name = "UltQGrade"
	cc.Parent = Lighting

	-- UI ----------------------------------------------------------------------------------
	local restoreCore = hideCoreGui()
	local restoreGuis = hideOtherGuis(gui)
	local layer = Instance.new("Frame")
	layer.Name = "UltQOverlay"
	layer.BackgroundTransparency = 1
	layer.Size = UDim2.fromScale(1, 1)
	layer.ZIndex = 40
	layer.Parent = gui
	local flash = overlayFrame(layer, "Flash", Color3.fromRGB(225, 240, 255), 41)
	local dark = overlayFrame(layer, "Dark", Color3.new(0, 0, 0), 42)
	local fade = overlayFrame(layer, "Fade", Color3.new(0, 0, 0), 45)
	local bars = {}
	for i = 1, 12 do
		local b = overlayFrame(layer, "Glitch" .. i, Color3.new(1, 1, 1), 43)
		b.Visible = false
		bars[i] = b
	end

	-- sets ----------------------------------------------------------------------------------
	local root = Instance.new("Folder")
	root.Name = "UltQStage"
	root.Parent = workspace
	local ctxs = {}
	local queue = {}
	for i, name in Shots.SET_ORDER do
		table.insert(queue, { name, STAGE_BASE * CFrame.new(i * SET_SPACING, 0, 0) })
	end
	local function build(name: string)
		if ctxs[name] then
			return ctxs[name]
		end
		for i, q in queue do
			if q[1] == name then
				table.remove(queue, i)
				local ctx = Shots.newCtx(root, q[2], character, name)
				Shots.Sets[name](ctx)
				ctxs[name] = ctx
				return ctx
			end
		end
		return nil
	end
	build("S01")
	build("S02")

	local sound: Sound? = nil
	if Config.SoundId ~= "" then
		local s = Instance.new("Sound")
		s.Name = "UltQSound"
		s.SoundId = Config.SoundId
		s.Volume = Config.Volume
		s.Parent = SoundService
		s:Play()
		sound = s
	end

	cam.CameraType = Enum.CameraType.Scriptable
	local t0 = os.clock()
	local finished = false
	local diedConn: RBXScriptConnection? = nil

	local function finish()
		if finished then
			return
		end
		finished = true
		RunService:UnbindFromRenderStep("UltQCinematic")
		if diedConn then
			diedConn:Disconnect()
		end
		for _, ctx in ctxs do
			ctx:destroy()
		end
		root:Destroy()
		layer:Destroy()
		bloom:Destroy()
		cc:Destroy()
		for _, e in disabled do
			if e.Parent then
				e.Enabled = true
			end
		end
		if atmosphere then
			atmosphere.Parent = Lighting
		end
		for k, v in savedLight do
			pcall(function()
				(Lighting :: any)[k] = v
			end)
		end
		restoreCore()
		restoreGuis()
		local char = Players.LocalPlayer.Character
		local hum = char and char:FindFirstChildOfClass("Humanoid")
		cam.CameraType = saved.type == Enum.CameraType.Scriptable and Enum.CameraType.Custom or saved.type
		cam.CameraSubject = hum or saved.subject
		cam.FieldOfView = saved.fov
		if sound then
			local s = sound
			task.delay(1.5, function()
				s:Destroy()
			end)
		end
		onDone()
	end

	local hum = character:FindFirstChildOfClass("Humanoid")
	if hum then
		diedConn = hum.Died:Connect(finish)
	end

	local step
	RunService:BindToRenderStep("UltQCinematic", Enum.RenderPriority.Camera.Value + 1, function()
		local ok, err = pcall(step)
		if not ok then
			warn("[UltQ] cinematic error, restoring camera:", err)
			finish()
		end
	end)

	step = function()
		local t = os.clock() - t0
		if t >= Config.Duration or not character.Parent then
			finish()
			return
		end
		local frame = math.floor(t * 60)

		-- active shot
		local shot = Shots.LIST[1]
		for _, s in Shots.LIST do
			if t >= s[2] then
				shot = s
			end
		end
		local ctx = build(shot[4]) or ctxs[shot[4]]
		-- build one queued set per frame so the start doesn't hitch
		if #queue > 0 then
			build(queue[1][1])
		end
		ctx:update(t)

		-- camera
		local def
		for _, c in ctxs do
			if c.cams[shot[1]] then
				def = c.cams[shot[1]]
			end
		end
		if def then
			local cf = CFrame.lookAt(def.pos(t), def.target(t)) * CFrame.Angles(0, 0, math.rad(def.roll(t)))
			local sh = def.shake
			if sh and t >= sh[1] and t <= sh[2] then
				local step = math.floor(t * 30 / (sh[5] or 1))
				local k = 1 - 0.5 * Kit.prog(t, sh[1], sh[2])
				cf = cf
					* CFrame.new(Kit.hash(step, 1) * sh[3] * k, Kit.hash(step, 2) * sh[3] * k, 0)
					* CFrame.Angles(0, 0, math.rad(Kit.hash(step, 3) * sh[4] * k))
			end
			local g = GLITCH(t)
			if g > 0 then
				cf = cf * CFrame.new(Kit.hash(frame, 7) * g / 900, 0, 0)
			end
			cam.CFrame = cf
			cam.FieldOfView = def.fov
		end

		-- post --------------------------------------------------------------------------
		local e = EXPOSURE(t)
		flash.BackgroundTransparency = 1 - math.clamp(e / 4.5, 0, 0.85)
		dark.BackgroundTransparency = 1 - math.clamp(-e / 2.5, 0, 0.9)
		fade.BackgroundTransparency = 1 - FADE(t)
		local post = ctx.post
		if post then
			cc.Saturation, cc.Contrast, cc.TintColor, cc.Brightness = post.saturation, post.contrast, post.tint, 0
			bloom.Intensity = post.bloom
		else
			cc.Saturation = 0.25
			cc.Contrast = 0.2
			cc.Brightness = math.clamp(e * 0.05, -0.15, 0.2)
			cc.TintColor = (t >= 0.92 and t < 1.0) and Color3.fromRGB(255, 205, 230) or Color3.new(1, 1, 1)
			bloom.Intensity = BLOOM(t)
		end
		-- glitch bars
		local g = GLITCH(t)
		for i, b in bars do
			if g > 0 and Kit.hash(frame, i) > 0.1 then
				b.Visible = true
				local y = (Kit.hash(frame, i + 20) + 1) / 2
				local h = 2 + math.abs(Kit.hash(frame, i + 40)) * g * 0.35
				b.Position = UDim2.new(Kit.hash(frame, i + 60) * g / 1400, 0, y, 0)
				b.Size = UDim2.new(1.05, 0, 0, h)
				local c = math.abs(Kit.hash(frame, i + 80))
				b.BackgroundColor3 = c > 0.66 and Color3.fromRGB(255, 255, 255) or (c > 0.33 and Color3.fromRGB(90, 170, 255) or Color3.fromRGB(20, 60, 255))
				b.BackgroundTransparency = 0.15 + c * 0.4
			else
				b.Visible = false
			end
		end
	end
end

return Cinematic
