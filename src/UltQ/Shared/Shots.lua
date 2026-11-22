-- Shots: the 15 shot sets of the ult, ported 1:1 from ult-blender/ult_build.py.
-- Every set is built from anchored, local-only parts around its own stage origin. All numbers
-- are in Blender space and converted by Kit.V / Kit.S / Kit.R.

local Kit = require(script.Parent.Kit)
local Rig = require(script.Parent.Rig)
local Config = require(script.Parent.Config)
local V, S, R = Kit.V, Kit.S, Kit.R
local P = Rig.P

local Shots = {}

-------------------------------------------------------------------------- set context ------
local Ctx = {}
Ctx.__index = Ctx

function Shots.newCtx(parent: Instance, stage: CFrame, character: Model, name: string)
	local folder = Instance.new("Folder")
	folder.Name = name
	folder.Parent = parent
	return setmetatable({
		folder = folder,
		stage = stage,
		char = character,
		movers = {},
		updaters = {},
		actors = {},
		cams = {},
		post = nil,
	}, Ctx)
end

function Ctx:n(count: number): number
	return math.max(1, math.floor(count * Config.Density + 0.5))
end

function Ctx:at(x: number, y: number, z: number, a: number?, b: number?, c: number?): CFrame
	return self.stage * CFrame.new(V(x, y, z)) * R(a, b, c)
end

function Ctx:box(size: { number }, pos: { number }, color: Color3, material: Enum.Material?, rot: { number }?, transparency: number?): Part
	local r = rot or { 0, 0, 0 }
	return Kit.part(self.folder, {
		Size = S(size[1], size[2], size[3]),
		CFrame = self:at(pos[1], pos[2], pos[3], r[1], r[2], r[3]),
		Color = color,
		Material = material or Enum.Material.Neon,
		Transparency = transparency,
	})
end

-- flat plate facing the camera (Blender XZ plane), w x h
function Ctx:plate(w: number, h: number, pos: { number }, color: Color3, transparency: number?, rot: { number }?): Part
	return self:box({ w, 0.05, h }, pos, color, Enum.Material.Neon, rot, transparency)
end

function Ctx:ballAt(pos: { number }, d: number, color: Color3, transparency: number?): Part
	return Kit.ball(self.folder, self:at(pos[1], pos[2], pos[3]), d, color, transparency)
end

function Ctx:light(pos: { number }, color: Color3, brightness: number, range: number): PointLight
	return Kit.light(self.folder, self:at(pos[1], pos[2], pos[3]), color, brightness, range)
end

-- dark box that hides the map / sky around this set
function Ctx:enclose(center: { number }, size: number)
	local c = self:at(center[1], center[2], center[3])
	local h = size / 2
	local col = Kit.rgb(0.004, 0.006, 0.02)
	for _, d in { Vector3.xAxis, -Vector3.xAxis, Vector3.yAxis, -Vector3.yAxis, Vector3.zAxis, -Vector3.zAxis } do
		local s = Vector3.new(math.abs(d.X) > 0 and 2 or size, math.abs(d.Y) > 0 and 2 or size, math.abs(d.Z) > 0 and 2 or size)
		Kit.part(self.folder, { Size = s, CFrame = c + d * h, Color = col, Material = Enum.Material.SmoothPlastic, Name = "Backdrop" })
	end
end

function Ctx:mover(part: BasePart, fn: (number) -> CFrame)
	table.insert(self.movers, { part, fn })
end

function Ctx:onUpdate(fn: (number) -> ())
	table.insert(self.updaters, fn)
end

function Ctx:actor(style: Rig.Style, spear: boolean?)
	local a = Rig.newActor(self.char, self.folder, self.stage, style)
	if spear == false and a.spearModel then
		a.spearModel:Destroy()
		a.spearWeld = nil
	end
	table.insert(self.actors, a)
	return a
end

-- camera: keys = { {t, {pos}, {target}, roll, mode?}, ... }
function Ctx:camera(name: string, lens: number, keys: { any }, shake: { number }?)
	local posKeys, tgtKeys, rollKeys = {}, {}, {}
	for _, k in keys do
		local m = k[5] or "linear"
		table.insert(posKeys, { k[1], self.stage * V(k[2][1], k[2][2], k[2][3]), m })
		table.insert(tgtKeys, { k[1], self.stage * V(k[3][1], k[3][2], k[3][3]), m })
		table.insert(rollKeys, { k[1], k[4], m })
	end
	self.cams[name] = {
		pos = Kit.track(posKeys),
		target = Kit.track(tgtKeys),
		roll = Kit.track(rollKeys),
		fov = math.deg(2 * math.atan(10.125 / lens)), -- Blender 36mm sensor, 16:9
		shake = shake, -- {t0, t1, amp, rotAmpDeg, every}
	}
end

-- flicker: part only visible during the listed [t0, t1) windows
function Ctx:flicker(parts: { BasePart }, windows: { { number } }, visibleT: number?)
	local vt = visibleT or 0
	self:onUpdate(function(t)
		local on = false
		for _, w in windows do
			if t >= w[1] and t < w[2] then
				on = true
				break
			end
		end
		for _, p in parts do
			p.Transparency = on and vt or 1
		end
	end)
end

