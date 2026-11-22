-- UltQ server / installer.
-- Drop the UltQ model into ServerScriptService. On start this script:
--   * copies the Shared modules to ReplicatedStorage (as "UltQShared") so clients can use them
--   * creates the RemoteEvent "UltQRemote"
--   * gives every player the UltQClient LocalScript (inside a ScreenGui that survives respawns)
--   * owns the cooldown, freezes the caster, and (optionally) deals damage at the impact.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local shared = script:WaitForChild("Shared")
local existing = ReplicatedStorage:FindFirstChild("UltQShared")
if existing then
	existing:Destroy()
end
local sharedCopy = shared:Clone()
sharedCopy.Name = "UltQShared"
sharedCopy.Parent = ReplicatedStorage

local Config = require(sharedCopy:WaitForChild("Config"))

local remote = ReplicatedStorage:FindFirstChild("UltQRemote") :: RemoteEvent?
if not remote then
	local r = Instance.new("RemoteEvent")
	r.Name = "UltQRemote"
	r.Parent = ReplicatedStorage
	remote = r
end
assert(remote)

local clientTemplate = script:WaitForChild("UltQClient")

local function giveClient(player: Player)
	local pg = player:WaitForChild("PlayerGui", 30)
	if not pg or pg:FindFirstChild("UltQ") then
		return
	end
	local gui = Instance.new("ScreenGui")
	gui.Name = "UltQ"
	gui.ResetOnSpawn = false
	gui.IgnoreGuiInset = true
	gui.DisplayOrder = 1000
	gui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
	local ls = clientTemplate:Clone()
	ls.Parent = gui
	gui.Parent = pg
end

Players.PlayerAdded:Connect(giveClient)
for _, p in Players:GetPlayers() do
	task.spawn(giveClient, p)
end

local lastCast: { [Player]: number } = {}

local function damageAround(caster: Player, center: Vector3)
	for _, model in workspace:GetDescendants() do
		if model:IsA("Humanoid") and model.Parent ~= caster.Character and model.Health > 0 then
			local root = model.Parent and model.Parent:FindFirstChild("HumanoidRootPart")
			if root and root:IsA("BasePart") and (root.Position - center).Magnitude <= Config.DamageRadius then
				model:TakeDamage(Config.Damage)
			end
		end
	end
end

remote.OnServerEvent:Connect(function(player: Player, action: any)
	if action ~= "cast" then
		return
	end
	local now = os.clock()
	if lastCast[player] and now - lastCast[player] < Config.Cooldown then
		return
	end
	local char = player.Character
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	local hrp = char and char:FindFirstChild("HumanoidRootPart")
	if not hum or hum.Health <= 0 or not hrp or not hrp:IsA("BasePart") then
		return
	end
	lastCast[player] = now
	remote:FireAllClients("cast", player, hrp.CFrame)

	if Config.LockMovement then
		hrp.Anchored = true
		task.delay(Config.Duration, function()
			if hrp.Parent then
				hrp.Anchored = false
			end
		end)
	end
	if Config.Damage > 0 then
		task.delay(Config.HitTime, function()
			if hrp.Parent then
				damageAround(player, hrp.Position)
			end
		end)
	end
end)

Players.PlayerRemoving:Connect(function(p)
	lastCast[p] = nil
end)
