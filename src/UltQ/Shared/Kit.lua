-- Kit: small helpers shared by the cinematic.
-- All set layouts were designed in Blender (Z-up, character faces -Y). Kit.V / Kit.S / Kit.R
-- convert Blender coordinates to Roblox (Y-up, character faces -Z) so the numbers match
-- ult-blender/ult_build.py one-to-one.

local Kit = {}

-- Blender position (x, y, z) -> Roblox Vector3 (-x, z, y)
function Kit.V(x: number, y: number, z: number): Vector3
	return Vector3.new(-x, z, y)
end

-- Blender box size (sx, sy, sz) -> Roblox Size (sx, sz, sy)
function Kit.S(sx: number, sy: number, sz: number): Vector3
	return Vector3.new(math.max(sx, 0.05), math.max(sz, 0.05), math.max(sy, 0.05))
end

-- Blender Euler XYZ (degrees) -> Roblox rotation CFrame
function Kit.R(a: number?, b: number?, c: number?): CFrame
	return CFrame.fromAxisAngle(Vector3.yAxis, math.rad(c or 0))
		* CFrame.fromAxisAngle(Vector3.zAxis, math.rad(b or 0))
		* CFrame.fromAxisAngle(Vector3.xAxis, -math.rad(a or 0))
end

function Kit.rgb(r: number, g: number, b: number): Color3
	return Color3.new(math.clamp(r, 0, 1), math.clamp(g, 0, 1), math.clamp(b, 0, 1))
end

-- palette (same as the Blender build)
Kit.BLUE = Kit.rgb(0.05, 0.25, 1)
Kit.DEEP = Kit.rgb(0.02, 0.06, 0.35)
Kit.CYAN = Kit.rgb(0.35, 0.65, 1)
Kit.ICE = Kit.rgb(0.78, 0.9, 1)
Kit.PINK = Kit.rgb(1, 0.2, 0.5)
Kit.NAVY = Kit.rgb(0.02, 0.03, 0.08)
Kit.DARK = Kit.rgb(0.03, 0.05, 0.14)
Kit.WHITE = Color3.new(1, 1, 1)
Kit.BLACK = Color3.new(0, 0, 0)
Kit.ORANGE = Kit.rgb(1, 0.45, 0.1)

export type PartProps = {
	Size: Vector3?,
	CFrame: CFrame?,
	Color: Color3?,
	Material: Enum.Material?,
	Transparency: number?,
	Shape: Enum.PartType?,
	Name: string?,
}

function Kit.part(parent: Instance, props: PartProps): Part
	local p = Instance.new("Part")
	p.Anchored = true
	p.CanCollide = false
	p.CanQuery = false
	p.CanTouch = false
	p.CastShadow = false
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.Material = props.Material or Enum.Material.Neon
	p.Color = props.Color or Kit.WHITE
	if props.Shape then
		p.Shape = props.Shape
	end
	p.Size = props.Size or Vector3.one
	p.Transparency = props.Transparency or 0
	p.CFrame = props.CFrame or CFrame.identity
	p.Name = props.Name or "FX"
	p.Parent = parent
	return p
end

-- Ball (sphere) part
function Kit.ball(parent: Instance, cf: CFrame, diameter: number, color: Color3, transparency: number?): Part
	return Kit.part(parent, {
		Shape = Enum.PartType.Ball,
		Size = Vector3.one * math.max(diameter, 0.05),
		CFrame = cf,
		Color = color,
		Transparency = transparency,
	})
end

-- Non-uniform ellipsoid (blades, discs)
function Kit.ellipsoid(parent: Instance, cf: CFrame, size: Vector3, color: Color3): Part
	local p = Kit.part(parent, { Size = Vector3.one, CFrame = cf, Color = color })
	local m = Instance.new("SpecialMesh")
	m.MeshType = Enum.MeshType.Sphere
	m.Scale = size
	m.Parent = p
	return p
end

-- A thin part spanning from a to b (lightning / ribbon / wisp segments)
function Kit.segment(parent: Instance, a: Vector3, b: Vector3, thickness: number, color: Color3, transparency: number?): Part
	local len = (b - a).Magnitude
	return Kit.part(parent, {
		Size = Vector3.new(thickness, thickness * 0.35 + 0.05, math.max(len, 0.05)),
		CFrame = CFrame.lookAt((a + b) / 2, b),
		Color = color,
		Transparency = transparency,
	})
end

