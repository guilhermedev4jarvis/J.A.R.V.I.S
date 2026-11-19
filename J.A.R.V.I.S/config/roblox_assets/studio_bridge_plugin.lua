--[[
  JARVIS Studio Bridge Plugin
  --------------------------
  Instalação no Roblox Studio:
    1) Abra o Studio → aba Plugins → "Plugins Folder" (ou %LOCALAPPDATA%/Roblox/Plugins no Windows)
    2) Copie este arquivo para a pasta de Plugins como:
         JarvisStudioBridge.lua
       (ou crie um Folder plugin com init.server.lua contendo este código)
    3) Reinicie o Studio. Aparecerá a toolbar "JARVIS Bridge".
    4) No JARVIS: roblox_assist action=bridge_start
    5) Clique "Connect" no plugin e deixe o Studio aberto.

  O plugin faz long-poll em http://127.0.0.1:28859/poll e aplica ops na Workspace
  com ChangeHistoryService (Ctrl+Z). CSG (UnionAsync) e EditableMesh são usados
  quando a API do Studio/experiencia permitir.
]]

local HttpService = game:GetService("HttpService")
local ChangeHistoryService = game:GetService("ChangeHistoryService")
local Workspace = game:GetService("Workspace")
local MaterialService = game:GetService("MaterialService")

local BASE = "http://127.0.0.1:28859"
local running = false
local toolbar = plugin:CreateToolbar("JARVIS Bridge")
local btn = toolbar:CreateButton("Connect", "Long-poll JARVIS bridge", "rbxassetid://6031280882")
btn.ClickableWhenViewportHidden = true

local function notify(msg)
	warn("[JARVIS Bridge] " .. tostring(msg))
end

local function colorFrom(t)
	if typeof(t) == "table" then
		return Color3.fromRGB(t[1] or 163, t[2] or 162, t[3] or 165)
	end
	return Color3.fromRGB(163, 162, 165)
end

local function ensureModel(name)
	local m = Workspace:FindFirstChild(name)
	if m and m:IsA("Model") then
		return m
	end
	if m then
		m:Destroy()
	end
	m = Instance.new("Model")
	m.Name = name or "JarvisModel"
	m.Parent = Workspace
	return m
end

local function makePart(className, props, parent)
	local p = Instance.new(className or "Part")
	p.Anchored = props.Anchored ~= false
	p.Name = props.Name or "Part"
	p.Size = Vector3.new(props.Size[1] or 4, props.Size[2] or 1, props.Size[3] or 4)
	local pos = props.Position or {0, 0, 0}
	local rot = props.Rotation or {0, 0, 0}
	p.CFrame = CFrame.new(pos[1], pos[2], pos[3]) * CFrame.Angles(
		math.rad(rot[1] or 0), math.rad(rot[2] or 0), math.rad(rot[3] or 0)
	)
	if props.Material then
		local ok, mat = pcall(function()
			return Enum.Material[props.Material]
		end)
		if ok and mat then
			p.Material = mat
		end
	end
	if props.Color then
		p.Color = colorFrom(props.Color)
	end
	if props.Transparency then
		p.Transparency = props.Transparency
	end
	if props.CanCollide ~= nil then
		p.CanCollide = props.CanCollide
	end
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.Parent = parent
	return p
end

local function applyCreatePart(op)
	local model = ensureModel(op.model or "JarvisBuild")
	local className = op.className or "Part"
	if className ~= "Part" and className ~= "WedgePart" and className ~= "CornerWedgePart"
		and className ~= "TrussPart" and className ~= "SpawnLocation" then
		className = "Part"
	end
	return makePart(className, op, model)
end

