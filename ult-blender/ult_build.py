"""
ROBLOX ULT — procedural Blender build script (Blender 4.2+ / 5.x)
==================================================================
Shot-for-shot recreation of the reference ult choreography using a Roblox R6
avatar, finished with a black/white impact-frame sequence.

Run it in Blender:  Scripting tab > Open > ult_build.py > Run Script
           or:      blender --background --python ult_build.py -- --out RobloxUlt.blend

Everything is generated: avatar rig, 15 shot sets, cameras (bound to timeline
markers so they cut automatically), lights, VFX meshes, the SFX track in the
sequencer and the compositor (bloom, RGB split, glitch, pink duotone flash,
impact frames, shake, fade).

Change FPS / resolution in the CONFIG block below and re-run to rebuild.
"""
import bpy, bmesh, math, random, os, sys
from mathutils import Vector, Euler, Quaternion, Matrix

# ----------------------------------------------------------------- CONFIG ---
FPS = 30                 # 30 or 60 — every key is placed in seconds, so both work
RES = (1920, 1080)
EEVEE_SAMPLES = 32
SET_SPACING = 400.0      # distance between shot sets (they never see each other)
EMIT = 0.42              # global emission multiplier (overall VFX brightness)
HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
SFX_PATH = os.path.join(HERE, "ult_sfx.wav")

# shot list: (name, start_sec, end_sec)
SHOTS = [
    ("S01_Arena",     0.00, 0.22),
    ("S02_HoloCU",    0.22, 0.67),
    ("S03_Ink",       0.67, 0.83),
    ("S04_GlitchCU",  0.83, 0.92),   # re-uses S02 set
    ("S05_PinkFlash", 0.92, 1.00),   # re-uses S03 set
    ("S06_Clones",    1.00, 1.47),
    ("S07_Rear",      1.47, 1.63),
    ("S08_Tunnel",    1.63, 1.97),
    ("S09_Portal",    1.97, 2.40),
    ("S10_Ribbons",   2.40, 2.72),
    ("S11_Dash",      2.72, 2.83),
    ("S12_Flash",     2.83, 3.00),
    ("S13_Hyper",     3.00, 3.47),
    ("S14_Crescent",  3.47, 3.62),
    ("S15_Flight",    3.62, 6.00),
    ("S16_Slash",     6.00, 6.40),
    ("S17_Impact",    6.40, 7.70),
]
END_TIME = 7.70

# palette
BLUE      = (0.02, 0.10, 1.0)
DEEPBLUE  = (0.01, 0.03, 0.25)
CYAN      = (0.20, 0.50, 1.0)
ICE       = (0.80, 0.92, 1.0)
PINK      = (1.0, 0.18, 0.45)
NAVY      = (0.008, 0.012, 0.04)
BLACK     = (0.01, 0.01, 0.012)
WHITE     = (1, 1, 1)
SKIN      = (0.93, 0.78, 0.66)
HAIR      = (0.86, 0.90, 0.98)
ORANGE    = (1.0, 0.35, 0.06)

# ---------------------------------------------------------------- HELPERS ---
def FR(t):
    return 1 + int(round(t * FPS))

def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.name = "RobloxUlt"
    return sc

def link(coll, ob):
    coll.objects.link(ob)
    return ob

def _channelbag(idblock):
    ad = idblock.animation_data
    if ad is None or ad.action is None:
        return None
    act = ad.action
    if hasattr(act, "layers") and len(act.layers):
        from bpy_extras import anim_utils
        return anim_utils.action_get_channelbag_for_slot(act, ad.action_slot)
    return act  # legacy (<4.4)

def set_interp(idblock, data_path, frame, interp, index=-1):
    cb = _channelbag(idblock)
    if cb is None:
        return
    for fc in cb.fcurves:
        if fc.data_path == data_path and (index < 0 or fc.array_index == index):
            for kp in fc.keyframe_points:
                if abs(kp.co[0] - frame) < 0.01:
                    kp.interpolation = interp
                    if interp == "BEZIER":
                        kp.easing = "AUTO"

def K(owner, path, t, value=None, interp="LINEAR", idblock=None, index=-1):
    """Insert key at time t (seconds). owner may be an object, node socket, etc."""
    if value is not None:
        if index >= 0:
            getattr(owner, path)[index] = value
        else:
            setattr(owner, path, value)
    f = FR(t)
    owner.keyframe_insert(path, frame=f, index=index)
    idb = idblock if idblock is not None else owner.id_data
    full = owner.path_from_id(path) if hasattr(owner, "path_from_id") and owner != idb else path
    set_interp(idb, full, f, interp, index)

def KQ(ob, t, q, interp="LINEAR"):
    ob.rotation_mode = "QUATERNION"
    K(ob, "rotation_quaternion", t, q, interp)

def vis(ob, ranges):
    """Key hide_render so the object only renders inside the given (start,end) ranges."""
    ob.hide_render = True
    ob.keyframe_insert("hide_render", frame=0)
    for a, b in ranges:
        ob.hide_render = False
        ob.keyframe_insert("hide_render", frame=FR(a))
        ob.hide_render = True
        ob.keyframe_insert("hide_render", frame=FR(b))

def new_coll(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c

# --------------------------------------------------------------- MATERIALS --
def _mat(name):
    m = bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    return m, nt, out

def M_emit(name, col, strength=1.0):
    m, nt, out = _mat(name)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*col, 1)
    e.inputs["Strength"].default_value = strength * EMIT
    nt.links.new(e.outputs[0], out.inputs[0])
    m.diffuse_color = (*col, 1)
    return m

