#!/usr/bin/env python3
"""The picture that tastes of one ingredient.

A single macro close-up of one ripe strawberry, cut in half, filling the
frame: glossy deep-red flesh, tiny pale achenes, juice shine and water
droplets, one fresh green leaf, on a dark charcoal background with a warm
rim light. No text.

Pure Python 3.13 standard library only. No network, no files read, fully
deterministic (fixed seed, value-noise texture). Writes /output/entry.png.
"""

import math
import os
import struct
import zlib

W = 768
H = 768
OUT = "/output/entry.png"

SEED = 20261123


# ---------------------------------------------------------------- utilities
def clamp(v, lo=0.0, hi=255.0):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(a, b, x):
    if x <= a:
        return 0.0
    if x >= b:
        return 1.0
    t = (x - a) / (b - a)
    return t * t * (3.0 - 2.0 * t)


def hash2(ix, iy, seed=SEED):
    """Deterministic 32-bit integer hash -> float in [0, 1)."""
    h = (ix * 374761393 + iy * 668265263 + seed * 974634211) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return h / 4294967296.0


def vnoise(x, y):
    """Bilinear value noise, deterministic."""
    ix = math.floor(x)
    iy = math.floor(y)
    fx = x - ix
    fy = y - iy
    sx = fx * fx * (3.0 - 2.0 * fx)
    sy = fy * fy * (3.0 - 2.0 * fy)
    a = hash2(ix, iy)
    b = hash2(ix + 1, iy)
    c = hash2(ix, iy + 1)
    d = hash2(ix + 1, iy + 1)
    return lerp(lerp(a, b, sx), lerp(c, d, sx), sy)


def fbm(x, y, octaves=3):
    total = 0.0
    amp = 0.5
    freq = 1.0
    for _ in range(octaves):
        total += amp * vnoise(x * freq, y * freq)
        amp *= 0.5
        freq *= 2.03
    return total


# ---------------------------------------------------------------- image buffer
buf = bytearray(W * H * 3)


def set_px(x, y, r, g, b):
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        buf[i] = int(clamp(r))
        buf[i + 1] = int(clamp(g))
        buf[i + 2] = int(clamp(b))


def get_px(x, y):
    i = (y * W + x) * 3
    return buf[i], buf[i + 1], buf[i + 2]


def add_px(x, y, r, g, b):
    """Additive blend (for glow / rim light)."""
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        buf[i] = int(clamp(buf[i] + r))
        buf[i + 1] = int(clamp(buf[i + 1] + g))
        buf[i + 2] = int(clamp(buf[i + 2] + b))


def blend_px(x, y, r, g, b, a):
    """Alpha blend a colour over the pixel."""
    if 0 <= x < W and 0 <= y < H and a > 0.0:
        i = (y * W + x) * 3
        buf[i] = int(clamp(lerp(buf[i], r, a)))
        buf[i + 1] = int(clamp(lerp(buf[i + 1], g, a)))
        buf[i + 2] = int(clamp(lerp(buf[i + 2], b, a)))


# ---------------------------------------------------------------- background
# Dark charcoal vertical gradient + warm amber glow behind the fruit +
# vignette + fine grain.
for y in range(H):
    fy = y / (H - 1)
    # vertical gradient: warm dark brown-black at top -> near black bottom
    br = lerp(38.0, 14.0, fy)
    bg = lerp(28.0, 10.0, fy)
    bb = lerp(24.0, 10.0, fy)
    row = y * W
    for x in range(W):
        dx = (x - 384.0) / 384.0
        dy = (y - 380.0) / 384.0
        d2 = dx * dx + dy * dy
        # warm glow centred on the fruit
        glow = math.exp(-d2 * 2.6)
        r = br + 96.0 * glow
        g = bg + 42.0 * glow
        b = bb + 16.0 * glow
        # vignette
        vig = 1.0 - 0.42 * smoothstep(0.55, 1.05, math.sqrt(d2))
        # grain
        gr = (hash2(x, y, SEED + 7) - 0.5) * 7.0
        i = (row + x) * 3
        buf[i] = int(clamp(r * vig + gr))
        buf[i + 1] = int(clamp(g * vig + gr))
        buf[i + 2] = int(clamp(b * vig + gr))