local function applyBuildStructure(op)
	-- High-level structure: expand to parts locally (mirror of JARVIS templates)
	local kind = op.structure or "box"
	local modelName = op.model or ("Jarvis_" .. tostring(kind))
	local model = ensureModel(modelName)
	-- clear previous children
	for _, ch in ipairs(model:GetChildren()) do
		ch:Destroy()
	end
	local W = op.width or 24
	local H = op.height or 12
	local D = op.depth or 24
	local origin = op.origin or {0, 0, 0}
	local ox, oy, oz = origin[1], origin[2], origin[3]
	local color = op.color or {163, 162, 165}
	local mat = op.material or "Concrete"
	local t = 1

	local function add(name, size, pos, className)
		return makePart(className or "Part", {
			Name = name,
			Size = size,
			Position = pos,
			Color = color,
			Material = mat,
		}, model)
	end

	if kind == "box" then
		add("Box", {W, H, D}, {ox, oy + H / 2, oz})
	elseif kind == "platform" then
		add("Platform", {W, t, D}, {ox, oy + t / 2, oz})
	elseif kind == "wall" then
		add("Wall", {W, H, t}, {ox, oy + H / 2, oz})
	elseif kind == "room" then
		add("Floor", {W, t, D}, {ox, oy + t / 2, oz})
		add("Ceiling", {W, t, D}, {ox, oy + H - t / 2, oz})
		add("WallN", {W, H - 2 * t, t}, {ox, oy + H / 2, oz - D / 2 + t / 2})
		add("WallS", {W, H - 2 * t, t}, {ox, oy + H / 2, oz + D / 2 - t / 2})
		add("WallW", {t, H - 2 * t, D - 2 * t}, {ox - W / 2 + t / 2, oy + H / 2, oz})
		add("WallE", {t, H - 2 * t, D - 2 * t}, {ox + W / 2 - t / 2, oy + H / 2, oz})
	elseif kind == "tower" then
		local floors = math.max(1, op.floors or 3)
		for i = 0, floors - 1 do
			local baseY = oy + i * H
			add("Floor_" .. (i + 1), {W, t, D}, {ox, baseY + t / 2, oz})
			add("WallN_" .. (i + 1), {W, H - t, t}, {ox, baseY + H / 2, oz - D / 2 + t / 2})
			add("WallS_" .. (i + 1), {W, H - t, t}, {ox, baseY + H / 2, oz + D / 2 - t / 2})
			add("WallW_" .. (i + 1), {t, H - t, D - 2 * t}, {ox - W / 2 + t / 2, baseY + H / 2, oz})
			add("WallE_" .. (i + 1), {t, H - t, D - 2 * t}, {ox + W / 2 - t / 2, baseY + H / 2, oz})
		end
		add("Roof", {W + 2, t, D + 2}, {ox, oy + floors * H + t / 2, oz})
	elseif kind == "stairs" then
		local steps = math.max(3, math.floor(H))
		local stepH = H / steps
		local stepD = math.max(1.5, D / steps)
		for i = 0, steps - 1 do
			add("Step_" .. (i + 1), {W, stepH, stepD}, {
				ox,
				oy + i * stepH + stepH / 2,
				oz - D / 2 + i * stepD + stepD / 2,
			}, "WedgePart")
		end
	elseif kind == "house" then
		add("Floor", {W, t, D}, {ox, oy + t / 2, oz})
		add("WallN", {W, H, t}, {ox, oy + H / 2, oz - D / 2 + t / 2})
		add("WallS", {W, H, t}, {ox, oy + H / 2, oz + D / 2 - t / 2})
		add("WallW", {t, H, D - 2 * t}, {ox - W / 2 + t / 2, oy + H / 2, oz})
		add("WallE", {t, H, D - 2 * t}, {ox + W / 2 - t / 2, oy + H / 2, oz})
		add("Chimney", {2, H * 0.4, 2}, {ox + W * 0.25, oy + H + 2, oz - D * 0.15})
	elseif kind == "bridge" then
		add("Deck", {W, t, D}, {ox, oy + H, oz})
		local pillars = math.max(2, math.floor(D / 12))
		for i = 0, pillars - 1 do
			local z = oz - D / 2 + (i + 0.5) * (D / pillars)
			add("PillarL_" .. (i + 1), {2, H, 2}, {ox - W / 2 + 2, oy + H / 2, z})
			add("PillarR_" .. (i + 1), {2, H, 2}, {ox + W / 2 - 2, oy + H / 2, z})
		end
	elseif kind == "arena" then
		local R = math.max(W, D) / 2
		add("ArenaFloor", {R * 2, t, R * 2}, {ox, oy + t / 2, oz})
		local segments = 16
		for i = 0, segments - 1 do
			local ang = (i / segments) * math.pi * 2
			local cx = ox + math.cos(ang) * (R - t)
			local cz = oz + math.sin(ang) * (R - t)
			local p = add("Wall_" .. (i + 1), {t, H, (2 * math.pi * R) / segments + 0.5}, {cx, oy + H / 2, cz})
			p.CFrame = CFrame.new(cx, oy + H / 2, cz) * CFrame.Angles(0, -ang, 0)
		end
	elseif kind == "pillar_grid" then
		local cols = math.max(2, math.floor(W / 8))
		local rows = math.max(2, math.floor(D / 8))
		for ix = 0, cols - 1 do
			for iz = 0, rows - 1 do
				local px = ox - W / 2 + (ix + 0.5) * (W / cols)
				local pz = oz - D / 2 + (iz + 0.5) * (D / rows)
				add(string.format("Pillar_%d_%d", ix + 1, iz + 1), {2, H, 2}, {px, oy + H / 2, pz})
			end
		end
		add("Canopy", {W, 1, D}, {ox, oy + H + 0.5, oz})
	else
		add("Box", {W, H, D}, {ox, oy + H / 2, oz})
	end
	return model
