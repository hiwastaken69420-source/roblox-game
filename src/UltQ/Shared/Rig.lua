-- Rig: clones the player's own avatar into a local-only "actor" and poses it by driving the
-- Motor6D joints directly (no animation asset upload needed). Works with R6 and R15.
-- Whatever the player is holding (an equipped Tool / custom weapon) is cloned with them, so
-- their own weapon appears in every shot.
-- Pose data is in Blender degrees (same POSES table as ult-blender/ult_build.py).

local Kit = require(script.Parent.Kit)
local V, R = Kit.V, Kit.R

local Rig = {}

Rig.POSES = {
	ready = { torso = { 10, 0, -12 }, head = { -4, 0, 12 }, armL = { -20, 0, 25 }, armR = { -70, 0, -10 }, legL = { -25, 0, 10 }, legR = { 20, 0, -6 } },
	chest_up = { torso = { 0, 0, 0 }, head = { -3, 0, 0 }, armL = { 0, 0, 8 }, armR = { -25, 0, -10 } },
	raise = { torso = { -8, 0, 15 }, head = { -10, 0, -5 }, armL = { -40, 0, 30 }, armR = { -160, 0, -15 }, legL = { -10, 0, 0 }, legR = { 10, 0, 0 } },
	stand = { torso = { 0, 0, 0 }, head = { 0, 0, 0 }, armL = { 0, 0, 6 }, armR = { -30, 0, -8 }, legL = { 0, 0, 3 }, legR = { 0, 0, -3 } },
	lunge = { torso = { 30, 0, -25 }, head = { -20, 0, 20 }, armL = { 40, 0, 35 }, armR = { -95, 0, -5 }, legL = { -60, 0, 0 }, legR = { 45, 0, 0 } },
	fly = { torso = { 78, 0, 0 }, head = { -55, 0, 0 }, armL = { 70, 0, 20 }, armR = { -165, 0, -5 }, legL = { 18, 0, 6 }, legR = { 32, 0, -6 } },
	fly2 = { torso = { 82, 0, 6 }, head = { -60, 0, 0 }, armL = { 80, 0, 30 }, armR = { -172, 0, -10 }, legL = { 25, 0, 8 }, legR = { 10, 0, -8 } },
	slash = { torso = { 25, 0, 40 }, head = { -15, 0, -30 }, armL = { 60, 0, 40 }, armR = { -80, 0, 80 }, legL = { -50, 0, 0 }, legR = { 55, 0, 0 } },
	thrust = { torso = { 22, 0, -35 }, head = { -22, 0, 30 }, armL = { 55, 0, 45 }, armR = { -90, 0, 5 }, legL = { -70, 0, 10 }, legR = { 55, 0, -5 } },
}

local PARTS = { "torso", "head", "armL", "armR", "legL", "legR" }
local ZERO = { 0, 0, 0 }

-- copy a pose and override some entries
function Rig.P(name: string, over: { [string]: any }?)
	local base = Rig.POSES[name]
	local out = {}
	for k, v in base do
		out[k] = v
	end
	if over then
		for k, v in over do
			out[k] = v
		end
	end
	return out
end

local JOINTS = {
	R6 = { torso = "RootJoint", head = "Neck", armL = "Left Shoulder", armR = "Right Shoulder", legL = "Left Hip", legR = "Right Hip" },
	R15 = { torso = "Root", head = "Neck", armL = "LeftShoulder", armR = "RightShoulder", legL = "LeftHip", legR = "RightHip" },
}

export type Style = "normal" | "dark" | "silhouette" | "ghost" | "none"

local STYLE = {
	normal = { fill = Kit.BLUE, fillT = 1, outline = Kit.CYAN, outlineT = 0.35 },
	dark = { fill = Kit.rgb(0.02, 0.03, 0.09), fillT = 0.05, outline = Kit.rgb(0.55, 0.8, 1), outlineT = 0 },
	silhouette = { fill = Kit.rgb(0.6, 0.85, 1), fillT = 0, outline = Kit.PINK, outlineT = 0 },
	ghost = { fill = Kit.rgb(0.12, 0.35, 1), fillT = 0.45, outline = Kit.rgb(0.45, 0.7, 1), outlineT = 0.1 },
}

local Actor = {}
Actor.__index = Actor

