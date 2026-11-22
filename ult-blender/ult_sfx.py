"""
ROBLOX ULT — procedural SFX track (no samples, 100% synthesized, royalty-free)
Every hit is timed to the shot list in ult_build.py.
    python ult_sfx.py            -> writes ult_sfx.wav (48 kHz stereo)
Needs numpy + scipy.
"""
import numpy as np, os, wave
from scipy import signal

SR = 48000
END = 8.4
HERE = os.path.dirname(os.path.abspath(__file__))
rng = np.random.default_rng(7)
L = np.zeros(int(END * SR)); R = np.zeros(int(END * SR))

def T(d): return np.arange(int(d * SR)) / SR
def noise(d): return rng.standard_normal(int(d * SR))
def sos(kind, f, order=4):
    f = np.atleast_1d(np.clip(f, 20, SR / 2 - 100))
    return signal.butter(order, f if len(f) > 1 else f[0], kind, fs=SR, output="sos")
def lp(x, f, o=4): return signal.sosfilt(sos("lowpass", f, o), x)
def hp(x, f, o=4): return signal.sosfilt(sos("highpass", f, o), x)
def bp(x, f0, f1, o=2): return signal.sosfilt(sos("bandpass", [f0, f1], o), x)
def env(d, a=0.005, decay=0.2, hold=0.0):
    t = T(d); e = np.minimum(t / max(a, 1e-4), 1.0)
    e *= np.where(t < a + hold, 1.0, np.exp(-(t - a - hold) / max(decay, 1e-4)))
    return e
def fade(x, fi=0.003, fo=0.01):
    n = len(x); a = min(n, int(fi * SR)); b = min(n, int(fo * SR))
    x = x.copy()
    if a: x[:a] *= np.linspace(0, 1, a)
    if b: x[-b:] *= np.linspace(1, 0, b)
    return x
def add(x, t, g=1.0, pan=0.0):
    i = int(t * SR); x = x[: max(0, len(L) - i)]
    if i < 0 or len(x) == 0: return
    l = np.cos((pan + 1) * np.pi / 4); r = np.sin((pan + 1) * np.pi / 4)
    if x.ndim == 2:
        L[i:i + len(x)] += x[:, 0] * g; R[i:i + len(x)] += x[:, 1] * g
    else:
        L[i:i + len(x)] += x * g * l * 1.414; R[i:i + len(x)] += x * g * r * 1.414
def norm(x, p=1.0): m = np.max(np.abs(x)) or 1; return x / m * p

def svf_sweep(x, f0, f1, q=4.0, curve=1.0):
    """State-variable band-pass with a swept centre frequency (whooshes, risers)."""
    n = len(x); out = np.empty(n); lo = bpv = 0.0
    fs = f0 * (f1 / f0) ** (np.linspace(0, 1, n) ** curve)
    k = 1.0 / q
    for i in range(n):
        f = 2 * np.sin(np.pi * fs[i] / SR)
        hi = x[i] - lo - k * bpv
        bpv += f * hi; lo += f * bpv
        out[i] = bpv
    return out

def sweep_sine(d, f0, f1, curve=1.0):
    f = f0 * (f1 / f0) ** (np.linspace(0, 1, int(d * SR)) ** curve)
    return np.sin(2 * np.pi * np.cumsum(f) / SR)

# ------------------------------------------------------------- SOUND KIT ---
def whoosh(d, f0=300, f1=3000, q=1.5, curve=1.0, shape=None):
    x = svf_sweep(noise(d), f0, f1, q, curve)
    t = np.linspace(0, 1, len(x))
    e = shape(t) if shape else np.sin(np.pi * t) ** 1.5
    return norm(x * e)

def sub_boom(d=1.2, f0=90, f1=28, click=True):
    x = sweep_sine(d, f0, f1, 0.4) * env(d, 0.002, d * 0.35)
    if click:
        c = hp(noise(0.02), 1500) * env(0.02, 0.0005, 0.004)
        x[: len(c)] += c * 0.6
    return norm(np.tanh(x * 1.8))

