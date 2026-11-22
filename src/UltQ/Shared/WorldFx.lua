-- WorldFx: what OTHER players see when someone casts the ult (they don't get the cinematic).
-- A charging aura, the slash line at 6.0s and a shockwave + flash at the impact (6.4s).

local TweenService = game:GetService("TweenService")
local Debris = game:GetService("Debris")

local Kit = require(script.Parent.Kit)
local Config = require(script.Parent.Config)

local WorldFx = {}

local function tween(inst: Instance, time: number, props: { [string]: any }, style: Enum.EasingStyle?)
	local tw = TweenService:Create(inst, TweenInfo.new(time, style or Enum.EasingStyle.Quad, Enum.EasingDirection.Out), props)
	tw:Play()
	return tw
end

function WorldFx.burst(caster: Player, cf: CFrame)
	local folder = Instance.new("Folder")
	folder.Name = "UltQWorldFx"
	folder.Parent = workspace
	Debris:AddItem(folder, Config.Duration + 2)
	local char = caster.Character
	local hrp = char and char:FindFirstChild("HumanoidRootPart")
	local center = hrp and (hrp :: BasePart).CFrame or cf

	if Config.SoundId ~= "" and hrp then
		local s = Instance.new("Sound")
		s.SoundId = Config.SoundId
		s.Volume = Config.Volume
		s.RollOffMaxDistance = 200
		s.Parent = hrp
		s:Play()
		Debris:AddItem(s, Config.Duration + 1)
	end

	-- charging aura
	local aura = Kit.ball(folder, center, 5, Kit.rgb(0.1, 0.35, 1), 0.6)
	local light = Instance.new("PointLight")
	light.Color = Kit.CYAN
	light.Range = 24
	light.Brightness = 3
	light.Parent = aura
	tween(aura, 0.4, { Size = Vector3.one * 8 }, Enum.EasingStyle.Back)
	task.spawn(function()
		local t0 = os.clock()
		while os.clock() - t0 < 6.0 and aura.Parent do
			local t = os.clock() - t0
			aura.Transparency = 0.6 + 0.15 * math.sin(t * 12)
			if hrp and hrp.Parent then
				aura.CFrame = (hrp :: BasePart).CFrame
			end
			task.wait()
		end
		aura:Destroy()
	end)

	-- 6.0s: the slash line
	task.delay(6.0, function()
		if not folder.Parent then
			return
		end
		local line = Kit.part(folder, { Size = Vector3.new(0.3, 0.05, 0.3), CFrame = center * CFrame.Angles(0, 0, math.rad(-12)), Color = Kit.rgb(1, 0.6, 0.9) })
		tween(line, 0.08, { Size = Vector3.new(0.3, 60, 0.3) })
		task.delay(0.25, function()
			tween(line, 0.3, { Transparency = 1, Size = Vector3.new(2, 60, 2) })
		end)
	end)

	-- 6.4s: impact shockwave + flash
	task.delay(Config.HitTime, function()
		if not folder.Parent then
			return
		end
		local flashBall = Kit.ball(folder, center, 2, Kit.WHITE, 0)
		tween(flashBall, 0.5, { Size = Vector3.one * 26, Transparency = 1 })
		local ring = Kit.part(folder, { Shape = Enum.PartType.Cylinder, Size = Vector3.new(0.4, 4, 4), CFrame = center * CFrame.Angles(0, 0, math.rad(90)), Color = Kit.ICE, Transparency = 0.2 })
		tween(ring, 0.9, { Size = Vector3.new(0.2, 70, 70), Transparency = 1 })
		local l = Instance.new("PointLight")
		l.Color = Kit.CYAN
		l.Range = 60
		l.Brightness = 10
		l.Parent = flashBall
		tween(l, 0.8, { Brightness = 0 })
		for _ = 1, 16 do
			local d = Kit.part(folder, { Size = Vector3.one * (math.random() * 0.6 + 0.2), CFrame = center, Color = Kit.ICE })
			local dir = Vector3.new(math.random() - 0.5, math.random() * 0.6, math.random() - 0.5).Unit * (12 + math.random() * 18)
			tween(d, 0.8, { CFrame = center + dir, Transparency = 1 })
		end
	end)
end

return WorldFx