-- Square outline made of 4 bars, lying in the Blender XZ plane (facing the camera along Blender Y).
-- Returns the 4 parts and their offsets relative to the ring centre (for animation).
function Kit.squareRing(parent: Instance, size: number, thick: number, color: Color3)
	local h = size / 2 - thick / 2
	local defs = {
		{ Vector3.new(0, h, 0), Vector3.new(size, thick, 0.1) },
		{ Vector3.new(0, -h, 0), Vector3.new(size, thick, 0.1) },
		{ Vector3.new(h, 0, 0), Vector3.new(thick, size, 0.1) },
		{ Vector3.new(-h, 0, 0), Vector3.new(thick, size, 0.1) },
	}
	local parts, offsets = {}, {}
	for _, d in defs do
		local p = Kit.part(parent, { Size = d[2], Color = color })
		table.insert(parts, p)
		table.insert(offsets, CFrame.new(d[1]))
	end
	return parts, offsets
end

-- 4-point star sparkle (two long thin crossed blades + glow ball)
function Kit.star(parent: Instance, color: Color3)
	local a = Kit.part(parent, { Size = Vector3.new(0.12, 2, 0.05), Color = color })
	local b = Kit.part(parent, { Size = Vector3.new(2, 0.12, 0.05), Color = color })
	local c = Kit.ball(parent, CFrame.identity, 0.35, Kit.WHITE)
	return { a, b, c }
end

-- Crescent made of arc segments (outer arc thick in the middle, thin at the tips)
function Kit.crescent(parent: Instance, radius: number, color: Color3, segments: number?)
	local n = segments or 20
	local parts, offsets = {}, {}
	for i = 0, n - 1 do
		local f0, f1 = i / n, (i + 1) / n
		local a0 = math.rad(40 + 280 * f0)
		local a1 = math.rad(40 + 280 * f1)
		local mid = (f0 + f1) / 2
		local thick = radius * 0.45 * math.sin(mid * math.pi) + 0.05
		local p0 = Vector3.new(math.cos(a0), math.sin(a0), 0) * (radius - thick / 2)
		local p1 = Vector3.new(math.cos(a1), math.sin(a1), 0) * (radius - thick / 2)
		local len = (p1 - p0).Magnitude + 0.05
		local p = Kit.part(parent, { Size = Vector3.new(thick, len, 0.1), Color = color })
		local up = (p1 - p0).Unit
		local right = up:Cross(Vector3.zAxis)
		table.insert(parts, p)
		table.insert(offsets, CFrame.fromMatrix((p0 + p1) / 2, right, up))
	end
	return parts, offsets
end

-- PointLight on an invisible anchor
function Kit.light(parent: Instance, cf: CFrame, color: Color3, brightness: number, range: number): PointLight
	local p = Kit.part(parent, { Size = Vector3.one * 0.1, CFrame = cf, Transparency = 1 })
	local l = Instance.new("PointLight")
	l.Color = color
	l.Brightness = brightness
	l.Range = math.min(range, 60)
	l.Shadows = false
	l.Parent = p
	return l
end

------------------------------------------------------------------------- animation ---------
function Kit.lerp(a: any, b: any, f: number): any
	local ty = typeof(a)
	if ty == "number" then
		return a + (b - a) * f
	elseif ty == "Vector3" or ty == "CFrame" or ty == "Color3" then
		return a:Lerp(b, f)
	end
	return if f < 1 then a else b
end

local function smooth(f: number): number
	return f * f * (3 - 2 * f)
end
Kit.smooth = smooth

-- keys = { {time, value, mode?}, ... } sorted by time. mode: "linear" (default), "ease", "const"
function Kit.track(keys: { any }): (number) -> any
	return function(t: number): any
		local first = keys[1]
		if t <= first[1] then
			return first[2]
		end
		for i = 1, #keys - 1 do
			local a, b = keys[i], keys[i + 1]
			if t < b[1] then
				local mode = a[3]
				if mode == "const" then
					return a[2]
				end
				local f = (t - a[1]) / math.max(b[1] - a[1], 1e-6)
				if mode == "ease" then
					f = smooth(f)
				end
				return Kit.lerp(a[2], b[2], f)
			end
		end
		return keys[#keys][2]
	end
end

-- 0..1 progress of t through [t0, t1]
function Kit.prog(t: number, t0: number, t1: number): number
	return math.clamp((t - t0) / (t1 - t0), 0, 1)
end

-- deterministic per-frame noise in [-1, 1]
function Kit.hash(i: number, salt: number): number
	local x = math.sin(i * 12.9898 + salt * 78.233) * 43758.5453
	return (x - math.floor(x)) * 2 - 1
end

return Kit