# soft contact shadow under the fruit
for y in range(600, 730):
    for x in range(180, 590):
        dx = (x - 384.0) / 210.0
        dy = (y - 668.0) / 52.0
        d2 = dx * dx + dy * dy
        if d2 < 1.0:
            a = (1.0 - d2) * 0.55
            i = (y * W + x) * 3
            buf[i] = int(buf[i] * (1.0 - a))
            buf[i + 1] = int(buf[i + 1] * (1.0 - a))
            buf[i + 2] = int(buf[i + 2] * (1.0 - a))


# ---------------------------------------------------------------- calyx leaves
# Five pointed leaves fanning from the top of the fruit, drawn as rotated
# elongated ellipses with a darker centre vein. Drawn before the body so
# their bases tuck behind the shoulders.
def draw_leaf(cx, cy, length, width, angle_deg, base_col, tip_col):
    ang = math.radians(angle_deg)
    ca, sa = math.cos(ang), math.sin(ang)
    # leaf runs from base (cx, cy) along direction (ca, sa)
    for ly in range(int(cy - length), int(cy + length) + 1):
        for lx in range(int(cx - length), int(cx + length) + 1):
            px = lx - cx
            py = ly - cy
            # rotate into leaf frame: u along leaf, v across
            u = px * ca + py * sa
            v = -px * sa + py * ca
            if u < -6 or u > length:
                continue
            # pointed tip: width shrinks toward both ends, widest at 35%
            t = u / length
            prof = math.sin(math.pi * (0.12 + 0.88 * t)) ** 0.7
            half = width * prof
            if abs(v) > half:
                continue
            edge = abs(v) / max(half, 0.001)
            shade = 1.0 - 0.35 * edge * edge
            # vein: darker line down the centre
            vein = math.exp(-(v * v) / 6.0) * 0.35
            r = lerp(base_col[0], tip_col[0], t) * shade * (1.0 - vein * 0.5)
            g = lerp(base_col[1], tip_col[1], t) * shade * (1.0 - vein * 0.4)
            b = lerp(base_col[2], tip_col[2], t) * shade * (1.0 - vein * 0.5)
            set_px(lx, ly, r, g, b)


# leaf angles: pointing up/out from the crown at (384, 196)
draw_leaf(384, 200, 118, 30, -90, (52, 128, 44), (96, 178, 74))   # centre up
draw_leaf(384, 200, 108, 27, -128, (46, 118, 40), (88, 168, 66))  # left
draw_leaf(384, 200, 108, 27, -52, (46, 118, 40), (88, 168, 66))   # right
draw_leaf(384, 200, 92, 24, -158, (40, 104, 36), (76, 150, 58))   # far left
draw_leaf(384, 200, 92, 24, -22, (40, 104, 36), (76, 150, 58))    # far right
# stem
for sy in range(96, 168):
    for sx in range(378, 391):
        dx = (sx - 384.5) / 6.0
        if dx * dx < 1.0:
            set_px(sx, sy, 96, 122, 52)


# ---------------------------------------------------------------- strawberry body
# Teardrop profile: wide shoulders, tapering to a soft point.
# y runs 168 .. 664; t = (y-168)/496.
def half_width(t):
    # sin profile: 0 at tip, wide through the middle, narrow crown
    return 285.0 * (math.sin(math.pi * (0.08 + 0.92 * t)) ** 1.15)


TOP_Y = 168
BOT_Y = 664