function Ctx:update(t: number)
	for _, a in self.actors do
		a:update(t)
	end
	local list, cfs = table.create(#self.movers), table.create(#self.movers)
	for i, m in self.movers do
		list[i] = m[1]
		cfs[i] = m[2](t)
	end
	if #list > 0 then
		workspace:BulkMoveTo(list, cfs, Enum.BulkMoveMode.FireCFrameChanged)
	end
	for _, fn in self.updaters do
		fn(t)
	end
end

function Ctx:destroy()
	for _, a in self.actors do
		a:destroy()
	end
	self.folder:Destroy()
end

local function lightningPts(p0: Vector3, p1: Vector3, segs: number, jitter: number, rng: Random): { Vector3 }
	local d = p1 - p0
	local side = d:Cross(Vector3.yAxis)
	if side.Magnitude < 1e-3 then
		side = d:Cross(Vector3.xAxis)
	end
	side = side.Unit
	local side2 = d:Cross(side).Unit
	local pts = {}
	for i = 0, segs do
		local f = i / segs
		local j = (i == 0 or i == segs) and 0 or jitter * math.sin(f * math.pi)
		table.insert(pts, p0 + d * f + side * rng:NextNumber(-j, j) + side2 * rng:NextNumber(-j, j) * 0.5)
	end
	return pts
end

local function chain(ctx, pts: { Vector3 }, thick: number, color: Color3, transparency: number?): { BasePart }
	local out: { BasePart } = {}
	for i = 1, #pts - 1 do
		table.insert(out, Kit.segment(ctx.folder, pts[i], pts[i + 1], thick, color, transparency))
	end
	return out
end

-- group of parts that move/scale/rotate together around a pivot
local function group(ctx, pivot: (number) -> CFrame, scale: (number) -> number, items: { { any } })
	-- items: { part, offsetCF, baseSize }
	ctx:onUpdate(function(t)
		local pc, s = pivot(t), scale(t)
		for _, it in items do
			local p, off, size = it[1], it[2], it[3]
			p.Size = Vector3.new(math.max(size.X * s, 0.05), math.max(size.Y * s, 0.05), size.Z)
			p.CFrame = pc * (off.Rotation + off.Position * s)
		end
	end)
end

local function ringItems(parts: { BasePart }, offsets: { CFrame }, extra: CFrame?)
	local items = {}
	for i, p in parts do
		table.insert(items, { p, (extra or CFrame.identity) * offsets[i], p.Size })
	end
	return items
end

--------------------------------------------------------------------------------- SETS -----
local Sets = {}

-- 0.00 Arena wide shot
function Sets.S01(ctx)
	local rng = Random.new(1)
	ctx:enclose({ 0, 20, 10 }, 200)
	ctx:box({ 120, 120, 0.4 }, { 0, 20, -0.2 }, Kit.rgb(0.03, 0.045, 0.09), Enum.Material.Metal)
	local grid = Kit.rgb(0.1, 0.3, 1)
	for i = -15, 15 do
		ctx:box({ 0.12, 120, 0.05 }, { i * 4, 20, 0.02 }, grid, nil, nil, 0.35)
		ctx:box({ 120, 0.12, 0.05 }, { 0, 20 + i * 4, 0.02 }, grid, nil, nil, 0.35)
	end
	local wall = Kit.rgb(0.04, 0.07, 0.14)
	ctx:box({ 120, 2, 40 }, { 0, 46, 20 }, wall, Enum.Material.Metal)
	for _, side in { -1, 1 } do
		for k = 0, 6 do
			local x, h = side * (10 + k * 4.5), 26 - k * 1.5
			for s = 0, 5 do
				local a = s / 5
				ctx:box({ 1.6, 2.2, h / 5 + 0.6 }, { x - side * a * a * 7, 34 - k * 2.5, 2 + a * h }, Kit.rgb(0.06, 0.1, 0.2), Enum.Material.Metal, { 0, side * a * 55, 0 })
			end
		end
		for k = 0, 4 do
			ctx:box({ 2.6, 0.3, 1.6 }, { side * (16 + k * 6), 44.5, 4 + (k % 2) * 3 }, Kit.ORANGE)
		end
	end
	for _, x in { -5, 5 } do
		ctx:box({ 1.4, 1.4, 18 }, { x, 38, 9 }, Kit.rgb(0.06, 0.1, 0.2), Enum.Material.Metal)
	end
	ctx:box({ 8, 0.3, 12 }, { 0, 44.6, 6 }, Kit.rgb(0.5, 0.75, 1))
	ctx:box({ 10.5, 1.5, 1.2 }, { 0, 38, 18 }, Kit.rgb(0.06, 0.1, 0.2), Enum.Material.Metal)
	ctx:box({ 0.25, 22, 0.05 }, { 0.6, -6, 0.03 }, Kit.rgb(0.7, 0.5, 1), nil, { 0, 0, 8 })
	for _ = 1, ctx:n(80) do
		local p0 = ctx:at(rng:NextNumber(-30, 30), rng:NextNumber(-4, 40), rng:NextNumber(0.5, 16))
		local drift = Vector3.new(rng:NextNumber(-0.3, 0.3), rng:NextNumber(0.4, 1.2), 0)
		local b = Kit.ball(ctx.folder, p0, rng:NextNumber(0.08, 0.25), Kit.rgb(0.3, 0.55, 1))
		ctx:mover(b, function(t)
			return p0 + drift * t * 3
		end)
	end
	local av = ctx:actor("normal")
	av:key(0.0, P("ready"), Vector3.new(0, 8, 2), { 0, 0, -15 })
	av:key(0.22, P("ready", { torso = { 14, 0, -15 }, armR = { -60, 0, -10 } }), Vector3.new(0, 8, 2), { 0, 0, -15 })
	ctx:light({ -6, 0, 10 }, Kit.rgb(0.35, 0.55, 1), 3, 40)
	ctx:light({ 4, 14, 6 }, Kit.rgb(0.45, 0.65, 1), 4, 30)
	ctx:light({ 1, 4, 0.5 }, Kit.rgb(1, 0.3, 0.7), 3, 10)
	ctx:camera("S01", 24, {
		{ 0.0, { 1.5, -14, 3.2 }, { 0, 10, 3.5 }, 0 },
		{ 0.22, { 1.2, -12.5, 3.0 }, { 0, 10, 3.4 }, 0 },
	})
end

-- 0.22 Hologram close-up (+ 0.83 glitch close-up camera)
function Sets.S02(ctx)
	local rng = Random.new(2)
	ctx:enclose({ 0, 0, 2 }, 60)
	local av = ctx:actor("normal", false)
	av:key(0.22, P("chest_up", { head = { -6, 0, -8 }, torso = { 0, 0, -10 } }), Vector3.zero)
	av:key(0.92, P("chest_up", { head = { -2, 0, -14 }, torso = { 0, 0, -14 } }), Vector3.zero)
	local holo = ctx:actor("ghost", false)
	holo:key(0.22, P("chest_up", { head = { -6, 0, -8 }, torso = { 0, 0, -10 } }), Vector3.new(0.25, 0.3, 0))
	local holoT = Kit.track({ { 0.22, 0.9 }, { 0.40, 0.45 }, { 0.67, 0.35 }, { 0.92, 0.8 } })
	ctx:onUpdate(function(t)
		holo.highlight.FillTransparency = holoT(t)
	end)
	-- data cubes streaming off the body
	for i = 1, ctx:n(50) do
		local p0 = Vector3.new(0.5 + rng:NextNumber(-1.6, 1.6), -0.3 + rng:NextNumber(-0.6, 0.6), 2.2 + rng:NextNumber(-1.4, 1.4))
		local p1 = p0 + Vector3.new(rng:NextNumber(0.8, 2.8), rng:NextNumber(-1.5, 0.2), rng:NextNumber(-0.8, 1.0))
		local s0 = rng:NextNumber(0.08, 0.3)
		local wire = i % 3 ~= 0
		local c = Kit.part(ctx.folder, { Size = Vector3.one * s0, Color = Kit.rgb(0.15, 0.45, 1), Transparency = wire and 0.75 or 0 })
		if wire then
			local sb = Instance.new("SelectionBox")
			sb.Adornee = c
			sb.Color3 = Kit.rgb(0.4, 0.7, 1)
			sb.LineThickness = 0.015
			sb.SurfaceTransparency = 1
			sb.Parent = c
		end
		ctx:onUpdate(function(t)
			local f = Kit.prog(t, 0.22, 0.92)
			local p = p0:Lerp(p1, f)
			c.Size = Vector3.one * math.max(s0 * (1 - f), 0.05)
			c.CFrame = ctx:at(p.X, p.Y, p.Z)
		end)
	end
	-- lightning arcs (each visible for 2 frames)
	for k = 0, 8 do
		local a = ctx:at(1.2, -0.6, 3.4).Position
		local b = ctx:at(3.2 + rng:NextNumber(0, 1), 0.4, 1.6 + rng:NextNumber(-0.4, 1.4)).Position
		local bolt = chain(ctx, lightningPts(a, b, 12, 0.35, rng), 0.05, Kit.rgb(0.55, 0.78, 1))
		local t0 = 0.29 + k * 0.067 + rng:NextNumber(0, 0.03)
		ctx:flicker(bolt, { { t0, t0 + 0.067 }, { t0 + 0.6, t0 + 0.64 } })
	end
	ctx:plate(14, 9, { 1, 4, 2.5 }, Kit.rgb(0.02, 0.07, 0.5), 0.55)
	ctx:light({ -2.5, -3, 3.5 }, Kit.rgb(0.35, 0.55, 1), 2, 14)
	ctx:light({ 2.5, 1.5, 3.5 }, Kit.rgb(0.3, 0.6, 1), 4, 10)
	ctx:camera("S02", 50, {
		{ 0.22, { 0.55, -4.2, 2.75 }, { 0.05, 0, 2.65 }, -3 },
		{ 0.67, { 0.45, -3.6, 2.72 }, { 0.05, 0, 2.62 }, -5 },
	})
	ctx:camera("S04", 65, {
		{ 0.83, { 0.1, -3.4, 2.75 }, { 0, 0, 2.7 }, 4 },
		{ 0.92, { 0.12, -3.2, 2.76 }, { 0, 0, 2.7 }, 5 },
	}, { 0.83, 0.92, 0.04, 1.0, 1 })
end

-- 0.67 Ink splash (+ 0.92 pink duotone flash)
function Sets.S03(ctx)
	local rng = Random.new(3)
	ctx:enclose({ 0, 0, 2 }, 60)
	local av = ctx:actor("silhouette", false)
	av:key(0.67, P("chest_up", { head = { -10, 0, 10 }, armR = { -40, 0, -30 }, armL = { -30, 0, 30 } }), Vector3.zero)
	av:key(1.0, P("chest_up", { head = { -14, 0, 14 }, armR = { -50, 0, -35 }, armL = { -40, 0, 35 } }), Vector3.zero)
	local ink = Kit.rgb(0.02, 0.1, 0.95)
	local blobs = {}
	local function blob(center: { number }, spread: { number }, count: number, dmin: number, dmax: number, delay: number)
		for _ = 1, ctx:n(count) do
			local p = ctx:at(center[1] + rng:NextNumber(-spread[1], spread[1]), center[2] + rng:NextNumber(0, spread[2]), center[3] + rng:NextNumber(-spread[3], spread[3]))
			local d = rng:NextNumber(dmin, dmax)
			local b = Kit.ball(ctx.folder, p, 0.05, ink)
			local grow = Kit.track({ { 0.67 + delay * rng:NextNumber(0, 1), 0.05 }, { 0.8, d * 0.85, "ease" }, { 1.0, d } })
			table.insert(blobs, b)
			ctx:onUpdate(function(t)
				b.Size = Vector3.one * grow(t)
			end)
		end
	end
	blob({ 0, 1.6, 2.4 }, { 4.5, 0.6, 3 }, 45, 1.2, 3.2, 0.1)
	blob({ 1.8, -1.2, 1.0 }, { 2.5, 0.3, 1.2 }, 18, 0.8, 2.0, 0.12)
	for _ = 1, ctx:n(30) do
		local from = ctx:at(0, 1, 2.5)
		local to = ctx:at(rng:NextNumber(-5, 5), rng:NextNumber(0.5, 1.4), rng:NextNumber(0, 5))
		local b = Kit.ball(ctx.folder, from, rng:NextNumber(0.1, 0.4), ink)
		table.insert(blobs, b)
		ctx:mover(b, function(t)
			return from:Lerp(to, Kit.smooth(Kit.prog(t, 0.67, 0.85)))
		end)
	end
	-- pink duotone frame: figure turns pink, ink stays blue
	ctx:onUpdate(function(t)
		if t >= 0.92 then
			av:setHighlight(Kit.rgb(1, 0.55, 0.78), 0, Kit.PINK, 0)
		else
			av:setHighlight(Kit.rgb(0.6, 0.85, 1), 0, Kit.PINK, 0)
		end
	end)
	ctx:camera("S03", 40, {
		{ 0.67, { 0.2, -5.0, 2.6 }, { 0.2, 0, 2.5 }, 6 },
		{ 0.83, { 0.2, -4.6, 2.6 }, { 0.2, 0, 2.5 }, 8 },
	})
	ctx:camera("S05", 30, {
		{ 0.92, { 0, -6.2, 2.4 }, { 0, 0, 2.3 }, -4 },
		{ 1.0, { 0, -6.6, 2.4 }, { 0, 0, 2.3 }, -5 },
	}, { 0.92, 1.0, 0.08, 1.5, 1 })
end

-- 1.00 Afterimage clones
function Sets.S06(ctx)
	local rng = Random.new(6)
	ctx:enclose({ 0, 4, 3 }, 60)
	local av = ctx:actor("normal", false)
	av:key(1.0, P("chest_up", { head = { -4, 0, 0 } }), Vector3.zero)
	av:key(1.47, P("chest_up", { head = { -8, 0, 12 }, torso = { 0, 0, 10 } }), Vector3.zero)
	for _, c in { { -2.3, 1.4, 25, 1.15 }, { 2.4, 1.6, -28, 1.2 }, { -4.2, 3.0, 35, 1.3 }, { 4.4, 3.2, -35, 1.3 } } do
		local g = ctx:actor("ghost", false)
		local from = Vector3.new(c[1], c[2], -0.2)
		local to = from + Vector3.new(c[1] * 0.12, 0.4, 0.15)
		g:key(1.0, P("chest_up", { head = { -10, 0, c[3] * 0.3 } }), from, { 0, 0, c[3] })
		g:key(1.47, P("chest_up", { head = { -10, 0, c[3] * 0.3 } }), to, { 0, 0, c[3] })
	end
	for gx = -10, 10 do
		for gz = -1, 11 do
			if rng:NextNumber() < 0.5 * Config.Density then
				local solid = rng:NextNumber() < 0.35
				ctx:plate(0.35, 0.35, { gx * 0.9, 9, gz * 0.9 }, Kit.rgb(0.1, 0.32, 1), solid and 0 or 0.6)
			end
		end
	end
	for _ = 1, ctx:n(40) do
		local s = rng:NextNumber(0.08, 0.24)
		local p0 = ctx:at(rng:NextNumber(-4.5, 4.5), rng:NextNumber(-1.5, 4), rng:NextNumber(2, 6.5))
		local fall = rng:NextNumber(1.5, 3.5)
		local b = Kit.part(ctx.folder, { Size = Vector3.one * s, CFrame = p0, Color = Kit.rgb(0.35, 0.6, 1) })
		ctx:mover(b, function(t)
			return p0 - Vector3.new(0, fall * Kit.prog(t, 1.0, 1.47), 0)
		end)
	end
	ctx:light({ -3, -4, 4 }, Kit.rgb(0.35, 0.55, 1), 3, 16)
	ctx:light({ 3, 2, 4.5 }, Kit.rgb(0.5, 0.7, 1), 4, 12)
	ctx:light({ 0.5, -2, 1 }, Kit.rgb(1, 0.3, 0.6), 1.5, 8)
	ctx:camera("S06", 32, {
		{ 1.0, { 0.3, -6.2, 2.0 }, { 0, 0, 2.5 }, 3 },
		{ 1.47, { 0.2, -5.2, 2.1 }, { 0, 0, 2.55 }, -2 },
	})
end

-- 1.47 Rear over-the-shoulder, square tunnel ahead
function Sets.S07(ctx)
	ctx:enclose({ 0, 30, 3 }, 140)
	local av = ctx:actor("normal")
	av:key(1.47, P("raise", { spear = { 150, 0, 10 } }), Vector3.zero, { 0, 0, 180 })
	av:key(1.63, P("raise", { armR = { -175, 0, -20 }, spear = { 170, 0, 20 } }), Vector3.zero, { 0, 0, 180 })
	for i = 0, ctx:n(34) - 1 do
		local col = (i % 3 == 0) and Kit.rgb(0.4, 0.65, 1) or Kit.rgb(0.03, 0.2, 1)
		local parts, offs = Kit.squareRing(ctx.folder, 16, 0.35, col)
		local base = i * 7
		group(ctx, function(t)
			return ctx:at(0, 4 + i * 2.2, 3, 0, base + 25 * Kit.prog(t, 1.47, 1.63), 0)
		end, function()
			return 1
		end, ringItems(parts, offs))
	end
	ctx:plate(40, 30, { 0, 80, 3 }, Kit.rgb(0.05, 0.2, 1), 0.2)
	ctx:light({ 0, 6, 5 }, Kit.rgb(0.4, 0.6, 1), 6, 30)
	ctx:light({ -3, -3, 3 }, Kit.rgb(0.2, 0.3, 1), 2, 12)
	ctx:camera("S07", 28, {
		{ 1.47, { 3.4, -6.5, 1.6 }, { -0.3, 8, 3.8 }, -12 },
		{ 1.63, { 3.0, -5.8, 1.8 }, { -0.3, 8, 3.9 }, -16 },
	})
end

-- 1.63 Infinite twisting square tunnel + spear-tip star glints
function Sets.S08(ctx)
	ctx:enclose({ 0, 30, 0 }, 140)
	for i = 0, ctx:n(60) - 1 do
		local col = (i % 3 == 0) and Kit.rgb(0.4, 0.65, 1) or Kit.rgb(0.03, 0.18, 1)
		local parts, offs = Kit.squareRing(ctx.folder, 9, 0.22, col)
		group(ctx, function(t)
			return ctx:at(0, i * 1.0, 0, 0, i * 6 - 40 * Kit.prog(t, 1.63, 1.97), 0)
		end, function()
			return 1
		end, ringItems(parts, offs))
	end
	ctx:plate(12, 12, { 0, 62, 0 }, Kit.rgb(0.4, 0.65, 1), 0.1)
	local av = ctx:actor("dark")
	av:scale(0.45)
	av:key(1.63, P("stand_spear", { spear = { 60, 0, 0 }, armR = { -60, 0, -10 } }), Vector3.new(0, 18, -1.2))
	av:key(1.97, P("stand_spear", { spear = { 66, 0, 0 }, armR = { -66, 0, -12 }, head = { -12, 0, 0 } }), Vector3.new(0, 18, -1.2))
	-- huge foreground spear + 4-point star glints
	local fs = ctx:at(2.0, 2.2, -0.9, 80, 0, -60)
	Kit.part(ctx.folder, { Size = Vector3.new(0.16, 6, 0.16), CFrame = fs * CFrame.new(0, -3, 0), Color = Kit.rgb(0.03, 0.03, 0.06), Material = Enum.Material.Metal })
	Kit.ellipsoid(ctx.folder, fs * CFrame.new(0, 0.7, 0), Vector3.new(0.45, 1.6, 0.1), Kit.ICE)
	for _, st in { { 0.9, 0.5, 1.66 }, { 0.45, 0.32, 1.72 }, { 1.3, 0.25, 1.78 } } do
		local center = (fs * CFrame.new(0, st[1], 0)).Position + Vector3.new(0, 0, -0.25)
		local parts = Kit.star(ctx.folder, Kit.rgb(0.75, 0.88, 1))
		local base = { Vector3.new(0.12, 2, 0.05), Vector3.new(2, 0.12, 0.05), Vector3.one * 0.35 }
		local sc = Kit.track({ { st[3] - 0.03, 0 }, { st[3] + 0.03, st[2], "ease" }, { 1.97, st[2] * 0.6 } })
		ctx:onUpdate(function(t)
			local s = sc(t)
			for i, p in parts do
				p.Size = Vector3.new(math.max(base[i].X * s, 0.05), math.max(base[i].Y * s, 0.05), 0.05)
				p.CFrame = CFrame.new(center)
				p.Transparency = s < 0.02 and 1 or 0
			end
		end)
	end
	ctx:light({ 0, 14, 0 }, Kit.rgb(0.4, 0.6, 1), 5, 30)
	ctx:camera("S08", 30, {
		{ 1.63, { 0, -2, 0 }, { 0, 20, -0.3 }, 8 },
		{ 1.97, { 0, 1, 0 }, { 0, 20, -0.3 }, -2 },
	})
end

-- 1.97 Diamond portal + crescent, cubes blasting out, lunge
function Sets.S09(ctx)
	local rng = Random.new(9)
	ctx:enclose({ 0, 20, 3 }, 120)
	local items = {}
	local frameCol = Kit.rgb(0.55, 0.78, 1)
	local p1, o1 = Kit.squareRing(ctx.folder, 7, 0.25, frameCol)
	local p2, o2 = Kit.squareRing(ctx.folder, 7.8, 0.06, frameCol)
	local diamond = CFrame.Angles(0, 0, math.rad(45))
	for _, it in ringItems(p1, o1, diamond) do
		table.insert(items, it)
	end
	for _, it in ringItems(p2, o2, diamond) do
		table.insert(items, it)
	end
	local cp, co = Kit.crescent(ctx.folder, 2.0, Kit.rgb(0.85, 0.93, 1))
	for _, it in ringItems(cp, co, CFrame.Angles(0, 0, math.rad(200)) * CFrame.new(0, 0, -0.05)) do
		table.insert(items, it)
	end
	local inner = Kit.part(ctx.folder, { Size = Vector3.new(6.6, 6.6, 0.05), Color = Kit.rgb(0.15, 0.4, 1), Transparency = 0.55 })
	table.insert(items, { inner, diamond * CFrame.new(0, 0, 0.3), inner.Size })
	local sc = Kit.track({ { 1.97, 0.2 }, { 2.10, 1.0, "ease" }, { 2.40, 1.15 } })
	local rot = Kit.track({ { 1.97, -30, "ease" }, { 2.40, 8 } })
	group(ctx, function(t)
		return ctx:at(0, 14, 3, 0, rot(t), 0)
	end, sc, items)
	local cols = { Kit.rgb(0.1, 0.35, 1), Kit.rgb(0.03, 0.06, 0.2), Kit.rgb(0.45, 0.72, 1) }
	for _ = 1, ctx:n(90) do
		local a = rng:NextNumber(0, 2 * math.pi)
		local r = rng:NextNumber(4.5, 16)
		local s = rng:NextNumber(0.15, 0.7)
		local from = ctx:at(math.cos(a) * 3.2, 14, 3 + math.sin(a) * 3.2)
		local to = ctx:at(math.cos(a) * r, 14 + rng:NextNumber(-6, 6), 3 + math.sin(a) * r * 0.7)
		local spin = CFrame.Angles(rng:NextNumber(0, 6), rng:NextNumber(0, 6), rng:NextNumber(0, 6))
		local st = 1.97 + rng:NextNumber(0, 0.12)
		local col = cols[rng:NextInteger(1, 3)]
		local c = Kit.part(ctx.folder, { Size = Vector3.one * s, Color = col, Material = col == cols[2] and Enum.Material.Metal or Enum.Material.Neon })
		ctx:mover(c, function(t)
			local f = Kit.prog(t, st, 2.40)
			return CFrame.new(from.Position:Lerp(to.Position, 1 - (1 - f) ^ 2)) * CFrame.identity:Lerp(spin, f)
		end)
	end
	for _ = 1, ctx:n(40) do
		local a = rng:NextNumber(0, 2 * math.pi)
		local r = rng:NextNumber(11, 15)
		local s = rng:NextNumber(1.5, 4)
		ctx:box({ s, rng:NextNumber(2, 8), s }, { math.cos(a) * r, rng:NextNumber(10, 45), 3 + math.sin(a) * r }, Kit.rgb(0.03, 0.06, 0.16), Enum.Material.Metal)
	end
	local av = ctx:actor("normal")
	av:key(1.97, P("lunge"), Vector3.new(3.8, 4.5, 0.5), { 0, 0, -120 })
	av:key(2.40, P("lunge", { torso = { 38, 0, -30 } }), Vector3.new(2.9, 5.5, 0.7), { 0, 0, -120 })
	ctx:light({ 0, 12, 3 }, Kit.rgb(0.45, 0.65, 1), 8, 40)
	ctx:light({ 6, 0, 4 }, Kit.rgb(0.35, 0.55, 1), 3, 16)
	ctx:camera("S09", 26, {
		{ 1.97, { 5.5, -4.5, 1.5 }, { 0, 14, 3 }, 18 },
		{ 2.40, { 6.2, -6.5, 1.2 }, { 0, 14, 3 }, 4 },
	})
end

-- 2.40 Smirk close-up with swirling energy ribbons
function Sets.S10(ctx)
	local rng = Random.new(10)
	ctx:enclose({ 0, 2, 2.6 }, 40)
	local av = ctx:actor("normal")
	av:key(2.40, P("chest_up", { head = { -8, 0, -18 }, torso = { 4, 0, -20 }, armR = { -120, 0, -40 }, spear = { 100, 0, 40 } }), Vector3.zero)
	av:key(2.72, P("chest_up", { head = { -12, 0, -8 }, torso = { 4, 0, -14 }, armR = { -130, 0, -45 }, spear = { 100, 0, 40 } }), Vector3.zero)
	local items = {}
	for k = 1, ctx:n(10) do
		local r = rng:NextNumber(1.5, 3.2)
		local a0 = rng:NextNumber(-0.6, math.pi + 0.6)
		local h = rng:NextNumber(-1.4, 1.3)
		local dz = rng:NextNumber(-0.03, 0.05)
		local col = (k % 3 == 0) and Kit.rgb(0.6, 0.85, 1) or Kit.rgb(0.05, 0.3, 1)
		local th = rng:NextNumber(0.04, 0.1)
		local prev
		for j = 0, 14 do
			local a = a0 + j * 0.16
			local p = V(math.cos(a) * r, math.abs(math.sin(a)) * r * 0.7 + 0.4, h + j * dz)
			if prev then
				local seg = Kit.part(ctx.folder, { Size = Vector3.new(th, th * 0.4, (p - prev).Magnitude + 0.05), Color = col })
				table.insert(items, { seg, CFrame.lookAt((p + prev) / 2, p), seg.Size })
			end
			prev = p
		end
	end
	local spin = Kit.track({ { 2.40, 0 }, { 2.72, -140 } })
	group(ctx, function(t)
		return ctx:at(0, 0, 2.6, 11, 0, spin(t))
	end, function()
		return 1
	end, items)
	ctx:plate(16, 10, { 0, 6, 2.6 }, Kit.rgb(0.02, 0.1, 0.8), 0.45)
	local moon = Kit.part(ctx.folder, { Shape = Enum.PartType.Cylinder, Size = Vector3.new(0.2, 3.2, 3.2), Color = Kit.rgb(0.55, 0.75, 1) })
	moon.CFrame = ctx:at(-2.4, 5, 3.4) * CFrame.Angles(0, math.rad(90), 0)
	ctx:light({ 2, -3, 3.5 }, Kit.rgb(0.5, 0.7, 1), 3, 12)
	ctx:light({ -2.2, 1.5, 3.4 }, Kit.rgb(0.4, 0.6, 1), 4, 10)
	ctx:camera("S10", 38, {
		{ 2.40, { 0.9, -4.0, 2.55 }, { 0, 0, 2.6 }, 6 },
		{ 2.72, { 0.6, -3.4, 2.6 }, { 0, 0, 2.65 }, 2 },
	})
end

-- 2.72 Dash through a cube field
function Sets.S11(ctx)
	local rng = Random.new(11)
	ctx:enclose({ 0, 40, 2 }, 140)
	local cols = { Kit.rgb(0.03, 0.06, 0.16), Kit.rgb(0.1, 0.35, 1), Kit.ICE }
	for _ = 1, ctx:n(150) do
		local s = rng:NextNumber(0.3, 1.6)
		local roll = rng:NextNumber()
		local col = roll < 0.6 and cols[1] or (roll < 0.9 and cols[2] or cols[3])
		ctx:box({ s, s, s }, { rng:NextNumber(-9, 9), 40 + rng:NextNumber(-40, 40), 2 + rng:NextNumber(-6, 6) }, col, col == cols[1] and Enum.Material.Metal or Enum.Material.Neon, { rng:NextNumber(0, 90), rng:NextNumber(0, 90), rng:NextNumber(0, 90) })
	end
	local av = ctx:actor("dark")
	av:key(2.72, P("fly"), Vector3.new(0.3, 10, 1.8), { 0, 0, 180 })
	av:key(2.83, P("fly"), Vector3.new(0, 34, 2.2), { 0, 0, 180 })
	ctx:light({ 0, 30, 2 }, Kit.rgb(0.4, 0.6, 1), 6, 60)
	ctx:camera("S11", 20, {
		{ 2.72, { 0, 0, 2 }, { 0, 40, 2 }, 0 },
		{ 2.83, { 0, 24, 2.3 }, { 0, 64, 2.3 }, 12 },
	})
end

-- 2.83 White-blue flash explosion with radial rays
function Sets.S12(ctx)
	local rng = Random.new(12)
	ctx:enclose({ 0, 10, 0 }, 120)
	local core = ctx:ballAt({ 0, 10, 0 }, 1, Kit.ICE)
	local cs = Kit.track({ { 2.83, 0.8 }, { 2.92, 7, "ease" }, { 3.0, 4 } })
	ctx:onUpdate(function(t)
		core.Size = Vector3.one * cs(t)
	end)
	local items = {}
	for k = 1, ctx:n(36) do
		local a = rng:NextNumber(0, 360)
		local ln = rng:NextNumber(8, 26)
		local w = rng:NextNumber(0.06, 0.3)
		local st = rng:NextNumber(0.5, 3)
		local ray = Kit.part(ctx.folder, { Size = Vector3.new(w, ln, 0.05), Color = (k % 2 == 0) and Kit.rgb(0.45, 0.72, 1) or Kit.rgb(0.05, 0.3, 1), Transparency = 0.1 })
		table.insert(items, { ray, CFrame.Angles(0, 0, math.rad(a)) * CFrame.new(0, st + ln / 2, rng:NextNumber(-1, 1)), ray.Size })
	end
	local rs = Kit.track({ { 2.83, 0.3 }, { 2.95, 1.2, "ease" } })
	local rr = Kit.track({ { 2.83, 0 }, { 3.0, 18 } })
	group(ctx, function(t)
		return ctx:at(0, 10, 0, 0, rr(t), 0)
	end, rs, items)
	ctx:plate(80, 50, { 0, 30, 0 }, Kit.rgb(0.03, 0.2, 1), 0)
	for _ = 1, ctx:n(30) do
		local s = rng:NextNumber(0.15, 0.6)
		ctx:box({ s, s, s }, { rng:NextNumber(-7, 7), 8 + rng:NextNumber(-3, 3), rng:NextNumber(-4, 4) }, Kit.ICE, nil, { rng:NextNumber(0, 90), rng:NextNumber(0, 90), 0 })
	end
	ctx:camera("S12", 24, {
		{ 2.83, { 0, -6, 0 }, { 0, 10, 0 }, 0 },
		{ 3.0, { 0, -3, 0 }, { 0, 10, 0 }, -6 },
	}, { 2.83, 3.0, 0.15, 2, 1 })
end

-- 3.00 Hyperspace streaks
function Sets.S13(ctx)
	local rng = Random.new(13)
	ctx:enclose({ 0, 70, 0 }, 380)
	local cols = { Kit.rgb(0.03, 0.08, 0.3), Kit.rgb(0.1, 0.35, 1), Kit.rgb(0.6, 0.8, 1), Kit.rgb(0.05, 0.15, 0.6) }
	for _ = 1, ctx:n(120) do
		local a = rng:NextNumber(0, 2 * math.pi)
		local r = rng:NextNumber(1.6, 14)
		local ln = rng:NextNumber(6, 40)
		local th = rng:NextNumber(0.15, 1.6) * (r / 8 + 0.3)
		local y0 = rng:NextNumber(0, 160)
		local dy = rng:NextNumber(70, 110)
		local roll = rng:NextNumber()
		local col = roll < 0.55 and cols[1] or cols[rng:NextInteger(2, 4)]
		local b = ctx:box({ th, ln, th * rng:NextNumber(0.3, 1) }, { math.cos(a) * r, y0, math.sin(a) * r }, col, roll < 0.55 and Enum.Material.Metal or Enum.Material.Neon, { 0, -math.deg(a), 0 })
		local cf0 = b.CFrame
		local off = V(0, -dy, 0)
		ctx:mover(b, function(t)
			return cf0 + off * Kit.prog(t, 3.0, 3.47)
		end)
	end
	local star = Kit.star(ctx.folder, Kit.WHITE)
	local base = { Vector3.new(0.12, 2, 0.05), Vector3.new(2, 0.12, 0.05), Vector3.one * 0.35 }
	local ss = Kit.track({ { 3.0, 2 }, { 3.1, 6 }, { 3.2, 3 }, { 3.3, 7 }, { 3.4, 4 }, { 3.47, 8 } })
	local sp = ctx:at(0, 60, 0)
	ctx:onUpdate(function(t)
		local s = ss(t)
		for i, p in star do
			p.Size = Vector3.new(math.max(base[i].X * s, 0.05), math.max(base[i].Y * s, 0.05), 0.05)
			p.CFrame = sp
		end
	end)
	ctx:ballAt({ 0, 70, 0 }, 6, Kit.rgb(0.7, 0.85, 1))
	ctx:plate(200, 200, { 0, 160, 0 }, Kit.rgb(0.0, 0.04, 0.3), 0)
	ctx:camera("S13", 22, {
		{ 3.0, { 0, -4, 0 }, { 0, 60, 0 }, 0 },
		{ 3.47, { 0, 4, 0 }, { 0, 60, 0 }, 25 },
	})
end

-- 3.47 Crescent flare, fade to dark
function Sets.S14(ctx)
	local rng = Random.new(14)
	ctx:enclose({ 0, 20, 0 }, 100)
	local cp, co = Kit.crescent(ctx.folder, 1.0, Kit.WHITE)
	local items = ringItems(cp, co, CFrame.Angles(0, 0, math.rad(90)))
	local sc = Kit.track({ { 3.47, 0.4 }, { 3.52, 1.3, "ease" }, { 3.62, 0.1 } })
	group(ctx, function()
		return ctx:at(0, 20, 0)
	end, sc, items)
	local rays = {}
	for _ = 1, ctx:n(30) do
		local ln = rng:NextNumber(10, 30)
		local ray = Kit.part(ctx.folder, { Size = Vector3.new(rng:NextNumber(0.05, 0.35), ln, 0.05), Color = Kit.rgb(0.1, 0.35, 1), Transparency = 0.2 })
		table.insert(rays, { ray, CFrame.Angles(0, 0, math.rad(rng:NextNumber(0, 360))) * CFrame.new(0, ln / 2, 0.5), ray.Size })
	end
	local rs = Kit.track({ { 3.47, 1 }, { 3.62, 0.3 } })
	local rr = Kit.track({ { 3.47, 0 }, { 3.62, -25 } })
	group(ctx, function(t)
		return ctx:at(0, 20, 0, 0, rr(t), 0)
	end, rs, rays)
	ctx:camera("S14", 30, {
		{ 3.47, { 0, 0, 0 }, { 0, 20, 0 }, 0 },
		{ 3.62, { 0, 2, 0 }, { 0, 20, 0 }, 8 },
	})
end

-- 3.62 Flight through the block tunnel toward the glowing core
function Sets.S15(ctx)
	local rng = Random.new(15)
	ctx:enclose({ 0, 70, 0 }, 400)
	local wallCols = { Kit.rgb(0.02, 0.035, 0.1), Kit.rgb(0.03, 0.06, 0.16), Kit.rgb(0.02, 0.05, 0.13) }
	local Rr = 9
	for _ = 1, ctx:n(350) do
		local y = rng:NextNumber(-10, 150)
		local side = rng:NextInteger(0, 3)
		local u = rng:NextNumber(-Rr, Rr)
		local inset = rng:NextNumber(0, 1.6)
		local sz = { rng:NextNumber(1, 3), rng:NextNumber(1, 5), rng:NextNumber(1, 3) }
		local p
		if side == 0 then
			p = { u, y, -Rr + inset }
		elseif side == 1 then
			p = { u, y, Rr - inset }
		elseif side == 2 then
			p = { -Rr + inset, y, u }
		else
			p = { Rr - inset, y, u }
		end
		if rng:NextNumber() < 0.07 then
			ctx:box(sz, p, Kit.rgb(0.05, 0.25, 1))
		else
			ctx:box(sz, p, wallCols[rng:NextInteger(1, 3)], Enum.Material.Metal)
		end
	end
	ctx:ballAt({ 0, 120, 0 }, 10, Kit.ICE)
	ctx:ballAt({ 0, 120, 0 }, 22, Kit.rgb(0.1, 0.35, 1), 0.7)
	ctx:plate(60, 60, { 0, 135, 0 }, Kit.rgb(0.05, 0.3, 1), 0)
	local dp, doff = Kit.squareRing(ctx.folder, 22, 0.6, Kit.rgb(0.6, 0.8, 1))
	local drot = Kit.track({ { 3.62, 45 }, { 6.0, 110 } })
	group(ctx, function(t)
		return ctx:at(0, 112, 0, 0, drot(t), 0)
	end, function()
		return 1
	end, ringItems(dp, doff))
	-- shards around the core
	for _ = 1, ctx:n(50) do
		local a = rng:NextNumber(0, 2 * math.pi)
		local r = rng:NextNumber(5, 12)
		local s = rng:NextNumber(0.3, 1.4)
		local glow = rng:NextNumber() < 0.5
		local c = Kit.part(ctx.folder, { Size = Vector3.one * s, Color = glow and Kit.ICE or Kit.rgb(0.03, 0.05, 0.16), Material = glow and Enum.Material.Neon or Enum.Material.Metal })
		local pos = ctx:at(math.cos(a) * r, 120 + rng:NextNumber(-6, 4), math.sin(a) * r).Position
		local rx, ry = rng:NextNumber(0, 6), rng:NextNumber(0, 6)
		ctx:mover(c, function(t)
			local f = Kit.prog(t, 3.62, 6.0)
			return CFrame.new(pos) * CFrame.Angles(rx + 3 * f, ry + 2 * f, 0)
		end)
	end
	-- floating debris along the path
	for _ = 1, ctx:n(80) do
		local p0 = ctx:at(rng:NextNumber(-7, 7), rng:NextNumber(0, 110), rng:NextNumber(-7, 7)).Position
		local d = V(rng:NextNumber(-1, 1), rng:NextNumber(-3, 0), rng:NextNumber(-1, 1))
		local s = rng:NextNumber(0.1, 0.5)
		local glow = rng:NextNumber() < 0.3
		local c = Kit.part(ctx.folder, { Size = Vector3.one * s, Color = glow and Kit.rgb(0.3, 0.55, 1) or Kit.rgb(0.03, 0.04, 0.1), Material = glow and Enum.Material.Neon or Enum.Material.Metal })
		local rx = rng:NextNumber(0, 6)
		ctx:mover(c, function(t)
			local f = Kit.prog(t, 3.62, 6.0)
			return CFrame.new(p0 + d * f) * CFrame.Angles(rx * f, rx, 0)
		end)
	end
	-- energy wisps swirling around the flight path
	local items = {}
	for k = 1, ctx:n(24) do
		local y0 = rng:NextNumber(15, 110)
		local r = rng:NextNumber(3.8, 5.6)
		local a0 = rng:NextNumber(0, 2 * math.pi)
		local col = (k % 3 == 0) and Kit.rgb(0.4, 0.65, 1) or Kit.rgb(0.05, 0.25, 1)
		local th = rng:NextNumber(0.06, 0.25)
		local prev
		for j = 0, 12 do
			local a = a0 + j * 0.3
			local p = V(math.cos(a) * r, y0 + j * rng:NextNumber(0.5, 1.1), math.sin(a) * r + math.sin(j * 0.5) * 0.4)
			if prev then
				local seg = Kit.part(ctx.folder, { Size = Vector3.new(th, th * 0.4, (p - prev).Magnitude + 0.05), Color = col, Transparency = 0.15 })
				table.insert(items, { seg, CFrame.lookAt((p + prev) / 2, p), seg.Size })
			end
			prev = p
		end
	end
	local swirl = Kit.track({ { 3.62, 0 }, { 6.0, -220 } })
	group(ctx, function(t)
		return ctx:at(0, 0, 0, 0, swirl(t), 0)
	end, function()
		return 1
	end, items)
	-- the flyer
	local av = ctx:actor("dark")
	local path = {
		{ 3.62, Vector3.new(-1.5, 8, -1), "fly", { 0, 0, 180 } },
		{ 4.4, Vector3.new(-0.5, 34, -0.2), "fly2", { 0, 14, 180 } },
		{ 5.2, Vector3.new(0.4, 60, 0.4), "fly", { 0, -10, 175 } },
		{ 6.0, Vector3.new(0, 86, 0), "fly2", { 0, 6, 182 } },
	}
	for _, k in path do
		av:key(k[1], P(k[3]), k[2], k[4])
	end
	local torso = av.model:FindFirstChild("Torso") or av.model:FindFirstChild("UpperTorso")
	if torso and torso:IsA("BasePart") then
		for _, off in { { -0.6, 0 }, { 0.6, 0 }, { 0, 0.8 } } do
			local tr = Kit.part(ctx.folder, { Size = Vector3.new(0.1, 7, 0.05), Color = Kit.rgb(0.15, 0.4, 1), Transparency = 0.25 })
			ctx:mover(tr, function()
				return torso.CFrame * CFrame.new(off[1], -4 + off[2], 0.3)
			end)
		end
	end
	for k = 0, 6 do
		ctx:light({ rng:NextNumber(-3, 3), 8 + k * 15, rng:NextNumber(-3, 3) }, Kit.rgb(0.1, 0.3, 1), 3, 50)
	end
	ctx:light({ 0, 110, 0 }, Kit.rgb(0.45, 0.65, 1), 10, 60)
	-- follow-cam locked to the flight path
	local keys = { { 3.62, { -4.0, -4, 2.2 }, { 0, 40, -0.5 }, -10, "ease" } }
	local offs = { { -3.4, -7, 1.6 }, { -3.0, -7.5, 1.2 }, { -2.6, -8, 1.0 } }
	local looks = { { 1.5, 25, -0.5 }, { 1.0, 28, -0.4 }, { 0.0, 34, 0.0 } }
	local rolls = { -8, 6, 14 }
	for i = 2, 4 do
		local pos = path[i][2]
		local o, l = offs[i - 1], looks[i - 1]
		table.insert(keys, { path[i][1], { pos.X + o[1], pos.Y + o[2], pos.Z + o[3] }, { pos.X + l[1], pos.Y + l[2], pos.Z + l[3] }, rolls[i - 1], "ease" })
	end
	ctx:camera("S15", 26, keys, { 3.62, 6.0, 0.06, 0.6, 2 })
end

-- 6.00 Final slash
function Sets.S16(ctx)
	local rng = Random.new(16)
	ctx:enclose({ 0, 10, 0 }, 120)
	for _ = 1, ctx:n(30) do
		ctx:box({ rng:NextNumber(2, 6), rng:NextNumber(2, 6), rng:NextNumber(2, 10) }, { rng:NextNumber(-20, 20), rng:NextNumber(10, 30), rng:NextNumber(-8, 10) }, Kit.rgb(0.05, 0.1, 0.25), Enum.Material.Metal)
		ctx:box({ 0.1, 0.1, rng:NextNumber(2, 8) }, { rng:NextNumber(-20, 20), rng:NextNumber(9, 20), rng:NextNumber(-8, 10) }, Kit.rgb(0.3, 0.55, 1))
	end
	local vline = ctx:box({ 0.12, 0.05, 40 }, { 0.5, 4, 0 }, Kit.rgb(1, 0.6, 0.9), nil, { 0, -12, 0 })
	local vglow = ctx:box({ 1.2, 0.05, 40 }, { 0.5, 4.1, 0 }, Kit.PINK, nil, { 0, -12, 0 }, 0.55)
	local vh = Kit.track({ { 6.0, 0 }, { 6.06, 1, "ease" }, { 6.4, 1 } })
	local vw = Kit.track({ { 6.0, 1 }, { 6.06, 1 }, { 6.4, 2.5 } })
	local vcf, gcf = vline.CFrame, vglow.CFrame
	ctx:onUpdate(function(t)
		local h, w = vh(t), vw(t)
		vline.Size = Vector3.new(0.12 * w, math.max(40 * h, 0.05), 0.05)
		vglow.Size = Vector3.new(1.2 * w, math.max(40 * h, 0.05), 0.05)
		vline.CFrame, vglow.CFrame = vcf, gcf
		vline.Transparency = h < 0.01 and 1 or 0
		vglow.Transparency = h < 0.01 and 1 or 0.55
	end)
	local beamCF = ctx:at(0, 6, -0.6, 0, 0, -8)
	local beam = Kit.part(ctx.folder, { Shape = Enum.PartType.Cylinder, Size = Vector3.new(1, 1, 1), CFrame = beamCF, Color = Kit.ICE })
	local halo = Kit.part(ctx.folder, { Shape = Enum.PartType.Cylinder, Size = Vector3.new(1, 1, 1), CFrame = beamCF, Color = Kit.rgb(0.05, 0.3, 1), Transparency = 0.55 })
	for _, b in { { beam, 0.45 }, { halo, 1.3 } } do
		local w = Kit.track({ { 6.05, 0 }, { 6.15, b[2] * 2, "ease" }, { 6.4, b[2] * 3.6 } })
		local l = Kit.track({ { 6.05, 0 }, { 6.15, 70, "ease" }, { 6.4, 80 } })
		ctx:onUpdate(function(t)
			local d = w(t)
			b[1].Size = Vector3.new(math.max(l(t), 0.05), math.max(d, 0.05), math.max(d, 0.05))
			b[1].CFrame = beamCF
			b[1].Transparency = d < 0.01 and 1 or (b[1] == beam and 0 or 0.55)
		end)
	end
	for _ = 1, ctx:n(60) do
		local from = ctx:at(0.5, 5, 0).Position
		local to = ctx:at(rng:NextNumber(-12, 12), rng:NextNumber(0, 14), rng:NextNumber(-8, 8)).Position
		local glow = rng:NextNumber() < 0.5
		local c = Kit.part(ctx.folder, { Size = Vector3.one * rng:NextNumber(0.1, 0.6), Color = glow and Kit.ICE or Kit.rgb(0.03, 0.04, 0.1), Material = glow and Enum.Material.Neon or Enum.Material.Metal, Transparency = 1 })
		local spin = rng:NextNumber(0, 6)
		ctx:onUpdate(function(t)
			local f = Kit.prog(t, 6.05, 6.4)
			c.Transparency = t < 6.05 and 1 or 0
			c.CFrame = CFrame.new(from:Lerp(to, 1 - (1 - f) ^ 2)) * CFrame.Angles(spin * f, spin, 0)
		end)
	end
	local av = ctx:actor("dark")
	av:key(6.0, P("slash"), Vector3.new(-7, 3, -1), { 0, 0, -100 })
	av:key(6.12, P("slash", { armR = { -80, 0, -60 } }), Vector3.new(4, 4, -0.5), { 0, 0, -90 })
	av:key(6.4, P("slash", { armR = { -70, 0, -80 } }), Vector3.new(7, 5, -0.3), { 0, 0, -85 })
	ctx:light({ 0.5, 3, 0 }, Kit.rgb(0.6, 0.75, 1), 8, 30)
	ctx:light({ 0.5, 2, 2 }, Kit.rgb(1, 0.4, 0.8), 5, 20)
	ctx:camera("S16", 22, {
		{ 6.0, { -1.5, -9, 0.5 }, { 0.5, 6, 0 }, 14 },
		{ 6.4, { -0.5, -6, 0.2 }, { 0.5, 6, 0 }, 22 },
	}, { 6.05, 6.4, 0.25, 3, 1 })
end

-- 6.40 IMPACT FRAMES finale
local IMPACT_SEQ = { -- {time, invert, red}
	{ 6.40, 1, 0 }, { 6.4667, 0, 0 }, { 6.5333, 1, 0 }, { 6.60, 0, 1 }, { 6.6667, 1, 0 },
	{ 6.7333, 0, 0 }, { 6.80, 1, 0 }, { 6.8667, 0, 1 }, { 6.9333, 0, 0 },
}
Shots.IMPACT_END = 7.20

function Sets.S17(ctx)
	local rng = Random.new(17)
	ctx:enclose({ 0, 10, 2 }, 120)
	local av = ctx:actor("dark")
	av:key(6.40, P("thrust", { armR = { -90, 0, 10 } }), Vector3.new(0, 6, 0.4), { 0, 0, -20 })
	av:key(6.80, P("thrust", { armR = { -92, 0, 12 }, torso = { 26, 0, -38 } }), Vector3.new(0, 6, 0.4), { 0, 0, -20 })
	av:key(7.70, P("thrust", { armR = { -94, 0, 14 }, torso = { 28, 0, -40 } }), Vector3.new(0, 6, 0.4), { 0, 0, -20 })
	local bg = ctx:plate(80, 50, { 0, 30, 2 }, Kit.WHITE, 0)
	local dark, light = {}, {}
	local items = {}
	for k = 1, ctx:n(50) do
		local ln = rng:NextNumber(8, 30)
		local w = rng:NextNumber(0.08, 0.7)
		local st = rng:NextNumber(1.5, 4)
		local p = Kit.part(ctx.folder, { Size = Vector3.new(w, ln, 0.05), Material = Enum.Material.SmoothPlastic })
		table.insert(k % 3 == 0 and light or dark, p)
		table.insert(items, { p, CFrame.Angles(0, 0, math.rad(rng:NextNumber(0, 360))) * CFrame.new(0, st + ln / 2, rng:NextNumber(0.5, 6)), p.Size })
	end
	local bs = Kit.track({ { 6.40, 0.6 }, { 6.55, 1.1, "ease" }, { 7.70, 1.3 } })
	local br = Kit.track({ { 6.40, 0 }, { 7.70, 30 } })
	group(ctx, function(t)
		return ctx:at(0.6, 3.5, 2.0, 0, br(t), 0)
	end, bs, items)
	-- shockwave ring
	local ring = {}
	local ringItemsList = {}
	for i = 0, 31 do
		local a0, a1 = i / 32 * 2 * math.pi, (i + 1) / 32 * 2 * math.pi
		local p0 = Vector3.new(math.cos(a0), math.sin(a0), 0)
		local p1 = Vector3.new(math.cos(a1), math.sin(a1), 0)
		local seg = Kit.part(ctx.folder, { Size = Vector3.new(0.07, (p1 - p0).Magnitude + 0.01, 0.05) })
		local up = (p1 - p0).Unit
		table.insert(ring, seg)
		table.insert(ringItemsList, { seg, CFrame.fromMatrix((p0 + p1) / 2, up:Cross(Vector3.zAxis), up), seg.Size })
	end
	group(ctx, function()
		return ctx:at(0.6, 4.5, 2.2)
	end, Kit.track({ { 6.40, 0.2 }, { 6.9, 9, "ease" }, { 7.7, 14 } }), ringItemsList)
	local core = ctx:ballAt({ 0.2, 0.2, 2.3 }, 0.3, Kit.WHITE)
	local cs = Kit.track({ { 6.40, 0.3 }, { 6.5, 0.9, "ease" }, { 7.2, 0.6 }, { 7.35, 2.4 }, { 7.7, 4 } })
	local debris = {}
	for _ = 1, ctx:n(40) do
		local s = rng:NextNumber(0.1, 0.6)
		table.insert(debris, ctx:box({ s, s, s }, { rng:NextNumber(-10, 10), 6 + rng:NextNumber(-6, 6), 2 + rng:NextNumber(-7, 7) }, Kit.WHITE, Enum.Material.SmoothPlastic, { rng:NextNumber(0, 90), rng:NextNumber(0, 90), 0 }))
	end
	local function paint(list: { BasePart }, col: Color3, neon: boolean)
		for _, p in list do
			p.Color = col
			p.Material = neon and Enum.Material.Neon or Enum.Material.SmoothPlastic
		end
	end
	local W, B = Kit.WHITE, Kit.BLACK
	ctx:onUpdate(function(t)
		core.Size = Vector3.one * cs(t)
		if t >= 6.40 and t < Shots.IMPACT_END then
			local inv, red = 0, 0
			for _, s in IMPACT_SEQ do
				if t >= s[1] then
					inv, red = s[2], s[3]
				end
			end
			local fg, bgc = (inv == 1) and W or B, (inv == 1) and B or W
			-- inv 0: white world, black silhouette with white outline. inv 1: the inverse.
			paint({ bg }, bgc, inv == 0)
			paint(dark, fg, inv == 1)
			paint(light, bgc, inv == 0)
			paint(ring, bgc, inv == 0)
			paint(debris, fg, inv == 1)
			paint({ core }, bgc, inv == 0)
			av:setHighlight(fg, 0, bgc, 0)
			ctx.post = { saturation = -1, contrast = 0.8, tint = red == 1 and Kit.rgb(1, 0.18, 0.3) or W, bloom = 0 }
		else
			paint({ bg }, Kit.rgb(0.02, 0.15, 1), true)
			paint(dark, Kit.rgb(0.02, 0.03, 0.1), false)
			paint(light, Kit.ICE, true)
			paint(ring, Kit.ICE, true)
			paint(debris, Kit.rgb(0.03, 0.05, 0.14), false)
			paint({ core }, Kit.ICE, true)
			av:setStyle("dark")
			ctx.post = nil
		end
	end)
	ctx:light({ 1, 2, 3 }, Kit.rgb(0.6, 0.75, 1), 6, 20)
	ctx:light({ -2, 10, 5 }, Kit.rgb(0.3, 0.5, 1), 6, 30)
	ctx:camera("S17", 26, {
		{ 6.40, { 1.6, -3.5, 1.4 }, { 0, 6, 2.3 }, -14 },
		{ 6.80, { 1.4, -4.3, 1.3 }, { 0, 6, 2.3 }, -10 },
		{ 7.70, { 1.2, -5.2, 1.2 }, { 0, 6, 2.3 }, -6 },
	}, { 6.40, 6.85, 0.22, 3.5, 1 })
end

Shots.Sets = Sets

-- shot list: {camera name, start, end, set builder name}
Shots.LIST = {
	{ "S01", 0.00, 0.22, "S01" },
	{ "S02", 0.22, 0.67, "S02" },
	{ "S03", 0.67, 0.83, "S03" },
	{ "S04", 0.83, 0.92, "S02" },
	{ "S05", 0.92, 1.00, "S03" },
	{ "S06", 1.00, 1.47, "S06" },
	{ "S07", 1.47, 1.63, "S07" },
	{ "S08", 1.63, 1.97, "S08" },
	{ "S09", 1.97, 2.40, "S09" },
	{ "S10", 2.40, 2.72, "S10" },
	{ "S11", 2.72, 2.83, "S11" },
	{ "S12", 2.83, 3.00, "S12" },
	{ "S13", 3.00, 3.47, "S13" },
	{ "S14", 3.47, 3.62, "S14" },
	{ "S15", 3.62, 6.00, "S15" },
	{ "S16", 6.00, 6.40, "S16" },
	{ "S17", 6.40, 7.70, "S17" },
}
Shots.SET_ORDER = { "S01", "S02", "S03", "S06", "S07", "S08", "S09", "S10", "S11", "S12", "S13", "S14", "S15", "S16", "S17" }

return Shots