def crunch(d=0.5, cutoff=4000):
    x = lp(noise(d), cutoff) * env(d, 0.001, d * 0.18)
    x = np.tanh(x * 6) * 0.7
    return norm(x)

def glitch(d=0.1, seed=0):
    g = np.random.default_rng(seed)
    out = np.zeros(int(d * SR)); i = 0
    while i < len(out):
        seg = int(g.uniform(0.006, 0.025) * SR)
        kind = g.integers(0, 4)
        tt = np.arange(seg) / SR
        if kind == 0: s = np.sign(np.sin(2 * np.pi * g.uniform(80, 900) * tt))          # square buzz
        elif kind == 1: s = g.standard_normal(seg)                                        # noise
        elif kind == 2: s = np.sin(2 * np.pi * g.uniform(1500, 6000) * tt)               # digital beep
        else: s = np.zeros(seg)                                                           # dropout
        s = np.round(s * 6) / 6                                                           # bit-crush
        hold = int(g.integers(1, 8)); s = np.repeat(s[::hold], hold)[:seg]               # sample-rate crush
        out[i:i + seg] = s[: len(out) - i] * g.uniform(0.4, 1.0); i += seg
    return norm(out) * 0.9

def blip(f, d=0.035):
    return np.sin(2 * np.pi * f * T(d)) * env(d, 0.001, 0.012)

def crackle(d, density=60, band=(1800, 9000), seed=1):
    g = np.random.default_rng(seed)
    x = np.zeros(int(d * SR))
    for _ in range(int(density * d)):
        i = g.integers(0, len(x) - 400); n = g.integers(40, 400)
        x[i:i + n] += g.standard_normal(n) * np.exp(-np.arange(n) / (n / 4)) * g.uniform(0.3, 1)
    x = bp(x, *band)
    buzz = np.sign(np.sin(2 * np.pi * 110 * T(d))) * 0.15 * (g.random(len(x)) < 0.0) # placeholder off
    return norm(x + buzz)

def zap(d=0.25, seed=2):
    g = np.random.default_rng(seed)
    t = T(d); f = 180 + 40 * np.sin(2 * np.pi * 37 * t)
    saw = 2 * ((np.cumsum(f) / SR) % 1) - 1
    x = bp(saw + 0.6 * g.standard_normal(len(t)), 600, 7000) * env(d, 0.002, d * 0.4)
    return norm(np.tanh(x * 3))

def ting(f=4200, d=0.9):
    ratios = [1, 2.76, 5.4, 8.93]
    x = sum(np.sin(2 * np.pi * f * r * T(d) + r) * np.exp(-T(d) * (3 + r * 3)) / (1 + r) for r in ratios)
    x[:int(0.002 * SR)] *= np.linspace(0, 1, int(0.002 * SR))
    return norm(x)

def shatter(d=0.45, n=70, seed=3):
    g = np.random.default_rng(seed); x = np.zeros(int(d * SR))
    for _ in range(n):
        f = g.uniform(2500, 9000); dd = g.uniform(0.02, 0.12)
        s = ting(f, dd) * g.uniform(0.2, 1) * np.exp(-g.uniform(0, 1) * 2)
        i = int(g.uniform(0, d * 0.7) ** 1.6 / (d * 0.7) ** 0.6 * SR)
        i = min(i, len(x) - len(s)); x[i:i + len(s)] += s
    x += hp(noise(d), 3000) * env(d, 0.001, 0.08) * 0.8
    return norm(x)

def pad(d, freqs, detune=0.006, bright=2500):
    t = T(d); x = np.zeros(len(t))
    for f in freqs:
        for dt in (-detune, 0, detune):
            ph = rng.uniform(0, 1)
            x += 2 * (((f * (1 + dt)) * t + ph) % 1) - 1
    x = lp(x, bright)
    e = np.minimum(t / (d * 0.3), 1) * np.minimum((d - t) / (d * 0.3), 1)
    return norm(x * e)