for y in range(TOP_Y, BOT_Y + 1):
    t = (y - TOP_Y) / (BOT_Y - TOP_Y)
    w = half_width(t)
    x0 = int(384 - w)
    x1 = int(384 + w)
    for x in range(x0, x1 + 1):
        u = (x - 384.0) / w            # -1 .. 1 across
        # --- base flesh: deep crimson at the rim, bright red mid, warm
        #     highlight toward the upper-left light
        edge = abs(u)
        # radial-ish depth from the centre of the fruit
        d = math.sqrt(u * u + (t - 0.42) * (t - 0.42) * 1.15)
        base = 1.0 - smoothstep(0.15, 1.0, d)
        r = lerp(122.0, 240.0, base)
        g = lerp(16.0, 58.0, base)
        b = lerp(20.0, 38.0, base)
        # upper-left light: brighter, slightly orange-red
        lx = (x - 300.0) / 260.0
        ly = (y - 300.0) / 300.0
        ld = math.sqrt(lx * lx + ly * ly)
        light = max(0.0, 1.0 - ld)
        r += 56.0 * light
        g += 16.0 * light
        b += 7.0 * light
        # darker rim at the very edge (rounded form)
        rim = smoothstep(0.82, 1.0, edge)
        r = lerp(r, 96.0, rim * 0.75)
        g = lerp(g, 12.0, rim * 0.75)
        b = lerp(b, 16.0, rim * 0.75)
        # pale pink core (cut flesh centre) - big and clearly lighter so
        # the halved, cut face reads at a glance
        cx = (x - 384.0) / 152.0
        cy = (y - 392.0) / 198.0
        cd = cx * cx + cy * cy
        core = max(0.0, 1.0 - cd)
        core = core * core
        r = lerp(r, 250.0, core * 0.58)
        g = lerp(g, 150.0, core * 0.58)
        b = lerp(b, 134.0, core * 0.58)
        # pale central column (the strawberry's heart)
        hx = (x - 384.0) / 56.0
        hy = (y - 400.0) / 150.0
        hd = hx * hx + hy * hy
        heart = max(0.0, 1.0 - hd)
        r = lerp(r, 252.0, heart * 0.30)
        g = lerp(g, 190.0, heart * 0.30)
        b = lerp(b, 172.0, heart * 0.30)
        # fine vertical fibre streaks
        fib = fbm(x * 0.055, y * 0.016, 3) - 0.5
        r += fib * 26.0
        g += fib * 10.0
        b += fib * 8.0
        # tiny juicy speckle
        sp = hash2(x, y, SEED + 31)
        if sp > 0.985:
            r += 26.0
            g += 8.0
        i = (y * W + x) * 3
        buf[i] = int(clamp(r))
        buf[i + 1] = int(clamp(g))
        buf[i + 2] = int(clamp(b))

# warm rim light on the right edge of the fruit
for y in range(TOP_Y, BOT_Y + 1):
    t = (y - TOP_Y) / (BOT_Y - TOP_Y)
    w = half_width(t)
    for x in range(int(384 + w * 0.55), int(384 + w) + 1):
        u = (x - 384.0) / w
        a = (u - 0.55) / 0.45
        a = a * a * 0.45
        add_px(x, y, 255.0 * a, 118.0 * a, 30.0 * a)


# ---------------------------------------------------------------- achenes (seeds)
# Small pale seeds set into the flesh in curved rows, each with a soft
# shadow pit and a bright top edge so they read as embedded.
SEED_ROWS = [
    (0.16, [-0.62, -0.31, 0.0, 0.31, 0.62]),
    (0.28, [-0.72, -0.44, -0.15, 0.15, 0.44, 0.72]),
    (0.40, [-0.78, -0.52, -0.26, 0.0, 0.26, 0.52, 0.78]),
    (0.52, [-0.76, -0.50, -0.24, 0.0, 0.24, 0.50, 0.76]),
    (0.64, [-0.68, -0.42, -0.15, 0.15, 0.42, 0.68]),
    (0.76, [-0.55, -0.28, 0.0, 0.28, 0.55]),
    (0.87, [-0.38, 0.0, 0.38]),
]
for t, us in SEED_ROWS:
    y = TOP_Y + t * (BOT_Y - TOP_Y)
    w = half_width(t)
    for si, u in enumerate(us):
        # deterministic jitter so the rows do not read as a grid
        jx = (hash2(si * 7 + 1, int(t * 100), SEED + 51) - 0.5) * 14.0
        jy = (hash2(si * 3 + 2, int(t * 100), SEED + 53) - 0.5) * 9.0
        sx = 384.0 + u * w + jx
        sy = y + jy
        js = 0.85 + 0.3 * hash2(si * 5 + 3, int(t * 100), SEED + 55)
        rx = 7.5 * js
        ry = 11.0 * js
        # slight tilt following the fruit's curve
        tilt = u * 0.35
        ca, sa = math.cos(tilt), math.sin(tilt)
        for dy in range(-14, 15):
            for dx in range(-11, 12):
                # rotate into seed frame
                ru = dx * ca + dy * sa
                rv = -dx * sa + dy * ca
                d2 = (ru / rx) ** 2 + (rv / ry) ** 2
                if d2 > 1.0:
                    continue
                # shadow pit just below the seed
                if d2 > 0.55:
                    blend_px(int(sx + dx), int(sy + dy), 120, 22, 26, 0.35)
                else:
                    # pale cream seed, brighter at its top
                    top = 1.0 - smoothstep(-ry, ry, rv)
                    r = lerp(238.0, 250.0, top)
                    g = lerp(214.0, 232.0, top)
                    b = lerp(150.0, 178.0, top)
                    blend_px(int(sx + dx), int(sy + dy), r, g, b, 0.92)