-- character: the player's character model. stage: CFrame of the set origin.
function Rig.newActor(character: Model, parent: Instance, stage: CFrame, style: Style?)
	local old = character.Archivable
	character.Archivable = true
	local clone = character:Clone()
	character.Archivable = old
	clone.Name = "UltActor"

	for _, d in clone:GetDescendants() do
		if d:IsA("BaseScript") or d:IsA("ModuleScript") or d:IsA("Sound") or d:IsA("ForceField") then
			d:Destroy()
		elseif d:IsA("BasePart") then
			d.Anchored = false
			d.CanCollide = false
			d.CanQuery = false
			d.CanTouch = false
			d.Massless = true
		elseif d:IsA("Motor6D") then
			d.Transform = CFrame.identity
		end
	end

	local hum = clone:FindFirstChildOfClass("Humanoid")
	if hum then
		local animator = hum:FindFirstChildOfClass("Animator")
		if animator then
			animator:Destroy()
		end
		hum.DisplayDistanceType = Enum.HumanoidDisplayDistanceType.None
		hum.HealthDisplayType = Enum.HumanoidHealthDisplayType.AlwaysOff
		hum.PlatformStand = true
		hum.RequiresNeck = false
		hum.BreakJointsOnDeath = false
	end

	local hrp = clone:FindFirstChild("HumanoidRootPart") :: BasePart
	hrp.Anchored = true
	hrp.Transparency = 1

	local rigType = (hum and hum.RigType == Enum.HumanoidRigType.R15) and "R15" or "R6"
	local self = setmetatable({}, Actor)
	self.model = clone
	self.hrp = hrp
	self.stage = stage
	self.rig = rigType
	self.keys = {}
	self.joints = {}
	for part, jname in JOINTS[rigType] do
		local j = clone:FindFirstChild(jname, true)
		if j and j:IsA("Motor6D") then
			self.joints[part] = j
		end
	end

	-- hip height: where the Blender "root" (hip centre) sits relative to the HumanoidRootPart
	self.hipToRoot = 1
	local hip = self.joints.legL
	local root = self.joints.torso
	if hip and root and hip.Part0 then
		local part0CF = root.C0 * root.C1:Inverse() -- torso/lower torso relative to HRP
		local hipPos = (part0CF * hip.C0).Position
		self.hipToRoot = -hipPos.Y
	end

	self.highlight = Instance.new("Highlight")
	self.highlight.DepthMode = Enum.HighlightDepthMode.Occluded
	self.highlight.Adornee = clone
	self.highlight.Parent = clone
	self:setStyle(style or "normal")

	clone.Parent = parent
	return self
end

function Actor:setStyle(style: Style)
	local s = STYLE[style]
	local h = self.highlight
	if not s then
		h.Enabled = false
		return
	end
	h.Enabled = true
	h.FillColor = s.fill
	h.FillTransparency = s.fillT
	h.OutlineColor = s.outline
	h.OutlineTransparency = s.outlineT
	if style == "ghost" then
		for _, d in self.model:GetDescendants() do
			if d:IsA("BasePart") and d ~= self.hrp then
				d.Transparency = math.max(d.Transparency, 0.55)
				d.Material = Enum.Material.Neon
				d.Color = Kit.rgb(0.1, 0.3, 1)
			elseif d:IsA("Decal") then
				d.Transparency = 0.6
			end
		end
	end
end

function Actor:setHighlight(fill: Color3, fillT: number, outline: Color3, outlineT: number)
	local h = self.highlight
	h.Enabled = true
	h.FillColor, h.FillTransparency, h.OutlineColor, h.OutlineTransparency = fill, fillT, outline, outlineT
end

function Actor:scale(s: number)
	pcall(function()
		self.model:ScaleTo(s)
	end)
	self.scaleFactor = s
end

-- key a pose. pose = Rig.P(...); loc = Blender hip position (relative to stage); rot = Blender degrees
function Actor:key(t: number, pose: any, loc: Vector3?, rot: { number }?)
	table.insert(self.keys, { t = t, pose = pose, loc = loc, rot = rot })
	table.sort(self.keys, function(a, b)
		return a.t < b.t
	end)
end

local function lerp3(a: { number }, b: { number }, f: number): { number }
	return { a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, a[3] + (b[3] - a[3]) * f }
end

-- rotate a joint by R (expressed in Part0's frame) about `pivot` (Part0 space, default = joint)
local function drive(j: Motor6D, rot: CFrame, pivot: Vector3?)
	local p = pivot or j.C0.Position
	local x = CFrame.new(p) * rot * CFrame.new(-p)
	j.Transform = j.C0:Inverse() * x * j.C0
end

function Actor:update(t: number)
	local keys = self.keys
	if #keys == 0 then
		return
	end
	local a, b, f = keys[1], keys[1], 0
	if t >= keys[#keys].t then
		a, b = keys[#keys], keys[#keys]
	elseif t > keys[1].t then
		for i = 1, #keys - 1 do
			if t < keys[i + 1].t then
				a, b = keys[i], keys[i + 1]
				f = Kit.smooth((t - a.t) / math.max(b.t - a.t, 1e-6))
				break
			end
		end
	end
	local s = self.scaleFactor or 1
	for _, name in PARTS do
		local j = self.joints[name]
		if j then
			local r = lerp3(a.pose[name] or ZERO, b.pose[name] or ZERO, f)
			if name == "torso" then
				drive(j, R(r[1], r[2], r[3]), Vector3.new(0, -self.hipToRoot, 0) + (j.C0.Position * Vector3.new(1, 0, 1)))
			else
				drive(j, R(r[1], r[2], r[3]))
			end
		end
	end
	local la, lb = a.loc or Vector3.zero, b.loc or a.loc or Vector3.zero
	local loc = la:Lerp(lb, f)
	local rot = lerp3(a.rot or ZERO, b.rot or a.rot or ZERO, f)
	self.hrp.CFrame = self.stage * CFrame.new(V(loc.X, loc.Y, loc.Z) + Vector3.new(0, self.hipToRoot * s, 0)) * R(rot[1], rot[2], rot[3])
end

function Actor:destroy()
	self.model:Destroy()
end

Rig.Actor = Actor
return Rig
