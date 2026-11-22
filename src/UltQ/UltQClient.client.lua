-- UltQ client: press Q (or controller Y / the mobile ULT button) to cast.
-- The server owns the cooldown; when it approves, the caster plays the cinematic and everyone
-- else sees the world burst around the caster.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ContextActionService = game:GetService("ContextActionService")

local player = Players.LocalPlayer
local shared = ReplicatedStorage:WaitForChild("UltQShared")
local Config = require(shared:WaitForChild("Config"))
local Cinematic = require(shared:WaitForChild("Cinematic"))
local WorldFx = require(shared:WaitForChild("WorldFx"))
local remote = ReplicatedStorage:WaitForChild("UltQRemote") :: RemoteEvent
local gui = script.Parent :: ScreenGui

local playing = false
local lastRequest = 0

local function onAction(_: string, state: Enum.UserInputState, _: InputObject)
	if state ~= Enum.UserInputState.Begin then
		return Enum.ContextActionResult.Pass
	end
	if playing or os.clock() - lastRequest < 0.4 then
		return Enum.ContextActionResult.Sink
	end
	local char = player.Character
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	if not hum or hum.Health <= 0 then
		return Enum.ContextActionResult.Sink
	end
	lastRequest = os.clock()
	remote:FireServer("cast")
	return Enum.ContextActionResult.Sink
end

ContextActionService:BindAction("UltQ", onAction, Config.MobileButton, Config.Key, Config.GamepadKey)
if Config.MobileButton then
	ContextActionService:SetTitle("UltQ", "ULT")
	ContextActionService:SetPosition("UltQ", UDim2.new(1, -170, 1, -170))
end

remote.OnClientEvent:Connect(function(action: string, caster: Player, cf: CFrame)
	if action ~= "cast" then
		return
	end
	if caster == player then
		if playing then
			return
		end
		local char = player.Character
		if not char then
			return
		end
		playing = true
		local ok, err = pcall(Cinematic.play, char, gui, function()
			playing = false
		end)
		if not ok then
			warn("[UltQ] cinematic failed:", err)
			playing = false
		end
	else
		WorldFx.burst(caster, cf)
	end
end)