def riser(d, f0=150, f1=1800):
    x = sweep_sine(d, f0, f1, 1.6) * 0.5 + svf_sweep(noise(d), f0 * 2, f1 * 4, 2.5, 1.6) * 0.8
    e = np.linspace(0, 1, len(x)) ** 2.2
    return norm(x * e)

def reverse_swell(d):
    x = hp(noise(d), 2500) * np.exp(-T(d)[::-1] * 2.0)
    x = x * np.linspace(0, 1, len(x)) ** 2
    return norm(x)

def slash(d=0.35):
    x = hp(noise(d), 3500) * env(d, 0.0008, 0.03)
    ring = sum(np.sin(2 * np.pi * f * T(d)) * np.exp(-T(d) * 9) for f in (2350, 3510, 5230, 7190))
    w = whoosh(d, 6000, 900, 1.2, 0.5, lambda t: np.exp(-t * 5))
    return norm(x * 1.2 + ring * 0.25 + w * 0.6)

def roar(d, base=55):
    t = T(d)
    x = lp(noise(d), 500) * 0.8 + np.tanh(2 * np.sin(2 * np.pi * base * t) + np.sin(2 * np.pi * base * 1.5 * t)) * 0.4
    trem = 0.75 + 0.25 * np.sin(2 * np.pi * 7 * t)
    return norm(x * trem)

def wind(d, f0=600, f1=1400):
    return norm(svf_sweep(noise(d), f0, f1, 0.9, 1.0) * (0.6 + 0.4 * np.sin(np.linspace(0, 9, int(d * SR)))))

def stereo_reverb(x, decay=0.45, length=1.6, wet=0.3):
    n = int(length * SR); t = np.arange(n) / SR
    irl = rng.standard_normal(n) * np.exp(-t / decay); irr = rng.standard_normal(n) * np.exp(-t / decay)
    irl = lp(irl, 6000); irr = lp(irr, 6000)
    wl = signal.fftconvolve(x, irl)[: len(x)]; wr = signal.fftconvolve(x, irr)[: len(x)]
    s = np.max(np.abs(x)) / max(np.max(np.abs(wl)), 1e-9)
    return wl * s * wet, wr * s * wet

# ============================================================ TIMELINE =====
# 0.00 Arena: energy hum + spear charge
add(lp(noise(0.3), 200) * env(0.3, 0.05, 0.2, 0.1), 0.0, 0.25)
hum = np.sin(2 * np.pi * 220 * T(0.3) + 3 * np.sin(2 * np.pi * 6 * T(0.3))) * np.linspace(0.2, 1, int(0.3 * SR))
add(fade(hum), 0.0, 0.18, 0.1)
add(riser(0.24, 300, 2400), 0.0, 0.35)
# 0.22 Hologram close-up: glitch burst + digital whoomp + data blips + electricity + shimmer
add(glitch(0.09, 1), 0.22, 0.7)
add(sub_boom(0.6, 140, 45), 0.22, 0.7)
add(whoosh(0.35, 3000, 400, 1.5, 0.7, lambda t: np.exp(-t * 4)), 0.22, 0.5, -0.3)
for k in range(26):
    add(blip(rng.uniform(1600, 5200)), 0.24 + k * 0.016 + rng.uniform(0, 0.01), 0.18, rng.uniform(-0.8, 0.8))
