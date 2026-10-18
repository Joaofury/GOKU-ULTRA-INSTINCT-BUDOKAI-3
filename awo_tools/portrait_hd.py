#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""portrait_hd.py - Retrato del select PS2 (B3/IW, #AMT 288x352 8 bpp) -> retrato HD.

Retratos HD = data_cmn 3884-3962 (par por slot: P1 fondo azul / P2 fondo rojo; Krillin
3930/3931; ver docs/03_formatos/MAPA_ROSTER_HD.md §7). Cada uno es un #AZT de 1 textura
con entrada logica 288x352 y un DDS A8R8G8B8 de 512x512 donde la imagen PS2 va ESCALADA
x1.3 (374x458) en la esquina superior izquierda (verificado contra el 3930 nativo:
error medio 2/255). Retratos de IW: DATA_CMN 1001-1086 (Janemba 1047/1048).

  python portrait_hd.py --src-iw 1047 --dst 3930 --mod mi_mod
  python portrait_hd.py --src-file retrato_ps2.bin --dst 3931 --mod mi_mod
  python portrait_hd.py --src-png imagen.png --dst 3930 --mod mi_mod   # cualquier imagen
"""
import argparse
import io
import os
import struct
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from afs_pair import hd, iw, ROOT  # noqa: E402
import amt_ps2  # noqa: E402

XBC = os.path.join(ROOT, "mod center",
                   "Xbox 360 Compression - Decompression tool from the XBOX Development Kit",
                   "xbcompress.exe")
SCALE = 1.3


def ps2_portrait(b):
    a = b[b.find(b"#AMT"):]
    return amt_ps2.decode(a, amt_ps2.entries(a)[0])


def build(dst_entry, img288):
    """Bin HD del retrato `dst_entry` con la imagen 288x352 (RGBA) dada."""
    h = bytearray(hd(dst_entry))
    o = struct.unpack(">I", h[0x20:0x24])[0]
    e = struct.unpack(">3I2H2H7I", h[o:o + 0x30])
    do, ds = e[7], e[8]
    W, H = struct.unpack("<II", h[do + 12:do + 20])[::-1]
    lw, lh = e[5], e[6]
    im = Image.fromarray(img288).convert("RGBA").resize((lw, lh), Image.LANCZOS)
    im = im.resize((int(round(lw * SCALE)), int(round(lh * SCALE))), Image.LANCZOS)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.paste(im, (0, 0))
    px = np.array(canvas)[..., [2, 1, 0, 3]].astype(np.uint8).tobytes()   # BGRA
    assert len(px) == ds - 128
    h[do + 128:do + ds] = px
    return h


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--src-iw", type=int)
    src.add_argument("--src-file")
    src.add_argument("--src-png")
    ap.add_argument("--dst", type=int, required=True)
    ap.add_argument("--mod", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "build", "win-amd64-release", "mods"))
    a = ap.parse_args()
    if a.src_iw is not None:
        img = ps2_portrait(bytes(iw(a.src_iw)))
    elif a.src_file:
        img = ps2_portrait(open(a.src_file, "rb").read())
    else:
        img = np.array(Image.open(a.src_png).convert("RGBA"))
    b = build(a.dst, img)
    dst = os.path.join(a.out, a.mod, "us", "data_cmn.afs", str(a.dst))
    os.makedirs(dst, exist_ok=True)
    raw, out = os.path.join(dst, "_raw.bin"), os.path.join(dst, "geom.bin")
    open(raw, "wb").write(b)
    if os.path.exists(out):
        os.remove(out)
    subprocess.run([XBC, "/N:2048", raw, out], capture_output=True, stdin=subprocess.DEVNULL,
                   env=dict(os.environ, MSYS_NO_PATHCONV="1"))
    os.remove(raw)
    print("retrato %d -> %s (%d B)" % (a.dst, out, os.path.getsize(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