# ---------------------------------------------------------------- gloss + juice
# Big soft specular sheen, upper-left of the fruit
for y in range(190, 470):
    for x in range(210, 470):
        dx = (x - 316.0) / 165.0
        dy = (y - 300.0) / 105.0
        d2 = dx * dx + dy * dy
        if d2 < 1.0:
            a = (1.0 - d2) ** 2 * 0.20
            add_px(x, y, 255.0 * a, 235.0 * a, 220.0 * a)
# two crisp specular dots
for (hx, hy, hr) in [(330, 262, 12), (352, 292, 7)]:
    for y in range(hy - hr - 2, hy + hr + 3):
        for x in range(hx - hr - 2, hx + hr + 3):
            d2 = ((x - hx) / hr) ** 2 + ((y - hy) / hr) ** 2
            if d2 < 1.0:
                a = (1.0 - d2) * 0.7
                add_px(x, y, 255.0 * a, 250.0 * a, 245.0 * a)

# juice droplets on the lower-right flesh (small, subtle)
for (dx0, dy0, dr) in [(512, 556, 11), (556, 486, 8)]:
    for y in range(dy0 - dr - 2, dy0 + dr + 3):
        for x in range(dx0 - dr - 2, dx0 + dr + 3):
            d2 = ((x - dx0) / dr) ** 2 + ((y - dy0) / dr) ** 2
            if d2 > 1.0:
                continue
            # droplet: translucent deep red, faint darker rim, bright dot
            rim = smoothstep(0.75, 1.0, math.sqrt(d2))
            pr, pg, pb = get_px(x, y)
            r = lerp(pr * 0.88 + 32.0, pr * 0.68, rim)
            g = lerp(pg * 0.88 + 6.0, pg * 0.68, rim)
            b = lerp(pb * 0.88 + 8.0, pb * 0.68, rim)
            set_px(x, y, r, g, b)
            # specular dot
            sx = dx0 - dr * 0.35
            sy = dy0 - dr * 0.4
            sd2 = ((x - sx) / (dr * 0.32)) ** 2 + ((y - sy) / (dr * 0.32)) ** 2
            if sd2 < 1.0:
                a = (1.0 - sd2) * 0.9
                add_px(x, y, 255.0 * a, 255.0 * a, 255.0 * a)

# faint juice smear highlight low on the fruit
for y in range(520, 640):
    for x in range(300, 470):
        dx = (x - 384.0) / 110.0
        dy = (y - 580.0) / 70.0
        d2 = dx * dx + dy * dy
        if d2 < 1.0:
            a = (1.0 - d2) ** 2 * 0.10
            add_px(x, y, 255.0 * a, 90.0 * a, 70.0 * a)


# ---------------------------------------------------------------- PNG encoder
def chunk(ctype, data):
    c = struct.pack(">I", len(data)) + ctype + data
    c += struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)
    return c


def write_png(path, width, height, rgb):
    # raw scanlines, per-row best filter among None / Sub / Up
    raw = bytearray()
    prev = bytearray(width * 3)
    for y in range(height):
        row = rgb[y * width * 3:(y + 1) * width * 3]
        best = None
        best_score = None
        for ftype in (0, 1, 2):
            if ftype == 0:
                frow = row
            elif ftype == 1:
                frow = bytearray(width * 3)
                for i in range(width * 3):
                    left = row[i - 3] if i >= 3 else 0
                    frow[i] = (row[i] - left) & 0xFF
            else:
                frow = bytearray(width * 3)
                for i in range(width * 3):
                    frow[i] = (row[i] - prev[i]) & 0xFF
            score = 0
            for v in frow:
                score += v if v < 128 else 256 - v
            if best_score is None or score < best_score:
                best_score = score
                best = (ftype, bytes(frow))
        raw.append(best[0])
        raw.extend(best[1])
        prev = bytearray(row)
    comp = zlib.compress(bytes(raw), 9)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)
    return len(png)


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    size = write_png(OUT, W, H, buf)
    print(f"wrote {OUT} {W}x{H} {size} bytes")


if __name__ == "__main__":
    main()