add(crackle(0.42, 90, seed=4), 0.26, 0.45, 0.6)
for t in (0.30, 0.38, 0.47, 0.56): add(zap(0.08, int(t * 100)), t, 0.35, 0.7)
add(pad(0.75, [523, 784, 1046, 1568], 0.008, 6000), 0.22, 0.12)
add(glitch(0.04, 2), 0.43, 0.45); add(glitch(0.03, 3), 0.60, 0.4)
# 0.67 Ink splash
splat = lp(noise(0.4), 1800) * env(0.4, 0.002, 0.09)
add(norm(np.tanh(splat * 4)), 0.67, 0.6)
add(sub_boom(0.4, 110, 50, False), 0.67, 0.45)
add(whoosh(0.25, 2500, 300, 1.0, 0.6, lambda t: np.exp(-t * 6)), 0.67, 0.5, 0.3)
# 0.83 Glitch close-up (heavy stutter)
add(glitch(0.09, 5), 0.83, 0.75, -0.2)
# 0.92 Pink flash: reverse swell into stab
add(reverse_swell(0.17), 0.75, 0.4)
add(sub_boom(0.9, 120, 32), 0.92, 0.85)
add(crunch(0.25, 7000), 0.92, 0.55)
# 1.00 Afterimage clones: angelic pad, falling-pixel blips
add(pad(0.6, [440, 659, 880, 1318], 0.01, 4000), 1.0, 0.22)
for k in range(14):
    add(blip(3000 - k * 140, 0.03), 1.02 + k * 0.03, 0.12, rng.uniform(-0.9, 0.9))
add(glitch(0.04, 6), 1.43, 0.4)
# 1.47 Spear swing + blade ring
add(whoosh(0.22, 400, 4000, 1.6, 0.8), 1.45, 0.6, -0.4)
add(ting(2600, 0.6), 1.55, 0.25, -0.2)
# 1.63 Infinite tunnel: deep vwoom + three star glints
add(norm(sweep_sine(0.35, 60, 180) * env(0.35, 0.02, 0.15)), 1.63, 0.5)
add(whoosh(0.34, 200, 900, 2.0), 1.63, 0.35)
for t, f, p in ((1.66, 5200, 0.6), (1.72, 6400, 0.5), (1.78, 4700, 0.7)): add(ting(f, 0.5), t, 0.35, p)
add(glitch(0.03, 7), 1.94, 0.45)
# 1.97 Portal opens: vwomp + crystal shatter
vw = sweep_sine(0.5, 320, 45, 0.5) * env(0.5, 0.005, 0.2)
add(norm(np.tanh(vw * 2)), 1.97, 0.8)
add(shatter(0.45, 80, 9), 1.98, 0.55)
add(stereo_reverb(shatter(0.45, 60, 10), 0.4, 1.0, 0.6)[0], 1.98, 0.3)
# 2.40 Energy ribbons swirl
sw = svf_sweep(noise(0.34), 400, 2400, 3.0) * (0.5 + 0.5 * np.sin(np.linspace(0, 14, int(0.34 * SR))))
add(norm(sw) * np.sin(np.linspace(0, np.pi, len(sw))), 2.40, 0.45, -0.3)
add(crackle(0.3, 70, seed=11), 2.42, 0.3, 0.5)
# 2.72 Dash + 2.83 massive flash boom
add(whoosh(0.2, 300, 6000, 1.3, 1.5, lambda t: t ** 2), 2.63, 0.8)
add(sub_boom(1.4, 100, 26), 2.83, 1.0)
add(crunch(0.6, 9000), 2.83, 0.6)
bl, br = stereo_reverb(crunch(0.6, 9000), 0.5, 1.6, 0.8); add(np.stack([bl, br], 1), 2.83, 0.35)
# 3.00 Hyperspace riser + rushing wind
add(riser(0.48, 180, 2200), 3.0, 0.55)
add(wind(0.47, 500, 3500), 3.0, 0.4)
for k in range(8): add(whoosh(0.08, 2000, 500, 1.0, 1, lambda t: np.exp(-t * 5)), 3.02 + k * 0.055, 0.18, rng.uniform(-1, 1))
# 3.47 Crescent flare ting, then a near-silent dip (like the reference)
add(ting(3300, 0.5), 3.47, 0.45); add(ting(4950, 0.4), 3.47, 0.25)
# 3.62 Into the tunnel: hit + sustained energy roar + wind + crackle + debris
add(sub_boom(0.9, 90, 30), 3.62, 0.8)
add(whoosh(0.4, 3000, 300, 1.0, 0.6, lambda t: np.exp(-t * 3)), 3.62, 0.6)
rr = roar(2.4); rr *= np.minimum(np.linspace(0, 6, len(rr)), 1)
add(rr, 3.62, 0.38)
add(wind(2.38, 400, 2600), 3.62, 0.3, -0.2)
for k in range(10): add(zap(0.12, 30 + k), 3.9 + k * 0.2 + rng.uniform(0, 0.1), 0.22, rng.uniform(-1, 1))
for k in range(22): add(crunch(0.05, 2500), 3.7 + rng.uniform(0, 2.2), 0.12, rng.uniform(-1, 1))
add(riser(0.95, 200, 3000), 5.02, 0.5)
add(pad(1.4, [110, 165, 220, 330], 0.01, 1800), 4.5, 0.2)
# 5.97 hard cut to silence, 6.00 SLASH
L[int(5.965 * SR):int(6.0 * SR)] *= 0.05; R[int(5.965 * SR):int(6.0 * SR)] *= 0.05
add(slash(0.4), 6.0, 0.9, 0.2)
add(sub_boom(1.0, 130, 35), 6.0, 0.8)
beam = lp(noise(0.4), 3000) * env(0.4, 0.02, 0.3, 0.1)
add(norm(np.tanh(beam * 3)), 6.05, 0.5)
add(reverse_swell(0.32), 6.08, 0.5)
# 6.40 IMPACT FRAMES: layered impact + a crunch-stutter on every flip
add(sub_boom(1.6, 85, 22), 6.40, 1.0)
add(crunch(0.5, 10000), 6.40, 0.8)
add(shatter(0.6, 90, 21), 6.41, 0.45)
il, ir = stereo_reverb(crunch(1.0, 10000) + sub_boom(1.0, 85, 22) * 0.5, 0.7, 2.2, 0.9)
add(np.stack([il, ir], 1), 6.40, 0.45)
for t in (6.4667, 6.5333, 6.6667, 6.7333, 6.80, 6.8667):
    add(norm(np.tanh(hp(noise(0.05), 800) * env(0.05, 0.0005, 0.012) * 8)), t, 0.5, rng.uniform(-0.5, 0.5))