end

local function applyUnion(op)
	-- Best-effort CSG. GeometryService:UnionAsync exists in newer Studio builds.
	local model = ensureModel(op.model or "JarvisCSG")
	local names = op.parts or {}
	local parts = {}
	for _, name in ipairs(names) do
		local inst = model:FindFirstChild(name, true)
		if inst and inst:IsA("BasePart") then
			table.insert(parts, inst)
		end
	end
	if #parts < 2 then
		notify("union needs >=2 parts in model")
		return
	end
	local ok, result = pcall(function()
		local gs = game:GetService("GeometryService")
		return gs:UnionAsync(parts[1], {table.unpack(parts, 2)})
	end)
	if ok and result then
		result.Name = op.resultName or "Union"
		result.Parent = model
		if op.destroySources then
			for _, p in ipairs(parts) do
				p:Destroy()
			end
		end
		notify("UnionAsync ok")
	else
		notify("UnionAsync unavailable or failed: " .. tostring(result))
	end
end

local function applyEditableMesh(op)
	-- EditableMesh / AssetService APIs vary by Studio version; best-effort.
	local ok, err = pcall(function()
		local AssetService = game:GetService("AssetService")
		if AssetService.CreateEditableMesh then
			local em = AssetService:CreateEditableMesh()
			-- vertices: {{x,y,z},...}  triangles: {{i,j,k},...} 1-based
			local verts = op.vertices or {}
			local tris = op.triangles or {}
			-- API surface is unstable; store as attributes for newer Studio to consume
			local model = ensureModel(op.model or "JarvisMesh")
			local holder = Instance.new("Folder")
			holder.Name = op.name or "EditableMeshData"
			holder:SetAttribute("VertexCount", #verts)
			holder:SetAttribute("TriangleCount", #tris)
			holder.Parent = model
			-- Also drop a proxy Part so something is visible
			makePart("Part", {
				Name = (op.name or "MeshProxy"),
				Size = op.size or {4, 4, 4},
				Position = op.position or {0, 2, 0},
				Color = op.color or {100, 100, 255},
				Material = "SmoothPlastic",
			}, model)
			notify("EditableMesh data stored (version-dependent API)")
		else
			error("CreateEditableMesh not available")
		end
	end)
	if not ok then
		notify("EditableMesh skipped: " .. tostring(err))
	end
end

local function applyOp(rec)
	local op = rec.op or rec
	local typ = op.type or op.Type
	ChangeHistoryService:SetWaypoint("JARVIS before " .. tostring(typ))
	if typ == "create_part" then
		applyCreatePart(op)
	elseif typ == "build_structure" then
		applyBuildStructure(op)
	elseif typ == "union" then
		applyUnion(op)
	elseif typ == "editable_mesh" then
		applyEditableMesh(op)
	elseif typ == "clear_model" then
		local m = Workspace:FindFirstChild(op.model or "JarvisBuild")
		if m then
			m:Destroy()
		end
	elseif typ == "notify" then
		notify(op.message or "")
	else
		notify("unknown op type: " .. tostring(typ))
	end
	ChangeHistoryService:SetWaypoint("JARVIS after " .. tostring(typ))
end

local function pollOnce()
	local ok, body = pcall(function()
		return HttpService:GetAsync(BASE .. "/poll", true)
	end)
	if not ok then
		return false, body
	end
	local data = HttpService:JSONDecode(body)
	if data and data.ops then
		for _, rec in ipairs(data.ops) do
			local ok2, err = pcall(applyOp, rec)
			if not ok2 then
				notify("op failed: " .. tostring(err))
			end
		end
	end
	return true
end

btn.Click:Connect(function()
	running = not running
	btn:SetActive(running)
	if running then
		notify("Connected to " .. BASE)
		task.spawn(function()
			while running do
				local ok, err = pollOnce()
				if not ok then
					notify("poll error (HttpService enabled? bridge up?): " .. tostring(err))
					task.wait(1.5)
				end
			end
			notify("Disconnected")
		end)
	end
end)

notify("Plugin loaded. Start JARVIS bridge, then press Connect.")
