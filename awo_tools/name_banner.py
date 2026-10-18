#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""name_banner.py - Cambia el ROTULO DE NOMBRE de un personaje en el select (B3 HD).

Los rotulos son texturas de la entrada 2027 (pantalla de seleccion) de los AFS de idioma
(data_usi = ingles US, data_eng, data_fra, data_ger, data_ita, data_spn): #AZT con ~40
texturas de 32 px de alto (indice 25 = COM ... 34 = Krillin, 36 = Piccolo ...; ver
`--list`). Cada textura es DDS sin comprimir A8R8G8B8 (BGRA) o DXT3; se respeta el formato.

El rotulo nuevo se dibuja en el estilo del juego (blanco, contorno negro, Comic Sans Bold)
con la misma caja (alto de mayusculas y ancho) que el original.

  python name_banner.py --list [--afs data_usi]                  # PNG de todos los rotulos
  python name_banner.py --tex 34 --name Janemba --mod mi_mod      # instala en data_usi+data_eng
        [--afs data_usi,data_eng,data_spn] [--entry 2027] [--font ruta.ttf]

Instala `mods/<mod>/us/<afs>/2027/geom.bin` (LZX /N:2048). Si el bin crece por encima del
`to_read` original hace falta el runtime con crecimiento virtual para todos los AFS
(AfsVirtualSize, handback 2026-10-03).
"""
import argparse
import io
import os
import struct
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _has_font(name):
    try:
        ImageFont.truetype(name, 8)
        return True
    except OSError:
        return False

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from afs_pair import hd, ROOT  # noqa: E402

XBC = os.path.join(ROOT, "mod center",
                   "Xbox 360 Compression - Decompression tool from the XBOX Development Kit",
                   "xbcompress.exe")


def textures(b):
    z = b.find(b"#AZT")
    n, idx = struct.unpack(">II", b[z + 0x10:z + 0x18])
    out = {}
    for t in range(n):
        o = struct.unpack(">I", b[z + idx + 4 * t:z + idx + 4 * t + 4])[0]
        if o:
            do, ds = struct.unpack(">II", b[z + o + 20:z + o + 28])
            out[t] = (z + do, ds)
    return out


def decode(b, at, size):
    return np.array(Image.open(io.BytesIO(bytes(b[at:at + size]))).convert("RGBA"))


def render_like(ref, text, font):
    """Rotulo nuevo con la misma caja de texto (alto/ancho) que `ref` (RGBA)."""
    ys, xs = np.where(ref[..., 3] > 40)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    h, w = ref.shape[:2]
    try:
        f = ImageFont.truetype(font, 64)
    except OSError:             # font missing on this PC: any bold system font, then Pillow's
        f = next((ImageFont.truetype(c, 64) for c in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mod center hd", "fonts",
                                               "Roboto-Bold.ttf"), "arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf")
                  if _has_font(c)), None) or ImageFont.load_default()
    tmp = Image.new("RGBA", (64 * len(text) + 40, 120), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((10, 10), text, font=f, fill=(255, 255, 255, 255),
                             stroke_width=7, stroke_fill=(0, 0, 0, 255))
    t = np.array(tmp)
    ty, tx = np.where(t[..., 3] > 40)
    crop = tmp.crop((tx.min(), ty.min(), tx.max() + 1, ty.max() + 1))
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    nw = min(bw, int(crop.width * bh / crop.height))
    crop = crop.resize((nw, bh), Image.LANCZOS)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.alpha_composite(crop, (int(x0 + (bw - nw) / 2), int(y0)))
    return np.array(out)


def find_icons(img):
    """Cajas (x0, y0, x1, y1) de los iconos circulares de una tira de la rueda."""
    al = img[..., 3] > 0
    cols = np.where(al.any(axis=0))[0]
    rows = np.where(al.any(axis=1))[0]
    segs, s0, prev = [], cols[0], cols[0]
    for c in cols[1:]:
        if c != prev + 1:
            segs.append((s0, prev))
            s0 = c
        prev = c
    segs.append((s0, prev))
    return [(a, rows.min(), b, rows.max()) for a, b in segs]


def make_icon(strip, box, face, center, size):
    """Sustituye el interior del icono `box` de `strip` por un recorte cuadrado de
    `face` (centro, lado en px de la fuente); se conserva el aro oscuro del original."""
    x0, y0, x1, y1 = box
    d = x1 - x0 + 1
    cx, cy = center
    src = Image.fromarray(face).convert("RGBA").crop(
        (int(cx - size / 2), int(cy - size / 2), int(cx + size / 2), int(cy + size / 2)))
    inner = np.array(src.resize((d, d), Image.LANCZOS))
    yy, xx = np.mgrid[0:d, 0:d]
    r = np.hypot(xx - (d - 1) / 2, yy - (d - 1) / 2)
    r_in = d / 2 - max(3, d // 18)
    out = strip.copy()
    reg = out[y0:y0 + d, x0:x0 + d]
    m = r < r_in
    reg[m, :3] = inner[m, :3]
    reg[m, 3] = 255
    return out


def write_texture(b, at, size, img):
    hdr = bytes(b[at:at + 128])
    h, w = struct.unpack("<II", hdr[12:20])
    flags, fourcc = struct.unpack("<II", hdr[80:88])
    if fourcc == 0x33545844:          # 'DXT3'
        sys.path.insert(0, os.path.join(HERE, "..", "mod center hd"))
        from texture_b3 import encode_dxt3
        data = encode_dxt3(img)
    else:                             # A8R8G8B8 (masks R=ff0000 ...): bytes BGRA
        data = img[..., [2, 1, 0, 3]].astype(np.uint8).tobytes()
    assert len(data) == size - 128, (len(data), size)
    b[at + 128:at + size] = data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--tex", type=int)
    ap.add_argument("--name")
    ap.add_argument("--mod")
    ap.add_argument("--afs", default="data_usi,data_eng")
    ap.add_argument("--entry", type=int, default=2027)
    ap.add_argument("--font", default="C:/Windows/Fonts/comicbd.ttf")
    ap.add_argument("--icon-tex", type=int, help="tira de iconos de la rueda (3-10)")
    ap.add_argument("--icon-index", type=int, default=0, help="icono dentro de la tira (0-4)")
    ap.add_argument("--icon-iw", type=int, help="retrato IW (DATA_CMN 1001-1086) de donde recortar la cara")
    ap.add_argument("--icon-png", help="imagen de donde recortar la cara")
    ap.add_argument("--icon-crop", default="144,176,180", help="cx,cy,lado del recorte en la fuente")
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "build", "win-amd64-release", "mods"))
    a = ap.parse_args()
    afs_list = [x.strip() for x in a.afs.split(",") if x.strip()]
    if a.list:
        b = bytearray(hd(a.entry, afs_list[0] + ".afs"))
        d = os.path.join(ROOT, "out", "analysis", "name_banners")
        os.makedirs(d, exist_ok=True)
        for t, (at, size) in textures(b).items():
            Image.fromarray(decode(b, at, size)).save(os.path.join(d, "tex%02d.png" % t))
        print("rotulos ->", d)
        return 0
    if a.tex is None or not a.name or not a.mod:
        ap.error("--tex, --name y --mod son obligatorios")
    face = None
    if a.icon_iw is not None:
        from portrait_hd import ps2_portrait
        from afs_pair import iw
        face = ps2_portrait(bytes(iw(a.icon_iw)))
    elif a.icon_png:
        face = np.array(Image.open(a.icon_png).convert("RGBA"))
    for afs in afs_list:
        b = bytearray(hd(a.entry, afs + ".afs"))
        texs = textures(b)
        at, size = texs[a.tex]
        img = render_like(decode(b, at, size), a.name, a.font)
        write_texture(b, at, size, img)
        if face is not None and a.icon_tex is not None:
            at2, size2 = texs[a.icon_tex]
            strip = decode(b, at2, size2)
            cx, cy, side = (float(x) for x in a.icon_crop.split(","))
            box = find_icons(strip)[a.icon_index]
            write_texture(b, at2, size2, make_icon(strip, box, face, (cx, cy), side))
        dst = os.path.join(a.out, a.mod, "us", afs + ".afs", str(a.entry))
        os.makedirs(dst, exist_ok=True)
        raw = os.path.join(dst, "_raw.bin")
        open(raw, "wb").write(b)
        out = os.path.join(dst, "geom.bin")
        if os.path.exists(out):
            os.remove(out)
        subprocess.run([XBC, "/N:2048", raw, out], capture_output=True, stdin=subprocess.DEVNULL,
                       env=dict(os.environ, MSYS_NO_PATHCONV="1"))
        os.remove(raw)
        print("%s.afs #%d tex %d -> '%s' (%d B) -> %s" % (afs, a.entry, a.tex, a.name,
                                                          os.path.getsize(out), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