def M_pbr(name, col, rough=0.45, metal=0.0, emis=None, emis_str=0.0, coat=0.0):
    m, nt, out = _mat(name)
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    p.inputs["Base Color"].default_value = (*col, 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    if coat and "Coat Weight" in p.inputs:
        p.inputs["Coat Weight"].default_value = coat
    if emis:
        p.inputs["Emission Color"].default_value = (*emis, 1)
        p.inputs["Emission Strength"].default_value = emis_str * EMIT
    nt.links.new(p.outputs[0], out.inputs[0])
    m.diffuse_color = (*col, 1)
    return m

def M_rimlit(name, col, rim_col=CYAN, rim_str=3.0, rough=0.5, metal=0.0):
    """Anime-ish: principled + fresnel rim emission (what gives the blue edge glow)."""
    m, nt, out = _mat(name)
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    p.inputs["Base Color"].default_value = (*col, 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    lw = nt.nodes.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.25
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.55
    ramp.color_ramp.elements[1].position = 0.75
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*rim_col, 1)
    nt.links.new(lw.outputs["Facing"], ramp.inputs[0])
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = rim_str * EMIT
    nt.links.new(ramp.outputs[0], mul.inputs[0])
    nt.links.new(mul.outputs[0], e.inputs["Strength"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(p.outputs[0], add.inputs[0]); nt.links.new(e.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs[0])
    m.diffuse_color = (*col, 1)
    return m

def M_ghost(name, col, alpha=0.5, strength=4.0):
    """Transparent glowing afterimage / hologram body."""
    m, nt, out = _mat(name)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*col, 1)
    e.inputs["Strength"].default_value = strength * EMIT
    lw = nt.nodes.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.35
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value = alpha * 0.45
    mr.inputs["To Max"].default_value = min(1.0, alpha * 1.6)
    nt.links.new(lw.outputs["Facing"], mr.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(mr.outputs[0], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(e.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    _blended(m)
    m.diffuse_color = (*col, alpha)
    return m

def _blended(m):
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try: setattr(m, attr, val)
        except Exception: pass
    try: m.use_backface_culling = False
    except Exception: pass

def M_holo(name, col, strength=6.0):
    """Pixel-block dissolve hologram. Returns (material, dissolve_socket)."""
    m, nt, out = _mat(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    snap = nt.nodes.new("ShaderNodeVectorMath"); snap.operation = "SNAP"
    snap.inputs[1].default_value = (0.18, 0.18, 0.18)
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 2.2; nz.inputs["Detail"].default_value = 2
    val = nt.nodes.new("ShaderNodeValue"); val.label = "Dissolve"; val.outputs[0].default_value = 0.0
    gt = nt.nodes.new("ShaderNodeMath"); gt.operation = "GREATER_THAN"
    nt.links.new(tc.outputs["Object"], snap.inputs[0]); nt.links.new(snap.outputs[0], nz.inputs["Vector"])
    nt.links.new(nz.outputs["Factor"], gt.inputs[0]); nt.links.new(val.outputs[0], gt.inputs[1])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    e = nt.nodes.new("ShaderNodeEmission"); e.inputs["Color"].default_value = (*col, 1)
    lw = nt.nodes.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.3
    mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs["To Min"].default_value = strength * 0.35 * EMIT; mr.inputs["To Max"].default_value = strength * 2 * EMIT
    nt.links.new(lw.outputs["Facing"], mr.inputs["Value"]); nt.links.new(mr.outputs[0], e.inputs["Strength"])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(gt.outputs[0], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(e.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    _blended(m)
    return m, val.outputs[0]

def M_wirecube(name, col, strength=8.0, fill=0.08):
    """Hologram 'data cube': glowing edges, faint fill."""
    m, nt, out = _mat(name)
    wf = nt.nodes.new("ShaderNodeWireframe"); wf.use_pixel_size = False; wf.inputs[0].default_value = 0.08
    e = nt.nodes.new("ShaderNodeEmission"); e.inputs["Color"].default_value = (*col, 1); e.inputs["Strength"].default_value = strength * EMIT
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs["To Min"].default_value = fill
    nt.links.new(wf.outputs[0], mr.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(mr.outputs[0], mix.inputs[0]); nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(e.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    _blended(m)
    return m

def M_streak(name, col, strength=10.0, axis="Z"):
    """Emission that fades to transparent at both ends along local axis (rays, beams, streaks)."""
    m, nt, out = _mat(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.elements[0].position = 0.0; cr.elements[0].color = (0, 0, 0, 1)
    cr.elements[1].position = 1.0; cr.elements[1].color = (0, 0, 0, 1)
    mid = cr.elements.new(0.55); mid.color = (1, 1, 1, 1)
    nt.links.new(sep.outputs[axis], ramp.inputs[0])
    e = nt.nodes.new("ShaderNodeEmission"); e.inputs["Color"].default_value = (*col, 1); e.inputs["Strength"].default_value = strength
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(ramp.outputs[0], mix.inputs[0]); nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(e.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    _blended(m)
    return m

def M_ink(name, col, strength=3.0):
    """Animated ink-splash blob. Returns (mat, threshold_socket, w_socket)."""
    m, nt, out = _mat(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.noise_dimensions = "4D"
    nz.inputs["Scale"].default_value = 2.6; nz.inputs["Detail"].default_value = 8; nz.inputs["Distortion"].default_value = 1.2
    nz.inputs["Roughness"].default_value = 0.65
    nt.links.new(tc.outputs["Generated"], nz.inputs["Vector"])
    gr = nt.nodes.new("ShaderNodeTexGradient"); gr.gradient_type = "SPHERICAL"
    mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Location"].default_value = (-0.5, 0.0, -0.5)
    mp.inputs["Scale"].default_value = (1.0, 0.0, 1.0)
    nt.links.new(tc.outputs["Generated"], mp.inputs[0])
    # spherical gradient expects -1..1 coords
    mp2 = nt.nodes.new("ShaderNodeVectorMath"); mp2.operation = "SCALE"; mp2.inputs["Scale"].default_value = 2.0
    nt.links.new(mp.outputs[0], mp2.inputs[0]); nt.links.new(mp2.outputs[0], gr.inputs[0])
    add = nt.nodes.new("ShaderNodeMath"); add.operation = "MULTIPLY_ADD"
    add.inputs[1].default_value = 0.9
    nt.links.new(nz.outputs["Factor"], add.inputs[0]); nt.links.new(gr.outputs["Factor"], add.inputs[2])
    thr = nt.nodes.new("ShaderNodeValue"); thr.label = "Threshold"; thr.outputs[0].default_value = 1.2
    gt = nt.nodes.new("ShaderNodeMath"); gt.operation = "GREATER_THAN"
    nt.links.new(add.outputs[0], gt.inputs[0]); nt.links.new(thr.outputs[0], gt.inputs[1])
    e = nt.nodes.new("ShaderNodeEmission"); e.inputs["Color"].default_value = (*col, 1); e.inputs["Strength"].default_value = strength
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(gt.outputs[0], mix.inputs[0]); nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(e.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    _blended(m)
    return m, thr.outputs[0], nz.inputs["W"]

def M_gridwall(name, col, line_col=BLUE, scale=1.0, line_str=2.0):
    """Dark sci-fi panel with glowing grid seams."""
    m, nt, out = _mat(name)
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    p.inputs["Base Color"].default_value = (*col, 1); p.inputs["Roughness"].default_value = 0.25; p.inputs["Metallic"].default_value = 0.6
    tc = nt.nodes.new("ShaderNodeTexCoord")
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Scale"].default_value = scale; br.inputs["Mortar Size"].default_value = 0.012
    br.inputs["Color1"].default_value = (0, 0, 0, 1); br.inputs["Color2"].default_value = (0, 0, 0, 1)
    br.inputs["Mortar"].default_value = (1, 1, 1, 1)
    br.offset = 0.0
    nt.links.new(tc.outputs["Object"], br.inputs["Vector"])
    p.inputs["Emission Color"].default_value = (*line_col, 1)
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = line_str * EMIT
    nt.links.new(br.outputs["Color"], mul.inputs[0]); nt.links.new(mul.outputs[0], p.inputs["Emission Strength"])
    nt.links.new(p.outputs[0], out.inputs[0])
    return m

# ------------------------------------------------------------------ MESHES --
_mesh_cache = {}

def mesh_box(size, offset=(0, 0, 0)):
    key = ("box", tuple(round(s, 4) for s in size), tuple(round(o, 4) for o in offset))
    if key in _mesh_cache:
        return _mesh_cache[key]
    sx, sy, sz = (s / 2 for s in size)
    ox, oy, oz = offset
    v = [(ox + x * sx, oy + y * sy, oz + z * sz) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    me = bpy.data.meshes.new("box")
    me.from_pydata(v, [], f); me.update()
    _mesh_cache[key] = me
    return me

def obj(name, me, coll, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), mat=None, parent=None):
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    if parent:
        o.parent = parent
    o.location = loc; o.rotation_euler = [math.radians(a) for a in rot]; o.scale = scale
    if mat is not None and me is not None:
        if len(o.material_slots) == 0:
            o.data.materials.append(None) if len(o.data.materials) == 0 else None
        o.material_slots[0].link = "OBJECT"
        o.material_slots[0].material = mat
    return o

def box(name, coll, size, loc=(0, 0, 0), mat=None, parent=None, offset=(0, 0, 0), rot=(0, 0, 0), bevel=0.0):
    o = obj(name, mesh_box(size, offset), coll, loc, rot, mat=mat, parent=parent)
    if bevel > 0:
        b = o.modifiers.new("Bevel", "BEVEL"); b.width = bevel; b.segments = 3; b.limit_method = "NONE"
    return o

def empty(name, coll, loc=(0, 0, 0), parent=None, size=0.5):
    e = bpy.data.objects.new(name, None); coll.objects.link(e)
    e.empty_display_size = size
    if parent: e.parent = parent
    e.location = loc
    return e

def mesh_from(name, verts, faces):
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update(); return me

def mesh_cyl(r, depth, segs=24, offset=(0, 0, 0)):
    key = ("cyl", r, depth, segs, offset)
    if key in _mesh_cache: return _mesh_cache[key]
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=r, radius2=r, depth=depth)
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector(offset))
    me = bpy.data.meshes.new("cyl"); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    _mesh_cache[key] = me
    return me

def mesh_sphere(r, segs=24, rings=12):
    key = ("sph", r, segs, rings)
    if key in _mesh_cache: return _mesh_cache[key]
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=r)
    me = bpy.data.meshes.new("sph"); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    _mesh_cache[key] = me
    return me

def mesh_plane(w, h, offset=(0, 0, 0)):
    """Plane in XZ (facing -Y)."""
    key = ("pl", w, h, offset)
    if key in _mesh_cache: return _mesh_cache[key]
    ox, oy, oz = offset
    v = [(ox - w / 2, oy, oz - h / 2), (ox + w / 2, oy, oz - h / 2), (ox + w / 2, oy, oz + h / 2), (ox - w / 2, oy, oz + h / 2)]
    me = mesh_from("plane", v, [(0, 1, 2, 3)])
    _mesh_cache[key] = me
    return me

def mesh_square_ring(size, thick):
    """Square outline in XZ plane."""
    key = ("ring", size, thick)
    if key in _mesh_cache: return _mesh_cache[key]
    a = size / 2; b = a - thick
    v = [(-a, 0, -a), (a, 0, -a), (a, 0, a), (-a, 0, a), (-b, 0, -b), (b, 0, -b), (b, 0, b), (-b, 0, b)]
    f = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me = mesh_from("ring", v, f); _mesh_cache[key] = me
    return me

def mesh_annulus(r_in, r_out, n=64):
    """Flat ring in XZ plane (facing -Y)."""
    key = ("ann", r_in, r_out, n)
    if key in _mesh_cache: return _mesh_cache[key]
    v = []
    for i in range(n):
        a = 2 * math.pi * i / n
        v += [(math.cos(a) * r_in, 0, math.sin(a) * r_in), (math.cos(a) * r_out, 0, math.sin(a) * r_out)]
    f = [(2 * i, 2 * ((i + 1) % n), 2 * ((i + 1) % n) + 1, 2 * i + 1) for i in range(n)]
    me = mesh_from("annulus", v, f); _mesh_cache[key] = me
    return me

def mesh_star4(r, inner=0.12):
    key = ("star", r, inner)
    if key in _mesh_cache: return _mesh_cache[key]
    v = [(0, 0, 0)]
    for i in range(8):
        a = math.pi / 2 * (i / 2)
        rr = r if i % 2 == 0 else r * inner
        a = i * math.pi / 4
        v.append((math.cos(a) * rr, 0, math.sin(a) * rr))
    f = [(0, 1 + i, 1 + (i + 1) % 8) for i in range(8)]
    me = mesh_from("star4", v, f); _mesh_cache[key] = me
    return me

def mesh_crescent(r, cut_off=0.42, cut_r=0.86, n=48):
    """Crescent moon in XZ plane (opening to +X)."""
    key = ("cres", r)
    if key in _mesh_cache: return _mesh_cache[key]
    cx = cut_off * r; cr = cut_r * r
    # intersection angles of the two circles
    # x^2+z^2=r^2 ; (x-cx)^2+z^2=cr^2 -> x = (r^2 - cr^2 + cx^2)/(2cx)
    xi = (r * r - cr * cr + cx * cx) / (2 * cx)
    zi = math.sqrt(max(r * r - xi * xi, 1e-6))
    a0 = math.atan2(zi, xi)
    outer = [(r * math.cos(a), 0, r * math.sin(a)) for a in [a0 + (2 * math.pi - 2 * a0) * i / n for i in range(n + 1)]]
    b0 = math.atan2(zi, xi - cx)
    inner = [(cx + cr * math.cos(a), 0, cr * math.sin(a)) for a in [-b0 + (2 * b0 - 2 * math.pi) * -i / n for i in range(1, n)]]
    inner = [(cx + cr * math.cos(a), 0, cr * math.sin(a)) for a in [(2 * math.pi - b0) - (2 * math.pi - 2 * b0) * i / n for i in range(1, n)]]
    verts = outer + inner
    bm = bmesh.new()
    bv = [bm.verts.new(p) for p in verts]
    face = bm.faces.new(bv)
    bmesh.ops.triangulate(bm, faces=[face], quad_method="BEAUTY", ngon_method="EAR_CLIP")
    me = bpy.data.meshes.new("crescent"); bm.to_mesh(me); bm.free()
    _mesh_cache[key] = me
    return me

def mesh_diamond(length, width, depth, back=0.25):
    """Spear head: elongated octahedron along +Z."""
    v = [(0, 0, length), (width, 0, 0), (0, depth, 0), (-width, 0, 0), (0, -depth, 0), (0, 0, -back * length)]
    f = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1), (5, 2, 1), (5, 3, 2), (5, 4, 3), (5, 1, 4)]
    return mesh_from("diamond", v, f)

def curve_obj(name, coll, pts, mat, bevel=0.02, extrude=0.0, cyclic=False, taper=None):
    cu = bpy.data.curves.new(name, "CURVE"); cu.dimensions = "3D"
    cu.bevel_depth = bevel; cu.extrude = extrude; cu.bevel_resolution = 2
    sp = cu.splines.new("POLY"); sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (p[0], p[1], p[2], 1)
        if taper:
            sp.points[i].radius = taper(i / max(1, len(pts) - 1))
    sp.use_cyclic_u = cyclic
    o = bpy.data.objects.new(name, cu); coll.objects.link(o)
    cu.materials.append(mat)
    return o

def lightning_pts(p0, p1, segs, jitter, rng):
    p0 = Vector(p0); p1 = Vector(p1); d = p1 - p0
    side = d.orthogonal().normalized(); side2 = d.cross(side).normalized()
    pts = []
    for i in range(segs + 1):
        f = i / segs
        j = 0 if i in (0, segs) else jitter * math.sin(f * math.pi)
        pts.append(p0 + d * f + side * rng.uniform(-j, j) + side2 * rng.uniform(-j, j) * 0.5)
    return pts

def look_quat(cam_loc, target, roll_deg=0.0):
    d = (Vector(target) - Vector(cam_loc))
    q = d.to_track_quat("-Z", "Y")
    if roll_deg:
        q = q @ Quaternion((0, 0, 1), math.radians(roll_deg))
    return q

# ------------------------------------------------------------- CAMERA RIG --
class Cam:
    """Empty 'dolly' carries the move; child camera carries shake."""
    def __init__(self, name, coll, lens=35, clip_end=300.0):
        self.rig = empty(name + "_Dolly", coll, size=1)
        self.rig.rotation_mode = "QUATERNION"
        cd = bpy.data.cameras.new(name); cd.lens = lens; cd.clip_start = 0.05; cd.clip_end = clip_end
        cd.sensor_width = 36
        self.cam = bpy.data.objects.new(name, cd); coll.objects.link(self.cam)
        self.cam.parent = self.rig
        self._lastq = None

    def key(self, t, loc, target, roll=0.0, lens=None, interp="BEZIER"):
        q = look_quat(loc, target, roll)
        if self._lastq is not None and self._lastq.dot(q) < 0:
            q.negate()
        self._lastq = q
        self.rig.location = loc
        K(self.rig, "location", t, interp=interp)
        KQ(self.rig, t, q, interp)
        if lens is not None:
            self.cam.data.lens = lens
            K(self.cam.data, "lens", t, interp=interp)

    def shake(self, t0, t1, amp=0.05, rot_amp=0.6, seed=1, every=1):
        rng = random.Random(seed)
        n = FR(t1) - FR(t0)
        for i in range(0, n + 1, every):
            t = t0 + i / FPS
            fade = 1.0 - (i / max(1, n)) * 0.5
            self.cam.location = (rng.uniform(-amp, amp) * fade, rng.uniform(-amp, amp) * fade, 0)
            self.cam.rotation_euler = (0, 0, math.radians(rng.uniform(-rot_amp, rot_amp) * fade))
            K(self.cam, "location", t, interp="CONSTANT")
            K(self.cam, "rotation_euler", t, interp="CONSTANT")
        self.cam.location = (0, 0, 0); self.cam.rotation_euler = (0, 0, 0)
        K(self.cam, "location", t1 + 1 / FPS, interp="CONSTANT")
        K(self.cam, "rotation_euler", t1 + 1 / FPS, interp="CONSTANT")

def bind(scene, cam, t):
    m = scene.timeline_markers.new(cam.cam.name, frame=FR(t))
    m.camera = cam.cam

# ------------------------------------------------------------------ AVATAR --
class Avatar:
    """Roblox R6-style avatar. Pivots match Roblox Motor6D joints:
    Root(hip centre) > Torso > Head / ArmL / ArmR ; Root > LegL / LegR.
    Faces -Y. 1 Blender unit = 1 stud."""
    PARTS = ("Torso", "Head", "ArmL", "ArmR", "LegL", "LegR")

    def __init__(self, name, coll, origin=(0, 0, 0), style="normal", face="open", spear=True, hair=True, mats=None):
        self.name = name; self.coll = coll
        self.mats = mats or avatar_mats(style)
        M = self.mats
        bev = 0.08
        self.root = empty(name + "_Root", coll, origin, size=1.2)
        self.root.rotation_mode = "XYZ"
        self.torso = box(name + "_Torso", coll, (2, 1, 2), mat=M["shirt"], parent=self.root, offset=(0, 0, 1), bevel=bev)
        # outfit details on torso (front = -Y)
        d = 0.51
        box(name + "_CollarL", coll, (0.12, 0.04, 1.1), (-0.32, -d, 1.45), M["trim"], self.torso, rot=(0, 28, 0))
        box(name + "_CollarR", coll, (0.12, 0.04, 1.1), (0.32, -d, 1.45), M["trim"], self.torso, rot=(0, -28, 0))
        box(name + "_Belt", coll, (2.02, 1.02, 0.18), (0, 0, 0.18), M["trim2"], self.torso)
        box(name + "_Emblem", coll, (0.28, 0.04, 0.28), (0, -d - 0.005, 0.95), M["glow"], self.torso, rot=(0, 45, 0))
        box(name + "_Strap", coll, (0.14, 1.04, 2.02), (0.55, 0, 1), M["trim2"], self.torso, rot=(0, -22, 0))
        # head
        self.head = obj(name + "_Head", mesh_cyl(0.62, 1.2, 32, (0, 0, 0.62)), coll, (0, 0, 2), parent=self.torso, mat=M["skin"])
        bv = self.head.modifiers.new("Bevel", "BEVEL"); bv.width = 0.22; bv.segments = 4; bv.limit_method = "ANGLE"
        self.face_sets = {}
        for fs in ("open", "closed", "smirk"):
            self.face_sets[fs] = self._face(fs)
        self.set_face(face)
        if hair:
            self._hair()
        # arms (pivot at shoulder)
        self.armL = box(name + "_ArmL", coll, (1, 1, 2), (1.5, 0, 1.5), M["sleeve"], self.torso, offset=(0, 0, -0.5), bevel=bev)
        self.armR = box(name + "_ArmR", coll, (1, 1, 2), (-1.5, 0, 1.5), M["sleeve"], self.torso, offset=(0, 0, -0.5), bevel=bev)
        for a in (self.armL, self.armR):
            box(a.name + "_Hand", coll, (1.02, 1.02, 0.42), (0, 0, -1.3), M["skin"], a, bevel=0.06)
            box(a.name + "_Cuff", coll, (1.04, 1.04, 0.12), (0, 0, -1.04), M["trim"], a)
        # legs (pivot at hip)
        self.legL = box(name + "_LegL", coll, (1, 1, 2), (0.5, 0, 0), M["pants"], self.root, offset=(0, 0, -1), bevel=bev)
        self.legR = box(name + "_LegR", coll, (1, 1, 2), (-0.5, 0, 0), M["pants"], self.root, offset=(0, 0, -1), bevel=bev)
        for lg in (self.legL, self.legR):
            box(lg.name + "_Shoe", coll, (1.03, 1.03, 0.4), (0, 0, -1.8), M["shoe"], lg, bevel=0.05)
            box(lg.name + "_Stripe", coll, (0.1, 1.03, 1.3), (0.3 if lg is self.legL else -0.3, 0, -0.9), M["trim"], lg)
        self.spear = None
        if spear:
            self._spear()
        for p in self.parts():
            p.rotation_mode = "XYZ"

    def parts(self):
        return [self.torso, self.head, self.armL, self.armR, self.legL, self.legR]

    def _face(self, kind):
        n = self.name; M = self.mats; c = self.coll; h = self.head
        objs = []
        y = -0.6
        if kind in ("open", "smirk"):
            for sx in (-1, 1):
                e = obj(f"{n}_Eye{kind}{sx}", mesh_sphere(0.5, 16, 8), c, (0.2 * sx, y, 0.74), scale=(0.1, 0.05, 0.17), mat=M["eye"], parent=h)
                g = obj(f"{n}_Iris{kind}{sx}", mesh_sphere(0.5, 16, 8), c, (0.2 * sx, y - 0.02, 0.72), scale=(0.06, 0.03, 0.1), mat=M["iris"], parent=h)
                s = obj(f"{n}_Spec{kind}{sx}", mesh_sphere(0.5, 8, 6), c, (0.2 * sx + 0.025, y - 0.04, 0.8), scale=(0.03, 0.02, 0.04), mat=M["spec"], parent=h)
                objs += [e, g, s]
                if kind == "smirk":  # determined brow
                    b = box(f"{n}_Brow{sx}", c, (0.2, 0.03, 0.035), (0.2 * sx, y - 0.01, 0.93), M["eye"], h, rot=(0, -14 * sx, 0))
                    objs.append(b)
        else:
            for sx in (-1, 1):
                b = box(f"{n}_Lid{sx}", c, (0.2, 0.03, 0.04), (0.2 * sx, y - 0.01, 0.7), M["eye"], h, rot=(0, 8 * sx, 0))
                objs.append(b)
        # mouth
        if kind == "smirk":
            pts = [(-0.14, y - 0.01, 0.42), (0.0, y - 0.02, 0.4), (0.12, y - 0.02, 0.43), (0.2, y - 0.01, 0.49)]
        elif kind == "closed":
            pts = [(-0.1, y - 0.01, 0.43), (0.0, y - 0.02, 0.41), (0.1, y - 0.01, 0.43)]
        else:
            pts = [(-0.18, y - 0.01, 0.46), (-0.08, y - 0.02, 0.4), (0.08, y - 0.02, 0.4), (0.18, y - 0.01, 0.46)]
        mo = curve_obj(f"{n}_Mouth{kind}", c, pts, M["eye"], bevel=0.018)
        mo.parent = h
        objs.append(mo)
        return objs

    def set_face(self, kind):
        self.face = kind
        for k, objs in self.face_sets.items():
            for o in objs:
                o["face_kind"] = k

    def _hair(self):
        n = self.name; M = self.mats; c = self.coll; h = self.head
        H = M["hair"]
        box(n + "_HairCap", c, (1.42, 1.42, 0.5), (0, 0.04, 1.22), H, h, bevel=0.18)
        box(n + "_HairBack", c, (1.46, 0.42, 2.7), (0, 0.5, 0.2), H, h, bevel=0.12, rot=(6, 0, 0))
        box(n + "_HairTail", c, (1.0, 0.3, 1.6), (0, 0.72, -1.7), H, h, bevel=0.12, rot=(14, 0, 0))
        for sx in (-1, 1):
            box(f"{n}_HairSide{sx}", c, (0.26, 0.6, 1.55), (0.66 * sx, -0.12, 0.45), H, h, bevel=0.08)
            box(f"{n}_HairLock{sx}", c, (0.2, 0.22, 1.2), (0.55 * sx, -0.5, 0.15), H, h, bevel=0.06, rot=(0, 6 * sx, 0))
            box(f"{n}_Clip{sx}", c, (0.12, 0.3, 0.3), (0.72 * sx, -0.1, 1.05), M["trim"], h, rot=(45, 0, 0))
        for i, x in enumerate((-0.38, -0.1, 0.18, 0.42)):
            box(f"{n}_Bang{i}", c, (0.32, 0.18, 0.55), (x, -0.6, 1.02), H, h, bevel=0.06, rot=(-8, 18 if i % 2 else -14, 0))
        # long side ribbons (white streamers) for motion
        box(n + "_Ribbon", c, (0.18, 0.06, 1.6), (0.6, 0.62, 0.9), M["trim"], h, rot=(18, 0, -18))

    def _spear(self):
        n = self.name; M = self.mats; c = self.coll
        sp = empty(n + "_Spear", c, (0, 0, -1.3), parent=self.armR, size=0.6)
        sp.rotation_mode = "XYZ"
        obj(n + "_Shaft", mesh_cyl(0.07, 8.0, 12, (0, 0, 1.0)), c, parent=sp, mat=M["metal"])
        box(n + "_ShaftGlow", c, (0.05, 0.05, 6.4), (0.0, -0.06, 1.2), M["glow"], sp)
        head = obj(n + "_SpearHead", mesh_diamond(2.0, 0.3, 0.06), c, (0, 0, 5.0), parent=sp, mat=M["blade"])
        for sx in (-1, 1):
            obj(f"{n}_Guard{sx}", mesh_diamond(0.9, 0.12, 0.04), c, (0.18 * sx, 0, 5.0), (0, -62 * sx, 0), parent=sp, mat=M["blade"])
        obj(n + "_Pommel", mesh_diamond(0.5, 0.14, 0.14), c, (0, 0, -3.0), (180, 0, 0), parent=sp, mat=M["blade"])
        self.spear = sp
        self.spear_tip = empty(n + "_SpearTip", c, (0, 0, 7.0), parent=sp, size=0.3)

    def all_objects(self):
        out = []
        def rec(o):
            out.append(o)
            for ch in o.children: rec(ch)
        rec(self.root)
        return out

    def pose(self, t, P, interp="BEZIER"):
        """P: dict part->(x,y,z) degrees; 'root_loc', 'root_rot', 'spear'."""
        for key, ob in (("torso", self.torso), ("head", self.head), ("armL", self.armL), ("armR", self.armR),
                        ("legL", self.legL), ("legR", self.legR)):
            r = P.get(key, (0, 0, 0))
            ob.rotation_euler = [math.radians(a) for a in r]
            K(ob, "rotation_euler", t, interp=interp)
        if self.spear is not None:
            self.spear.rotation_euler = [math.radians(a) for a in P.get("spear", (90, 0, 0))]
            K(self.spear, "rotation_euler", t, interp=interp)
        if "root_rot" in P:
            self.root.rotation_euler = [math.radians(a) for a in P["root_rot"]]
            K(self.root, "rotation_euler", t, interp=interp)
        if "root_loc" in P:
            self.root.location = P["root_loc"]
            K(self.root, "location", t, interp=interp)


_mat_cache = {}
def avatar_mats(style):
    if style in _mat_cache: return _mat_cache[style]
    if style == "normal":
        M = dict(
            shirt=M_rimlit("AV_Shirt", (0.015, 0.016, 0.025), CYAN, 2.5, 0.35),
            trim=M_pbr("AV_Trim", (0.9, 0.05, 0.16), 0.35, emis=PINK, emis_str=1.2),
            trim2=M_pbr("AV_Trim2", (0.05, 0.05, 0.07), 0.3, 0.7),
            glow=M_emit("AV_Glow", CYAN, 12),
            skin=M_rimlit("AV_Skin", SKIN, (0.5, 0.75, 1.0), 1.6, 0.55),
            sleeve=M_rimlit("AV_Sleeve", (0.02, 0.02, 0.03), CYAN, 2.5, 0.35),
            pants=M_rimlit("AV_Pants", (0.02, 0.025, 0.06), CYAN, 2.0, 0.4),
            shoe=M_pbr("AV_Shoe", (0.9, 0.92, 0.95), 0.3),
            hair=M_rimlit("AV_Hair", HAIR, (0.55, 0.8, 1.0), 2.5, 0.4),
            eye=M_pbr("AV_Eye", (0.005, 0.005, 0.01), 0.2),
            iris=M_emit("AV_Iris", (0.35, 0.7, 1.0), 6),
            spec=M_emit("AV_Spec", WHITE, 10),
            metal=M_pbr("AV_Metal", (0.04, 0.05, 0.08), 0.2, 1.0),
            blade=M_emit("AV_Blade", ICE, 9),
        )
    elif style == "holo":
        g, _ = M_holo("AV_Holo", BLUE, 3)
        M = {k: g for k in ("shirt", "trim", "trim2", "skin", "sleeve", "pants", "shoe", "hair", "metal")}
        M.update(glow=M_emit("AV_HoloGlow", ICE, 10), eye=M_emit("AV_HoloEye", ICE, 12), iris=M_emit("AV_HoloIris", WHITE, 15),
                 spec=M_emit("AV_HoloSpec", WHITE, 15), blade=M_emit("AV_HoloBlade", ICE, 12))
        M["_dissolve_mat"] = g
    elif style == "ghost":
        g = M_ghost("AV_Ghost", (0.04, 0.18, 1.0), 0.3, 3.5)
        M = {k: g for k in ("shirt", "trim", "trim2", "skin", "sleeve", "pants", "shoe", "hair", "metal", "eye", "glow", "blade")}
        M.update(iris=M_emit("AV_GhostIris", ICE, 10), spec=M_emit("AV_GhostSpec", WHITE, 10))
    elif style == "silhouette":
        w = M_emit("AV_Sil", (0.55, 0.8, 1.0), 5)
        pk = M_emit("AV_SilPink", PINK, 7)
        M = {k: w for k in ("shirt", "trim2", "skin", "sleeve", "pants", "shoe", "hair", "metal", "glow", "blade", "iris", "spec")}
        M.update(trim=pk, eye=M_emit("AV_SilEye", (0.2, 0.3, 1.0), 4))
    elif style == "dark":   # back-lit, nearly black body with hot rim (flight / tunnel shots)
        rim = (0.4, 0.7, 1.0)
        dk = M_rimlit("AV_Dark", (0.01, 0.012, 0.02), rim, 9, 0.3)
        hr = M_rimlit("AV_DarkHair", (0.35, 0.45, 0.65), rim, 8, 0.35)
        M = {k: dk for k in ("shirt", "trim2", "skin", "sleeve", "pants", "shoe", "metal", "eye")}
        M.update(hair=hr, trim=M_emit("AV_DarkTrim", PINK, 6), glow=M_emit("AV_DarkGlow", ICE, 14),
                 iris=M_emit("AV_DarkIris", ICE, 14), spec=M_emit("AV_DarkSpec", WHITE, 10), blade=M_emit("AV_DarkBlade", ICE, 16))
    _mat_cache[style] = M
    return M

# poses (degrees). +X on arms/legs swings them BACK, -X swings forward/up.
POSES = {
    "idle_spear": dict(torso=(4, 0, 0), head=(4, 0, 0), armL=(-8, 0, 10), armR=(-35, 0, -8), legL=(0, 0, 4), legR=(0, 0, -4), spear=(118, 0, 0)),
    "ready":      dict(torso=(10, 0, -12), head=(-4, 0, 12), armL=(-20, 0, 25), armR=(-70, 0, -10), legL=(-25, 0, 10), legR=(20, 0, -6), spear=(80, 0, 0)),
    "chest_up":   dict(torso=(0, 0, 0), head=(-3, 0, 0), armL=(0, 0, 8), armR=(-25, 0, -10), spear=(150, 0, 0)),
    "raise":      dict(torso=(-8, 0, 15), head=(-10, 0, -5), armL=(-40, 0, 30), armR=(-160, 0, -15), legL=(-10, 0, 0), legR=(10, 0, 0), spear=(170, 0, 0)),
    "stand_spear":dict(torso=(0, 0, 0), head=(0, 0, 0), armL=(0, 0, 6), armR=(-30, 0, -8), legL=(0, 0, 3), legR=(0, 0, -3), spear=(120, 0, 0)),
    "lunge":      dict(torso=(30, 0, -25), head=(-20, 0, 20), armL=(40, 0, 35), armR=(-95, 0, -5), legL=(-60, 0, 0), legR=(45, 0, 0), spear=(180, 0, 0)),
    "fly":        dict(torso=(78, 0, 0), head=(-55, 0, 0), armL=(70, 0, 20), armR=(-165, 0, -5), legL=(18, 0, 6), legR=(32, 0, -6), spear=(180, 0, 0)),
    "fly2":       dict(torso=(82, 0, 6), head=(-60, 0, 0), armL=(80, 0, 30), armR=(-172, 0, -10), legL=(25, 0, 8), legR=(10, 0, -8), spear=(182, 0, 0)),
    "slash":      dict(torso=(25, 0, 40), head=(-15, 0, -30), armL=(60, 0, 40), armR=(-80, 0, 80), legL=(-50, 0, 0), legR=(55, 0, 0), spear=(150, 0, 0)),
    "thrust":     dict(torso=(22, 0, -35), head=(-22, 0, 30), armL=(55, 0, 45), armR=(-90, 0, 5), legL=(-70, 0, 10), legR=(55, 0, -5), spear=(180, 0, 0)),
}

def P(name, **over):
    d = dict(POSES[name]); d.update(over); return d

# ---------------------------------------------------------- SET HELPERS ----
def point_light(name, coll, loc, color, power, radius=0.5):
    ld = bpy.data.lights.new(name, "POINT"); ld.color = color; ld.energy = power
    ld.shadow_soft_size = radius
    o = bpy.data.objects.new(name, ld); coll.objects.link(o); o.location = loc
    return o

def area_light(name, coll, loc, target, color, power, size=4.0):
    ld = bpy.data.lights.new(name, "AREA"); ld.color = color; ld.energy = power; ld.size = size
    o = bpy.data.objects.new(name, ld); coll.objects.link(o); o.location = loc
    o.rotation_mode = "QUATERNION"; o.rotation_quaternion = look_quat(loc, target)
    return o

def cube_field(name, coll, n, center, spread, size_rng, mats, rng, shape=None):
    out = []
    me = mesh_box((1, 1, 1))
    for i in range(n):
        if shape:
            p = shape(rng)
        else:
            p = (rng.uniform(-spread[0], spread[0]), rng.uniform(-spread[1], spread[1]), rng.uniform(-spread[2], spread[2]))
        s = rng.uniform(*size_rng)
        o = obj(f"{name}{i:03d}", me, coll, (center[0] + p[0], center[1] + p[1], center[2] + p[2]),
                (rng.uniform(0, 90), rng.uniform(0, 90), rng.uniform(0, 90)), (s, s, s), mat=rng.choice(mats))
        out.append(o)
    return out

def square_tunnel(name, coll, origin, n, size, step, twist, thick, mat, mat_alt=None):
    rings = []
    for i in range(n):
        o = obj(f"{name}{i:02d}", mesh_square_ring(size, thick), coll, (origin[0], origin[1] + i * step, origin[2]),
                (0, i * twist, 0), mat=(mat_alt if (mat_alt and i % 3 == 0) else mat))
        rings.append(o)
    return rings

# ================================================================ SHOTS =====
class Ctx:
    pass

def build_S01(C, i):
    """Wide gameplay shot: dark sci-fi hangar, character with glowing spear."""
    c = new_coll("S01_Arena", C.root); O = Vector((i * SET_SPACING, 0, 0)); rng = random.Random(1)
    floor_m = M_gridwall("S01_Floor", (0.02, 0.03, 0.06), (0.1, 0.25, 1.0), 0.12, 1.5)
    box("S01_Floor", c, (120, 120, 0.4), O + Vector((0, 20, -0.2)), floor_m)
    wall_m = M_pbr("S01_Wall", (0.03, 0.05, 0.1), 0.35, 0.7)
    rib_m = M_rimlit("S01_Rib", (0.05, 0.08, 0.16), (0.2, 0.45, 1.0), 1.2, 0.3, 0.6)
    win_m = M_emit("S01_Window", ORANGE, 25)
    win2 = M_emit("S01_WinBlue", (0.5, 0.75, 1.0), 6)
    # back wall + blocky arch ribs
    box("S01_BackWall", c, (120, 2, 40), O + Vector((0, 46, 20)), wall_m)
    for side in (-1, 1):
        for k in range(7):
            x = side * (10 + k * 4.5)
            h = 26 - k * 1.5
            # rib segments forming an arch curving toward centre
            for s in range(6):
                a = s / 5
                px = x - side * a * a * 7; pz = 2 + a * h
                box(f"S01_Rib{side}{k}{s}", c, (1.6, 2.2, h / 5 + 0.6), O + Vector((px, 34 - k * 2.5, pz)), rib_m, rot=(0, side * a * 55, 0))
        for k in range(5):
            box(f"S01_Win{side}{k}", c, (2.6, 0.3, 1.6), O + Vector((side * (16 + k * 6), 44.5, 4 + (k % 2) * 3)), win_m)
    # central doorway / pillars
    for x in (-5, 5):
        box(f"S01_Pillar{x}", c, (1.4, 1.4, 18), O + Vector((x, 38, 9)), rib_m)
    box("S01_Door", c, (8, 0.3, 12), O + Vector((0, 44.6, 6)), win2)
    box("S01_DoorBar", c, (10.5, 1.5, 1.2), O + Vector((0, 38, 18)), rib_m)
    # floor energy line (from spear tip toward camera)
    line = obj("S01_FloorLine", mesh_plane(0.25, 22), c, O + Vector((0.6, -6, 0.03)), (90, 0, 8), mat=M_streak("S01_LineMat", (0.6, 0.4, 1.0), 25, "Z"))
    # floating particles
    pm = M_emit("S01_Part", (0.25, 0.5, 1.0), 30)
    for k in range(140):
        p = O + Vector((rng.uniform(-30, 30), rng.uniform(-4, 40), rng.uniform(0.5, 16)))
        s = rng.uniform(0.03, 0.12)
        o = obj(f"S01_P{k}", mesh_sphere(1, 8, 4), c, p, scale=(s, s, s), mat=pm)
        K(o, "location", 0.0); o.location = p + Vector((rng.uniform(-0.3, 0.3), 0, rng.uniform(0.2, 0.6))); K(o, "location", 0.3)
    av = Avatar("S01_Av", c, O + Vector((0, 8, 2)), "normal", "open")
    av.root.rotation_euler = (0, 0, math.radians(-15))
    av.pose(0.0, P("ready")); av.pose(0.22, P("ready", torso=(14, 0, -15), armR=(-60, 0, -10)))
    point_light("S01_Key", c, O + Vector((-6, 0, 10)), (0.3, 0.5, 1.0), 2500, 3)
    point_light("S01_Rim", c, O + Vector((4, 14, 6)), (0.4, 0.6, 1.0), 3000, 2)
    point_light("S01_Pink", c, O + Vector((1, 4, 0.5)), (1.0, 0.3, 0.7), 600, 0.5)
    area_light("S01_Fill", c, O + Vector((0, 30, 20)), O + Vector((0, 0, 0)), (0.2, 0.35, 1.0), 20000, 30)
    cam = Cam("CAM_S01", c, 24)
    cam.key(0.0, O + Vector((1.5, -14, 3.2)), O + Vector((0, 10, 3.5)), 0, interp="LINEAR")
    cam.key(0.22, O + Vector((1.2, -12.5, 3.0)), O + Vector((0, 10, 3.4)), 0, interp="LINEAR")
    C.cams["S01"] = cam
    return c, [(0.0, 0.22)]

def build_S02(C, i):
    """Face close-up dissolving into holographic data cubes, glitch bars, lightning."""
    c = new_coll("S02_HoloCU", C.root); O = Vector((i * SET_SPACING, 0, 0)); rng = random.Random(2)
    av = Avatar("S02_Av", c, O, "normal", "open", spear=False)
    av.pose(0.22, P("chest_up", head=(-6, 0, -8), torso=(0, 0, -10)))
    av.pose(0.92, P("chest_up", head=(-2, 0, -14), torso=(0, 0, -14)))
    # holographic duplicate that grows in and dissolves (right side)
    gh = Avatar("S02_Holo", c, O + Vector((0.25, 0.3, 0.0)), "holo", "open", spear=False, hair=True)
    gh.pose(0.22, P("chest_up", head=(-6, 0, -8), torso=(0, 0, -10)))
    diss = avatar_mats("holo")["_dissolve_mat"]
    vnode = [n for n in diss.node_tree.nodes if n.label == "Dissolve"][0].outputs[0]
    K(vnode, "default_value", 0.22, 0.95, idblock=diss.node_tree)
    K(vnode, "default_value", 0.40, 0.45, idblock=diss.node_tree)
    K(vnode, "default_value", 0.67, 0.30, idblock=diss.node_tree)
    K(vnode, "default_value", 0.92, 0.70, idblock=diss.node_tree)
    gh.root.scale = (1.06, 1.06, 1.06)
    # data cubes streaming from body (bottom/right)
    wc = M_wirecube("S02_DataCube", (0.1, 0.35, 1.0), 7, 0.08)
    sc = M_emit("S02_SolidCube", (0.05, 0.25, 1.0), 4)
    cubes = cube_field("S02_C", c, 90, O + Vector((0.5, -0.3, 2.2)), (1.6, 0.6, 1.4), (0.06, 0.28), [wc, wc, sc], rng)
    for o in cubes:
        p0 = o.location.copy(); o.rotation_euler = (0, 0, 0)
        K(o, "location", 0.22); K(o, "scale", 0.22)
        o.location = p0 + Vector((rng.uniform(0.8, 2.8), rng.uniform(-1.5, 0.2), rng.uniform(-0.8, 1.0)))
        K(o, "location", 0.92)
        o.scale = (0, 0, 0); K(o, "scale", 0.92)
    # glitch bars (horizontal thin emissive slices across the face, flicker)
    gb = M_emit("S02_GlitchBar", (0.35, 0.6, 1.0), 14)
    bars = []
    for k in range(10):
        b = obj(f"S02_Bar{k}", mesh_plane(1, 1), c, O + Vector((rng.uniform(-0.6, 0.8), -1.4, rng.uniform(2.3, 3.6))),
                scale=(rng.uniform(0.6, 2.8), 1, rng.uniform(0.008, 0.04)), mat=gb)
        b["manual_vis"] = True
        frames = sorted(rng.sample(range(FR(0.22), FR(0.92)), 4))
        vis(b, [((f - 1) / FPS, (f + 1 - 1) / FPS) for f in frames])
        bars.append(b)
    # lightning arcs (right side) — several variants each visible single frames
    lm = M_emit("S02_Bolt", (0.5, 0.75, 1.0), 25)
    for k in range(9):
        pts = lightning_pts(O + Vector((1.2, -0.6, 3.4)), O + Vector((3.2 + rng.uniform(0, 1), 0.4, 1.6 + rng.uniform(-0.4, 1.4))), 12, 0.35, rng)
        bo = curve_obj(f"S02_Bolt{k}", c, pts, lm, bevel=0.012)
        bo["manual_vis"] = True
        f = FR(0.22) + 2 + k * 2 + rng.randint(0, 1)
        vis(bo, [((f - 1) / FPS, (f + 1) / FPS)])
    # backdrop: deep black with faint blue haze plane
    hz = M_ink("S02_Haze", (0.01, 0.04, 0.6), 0.8)
    hzo = obj("S02_HazePlane", mesh_plane(14, 9), c, O + Vector((1.0, 4, 2.5)), mat=hz[0])
    hz_thr = hz[1]; K(hz_thr, "default_value", 0.22, 0.95, idblock=hz[0].node_tree)
    K(hz_thr, "default_value", 0.92, 0.72, idblock=hz[0].node_tree)
    point_light("S02_Key", c, O + Vector((-2.5, -3, 3.5)), (0.35, 0.55, 1.0), 450, 1)
    point_light("S02_Rim", c, O + Vector((2.5, 1.5, 3.5)), (0.3, 0.6, 1.0), 900, 0.5)
    point_light("S02_Under", c, O + Vector((0.8, -1.5, 1.2)), (0.3, 0.5, 1.0), 250, 0.3)
    cam = Cam("CAM_S02", c, 50)
    cam.key(0.22, O + Vector((0.55, -4.2, 2.75)), O + Vector((0.05, 0, 2.65)), -3, interp="LINEAR")
    cam.key(0.67, O + Vector((0.45, -3.6, 2.72)), O + Vector((0.05, 0, 2.62)), -5, interp="LINEAR")
    C.cams["S02"] = cam
    cam2 = Cam("CAM_S04", c, 65)   # glitch close-up variant
    cam2.key(0.83, O + Vector((0.1, -3.4, 2.75)), O + Vector((0.0, 0, 2.7)), 4, interp="LINEAR")
    cam2.key(0.92, O + Vector((0.12, -3.2, 2.76)), O + Vector((0.0, 0, 2.7)), 5, interp="LINEAR")
    cam2.shake(0.83, 0.92, 0.04, 1.0, seed=4)
    C.cams["S04"] = cam2
    return c, [(0.22, 0.67), (0.83, 0.92)]

def build_S03(C, i):
    """Over-exposed silhouette on expanding blue ink splash; re-used for pink duotone flash."""
    c = new_coll("S03_Ink", C.root); O = Vector((i * SET_SPACING, 0, 0)); rng = random.Random(3)
    av = Avatar("S03_Av", c, O, "silhouette", "open", spear=False)
    av.pose(0.67, P("chest_up", head=(-10, 0, 10), armR=(-40, 0, -30), armL=(-30, 0, 30)))
    av.pose(1.0, P("chest_up", head=(-14, 0, 14), armR=(-50, 0, -35), armL=(-40, 0, 35)))
    ink, thr, w = M_ink("S03_InkMat", (0.01, 0.06, 1.0), 2.2)
    ink_o = obj("S03_InkPlane", mesh_plane(12, 8), c, O + Vector((0, 1.5, 2.4)), mat=ink)
    K(thr, "default_value", 0.67, 1.25, idblock=ink.node_tree)
    K(thr, "default_value", 0.80, 0.78, idblock=ink.node_tree)
    K(thr, "default_value", 1.00, 0.62, idblock=ink.node_tree)
    K(w, "default_value", 0.67, 0.0, idblock=ink.node_tree)
    K(w, "default_value", 1.00, 1.2, idblock=ink.node_tree)
    # second ink layer in front (partial occlusion like the reference)
    ink2, thr2, w2 = M_ink("S03_InkFront", (0.02, 0.1, 1.0), 2.6)
    obj("S03_InkFrontPlane", mesh_plane(9, 6), c, O + Vector((1.5, -1.2, 1.2)), mat=ink2)
    K(thr2, "default_value", 0.67, 1.4, idblock=ink2.node_tree)
    K(thr2, "default_value", 0.83, 1.02, idblock=ink2.node_tree)
    K(thr2, "default_value", 1.00, 0.9, idblock=ink2.node_tree)
    K(w2, "default_value", 0.67, 3.0, idblock=ink2.node_tree); K(w2, "default_value", 1.0, 4.0, idblock=ink2.node_tree)
    # splatter droplets
    dm = M_emit("S03_Drop", (0.05, 0.2, 1.0), 5)
    for k in range(40):
        p = O + Vector((rng.uniform(-5, 5), rng.uniform(0.5, 1.4), rng.uniform(0, 5)))
        s = rng.uniform(0.04, 0.22)
        d = obj(f"S03_Drop{k}", mesh_sphere(1, 10, 6), c, O + Vector((0, 1, 2.5)), scale=(s, s, s), mat=dm)
        K(d, "location", 0.67); d.location = p; K(d, "location", 0.85, interp="BEZIER")
    cam = Cam("CAM_S03", c, 40)
    cam.key(0.67, O + Vector((0.2, -5.0, 2.6)), O + Vector((0.2, 0, 2.5)), 6, interp="LINEAR")
    cam.key(0.83, O + Vector((0.2, -4.6, 2.6)), O + Vector((0.2, 0, 2.5)), 8, interp="LINEAR")
    C.cams["S03"] = cam
    cam5 = Cam("CAM_S05", c, 30)
    cam5.key(0.92, O + Vector((0.0, -6.2, 2.4)), O + Vector((0, 0, 2.3)), -4, interp="LINEAR")
    cam5.key(1.0, O + Vector((0.0, -6.6, 2.4)), O + Vector((0, 0, 2.3)), -5, interp="LINEAR")
    cam5.shake(0.92, 1.0, 0.08, 1.5, seed=5)
    C.cams["S05"] = cam5
    return c, [(0.67, 0.83), (0.92, 1.0)]

def build_S06(C, i):
    """Chest-up, afterimage clones either side, falling pixel squares."""
    c = new_coll("S06_Clones", C.root); O = Vector((i * SET_SPACING, 0, 0)); rng = random.Random(6)
    av = Avatar("S06_Av", c, O, "normal", "closed", spear=False)
    av.set_face("closed")
    av.pose(1.0, P("chest_up", head=(-4, 0, 0), torso=(0, 0, 0)))
    av.pose(1.47, P("chest_up", head=(-8, 0, 12), torso=(0, 0, 10)))
    av_open = av.face_sets["open"]; av_closed = av.face_sets["closed"]
    for o in av_closed: o["manual_vis"] = True; vis(o, [(1.0, 1.25)])
    for o in av_open: o["manual_vis"] = True; vis(o, [(1.25, 1.47)])
    for o in av.face_sets["smirk"]: o["manual_vis"] = True; vis(o, [])
    clones = []
    for k, (dx, dy, rz, sc) in enumerate(((-2.3, 1.4, 25, 1.15), (2.4, 1.6, -28, 1.2), (-4.2, 3.0, 35, 1.3), (4.4, 3.2, -35, 1.3))):
        g = Avatar(f"S06_Clone{k}", c, O + Vector((dx, dy, -0.2)), "ghost", "closed", spear=False)
        g.root.rotation_euler = (0, 0, math.radians(rz)); g.root.scale = (sc, sc, sc)
        g.pose(1.0, P("chest_up", head=(-10, 0, rz * 0.3)))
        clones.append(g)
        K(g.root, "location", 1.0)
        g.root.location = g.root.location + Vector((dx * 0.12, 0.4, 0.15)); K(g.root, "location", 1.47)
    # background grid of squares
    sqm = M_emit("S06_Sq", (0.1, 0.3, 1.0), 3)
    sqm2 = M_wirecube("S06_SqW", (0.2, 0.45, 1.0), 6, 0.0)
    for gx in range(-14, 15):
        for gz in range(-1, 12):
            if rng.random() < 0.55:
                o = obj(f"S06_G{gx}_{gz}", mesh_plane(0.35, 0.35), c, O + Vector((gx * 0.9, 9, gz * 0.9)), mat=rng.choice([sqm, sqm2, sqm2]))
    # falling pixel squares (front + mid)
    fm = M_emit("S06_Fall", (0.35, 0.6, 1.0), 9)
    for k in range(70):
        s = rng.uniform(0.05, 0.22)
        p = O + Vector((rng.uniform(-4.5, 4.5), rng.uniform(-1.5, 4), rng.uniform(2, 6.5)))
        o = obj(f"S06_F{k}", mesh_box((1, 1, 1)), c, p, scale=(s, s, s), mat=fm if rng.random() < 0.6 else sqm2)
        K(o, "location", 1.0); o.location = p - Vector((0, 0, rng.uniform(1.5, 3.5))); K(o, "location", 1.47)
    point_light("S06_Key", c, O + Vector((-3, -4, 4)), (0.35, 0.55, 1.0), 900, 1.5)
    point_light("S06_Rim", c, O + Vector((3, 2, 4.5)), (0.5, 0.7, 1.0), 1500, 0.5)
    point_light("S06_Pink", c, O + Vector((0.5, -2, 1.0)), (1.0, 0.3, 0.6), 120, 0.5)
    cam = Cam("CAM_S06", c, 32)
    cam.key(1.0, O + Vector((0.3, -6.2, 2.0)), O + Vector((0, 0, 2.5)), 3, interp="LINEAR")
    cam.key(1.47, O + Vector((0.2, -5.2, 2.1)), O + Vector((0, 0, 2.55)), -2, interp="LINEAR")
    C.cams["S06"] = cam
    return c, [(1.0, 1.47)]

def build_S07(C, i):
    """Rear over-shoulder, spear across, square tunnel opening ahead."""
    c = new_coll("S07_Rear", C.root); O = Vector((i * SET_SPACING, 0, 0)); rng = random.Random(7)
    av = Avatar("S07_Av", c, O, "normal", "open")
    av.root.rotation_euler = (0, 0, math.radians(180))   # facing +Y, away from camera
    av.pose(1.47, P("raise", spear=(150, 0, 10)))
    av.pose(1.63, P("raise", armR=(-175, 0, -20), spear=(170, 0, 20)))
    tm = M_emit("S07_Ring", (0.03, 0.18, 1.0), 5); tm2 = M_emit("S07_Ring2", (0.4, 0.65, 1.0), 9)
    rings = square_tunnel("S07_T", c, O + Vector((0, 4, 3)), 34, 16, 2.2, 7, 0.35, tm, tm2)
    for r in rings:
        K(r, "rotation_euler", 1.47); r.rotation_euler.y += math.radians(25); K(r, "rotation_euler", 1.63)
    haze = obj("S07_Haze", mesh_plane(40, 30), c, O + Vector((0, 80, 3)), mat=M_emit("S07_HazeM", (0.1, 0.25, 1.0), 2.5))
    point_light("S07_Rim", c, O + Vector((0, 6, 5)), (0.4, 0.6, 1.0), 4000, 2)
    point_light("S07_Fill", c, O + Vector((-3, -3, 3)), (0.2, 0.3, 1.0), 300, 1)
    cam = Cam("CAM_S07", c, 28)
    cam.key(1.47, O + Vector((3.4, -6.5, 1.6)), O + Vector((-0.3, 8, 3.8)), -12, interp="LINEAR")
    cam.key(1.63, O + Vector((3.0, -5.8, 1.8)), O + Vector((-0.3, 8, 3.9)), -16, interp="LINEAR")
    C.cams["S07"] = cam
    return c, [(1.47, 1.63)]

def build_S08(C, i):
    """Infinite twisting square tunnel, tiny character in centre, spear-tip star glints in foreground."""
    c = new_coll("S08_Tunnel", C.root); O = Vector((i * SET_SPACING, 0, 0)); rng = random.Random(8)
    tm = M_emit("S08_Ring", (0.03, 0.18, 1.0), 4); tm2 = M_emit("S08_Ring2", (0.4, 0.65, 1.0), 9)
    rings = square_tunnel("S08_T", c, O, 60, 9, 1.0, 6, 0.22, tm, tm2)
    piv = empty("S08_Pivot", c, O)
    for r in rings: r.parent = piv; r.location -= O
    piv.rotation_mode = "XYZ"
    K(piv, "rotation_euler", 1.63, (0, 0, 0)); K(piv, "rotation_euler", 1.97, (0, math.radians(-40), 0))
    # glowing haze at end
    obj("S08_End", mesh_plane(12, 12), c, O + Vector((0, 62, 0)), mat=M_emit("S08_EndM", (0.4, 0.65, 1.0), 6))
    av = Avatar("S08_Av", c, O + Vector((0, 18, -1.2)), "dark", "open")
    av.root.scale = (0.45, 0.45, 0.45)
    av.pose(1.63, P("stand_spear", spear=(60, 0, 0), armR=(-60, 0, -10)))
    av.pose(1.97, P("stand_spear", spear=(66, 0, 0), armR=(-66, 0, -12), head=(-12, 0, 0)))
    # foreground spear (huge, close to camera, right side) with star glints
    fs = empty("S08_FGSpear", c, O + Vector((2.0, 2.2, -0.9)))
    fs.rotation_euler = (math.radians(80), 0, math.radians(-60))
    obj("S08_FGShaft", mesh_cyl(0.08, 6, 12, (0, 0, -3)), c, parent=fs, mat=M_pbr("S08_Metal", (0.02, 0.02, 0.04), 0.2, 1))
    obj("S08_FGHead", mesh_diamond(1.4, 0.22, 0.05), c, (0, 0, 0), parent=fs, mat=M_emit("S08_Blade", ICE, 12))
    stm = M_emit("S08_Star", (0.7, 0.85, 1.0), 40)
    R = fs.rotation_euler.to_matrix()
    for k, (dz, sz, t0) in enumerate(((0.9, 0.5, 1.66), (0.45, 0.32, 1.72), (1.3, 0.25, 1.78))):
        p = fs.location + R @ Vector((0, 0, dz)) + Vector((0, -0.25, 0))
        st = obj(f"S08_Star{k}", mesh_star4(1.0, 0.1), c, p, mat=stm)
        st.scale = (0, 0, 0); K(st, "scale", t0 - 0.03)
        st.scale = (sz, sz, sz); K(st, "scale", t0 + 0.03, interp="BEZIER")
        st.scale = (sz * 0.6, sz * 0.6, sz * 0.6); K(st, "scale", 1.97)
    point_light("S08_Light", c, O + Vector((0, 14, 0)), (0.4, 0.6, 1.0), 2500, 1)
    point_light("S08_FG", c, O + Vector((1.2, 0.5, -0.3)), (0.4, 0.6, 1.0), 120, 0.2)
    cam = Cam("CAM_S08", c, 30)
    cam.key(1.63, O + Vector((0, -2, 0)), O + Vector((0, 20, -0.3)), 8, interp="LINEAR")
    cam.key(1.97, O + Vector((0, 1.0, 0)), O + Vector((0, 20, -0.3)), -2, interp="LINEAR")
    C.cams["S08"] = cam
    return c, [(1.63, 1.97)]

def build_S09(C, i):
    """Diamond portal with crescent emblem, pixel cubes blasting out, lunge."""
    c = new_coll("S09_Portal", C.root); O = Vector((i * SET_SPACING, 0, 0)); rng = random.Random(9)
    pm = M_emit("S09_Frame", (0.55, 0.78, 1.0), 25)
    port = empty("S09_PortalPivot", c, O + Vector((0, 14, 3)))
    fr = obj("S09_Diamond", mesh_square_ring(7, 0.25), c, (0, 0, 0), (0, 45, 0), mat=pm, parent=port)
    fr2 = obj("S09_Diamond2", mesh_square_ring(7.8, 0.06), c, (0, 0.1, 0), (0, 45, 0), mat=pm, parent=port)
    cres = obj("S09_Crescent", mesh_crescent(2.0), c, (0, -0.05, 0), (0, 200, 0), mat=M_emit("S09_Cres", (0.8, 0.9, 1.0), 30), parent=port)
    inner = obj("S09_Inner", mesh_plane(6.6, 6.6), c, (0, 0.3, 0), (0, 45, 0), mat=M_ghost("S09_InnerM", (0.2, 0.45, 1.0), 0.6, 6), parent=port)
    port.rotation_mode = "XYZ"
    K(port, "scale", 1.97, (0.2, 0.2, 0.2)); K(port, "scale", 2.10, (1.0, 1.0, 1.0), interp="BEZIER"); K(port, "scale", 2.40, (1.15, 1.15, 1.15))
    K(port, "rotation_euler", 1.97, (0, math.radians(-30), 0)); K(port, "rotation_euler", 2.40, (0, math.radians(8), 0), interp="BEZIER")
    # pixel cubes exploding outward from portal
    cm = [M_emit("S09_Cube", (0.15, 0.4, 1.0), 6), M_pbr("S09_CubeDark", (0.02, 0.05, 0.18), 0.3, 0.4, emis=(0.1, 0.3, 1.0), emis_str=0.8), M_wirecube("S09_CubeW", (0.4, 0.7, 1.0), 12, 0.2)]
    for k in range(150):
        o = obj(f"S09_C{k}", mesh_box((1, 1, 1)), c, O + Vector((0, 14, 3)), mat=rng.choice(cm))
        s = rng.uniform(0.15, 0.7); o.scale = (s, s, s)
        a = rng.uniform(0, 2 * math.pi); r = rng.uniform(4.5, 16)
        dest = O + Vector((math.cos(a) * r, 14 + rng.uniform(-6, 6), 3 + math.sin(a) * r * 0.7))
        st = 1.97 + rng.uniform(0.0, 0.12)
        o.location = O + Vector((math.cos(a) * 3.2, 14, 3 + math.sin(a) * 3.2)); K(o, "location", st); K(o, "rotation_euler", st)
        o.location = dest; o.rotation_euler = (rng.uniform(0, 6), rng.uniform(0, 6), rng.uniform(0, 6)); K(o, "location", 2.40); K(o, "rotation_euler", 2.40)
    # dark block tunnel walls behind
    wm = M_pbr("S09_Wall", (0.02, 0.04, 0.12), 0.3, 0.5)
    for k in range(70):
        a = rng.uniform(0, 2 * math.pi); r = rng.uniform(11, 15)
        s = rng.uniform(1.5, 4)
        box(f"S09_W{k}", c, (s, rng.uniform(2, 8), s), O + Vector((math.cos(a) * r, rng.uniform(10, 45), 3 + math.sin(a) * r)), wm)
    av = Avatar("S09_Av", c, O + Vector((3.5, 4, 0.5)), "normal", "smirk")
    av.root.rotation_euler = (0, 0, math.radians(-120))
    av.pose(1.97, P("lunge", root_loc=O + Vector((3.8, 4.5, 0.5))))
    av.pose(2.40, P("lunge", torso=(38, 0, -30), root_loc=O + Vector((2.9, 5.5, 0.7))))
    point_light("S09_Core", c, O + Vector((0, 12, 3)), (0.45, 0.65, 1.0), 9000, 2)
    point_light("S09_Key", c, O + Vector((6, 0, 4)), (0.35, 0.55, 1.0), 900, 1)
    cam = Cam("CAM_S09", c, 26)
    cam.key(1.97, O + Vector((5.5, -4.5, 1.5)), O + Vector((0, 14, 3)), 18, interp="LINEAR")
    cam.key(2.40, O + Vector((6.2, -6.5, 1.2)), O + Vector((0, 14, 3)), 4, interp="LINEAR")
    C.cams["S09"] = cam
    return c, [(1.97, 2.40)]

def build_S10(C, i):
    """Face close-up, smirk, energy ribbons swirling."""
    c = new_coll("S10_Ribbons", C.root); O = Vector((i * SET_SPACING, 0, 0)); rng = random.Random(10)
    av = Avatar("S10_Av", c, O, "normal", "smirk", spear=True)
    av.pose(2.40, P("chest_up", head=(-8, 0, -18), torso=(4, 0, -20), armR=(-120, 0, -40), spear=(100, 0, 40)))
    av.pose(2.72, P("chest_up", head=(-12, 0, -8), torso=(4, 0, -14), armR=(-130, 0, -45), spear=(100, 0, 40)))
    rm = M_emit("S10_Ribbon", (0.05, 0.3, 1.0), 9)
    rm2 = M_emit("S10_Ribbon2", (0.6, 0.85, 1.0), 12)
    piv = empty("S10_Swirl", c, O + Vector((0, 0, 2.6))); piv.rotation_mode = "XYZ"
    for k in range(12):
        r = rng.uniform(1.5, 3.2); a0 = rng.uniform(-0.6, math.pi + 0.6); h = rng.uniform(-1.4, 1.3)
        pts = [(math.cos(a0 + j * 0.12) * r, abs(math.sin(a0 + j * 0.12)) * r * 0.7 + 0.4, h + j * rng.uniform(-0.03, 0.05)) for j in range(20)]
        rb = curve_obj(f"S10_R{k}", c, pts, rm if k % 3 else rm2, bevel=0.0, extrude=rng.uniform(0.015, 0.05))
        rb.parent = piv; rb.data.twist_mode = "MINIMUM"
    K(piv, "rotation_euler", 2.40, (0.2, 0, 0)); K(piv, "rotation_euler", 2.72, (0.25, 0, math.radians(-140)))
    bg = obj("S10_BG", mesh_plane(16, 10), c, O + Vector((0, 6, 2.6)), mat=M_ink("S10_BGM", (0.01, 0.08, 1.0), 1.4)[0])
    obj("S10_Moon", mesh_sphere(1, 32, 16), c, O + Vector((-2.4, 5, 3.4)), scale=(1.6, 0.1, 1.6), mat=M_emit("S10_MoonM", (0.6, 0.8, 1.0), 4))
    point_light("S10_Key", c, O + Vector((2, -3, 3.5)), (0.5, 0.7, 1.0), 650, 1)
    point_light("S10_Rim", c, O + Vector((-2.2, 1.5, 3.4)), (0.4, 0.6, 1.0), 1100, 0.5)
    cam = Cam("CAM_S10", c, 38)
    cam.key(2.40, O + Vector((0.9, -4.0, 2.55)), O + Vector((0, 0, 2.6)), 6, interp="LINEAR")
    cam.key(2.72, O + Vector((0.6, -3.4, 2.6)), O + Vector((0, 0, 2.65)), 2, interp="LINEAR")
    C.cams["S10"] = cam
    return c, [(2.40, 2.72)]

def build_S11(C, i):
    """Dash: camera rockets through a cube field behind the streaking character."""
    c = new_coll("S11_Dash", C.root); O = Vector((i * SET_SPACING, 0, 0)); rng = random.Random(11)
    cm = [M_pbr("S11_Dark", (0.02, 0.04, 0.12), 0.25, 0.6), M_emit("S11_Glow", (0.2, 0.45, 1.0), 8), M_emit("S11_White", ICE, 20)]
    cube_field("S11_C", c, 260, O + Vector((0, 40, 2)), (9, 40, 6), (0.3, 1.6), cm, rng)
    av = Avatar("S11_Av", c, O + Vector((0, 12, 2)), "dark", "open")
    av.root.rotation_euler = (0, 0, math.radians(180))
    av.pose(2.72, P("fly", root_loc=O + Vector((0.3, 10, 1.8))))
    av.pose(2.83, P("fly", root_loc=O + Vector((0, 34, 2.2))))
    point_light("S11_L", c, O + Vector((0, 60, 2)), (0.4, 0.6, 1.0), 30000, 3)
    cam = Cam("CAM_S11", c, 20)
    cam.key(2.72, O + Vector((0, 0, 2)), O + Vector((0, 40, 2)), 0, interp="LINEAR")
    cam.key(2.83, O + Vector((0, 24, 2.3)), O + Vector((0, 64, 2.3)), 12, interp="LINEAR")
    C.cams["S11"] = cam
    return c, [(2.72, 2.83)]

def build_S12(C, i):
    """White-blue flash explosion with radial light rays."""
    c = new_coll("S12_Flash", C.root); O = Vector((i * SET_SPACING, 0, 0)); rng = random.Random(12)
    core = obj("S12_Core", mesh_sphere(1, 32, 16), c, O + Vector((0, 10, 0)), mat=M_emit("S12_CoreM", ICE, 30))
    K(core, "scale", 2.83, (0.4, 0.4, 0.4)); K(core, "scale", 2.92, (3.5, 3.5, 3.5), interp="BEZIER"); K(core, "scale", 3.0, (2.0, 2.0, 2.0))
    rm = M_streak("S12_Ray", (0.4, 0.7, 1.0), 14, "Z"); rm2 = M_streak("S12_Ray2", (0.05, 0.25, 1.0), 9, "Z")
    piv = empty("S12_Rays", c, O + Vector((0, 10, 0))); piv.rotation_mode = "XYZ"
    for k in range(36):
        a = rng.uniform(0, 360)
        ln = rng.uniform(8, 26); w = rng.uniform(0.03, 0.18)
        r = obj(f"S12_R{k}", mesh_plane(w, ln, (0, 0, ln / 2 + rng.uniform(0.5, 3))), c, (0, rng.uniform(-1, 1), 0), (0, a, 0), mat=rm if k % 2 else rm2, parent=piv)
    K(piv, "rotation_euler", 2.83, (0, 0, 0)); K(piv, "rotation_euler", 3.0, (0, math.radians(18), 0))
    K(piv, "scale", 2.83, (0.3, 1, 0.3)); K(piv, "scale", 2.95, (1.2, 1, 1.2), interp="BEZIER")
    obj("S12_BG", mesh_plane(80, 50), c, O + Vector((0, 30, 0)), mat=M_emit("S12_BGM", (0.03, 0.2, 1.0), 2))
    cube_field("S12_D", c, 50, O + Vector((0, 8, 0)), (7, 3, 4), (0.15, 0.6), [M_emit("S12_Deb", ICE, 15)], rng)
    cam = Cam("CAM_S12", c, 24)
    cam.key(2.83, O + Vector((0, -6, 0)), O + Vector((0, 10, 0)), 0, interp="LINEAR")
    cam.key(3.0, O + Vector((0, -3, 0)), O + Vector((0, 10, 0)), -6, interp="LINEAR")
    cam.shake(2.83, 3.0, 0.15, 2, seed=12)
    C.cams["S12"] = cam
    return c, [(2.83, 3.0)]

def build_S13(C, i):
    """Hyperspace: radial blocks streaking past toward the vanishing point + starburst."""
    c = new_coll("S13_Hyper", C.root); O = Vector((i * SET_SPACING, 0, 0)); rng = random.Random(13)
    mats = [M_pbr("S13_Blk", (0.02, 0.05, 0.2), 0.25, 0.6, emis=(0.1, 0.3, 1.0), emis_str=0.6),
            M_emit("S13_Glow", (0.15, 0.4, 1.0), 6), M_emit("S13_Hot", (0.6, 0.8, 1.0), 25), M_rimlit("S13_Rim", (0.02, 0.06, 0.25), CYAN, 5, 0.3)]
    for k in range(170):
        a = rng.uniform(0, 2 * math.pi); r = rng.uniform(1.6, 14)
        ln = rng.uniform(6, 40); th = rng.uniform(0.15, 1.6) * (r / 8 + 0.3)
        y0 = rng.uniform(0, 160)
        o = obj(f"S13_B{k}", mesh_box((1, 1, 1)), c, O + Vector((math.cos(a) * r, y0, math.sin(a) * r)),
                (0, math.degrees(-a), 0), (th, ln, th * rng.uniform(0.3, 1.0)), mat=mats[0 if rng.random() < 0.55 else rng.randint(1, 3)])
        K(o, "location", 3.0); o.location.y -= rng.uniform(70, 110); K(o, "location", 3.47)
    star = obj("S13_Star", mesh_star4(1, 0.08), c, O + Vector((0, 60, 0)), mat=M_emit("S13_StarM", WHITE, 60))
    for t, s in ((3.0, 2), (3.1, 6), (3.2, 3), (3.3, 7), (3.4, 4), (3.47, 8)):
        K(star, "scale", t, (s, s, s))
    obj("S13_Core", mesh_sphere(1, 24, 12), c, O + Vector((0, 70, 0)), scale=(3, 3, 3), mat=M_emit("S13_CoreM", (0.7, 0.85, 1.0), 25))
    obj("S13_BG", mesh_plane(200, 200), c, O + Vector((0, 160, 0)), mat=M_emit("S13_BGM", (0.0, 0.05, 0.35), 1))
    cam = Cam("CAM_S13", c, 22, 400)
    cam.key(3.0, O + Vector((0, -4, 0)), O + Vector((0, 60, 0)), 0, interp="LINEAR")
    cam.key(3.47, O + Vector((0, 4, 0)), O + Vector((0, 60, 0)), 25, interp="LINEAR")
    C.cams["S13"] = cam
    return c, [(3.0, 3.47)]

def build_S14(C, i):
    """Crescent flare at vanishing point, then fade to dark."""
    c = new_coll("S14_Crescent", C.root); O = Vector((i * SET_SPACING, 0, 0)); rng = random.Random(14)
    cr = obj("S14_Cres", mesh_crescent(1.0), c, O + Vector((0, 20, 0)), (0, 90, 0), mat=M_emit("S14_CresM", WHITE, 50))
    K(cr, "scale", 3.47, (0.4, 0.4, 0.4)); K(cr, "scale", 3.52, (1.3, 1.3, 1.3), interp="BEZIER"); K(cr, "scale", 3.62, (0.1, 0.1, 0.1))
    rm = M_streak("S14_Ray", (0.2, 0.45, 1.0), 12, "Z")
    piv = empty("S14_Rays", c, O + Vector((0, 20, 0))); piv.rotation_mode = "XYZ"
    for k in range(30):
        ln = rng.uniform(10, 30)
        obj(f"S14_R{k}", mesh_plane(rng.uniform(0.05, 0.4), ln, (0, 0, ln / 2)), c, (0, 0.5, 0), (0, rng.uniform(0, 360), 0), mat=rm, parent=piv)
    K(piv, "scale", 3.47, (1, 1, 1)); K(piv, "scale", 3.62, (0.3, 1, 0.3))
    K(piv, "rotation_euler", 3.47, (0, 0, 0)); K(piv, "rotation_euler", 3.62, (0, math.radians(-25), 0))
    cam = Cam("CAM_S14", c, 30)
    cam.key(3.47, O + Vector((0, 0, 0)), O + Vector((0, 20, 0)), 0, interp="LINEAR")
    cam.key(3.62, O + Vector((0, 2, 0)), O + Vector((0, 20, 0)), 8, interp="LINEAR")
    C.cams["S14"] = cam
    return c, [(3.47, 3.62)]

def build_S15(C, i):
    """Long flight through a block tunnel toward the glowing core, energy wisps, debris."""
    c = new_coll("S15_Flight", C.root); O = Vector((i * SET_SPACING, 0, 0)); rng = random.Random(15)
    wall = [M_pbr("S15_W1", (0.01, 0.02, 0.07), 0.25, 0.6), M_pbr("S15_W2", (0.015, 0.035, 0.12), 0.3, 0.5),
            M_rimlit("S15_W3", (0.01, 0.03, 0.1), (0.05, 0.25, 1.0), 2.0, 0.3, 0.4)]
    glow = M_emit("S15_WGlow", (0.03, 0.2, 1.0), 6)
    # tunnel walls: blocks arranged on a square cross-section, varying inset
    R = 9.0
    for k in range(900):
        y = rng.uniform(-10, 150)
        side = rng.randint(0, 3); u = rng.uniform(-R, R)
        inset = rng.uniform(0, 1.6)
        sz = (rng.uniform(1, 3), rng.uniform(1, 5), rng.uniform(1, 3))
        if side == 0: p = (u, y, -R + inset)
        elif side == 1: p = (u, y, R - inset)
        elif side == 2: p = (-R + inset, y, u)
        else: p = (R - inset, y, u)
        m = glow if rng.random() < 0.07 else rng.choice(wall)
        box(f"S15_B{k}", c, sz, O + Vector(p), m)
    # the core: blinding orb + diamond cage
    core = obj("S15_Core", mesh_sphere(1, 32, 16), c, O + Vector((0, 120, 0)), scale=(5, 5, 5), mat=M_emit("S15_CoreM", ICE, 22))
    halo = obj("S15_Halo", mesh_sphere(1, 32, 16), c, O + Vector((0, 120, 0)), scale=(11, 11, 11), mat=M_ghost("S15_HaloM", (0.05, 0.3, 1.0), 0.3, 6))
    dia = obj("S15_Diamond", mesh_square_ring(22, 0.6), c, O + Vector((0, 112, 0)), (0, 45, 0), mat=M_emit("S15_DiaM", (0.6, 0.8, 1.0), 20))
    dia.rotation_mode = "XYZ"; K(dia, "rotation_euler", 3.62, (0, math.radians(45), 0)); K(dia, "rotation_euler", 6.0, (0, math.radians(110), 0))
    shard = [M_emit("S15_Shard", ICE, 15), M_pbr("S15_ShardD", (0.02, 0.04, 0.15), 0.2, 0.6)]
    for k in range(90):
        a = rng.uniform(0, 2 * math.pi); r = rng.uniform(5, 12)
        s = rng.uniform(0.3, 1.4)
        o = obj(f"S15_Sh{k}", mesh_box((1, 1, 1)), c, O + Vector((math.cos(a) * r, 120 + rng.uniform(-6, 4), math.sin(a) * r)), scale=(s, s, s), mat=rng.choice(shard))
        o.rotation_euler = (rng.uniform(0, 6), rng.uniform(0, 6), rng.uniform(0, 6)); K(o, "rotation_euler", 3.62)
        o.rotation_euler = (o.rotation_euler[0] + 3, o.rotation_euler[1] + 2, o.rotation_euler[2]); K(o, "rotation_euler", 6.0)
    # floating debris along the path
    deb = [M_pbr("S15_Deb", (0.02, 0.03, 0.08), 0.3, 0.5), M_emit("S15_DebG", (0.3, 0.55, 1.0), 10)]
    for k in range(160):
        p = O + Vector((rng.uniform(-7, 7), rng.uniform(0, 110), rng.uniform(-7, 7)))
        s = rng.uniform(0.08, 0.5)
        o = obj(f"S15_D{k}", mesh_box((1, 1, 1)), c, p, scale=(s, s, s), mat=deb[0 if rng.random() < 0.7 else 1])
        K(o, "location", 3.62); K(o, "rotation_euler", 3.62)
        o.location = p + Vector((rng.uniform(-1, 1), rng.uniform(-3, 0), rng.uniform(-1, 1)))
        o.rotation_euler = (rng.uniform(0, 6), rng.uniform(0, 6), 0); K(o, "location", 6.0); K(o, "rotation_euler", 6.0)
    # energy wisps (flame-like swirling ribbons around the flight path)
    wm = M_emit("S15_Wisp", (0.03, 0.2, 1.0), 5); wm2 = M_emit("S15_Wisp2", (0.35, 0.6, 1.0), 8)
    swirl = empty("S15_Swirl", c, O + Vector((0, 0, 0))); swirl.rotation_mode = "XYZ"
    for k in range(34):
        y0 = rng.uniform(15, 110); r = rng.uniform(3.8, 5.6); a0 = rng.uniform(0, 2 * math.pi)
        pts = []
        for j in range(26):
            a = a0 + j * 0.16
            pts.append((math.cos(a) * r, y0 + j * rng.uniform(0.25, 0.6), math.sin(a) * r + math.sin(j * 0.5) * 0.4))
        w = curve_obj(f"S15_Wisp{k}", c, pts, wm if k % 3 else wm2, bevel=0, extrude=rng.uniform(0.03, 0.15))
        w.parent = swirl; w.data.twist_mode = "MINIMUM"
    swirl.location = O
    K(swirl, "rotation_euler", 3.62, (0, 0, 0)); K(swirl, "rotation_euler", 6.0, (0, math.radians(-220), 0))
    # character flying (back-lit, dark with rim), hair ribbon trails
    av = Avatar("S15_Av", c, O + Vector((0, 6, 0)), "dark", "open")
    av.root.rotation_euler = (0, 0, math.radians(180))
    path = [(3.62, Vector((-1.5, 8, -1)), "fly", (0, 0, 180)), (4.4, Vector((-0.5, 34, -0.2)), "fly2", (0, 14, 180)),
            (5.2, Vector((0.4, 60, 0.4)), "fly", (0, -10, 175)), (6.0, Vector((0.0, 86, 0.0)), "fly2", (0, 6, 182))]
    for t, pos, pose, rot in path:
        av.pose(t, P(pose, root_loc=O + pos, root_rot=rot))
    C._s15_path = path
    trm = M_streak("S15_Trail", (0.1, 0.35, 1.0), 9, "Z")
    for k, (dx, dz) in enumerate(((-0.6, 0.0), (0.6, 0.0), (0.0, 0.8))):
        tr = obj(f"S15_Trail{k}", mesh_plane(0.1, 7, (0, 0, -3.5)), c, (dx, -0.2, 1.0 + dz), (0, 0, 0), mat=trm, parent=av.torso)
    # lights: the core lights the tunnel
    point_light("S15_CoreL", c, O + Vector((0, 110, 0)), (0.4, 0.6, 1.0), 2.5e5, 5)
    for k in range(7):
        point_light(f"S15_Tun{k}", c, O + Vector((rng.uniform(-3, 3), 8 + k * 15, rng.uniform(-3, 3))), (0.05, 0.25, 1.0), 2500, 3)
    obj("S15_Glow", mesh_plane(60, 60), c, O + Vector((0, 135, 0)), mat=M_emit("S15_GlowM", (0.05, 0.3, 1.0), 4))
    pl = point_light("S15_Follow", c, O + Vector((0, 10, 3)), (0.35, 0.55, 1.0), 2500, 1)
    K(pl, "location", 3.62, O + Vector((1.5, 12, 3))); K(pl, "location", 6.0, O + Vector((1.5, 92, 3)))
    cam = Cam("CAM_S15", c, 26, 400)
    # follow-cam locked to the flight path (behind / left / above), looking past her into the core
    cam.key(3.62, O + Vector((-4.0, -4, 2.2)), O + Vector((0, 40, -0.5)), -10, interp="BEZIER")
    for (t, pos, _, _), off, look, roll in zip(C._s15_path[1:], ((-3.4, -7, 1.6), (-3.0, -7.5, 1.2), (-2.6, -8, 1.0)),
                                              ((1.5, 25, -0.5), (1.0, 28, -0.4), (0.0, 34, 0.0)), (-8, 6, 14)):
        cam.key(t, O + pos + Vector(off), O + pos + Vector(look), roll, interp="BEZIER")
    cam.shake(3.62, 6.0, 0.06, 0.6, seed=15, every=2)
    C.cams["S15"] = cam
    return c, [(3.62, 6.0)]

def build_S16(C, i):
    """Final slash: vertical pink line + horizontal blue-white beam, debris, whiteout."""
    c = new_coll("S16_Slash", C.root); O = Vector((i * SET_SPACING, 0, 0)); rng = random.Random(16)
    wm = M_gridwall("S16_Wall", (0.04, 0.08, 0.2), (0.3, 0.55, 1.0), 0.3, 3)
    for k in range(40):
        box(f"S16_W{k}", c, (rng.uniform(2, 6), rng.uniform(2, 6), rng.uniform(2, 10)),
            O + Vector((rng.uniform(-20, 20), rng.uniform(10, 30), rng.uniform(-8, 10))), wm)
    vline = obj("S16_VLine", mesh_plane(0.12, 40), c, O + Vector((0.5, 4, 0)), (0, -12, 0), mat=M_emit("S16_VLineM", (1.0, 0.45, 0.85), 60))
    vglow = obj("S16_VGlow", mesh_plane(1.2, 40), c, O + Vector((0.5, 4.1, 0)), (0, -12, 0), mat=M_streak("S16_VGlowM", PINK, 15, "X"))
    beam = obj("S16_Beam", mesh_cyl(1, 1, 24), c, O + Vector((0, 6, -0.6)), (0, 90, -8), mat=M_emit("S16_BeamM", (0.6, 0.8, 1.0), 18))
    beamh = obj("S16_BeamHalo", mesh_cyl(1, 1, 24), c, O + Vector((0, 6.2, -0.6)), (0, 90, -8), mat=M_ghost("S16_BeamHaloM", (0.05, 0.25, 1.0), 0.5, 6))
    for o in (vline, vglow):
        K(o, "scale", 6.0, (1, 1, 0.0)); K(o, "scale", 6.06, (1, 1, 1.0), interp="BEZIER"); K(o, "scale", 6.4, (2.5, 1, 1.0))
    for o, w in ((beam, 0.45), (beamh, 1.3)):
        K(o, "scale", 6.05, (0.0, 0.0, 0.0)); K(o, "scale", 6.15, (w, w, 70), interp="BEZIER"); K(o, "scale", 6.4, (w * 1.8, w * 1.8, 80))
    dm = [M_pbr("S16_Deb", (0.02, 0.03, 0.08), 0.3, 0.5), M_emit("S16_DebG", ICE, 15)]
    for k in range(90):
        o = obj(f"S16_D{k}", mesh_box((1, 1, 1)), c, O + Vector((0.5, 5, 0)), mat=rng.choice(dm))
        s = rng.uniform(0.1, 0.6); o.scale = (s, s, s)
        K(o, "location", 6.05)
        o.location = O + Vector((rng.uniform(-12, 12), rng.uniform(0, 14), rng.uniform(-8, 8))); o.rotation_euler = (rng.uniform(0, 6), rng.uniform(0, 6), 0)
        K(o, "location", 6.4); K(o, "rotation_euler", 6.4)
    av = Avatar("S16_Av", c, O + Vector((-6, 3, -1)), "dark", "open")
    av.pose(6.0, P("slash", root_loc=O + Vector((-7, 3, -1)), root_rot=(0, 0, -100)))
    av.pose(6.12, P("slash", armR=(-80, 0, -60), root_loc=O + Vector((4, 4, -0.5)), root_rot=(0, 0, -90)))
    av.pose(6.4, P("slash", armR=(-70, 0, -80), root_loc=O + Vector((7, 5, -0.3)), root_rot=(0, 0, -85)))
    point_light("S16_L", c, O + Vector((0.5, 3, 0)), (0.6, 0.75, 1.0), 8000, 2)
    point_light("S16_P", c, O + Vector((0.5, 2, 2)), (1.0, 0.4, 0.8), 2000, 1)
    cam = Cam("CAM_S16", c, 22)
    cam.key(6.0, O + Vector((-1.5, -9, 0.5)), O + Vector((0.5, 6, 0)), 14, interp="LINEAR")
    cam.key(6.4, O + Vector((-0.5, -6, 0.2)), O + Vector((0.5, 6, 0)), 22, interp="LINEAR")
    cam.shake(6.05, 6.4, 0.25, 3, seed=16)
    C.cams["S16"] = cam
    return c, [(6.0, 6.4)]

def build_S17(C, i):
    """IMPACT FRAME finale: spear thrust at camera, radial speed wedges, shockwave.
    The compositor turns this into hard black/white flip frames + a red frame."""
    c = new_coll("S17_Impact", C.root); O = Vector((i * SET_SPACING, 0, 0)); rng = random.Random(17)
    av = Avatar("S17_Av", c, O + Vector((0, 6, 0.4)), "dark", "smirk")
    av.root.rotation_euler = (0, 0, math.radians(-20))
    av.pose(6.40, P("thrust", armR=(-90, 0, 10)))
    av.pose(6.80, P("thrust", armR=(-92, 0, 12), torso=(26, 0, -38)))
    av.pose(7.70, P("thrust", armR=(-94, 0, 14), torso=(28, 0, -40)))
    # radial speed wedges (dark slivers + bright slivers) converging on the spear tip
    wm_d = M_emit("S17_WedgeDark", (0.0, 0.0, 0.0), 0)
    wm_l = M_streak("S17_WedgeLight", (0.8, 0.9, 1.0), 25, "Z")
    piv = empty("S17_Burst", c, O + Vector((0.6, 3.5, 2.0))); piv.rotation_mode = "XYZ"
    for k in range(70):
        ln = rng.uniform(8, 30); w = rng.uniform(0.05, 0.9)
        v = [(-w, 0, rng.uniform(1.5, 4)), (w, 0, rng.uniform(1.5, 4)), (0, 0, ln)]
        me = mesh_from(f"S17_Wg{k}", v, [(0, 1, 2)])
        obj(f"S17_Wedge{k}", me, c, (0, rng.uniform(0.5, 6), 0), (0, rng.uniform(0, 360), 0), mat=wm_l if k % 3 == 0 else wm_d, parent=piv)
    K(piv, "rotation_euler", 6.40, (0, 0, 0)); K(piv, "rotation_euler", 7.70, (0, math.radians(30), 0))
    K(piv, "scale", 6.40, (0.6, 1, 0.6)); K(piv, "scale", 6.55, (1.1, 1, 1.1), interp="BEZIER"); K(piv, "scale", 7.70, (1.3, 1, 1.3))
    # shockwave ring + core flash at the tip
    ring = obj("S17_Shock", mesh_annulus(0.93, 1.0), c, O + Vector((0.6, 4.5, 2.2)), mat=M_emit("S17_ShockM", (0.6, 0.8, 1.0), 20))
    K(ring, "scale", 6.40, (0.2, 0.2, 1)); K(ring, "scale", 6.9, (9, 9, 1), interp="BEZIER"); K(ring, "scale", 7.7, (14, 14, 1))
    core = obj("S17_Core", mesh_sphere(1, 32, 16), c, O + Vector((0.2, 0.2, 2.3)), mat=M_emit("S17_CoreM", WHITE, 30))
    K(core, "scale", 6.40, (0.15, 0.15, 0.15)); K(core, "scale", 6.5, (0.45, 0.45, 0.45), interp="BEZIER"); K(core, "scale", 7.2, (0.3, 0.3, 0.3)); K(core, "scale", 7.35, (1.2, 1.2, 1.2)); K(core, "scale", 7.7, (2.0, 2.0, 2.0))
    cube_field("S17_Deb", c, 80, O + Vector((0, 6, 2)), (10, 6, 7), (0.1, 0.6), [M_emit("S17_DebM", ICE, 12), M_pbr("S17_DebD", (0.02, 0.03, 0.08), 0.3, 0.5)], rng)
    bgm = M_emit("S17_BGM", (0.02, 0.12, 1.0), 9)
    obj("S17_BG", mesh_plane(80, 50), c, O + Vector((0, 30, 2)), mat=bgm)
    bgs = [n for n in bgm.node_tree.nodes if n.type == "EMISSION"][0].inputs["Strength"]
    K(bgs, "default_value", 7.18, 9 * EMIT, "CONSTANT", idblock=bgm.node_tree)    # bright for the B/W threshold
    K(bgs, "default_value", 7.20, 1.6 * EMIT, "LINEAR", idblock=bgm.node_tree)    # deep blue once colour returns
    point_light("S17_Key", c, O + Vector((1, 2, 3)), (0.6, 0.75, 1.0), 3000, 1)
    point_light("S17_Back", c, O + Vector((-2, 10, 5)), (0.3, 0.5, 1.0), 6000, 2)
    cam = Cam("CAM_S17", c, 26)
    cam.key(6.40, O + Vector((1.6, -3.5, 1.4)), O + Vector((0, 6, 2.3)), -14, interp="LINEAR")
    cam.key(6.80, O + Vector((1.4, -4.3, 1.3)), O + Vector((0, 6, 2.3)), -10, interp="LINEAR")
    cam.key(7.70, O + Vector((1.2, -5.2, 1.2)), O + Vector((0, 6, 2.3)), -6, interp="LINEAR")
    cam.shake(6.40, 6.85, 0.22, 3.5, seed=17)
    C.cams["S17"] = cam
    return c, [(6.40, 7.70)]

# =========================================================== COMPOSITOR =====
def build_compositor(sc):
    ng = bpy.data.node_groups.new("ULT_Compositor", "CompositorNodeTree")
    sc.compositing_node_group = ng
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    N = ng.nodes; L = ng.links
    def n(t, x, y, label=None, **inp):
        nd = N.new(t); nd.location = (x, y)
        if label: nd.label = label; nd.name = label
        for k, v in inp.items():
            nd.inputs[k.replace("_", " ")].default_value = v
        return nd
    rl = n("CompositorNodeRLayers", -1400, 0)
    # --- bloom
    gl = n("CompositorNodeGlare", -1150, 0, "Bloom")
    gl.inputs["Type"].default_value = "Bloom"
    gl.inputs["Threshold"].default_value = 1.0
    gl.inputs["Strength"].default_value = 0.45
    gl.inputs["Size"].default_value = 0.7
    L.new(rl.outputs["Image"], gl.inputs["Image"])
    gl2 = n("CompositorNodeGlare", -950, 0, "Streaks")
    gl2.inputs["Type"].default_value = "Streaks"
    gl2.inputs["Threshold"].default_value = 6.0
    gl2.inputs["Strength"].default_value = 0.18
    gl2.inputs["Streaks"].default_value = 4
    gl2.inputs["Streaks Angle"].default_value = math.radians(45)
    L.new(gl.outputs["Image"], gl2.inputs["Image"])
    # --- glitch: horizontal band displacement driven by per-frame white noise
    co = n("CompositorNodeImageCoordinates", -950, -400)
    L.new(gl2.outputs["Image"], co.inputs["Image"])
    sepc = n("ShaderNodeSeparateXYZ", -780, -400); L.new(co.outputs["Normalized"], sepc.inputs[0])
    band = n("ShaderNodeMath", -620, -400); band.operation = "MULTIPLY"; band.inputs[1].default_value = 22.0
    L.new(sepc.outputs["Y"], band.inputs[0])
    flo = n("ShaderNodeMath", -470, -400); flo.operation = "FLOOR"; L.new(band.outputs[0], flo.inputs[0])
    st = n("CompositorNodeSceneTime", -620, -560)
    comb = n("ShaderNodeCombineXYZ", -320, -450); L.new(flo.outputs[0], comb.inputs["X"]); L.new(st.outputs["Frame"], comb.inputs["Y"])
    wn = n("ShaderNodeTexWhiteNoise", -170, -450); wn.noise_dimensions = "3D"; L.new(comb.outputs[0], wn.inputs["Vector"])
    gate = n("ShaderNodeMath", -20, -400); gate.operation = "GREATER_THAN"; gate.inputs[1].default_value = 0.72
    L.new(wn.outputs["Value"], gate.inputs[0])
    sepn = n("ShaderNodeSeparateColor" if False else "CompositorNodeSeparateColor", -20, -560); L.new(wn.outputs["Color"], sepn.inputs[0])
    off = n("ShaderNodeMath", 130, -520); off.operation = "SUBTRACT"; off.inputs[1].default_value = 0.5; L.new(sepn.outputs["Green"], off.inputs[0])
    gm = n("ShaderNodeMath", 280, -450); gm.operation = "MULTIPLY"; L.new(gate.outputs[0], gm.inputs[0]); L.new(off.outputs[0], gm.inputs[1])
    gamt = n("ShaderNodeValue", 130, -650, "GlitchAmount"); gamt.outputs[0].default_value = 0.0
    gpx = n("ShaderNodeMath", 430, -500); gpx.operation = "MULTIPLY"; L.new(gm.outputs[0], gpx.inputs[0]); L.new(gamt.outputs[0], gpx.inputs[1])
    dv = n("ShaderNodeCombineXYZ", 580, -500); L.new(gpx.outputs[0], dv.inputs["X"])
    disp = n("CompositorNodeDisplace", 750, 0); L.new(gl2.outputs["Image"], disp.inputs["Image"]); L.new(dv.outputs[0], disp.inputs["Displacement"])
    # --- RGB split (chromatic aberration)
    sep = n("CompositorNodeSeparateColor", 920, 0); L.new(disp.outputs[0], sep.inputs[0])
    ca = n("ShaderNodeValue", 920, -250, "RGBSplit"); ca.outputs[0].default_value = 2.0
    neg = n("ShaderNodeMath", 1060, -250); neg.operation = "MULTIPLY"; neg.inputs[1].default_value = -1; L.new(ca.outputs[0], neg.inputs[0])
    tR = n("CompositorNodeTranslate", 1200, 150); L.new(sep.outputs["Red"], tR.inputs["Image"]); L.new(ca.outputs[0], tR.inputs["X"])
    tB = n("CompositorNodeTranslate", 1200, -150); L.new(sep.outputs["Blue"], tB.inputs["Image"]); L.new(neg.outputs[0], tB.inputs["X"])
    for nd in (tR, tB, disp):
        for ax in ("Extension X", "Extension Y"):
            try: nd.inputs[ax].default_value = "Extend"
            except Exception: pass
    cmb = n("CompositorNodeCombineColor", 1380, 0)
    L.new(tR.outputs[0], cmb.inputs["Red"]); L.new(sep.outputs["Green"], cmb.inputs["Green"]); L.new(tB.outputs[0], cmb.inputs["Blue"])
    # --- exposure (flashes / whiteouts)
    ex = n("CompositorNodeExposure", 1550, 0, "Flash"); L.new(cmb.outputs[0], ex.inputs["Image"])
    # --- pink duotone flash
    bw = n("CompositorNodeRGBToBW", 1720, -250); L.new(ex.outputs[0], bw.inputs[0])
    duo = n("ShaderNodeValToRGB", 1880, -250, "DuotoneRamp")
    e = duo.color_ramp.elements
    e[0].position = 0.0; e[0].color = (0.02, 0.06, 0.85, 1)
    e[1].position = 1.0; e[1].color = (1.0, 0.75, 0.85, 1)
    m1 = e.new(0.35); m1.color = (0.08, 0.12, 1.0, 1)
    m2 = e.new(0.6); m2.color = (1.0, 0.12, 0.38, 1)
    L.new(bw.outputs[0], duo.inputs[0])
    mixd = n("ShaderNodeMix", 2100, 0, "Duotone"); mixd.data_type = "RGBA"; mixd.inputs["Factor"].default_value = 0
    L.new(ex.outputs[0], mixd.inputs[6]); L.new(duo.outputs[0], mixd.inputs[7])
    # --- IMPACT FRAME: hard threshold B/W, keyed invert + red variant
    bw2 = n("CompositorNodeRGBToBW", 2100, -400); L.new(rl.outputs["Image"], bw2.inputs[0])
    thr = n("ShaderNodeMath", 2250, -400); thr.operation = "GREATER_THAN"; thr.inputs[1].default_value = 0.45
    L.new(bw2.outputs[0], thr.inputs[0])
    inv = n("ShaderNodeValue", 2250, -600, "ImpactInvert"); inv.outputs[0].default_value = 0
    dif = n("ShaderNodeMath", 2400, -450); dif.operation = "SUBTRACT"; L.new(thr.outputs[0], dif.inputs[0]); L.new(inv.outputs[0], dif.inputs[1])
    ab = n("ShaderNodeMath", 2550, -450); ab.operation = "ABSOLUTE"; L.new(dif.outputs[0], ab.inputs[0])
    red = n("ShaderNodeValue", 2550, -650, "ImpactRed"); red.outputs[0].default_value = 0
    gch = n("ShaderNodeMath", 2700, -600); gch.operation = "MULTIPLY_ADD"; gch.inputs[1].default_value = -0.94; gch.inputs[2].default_value = 1.0
    L.new(red.outputs[0], gch.inputs[0])
    bch = n("ShaderNodeMath", 2700, -750); bch.operation = "MULTIPLY_ADD"; bch.inputs[1].default_value = -0.85; bch.inputs[2].default_value = 1.0
    L.new(red.outputs[0], bch.inputs[0])
    gg = n("ShaderNodeMath", 2850, -550); gg.operation = "MULTIPLY"; L.new(ab.outputs[0], gg.inputs[0]); L.new(gch.outputs[0], gg.inputs[1])
    bb = n("ShaderNodeMath", 2850, -700); bb.operation = "MULTIPLY"; L.new(ab.outputs[0], bb.inputs[0]); L.new(bch.outputs[0], bb.inputs[1])
    icol = n("CompositorNodeCombineColor", 3000, -500)
    L.new(ab.outputs[0], icol.inputs["Red"]); L.new(gg.outputs[0], icol.inputs["Green"]); L.new(bb.outputs[0], icol.inputs["Blue"])
    mixi = n("ShaderNodeMix", 3200, 0, "Impact"); mixi.data_type = "RGBA"; mixi.inputs["Factor"].default_value = 0
    L.new(mixd.outputs[2], mixi.inputs[6]); L.new(icol.outputs[0], mixi.inputs[7])
    # --- vignette
    ell = n("CompositorNodeEllipseMask", 3200, -300)
    ell.inputs["Size"].default_value = (1.25, 1.25)
    vb = n("CompositorNodeBlur", 3380, -300); vb.inputs["Size"].default_value = (300, 300)
    L.new(ell.outputs[0], vb.inputs["Image"])
    vm = n("ShaderNodeMapRange", 3550, -300); vm.inputs["To Min"].default_value = 0.55
    L.new(vb.outputs[0], vm.inputs["Value"])
    vig = n("ShaderNodeMix", 3720, 0, "Vignette"); vig.data_type = "RGBA"; vig.blend_type = "MULTIPLY"; vig.inputs["Factor"].default_value = 1.0
    L.new(mixi.outputs[2], vig.inputs[6]); L.new(vm.outputs[0], vig.inputs[7])
    # --- final fade
    fade = n("CompositorNodeExposure", 3900, 0, "Fade"); L.new(vig.outputs[2], fade.inputs["Image"])
    go = N.new("NodeGroupOutput"); go.location = (4100, 0)
    L.new(fade.outputs[0], go.inputs[0])
    return ng

def animate_compositor(ng):
    N = ng.nodes
    g = N["GlitchAmount"].outputs[0]; ca = N["RGBSplit"].outputs[0]; fl = N["Flash"].inputs["Exposure"]
    duo = N["Duotone"].inputs["Factor"]; imp = N["Impact"].inputs["Factor"]; inv = N["ImpactInvert"].outputs[0]
    red = N["ImpactRed"].outputs[0]; fade = N["Fade"].inputs["Exposure"]; bloom = N["Bloom"].inputs["Strength"]
    def k(sock, t, v, interp="CONSTANT"):
        K(sock, "default_value", t, v, interp, idblock=ng)
    # glitch bursts (pixels of horizontal displacement)
    for t, v in ((0.0, 0), (0.22, 90), (0.29, 0), (0.43, 60), (0.47, 0), (0.60, 40), (0.63, 0), (0.67, 120), (0.70, 0),
                 (0.83, 160), (0.86, 70), (0.89, 140), (0.92, 0), (1.43, 60), (1.47, 0), (1.94, 50), (1.97, 0),
                 (2.70, 80), (2.76, 0), (3.60, 90), (3.66, 0), (5.97, 120), (6.0, 0), (6.05, 150), (6.12, 0),
                 (7.40, 140), (7.47, 0)):
        k(g, t, v)
    # RGB split (pixels)
    for t, v, it in ((0.0, 1.5, "CONSTANT"), (0.22, 10, "LINEAR"), (0.4, 3, "CONSTANT"), (0.83, 14, "CONSTANT"), (0.92, 4, "CONSTANT"),
                     (1.0, 2, "CONSTANT"), (1.63, 4, "CONSTANT"), (2.72, 14, "LINEAR"), (2.95, 6, "LINEAR"), (3.47, 3, "CONSTANT"),
                     (3.62, 6, "LINEAR"), (6.0, 7, "CONSTANT"), (6.05, 12, "LINEAR"), (6.4, 10, "CONSTANT"), (6.4, 0, "CONSTANT"),
                     (7.20, 12, "LINEAR"), (7.70, 3, "CONSTANT")):
        k(ca, t, v, it)
    # exposure flashes
    for t, v, it in ((0.0, 0, "CONSTANT"), (0.22, 1.2, "LINEAR"), (0.27, 0, "CONSTANT"), (0.67, 0.8, "LINEAR"), (0.75, 0.2, "CONSTANT"),
                     (0.83, 0, "CONSTANT"), (1.0, 1.4, "LINEAR"), (1.08, 0, "CONSTANT"), (1.97, 1.0, "LINEAR"), (2.05, 0, "CONSTANT"),
                     (2.79, 0.3, "LINEAR"), (2.83, 1.3, "LINEAR"), (3.0, 0.2, "CONSTANT"), (3.0, 1.2, "LINEAR"), (3.08, 0, "CONSTANT"),
                     (3.47, 1.5, "LINEAR"), (3.55, -0.5, "LINEAR"), (3.62, -2.0, "LINEAR"), (3.80, 0, "CONSTANT"),
                     (5.6, 0, "LINEAR"), (6.0, 0.6, "CONSTANT"), (6.0, 1.5, "LINEAR"), (6.1, 0.2, "LINEAR"), (6.28, 1.0, "LINEAR"), (6.37, 4.0, "CONSTANT"),
                     (6.40, 0, "CONSTANT"), (7.20, 0, "LINEAR"), (7.25, 1.0, "LINEAR"), (7.40, 0.0, "CONSTANT")):
        k(fl, t, v, it)
    # pink duotone flash
    k(duo, 0.0, 0); k(duo, 0.92, 1); k(duo, 1.0, 0)
    # IMPACT FRAMES — black/white flips every 2 frames @30fps, one red frame, hold, then back to colour
    seq = [(6.40, 1, 1, 0), (6.4667, 1, 0, 0), (6.5333, 1, 1, 0), (6.60, 1, 0, 1), (6.6667, 1, 1, 0), (6.7333, 1, 0, 0),
           (6.80, 1, 1, 0), (6.8667, 1, 0, 1), (6.9333, 1, 0, 0), (7.20, 0, 0, 0)]
    for t, on, iv, rd in seq:
        k(imp, t, on); k(inv, t, iv); k(red, t, rd)
    k(imp, 0.0, 0); k(inv, 0.0, 0); k(red, 0.0, 0)
    # bloom punch on flashes
    for t, v in ((0.0, 0.45), (2.83, 0.9), (3.0, 0.45), (6.0, 0.8), (6.40, 0.45), (7.25, 1.0)):
        k(bloom, t, v)
    # fade out
    k(fade, 0.0, 0); k(fade, 7.45, 0, "LINEAR"); k(fade, 7.70, -10, "CONSTANT")

# ================================================================= MAIN =====
def main(out_path=None, sfx=True):
    sc = reset_scene()
    sc.render.fps = FPS; sc.render.fps_base = 1
    sc.frame_start = 1; sc.frame_end = FR(END_TIME)
    sc.render.resolution_x, sc.render.resolution_y = RES; sc.render.resolution_percentage = 100
    sc.render.engine = "BLENDER_EEVEE"
    ee = sc.eevee
    ee.taa_render_samples = EEVEE_SAMPLES
    try:
        ee.use_raytracing = False
        ee.use_shadows = True
    except Exception: pass
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.5
    sc.view_settings.view_transform = "Standard"   # keeps the blues saturated like the reference
    sc.view_settings.look = "None"
    sc.render.film_transparent = False
    w = bpy.data.worlds.new("ULT_World"); sc.world = w
    if w.node_tree is None: w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.0005, 0.001, 0.004, 1); bg.inputs[1].default_value = 1.0
    C = Ctx(); C.cams = {}
    C.root = new_coll("ULT_Shots")
    builders = [build_S01, build_S02, build_S03, build_S06, build_S07, build_S08, build_S09, build_S10,
                build_S11, build_S12, build_S13, build_S14, build_S15, build_S16, build_S17]
    for idx, b in enumerate(builders):
        coll, ranges = b(C, idx)
        for o in list(coll.all_objects):
            if o.get("manual_vis"):
                continue
            kind = o.get("face_kind")
            if kind is None:
                vis(o, ranges)
            else:   # face expression parts: only the avatar's chosen expression renders
                owner = "_".join(o.name.split("_")[:2])
                vis(o, ranges if kind == _avatar_face.get(owner) else [])
    # camera cuts
    for name, t0, t1 in SHOTS:
        key = name.split("_")[0]
        bind(sc, C.cams[key], t0)
    sc.camera = C.cams["S01"].cam
    ng = build_compositor(sc)
    animate_compositor(ng)
    # sound
    if sfx and os.path.exists(SFX_PATH):
        se = sc.sequence_editor_create()
        snd = se.strips.new_sound("ULT_SFX", SFX_PATH, 1, 1)
        sc.render.ffmpeg.audio_codec = "AAC"
    # default output: MP4
    try: sc.render.image_settings.media_type = "VIDEO"   # Blender 5.x
    except Exception: pass
    sc.render.image_settings.file_format = "FFMPEG"
    sc.render.ffmpeg.format = "MPEG4"; sc.render.ffmpeg.codec = "H264"
    sc.render.ffmpeg.constant_rate_factor = "HIGH"
    sc.render.filepath = "//render/RobloxUlt_"
    sc.frame_set(1)
    if out_path:
        bpy.ops.wm.save_as_mainfile(filepath=out_path)
    return sc

# remember which face each avatar uses (populated by Avatar.set_face)
_avatar_face = {}
_orig_set_face = Avatar.set_face
def _set_face(self, kind):
    _orig_set_face(self, kind)
    _avatar_face[self.name] = kind
Avatar.set_face = _set_face

if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = None
    if "--out" in argv:
        out = os.path.abspath(argv[argv.index("--out") + 1])
    main(out)