add(sub_boom(0.6, 120, 40), 6.60, 0.6)            # red frame thump
tin = np.sin(2 * np.pi * 7400 * T(0.8)) * env(0.8, 0.02, 0.35)
add(tin, 6.93, 0.06)                              # ear ring
# 7.20 colour returns: final blast + reverse tail into fade
add(sub_boom(1.0, 70, 25), 7.20, 0.7)
add(whoosh(0.6, 2500, 200, 0.8, 0.5, lambda t: np.exp(-t * 3)), 7.20, 0.45)
fl, fr = stereo_reverb(crunch(0.3, 6000), 0.6, 1.5, 0.9); add(np.stack([fl, fr], 1), 7.20, 0.3)

# ---------------------------------------------------------------- MASTER ---
st = np.stack([L, R], 1)
st = st - signal.sosfilt(sos("lowpass", 22, 2), st, axis=0)        # DC/rumble trim
pk = np.max(np.abs(st)); st = st / pk * 0.98
st = np.tanh(st * 1.6) / np.tanh(1.6)                              # glue / soft-clip
n_out = int(7.95 * SR); st = st[:n_out]
st[-int(0.25 * SR):] *= np.linspace(1, 0, int(0.25 * SR))[:, None]
pcm = (st * 32767 * 0.95).astype(np.int16)
out = os.path.join(HERE, "ult_sfx.wav")
with wave.open(out, "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
print("wrote", out, f"{len(pcm)/SR:.2f}s")
