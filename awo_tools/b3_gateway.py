#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""b3_gateway.py - PASARELA de modelos 3D -> bin #AMB de B3 HD (Vía B, emisión exacta).

Convierte una malla (PS2 #AMO0 vía extract.json, OBJ o glTF 2.0) en el AWG0 de una
PLANTILLA HD (bin #AMB descomprimido), escribiendo ventanas + IB + tabla de draws
con la semántica verificada en juego (2026-10-03):

  * Ventana de 44 B: pos@0 (local del hueso), w@12, bone@16, nrm@20, FFFFFFFF@32, uv@36.
  * `bone` = SLOT DE PALETA (skin_slots.py), no el índice de esqueleto.
  * TABLA DE DRAWS del AWG0 (RE 2026-10-03, este fichero):
      para cada hueso con `arm` (eje+0x34) cuyo bloque tiene part-header (vals[1]):
        header @ AWG0+vals[1] (0x60) = draw #0 del grupo; +0x00 = nº de draws del grupo;
        los draws #1..n-1 siguen a stride 0x60.
      Campos de cada draw (u32 BE salvo indicación):
        +0x24 material (u16 alto)   +0x30 prim (5 = strip skinneado por paleta,
        4 = lista rígida con la matriz del hueso del grupo en c8..c11)
        +0x38 A_start  +0x3C A_count (rango de ventanas)
        +0x40 B_start  +0x44 B_count (rango del IB)   +0x48 flag (u8) + label
    Los draws del AWG0 están en el MISMO ORDEN que las partes del #AMO0 PS2 del mismo
    personaje (Cell F2: 36 = 36) y el material es el índice del par (tex, shader).
  * TABLA DE MATERIALES: AWG0+g(0x20), g(0x24) entradas de 0x50 B: +0x30 textura,
    +0x34 shader.  g(0x18) = nº de texturas del #AZT.

Modos de asignación parte->draw (`--assign`):
  order     parte i -> draw i (PS2 del MISMO personaje que la plantilla; exacto).
  material  por material de la plantilla (fuente con claves (tex,shader) iguales).
  atlas     TODO a un draw skinneado; las texturas de la fuente se empaquetan en la
            textura de ese draw (cualquier modelo 3D; 1 material).
  ps2native PS2 de OTRO personaje con SUS texturas (--textures-from <amb PS2>): su #AMT pasa
            a ser el #AZT; un draw + material por combinacion (tex, shader) de la fuente
            (= (color, rampa) HD); partes rigidas al draw rigido del hueso con el mismo sufijo.
  Huesos: si la fuente usa otro prefijo (JNB_, PKN_...) se mapean POR SUFIJO a la plantilla
  (el juego enlaza animaciones por sufijo), subiendo al padre si el hueso no existe.
  Siempre: soldadura de vertices identicos por draw y la tabla de paleta (AWG0+0x38) se
  conserva pegada al IB (awg_vertex_buffer.grow).

Uso:
  python b3_gateway.py --template <hd.bin> --out <port.bin> (--ps2 x.json | --obj m.obj |
      --gltf m.gltf|.glb) [--assign order|material|multi|atlas|ps2native]
      [--textures-from <amb PS2>] [--aux keep|hide]
      [--fit-height H | --scale S] [--up y|z] [--yaw DEG] [--weight1] [--report r.json]

El resultado es un #AMB DESCOMPRIMIDO: comprimir con `xbcompress /N:2048` e instalar
como override de la entrada AFS del personaje (UN SOLO mod activo por slot).
"""
import argparse
import base64
import json
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from awg_vertex_buffer import AwgVertexBuffer, minv_affine, mvec, be32, set32  # noqa: E402
from skin_slots import SkinSlots  # noqa: E402

DRAW = 0x60
MAT = 0x50
# Ventanas del AWG0 que el combate tolera: 3041 y 3261 (maximo nativo, e366)
# validados; 5148 hace desaparecer el cuerpo skinneado en combate (2026-10-03).
WINDOW_BUDGET = 3261


# =============================================================================
# Plantilla: tabla de draws + materiales + texturas
# =============================================================================
class DrawTable:
    """Draws del AWG0 de la plantilla (orden del fichero == orden de partes PS2)."""

    def __init__(self, avb):
        self.avb = avb
        b, a0 = avb.data, avb.awg0
        g = lambda o: be32(b, a0 + o)
        self.labels = avb.bone_labels()
        axes = a0 + g(0x14)
        self.draws = []
        for bone in range(g(0x10)):
            arm = be32(b, axes + bone * 80 + 0x34)
            if not arm:
                continue
            hdr_rel = be32(b, a0 + arm + 4)
            if not hdr_rel:
                continue
            hdr = a0 + hdr_rel
            n = be32(b, hdr)
            for k in range(n):
                d = hdr + k * DRAW
                self.draws.append({
                    "abs": d, "group_bone": bone, "k": k,
                    "material": be32(b, d + 0x24) >> 16,
                    "prim": be32(b, d + 0x30),
                    "A": (be32(b, d + 0x38), be32(b, d + 0x3C)),
                    "B": (be32(b, d + 0x40), be32(b, d + 0x44)),
                    "label": bytes(b[d + 0x49:d + 0x60]).split(b"\0")[0].decode("latin1"),
                })
        self.n_mat = g(0x24)
        self.n_tex = g(0x18)
        mt = a0 + g(0x20)
        self.mat_base = mt
        self.materials = [{"tex": be32(b, mt + i * MAT + 0x30),
                           "shader": be32(b, mt + i * MAT + 0x34),   # = textura RAMPA toon
                           "flags": (be32(b, mt + i * MAT + 0x38), be32(b, mt + i * MAT + 0x3C))}
                          for i in range(self.n_mat)]

    def set_material(self, mi, tex=None, ramp=None, flags=None):
        b, o = self.avb.data, self.mat_base + mi * MAT
        if tex is not None:
            set32(b, o + 0x30, tex)
        if ramp is not None:
            set32(b, o + 0x34, ramp)
        if flags is not None:
            set32(b, o + 0x38, flags[0])
            set32(b, o + 0x3C, flags[1])

    def skinned(self, d):
        return d["prim"] == 5

    def set_range(self, d, a_start, a_count, b_start, b_count):
        b = self.avb.data
        set32(b, d["abs"] + 0x38, a_start)
        set32(b, d["abs"] + 0x3C, a_count)
        set32(b, d["abs"] + 0x40, b_start)
        set32(b, d["abs"] + 0x44, b_count)


def bone_suffix(label):
    """'XJNB_NLF' -> 'NLF', 'JNB_T_TAIL1' -> 'T_TAIL1' (el juego enlaza animaciones por
    sufijo de hueso: Krillin usa animaciones GOK_* de Goku)."""
    s = label.lstrip("X")
    return s.split("_", 1)[1] if "_" in s else s


def suffix_bonemap(src_labels, src_parents, tmpl_labels):
    """{label fuente: label plantilla} por sufijo; si el sufijo no existe en la plantilla
    se sube por los padres de la FUENTE hasta uno que exista."""
    by_suf = {}
    for t in tmpl_labels:
        by_suf.setdefault(bone_suffix(t), t)
    out = {}
    for i, lab in enumerate(src_labels):
        j, seen = i, set()
        while j >= 0 and j not in seen:
            seen.add(j)
            t = by_suf.get(bone_suffix(src_labels[j]))
            if t:
                out[lab] = t
                break
            j = src_parents[j] if j < len(src_parents) else -1
        else:
            out[lab] = tmpl_labels[0]
    return out


def replace_azt(data, new_azt):
    """Sustituye el hijo #AZT del #AMB raiz por new_azt (los hijos posteriores se mueven)."""
    n, tbl = be32(data, 0x10), be32(data, 0x14)
    kids = [(be32(data, tbl + 16 * k), be32(data, tbl + 16 * k + 4)) for k in range(n)]
    out = bytearray(data[:min(o for o, _ in kids if o)])
    for k, (off, size) in enumerate(kids):
        blob = new_azt if bytes(data[off:off + 4]) == b"#AZT" else bytes(data[off:off + size])
        out += bytes((-len(out)) % 32)
        set32(out, tbl + 16 * k, len(out))
        set32(out, tbl + 16 * k + 4, len(blob))
        out += blob
    out += bytes((-len(out)) % 32)
    return out


def clamp_awg_textures(data, n_tex):
    """Tras cambiar el #AZT: n_tex en +0x18 de cada AWG y materiales fuera de rango
    (AWG auxiliares ocultos que aun apuntan a texturas de la plantilla) -> textura 0."""
    awo = 0x40
    n_awg = be32(data, awo + 0x18)
    tbl = awo + be32(data, awo + 0x1C)
    for i in range(n_awg):
        a = awo + be32(data, tbl + i * 4)
        set32(data, a + 0x18, n_tex)
        mt, nm = a + be32(data, a + 0x20), be32(data, a + 0x24)
        for m in range(min(nm, 256)):
            o = mt + m * MAT
            if be32(data, o + 0x30) >= n_tex:
                set32(data, o + 0x30, 0)
            r = be32(data, o + 0x34)
            if r != 0xFFFFFFFF and r >= n_tex:
                set32(data, o + 0x34, 0xFFFFFFFF)


def hide_aux_awgs(data):
    """Anula el dibujo de los AWG auxiliares (1..n-1: manos/cara HD de la plantilla)
    rellenando su IB con el índice 0 (triángulos degenerados). No mueve bytes."""
    awo = 0x40
    n_awg = be32(data, awo + 0x18)
    tbl = awo + be32(data, awo + 0x1C)
    hidden = 0
    for i in range(1, n_awg):
        a = awo + be32(data, tbl + i * 4)
        ib, sz = a + be32(data, a + 0x30), be32(data, a + 0x34)
        if 0 < sz < 0x100000 and ib + sz <= len(data):
            data[ib:ib + sz] = b"\0" * sz
            hidden += 1
    return hidden


# =============================================================================
# Stripify (mismo algoritmo validado que ports/port_b3_strip.py)
# =============================================================================
def runs_in_order(tris):
    runs, cur = [], None
    for t in tris:
        if cur is None:
            cur = [t[0], t[1], t[2]]
            continue
        s = set(t)
        if len(cur) >= 2 and cur[-2] in s and cur[-1] in s:
            o = [x for x in t if x not in (cur[-2], cur[-1])]
            if o:
                cur.append(o[0])
                continue
        runs.append(cur)
        cur = [t[0], t[1], t[2]]
    if cur:
        runs.append(cur)
    return runs


def strip_tri(seq, i):
    a, b, c = seq[i], seq[i + 1], seq[i + 2]
    return (a, b, c) if i % 2 == 0 else (b, a, c)


def stripify(tris):
    """Lista de triángulos -> UNA tira con winding conservado (degenerados de unión)."""
    out = []
    for r in runs_in_order(tris):
        if not out:
            out.extend(r)
            continue
        # unir: repetir el ultimo y el primero; ajustar paridad para que el
        # primer triangulo de r empiece en posicion par (mismo winding)
        out += [out[-1], r[0]]
        if len(out) % 2 == 1:
            out.append(r[0])
        out.extend(r)
    return out


def check_strip(seq, tris):
    """Verifica que la tira reproduce exactamente el conjunto de triángulos (con winding)."""
    def key(t):
        a, b, c = t
        m = min(range(3), key=lambda i: t[i])
        return t[m:] + t[:m]
    want = {key(tuple(t)) for t in tris if len(set(t)) == 3}
    got = set()
    for i in range(len(seq) - 2):
        t = strip_tri(seq, i)
        if len(set(t)) == 3:
            got.add(key(t))
    return want <= got, len(want - got), len(got - want)


# =============================================================================
# Fuentes -> grupos
#   grupo = {"name", "mat_key", "rigid": label|None, "verts":[...], "tris":[...],
#            "texture": ruta|None}
#   vértice = {"pos","nrm","uv","bone": label|None, "w"}
# =============================================================================
def load_ps2(path):
    ex = json.load(open(path))
    labels = ex["labels"]
    skin = {int(k): v for k, v in ex["skin"].items()}
    groups = []
    for pi, p in enumerate(ex["parts"]):
        pb = int(p.get("bone", 0))
        rigid = labels[pb] if pb else None
        loc, verts = {}, []
        for v in p["verts"]:
            oa = v[0]
            sv = skin.get(oa)
            if rigid:
                bl, w = rigid, 1.0
            elif sv:
                bl = labels[int(sv[0])]
                w = struct.unpack("<f", struct.pack("<I", int(sv[1]) & 0xFFFFFFFF))[0]
            else:
                bl, w = labels[0], 1.0
            loc[len(verts)] = len(verts)
            verts.append({"pos": tuple(v[1:4]), "nrm": tuple(v[4:7]), "uv": tuple(v[7:9]),
                          "bone": bl, "w": w})
        tris = [tuple(t) for t in p["tris"] if max(t) < len(verts)]
        groups.append({"name": "part%02d" % pi, "mat_key": (p["tex"], p["shader"] & 0xFFFFFFFF),
                       "rigid": rigid, "verts": verts, "tris": tris, "texture": None,
                       "ps2": True})
    return groups


def load_obj(path):
    base = os.path.dirname(os.path.abspath(path))
    P, N, T = [], [], []
    mtl_tex, mtl_ramp, mtl_flags, cur_mtl = {}, {}, {}, "default"
    faces = {}

    def parse_mtl(fn):
        cur = None
        for line in open(fn, encoding="utf-8", errors="replace"):
            s = line.strip().split(None, 1)
            if not s:
                continue
            if s[0] == "newmtl":
                cur = s[1].strip()
            elif s[0].lower() == "map_kd" and cur and len(s) > 1:
                mtl_tex[cur] = os.path.join(os.path.dirname(fn), s[1].strip().split()[-1])
            elif s[0].lower() == "map_ka" and cur and len(s) > 1:
                mtl_ramp[cur] = os.path.join(os.path.dirname(fn), s[1].strip().split()[-1])
            elif s[0] == "#" and len(s) > 1 and s[1].startswith("b3_flags") and cur:
                f = s[1].split()
                mtl_flags[cur] = (int(f[1], 16), int(f[2], 16))

    for line in open(path, encoding="utf-8", errors="replace"):
        s = line.split()
        if not s:
            continue
        if s[0] == "v":
            P.append(tuple(float(x) for x in s[1:4]))
        elif s[0] == "vn":
            N.append(tuple(float(x) for x in s[1:4]))
        elif s[0] == "vt":
            T.append((float(s[1]), float(s[2]) if len(s) > 2 else 0.0))
        elif s[0] == "mtllib":
            fn = os.path.join(base, line.split(None, 1)[1].strip())
            if os.path.exists(fn):
                parse_mtl(fn)
        elif s[0] == "usemtl":
            cur_mtl = s[1]
        elif s[0] == "f":
            idx = []
            for c in s[1:]:
                f = c.split("/")
                vi = int(f[0])
                ti = int(f[1]) if len(f) > 1 and f[1] else 0
                ni = int(f[2]) if len(f) > 2 and f[2] else 0
                fix = lambda i, L: (i - 1) if i > 0 else (len(L) + i) if i < 0 else -1
                idx.append((fix(vi, P), fix(ti, T), fix(ni, N)))
            for k in range(1, len(idx) - 1):
                faces.setdefault(cur_mtl, []).append((idx[0], idx[k], idx[k + 1]))
    groups = []
    for mtl, fl in faces.items():
        vmap, verts, tris = {}, [], []
        for f in fl:
            t = []
            for key in f:
                j = vmap.get(key)
                if j is None:
                    j = len(verts)
                    vmap[key] = j
                    vi, ti, ni = key
                    uv = T[ti] if ti >= 0 else (0.0, 0.0)
                    verts.append({"pos": P[vi], "nrm": N[ni] if ni >= 0 else None,
                                  "uv": (uv[0], 1.0 - uv[1]), "bone": None, "w": 1.0})
                t.append(j)
            tris.append(tuple(t))
        groups.append({"name": mtl, "mat_key": mtl, "rigid": None, "verts": verts,
                       "tris": tris, "texture": mtl_tex.get(mtl), "ramp": mtl_ramp.get(mtl),
                       "flags": mtl_flags.get(mtl)})
    return groups


def load_gltf(path):
    """glTF 2.0 (.gltf con buffers externos/base64 o .glb). Lee POSITION/NORMAL/
    TEXCOORD_0/JOINTS_0/WEIGHTS_0 + baseColorTexture. Aplica la jerarquía de nodos."""
    import numpy as np
    raw = open(path, "rb").read()
    bin_chunk = None
    if raw[:4] == b"glTF":
        jl = struct.unpack("<I", raw[12:16])[0]
        js = json.loads(raw[20:20 + jl])
        o = 20 + jl
        if o < len(raw):
            bl = struct.unpack("<I", raw[o:o + 4])[0]
            bin_chunk = raw[o + 8:o + 8 + bl]
    else:
        js = json.loads(raw.decode("utf-8"))
    base = os.path.dirname(os.path.abspath(path))

    def buf(i):
        b = js["buffers"][i]
        uri = b.get("uri")
        if uri is None:
            return bin_chunk
        if uri.startswith("data:"):
            return base64.b64decode(uri.split(",", 1)[1])
        return open(os.path.join(base, uri), "rb").read()
    bufs = {}

    CT = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
    NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

    def acc(i):
        a = js["accessors"][i]
        bv = js["bufferViews"][a["bufferView"]]
        if bv["buffer"] not in bufs:
            bufs[bv["buffer"]] = buf(bv["buffer"])
        data = bufs[bv["buffer"]]
        dt = np.dtype(CT[a["componentType"]])
        nc = NC[a["type"]]
        off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride", 0) or dt.itemsize * nc
        cnt = a["count"]
        arr = np.ndarray((cnt, nc), dtype=dt, buffer=data, offset=off,
                         strides=(stride, dt.itemsize)).astype(np.float64)
        if a.get("normalized") and dt.kind in "iu":
            arr /= float(np.iinfo(dt).max)
        return arr

    def node_mat(n):
        if "matrix" in n:
            return np.array(n["matrix"], float).reshape(4, 4).T
        t = n.get("translation", [0, 0, 0])
        r = n.get("rotation", [0, 0, 0, 1])
        s = n.get("scale", [1, 1, 1])
        x, y, z, w = r
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        M = np.eye(4)
        M[:3, :3] = R * np.array(s)[None, :]
        M[:3, 3] = t
        return M

    nodes = js.get("nodes", [])
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i

    def world(i):
        M = node_mat(nodes[i])
        while i in parent:
            i = parent[i]
            M = node_mat(nodes[i]) @ M
        return M

    def tex_path(mi):
        if mi is None:
            return None
        m = js["materials"][mi]
        t = m.get("pbrMetallicRoughness", {}).get("baseColorTexture")
        if not t:
            return None
        img = js["images"][js["textures"][t["index"]]["source"]]
        if "uri" in img and not img["uri"].startswith("data:"):
            return os.path.join(base, img["uri"])
        # imagen embebida -> volcar a fichero temporal junto a la salida
        if "bufferView" in img:
            bv = js["bufferViews"][img["bufferView"]]
            if bv["buffer"] not in bufs:
                bufs[bv["buffer"]] = buf(bv["buffer"])
            data = bufs[bv["buffer"]][bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]]
        else:
            data = base64.b64decode(img["uri"].split(",", 1)[1])
        fn = os.path.join(base, "_gltf_tex_%d.png" % mi)
        open(fn, "wb").write(data)
        return fn

    groups = []
    for ni, n in enumerate(nodes):
        if "mesh" not in n:
            continue
        skin = js["skins"][n["skin"]] if "skin" in n else None
        jnames = [nodes[j].get("name", "joint%d" % j) for j in skin["joints"]] if skin else None
        W = world(ni)
        for pi, prim in enumerate(js["meshes"][n["mesh"]]["primitives"]):
            if prim.get("mode", 4) != 4:
                continue
            at = prim["attributes"]
            P = acc(at["POSITION"])
            Nn = acc(at["NORMAL"]) if "NORMAL" in at else None
            UV = acc(at["TEXCOORD_0"]) if "TEXCOORD_0" in at else np.zeros((len(P), 2))
            J = acc(at["JOINTS_0"]) if skin and "JOINTS_0" in at else None
            Wt = acc(at["WEIGHTS_0"]) if skin and "WEIGHTS_0" in at else None
            if skin is None:  # malla estática: aplicar la matriz del nodo
                P = (W @ np.c_[P, np.ones(len(P))].T).T[:, :3]
                if Nn is not None:
                    Nn = (W[:3, :3] @ Nn.T).T
            I = acc(prim["indices"]).astype(int).ravel() if "indices" in prim else np.arange(len(P))
            verts = []
            for k in range(len(P)):
                bl, w = None, 1.0
                if J is not None:
                    j = int(np.argmax(Wt[k]))
                    bl, w = jnames[int(J[k][j])], float(Wt[k][j])
                verts.append({"pos": tuple(P[k]), "nrm": tuple(Nn[k]) if Nn is not None else None,
                              "uv": (float(UV[k][0]), float(UV[k][1])), "bone": bl, "w": w})
            tris = [tuple(I[i:i + 3]) for i in range(0, len(I) - 2, 3)]
            groups.append({"name": "%s_%d" % (n.get("name", "mesh%d" % ni), pi),
                           "mat_key": prim.get("material"), "rigid": None, "verts": verts,
                           "tris": tris, "texture": tex_path(prim.get("material"))})
    return groups


# =============================================================================
# Utilidades de geometría
# =============================================================================
def face_normals(groups):
    """Rellena normales ausentes con la media de las normales de cara."""
    for gr in groups:
        if all(v["nrm"] is not None for v in gr["verts"]):
            continue
        acc = [[0.0, 0.0, 0.0] for _ in gr["verts"]]
        for a, b, c in gr["tris"]:
            pa, pb, pc = (gr["verts"][i]["pos"] for i in (a, b, c))
            u = [pb[i] - pa[i] for i in range(3)]
            w = [pc[i] - pa[i] for i in range(3)]
            n = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
            for i in (a, b, c):
                for k in range(3):
                    acc[i][k] += n[k]
        for v, n in zip(gr["verts"], acc):
            if v["nrm"] is None:
                l = math.sqrt(sum(x * x for x in n)) or 1.0
                v["nrm"] = tuple(x / l for x in n)


def transform_groups(groups, up="y", yaw=0.0, scale=None, fit_height=None, template_pts=None):
    """Lleva la fuente al espacio de modelo de la plantilla: eje arriba, giro, escala y
    centrado (pies en el suelo de la plantilla, centro XZ alineado)."""
    import numpy as np
    pts = np.array([v["pos"] for g in groups for v in g["verts"]], float)
    R = np.eye(3)
    if up == "z":  # Z-up (Blender sin conversión) -> Y-up
        R = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    R = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]) @ R
    q = pts @ R.T
    sc = 1.0
    if fit_height and np.ptp(q[:, 1]) > 0:
        sc = fit_height / np.ptp(q[:, 1])
    elif scale:
        sc = scale
    q *= sc
    off = np.zeros(3)
    if template_pts is not None:
        tp = np.asarray(template_pts)
        off[1] = tp[:, 1].min() - q[:, 1].min()
        off[[0, 2]] = (tp[:, [0, 2]].min(0) + tp[:, [0, 2]].max(0)) / 2 - \
                      (q[:, [0, 2]].min(0) + q[:, [0, 2]].max(0)) / 2
    i = 0
    for g in groups:
        for v in g["verts"]:
            v["pos"] = tuple(q[i] + off)
            if v["nrm"] is not None:
                n = R @ np.array(v["nrm"], float)
                v["nrm"] = tuple(n / (np.linalg.norm(n) or 1.0))
            i += 1
    return sc


def template_surface(avb, world, ss):
    """Vértices de la plantilla en model-space (bind) + su hueso de esqueleto."""
    import numpy as np
    pts, bones = [], []
    for w in avb.vertices():
        s = w["bone"] & 0xFF
        if s == 0:
            continue
        sk = ss.bone_of.get(s, 0)
        m = mvec(world[sk], [w["pos"][0], w["pos"][1], w["pos"][2], 1.0])
        pts.append(m[:3])
        bones.append(sk)
    return np.array(pts), np.array(bones)


def skin_by_nearest(groups, tpts, tbones, labels, k=8):
    """Hueso de cada vértice = voto de los k vértices más cercanos de la plantilla
    (vale para cualquier malla sin rig compatible)."""
    import numpy as np
    from scipy.spatial import cKDTree
    tree = cKDTree(tpts)
    for g in groups:
        P = np.array([v["pos"] for v in g["verts"]])
        if not len(P):
            continue
        d, nn = tree.query(P, k=min(k, len(tpts)))
        for v, row, dd in zip(g["verts"], nn, d):
            wts = {}
            for j, dj in zip(np.atleast_1d(row), np.atleast_1d(dd)):
                b = int(tbones[j])
                wts[b] = wts.get(b, 0.0) + 1.0 / (1e-6 + dj)
            v["bone"] = labels[max(wts, key=wts.get)]
            v["w"] = 1.0


# =============================================================================
# Texturas (modo atlas)
# =============================================================================
def resize_rgba(img, size):
    """Redimensiona canal a canal: Pillow remuestrea RGBA PREMULTIPLICADO y borra el
    color donde alpha=0 (las texturas HD usan alpha=0 como mascara, no como
    transparencia)."""
    from PIL import Image
    img = img.convert("RGBA")
    if img.size == tuple(size):
        return img
    return Image.merge("RGBA", [c.resize(size, Image.LANCZOS) for c in img.split()])


def pack_atlas(groups, W, H):
    """Empaqueta las texturas de los grupos en un lienzo WxH (rejilla por filas,
    tamaño proporcional al área UV) y remapea las UV. Devuelve la imagen RGBA."""
    from PIL import Image
    texs = []
    for g in groups:
        img = None
        if g.get("texture") and os.path.exists(g["texture"]):
            img = Image.open(g["texture"]).convert("RGBA")
        texs.append(img)
    n = len(groups)
    cols = max(1, int(math.ceil(math.sqrt(n))))
    rows = int(math.ceil(n / cols))
    cw, ch = W // cols, H // rows
    atlas = Image.new("RGBA", (W, H), (128, 128, 128, 255))
    pad = 2
    for i, (g, img) in enumerate(zip(groups, texs)):
        x0, y0 = (i % cols) * cw, (i // cols) * ch
        if img is not None:
            atlas.paste(resize_rgba(img, (cw - 2 * pad, ch - 2 * pad)), (x0 + pad, y0 + pad))
        else:
            avg = (200, 200, 200, 255)
            atlas.paste(Image.new("RGBA", (cw - 2 * pad, ch - 2 * pad), avg), (x0 + pad, y0 + pad))
        for v in g["verts"]:
            u, t = v["uv"]
            u, t = u - math.floor(u) if not 0 <= u <= 1 else u, t - math.floor(t) if not 0 <= t <= 1 else t
            v["uv"] = ((x0 + pad + u * (cw - 2 * pad)) / W, (y0 + pad + t * (ch - 2 * pad)) / H)
    return atlas


def write_texture(data, tex_index, img):
    """Escribe una imagen RGBA en la textura `tex_index` del #AZT (DXT3, mismo tamaño)."""
    import numpy as np
    sys.path.insert(0, os.path.join(HERE, "..", "mod center hd"))
    from texture_b3 import parse_azt, encode_dxt3
    _, texs = parse_azt(bytes(data))
    t = texs[tex_index]
    rgba = np.array(resize_rgba(img, (t["w"], t["h"])))
    bm = encode_dxt3(rgba)
    if t["size"] - 128 < len(bm) or bytes(data[t["bitmap_abs"] - 128 + 84:t["bitmap_abs"] - 128 + 88]) != b"DXT3":
        raise SystemExit("[X] textura %d no es DXT3 %dx%d (no se puede reescribir en sitio)"
                         % (tex_index, t["w"], t["h"]))
    o = t["bitmap_abs"]
    data[o:o + len(bm)] = bm
    return t["w"], t["h"]


# =============================================================================
# Emisión
# =============================================================================
def assign(groups, table, mode):
    """Devuelve {draw_index: [grupos]}."""
    draws = table.draws
    out = {}
    if mode == "order":
        if len(groups) != len(draws):
            raise SystemExit("[X] --assign order: %d grupos != %d draws de la plantilla"
                             % (len(groups), len(draws)))
        for i, g in enumerate(groups):
            out.setdefault(i, []).append(g)
        return out
    if mode == "atlas":
        body = next(i for i, d in enumerate(draws) if table.skinned(d))
        for g in groups:
            g["rigid"] = None
        out[body] = list(groups)
        return out
    if mode == "ps2native":
        # Fuente PS2 de OTRO personaje con sus propias texturas (#AMT -> #AZT): cada
        # combinacion (tex, shader) de la fuente va a su propio draw skinneado; las
        # partes rigidas (manos/cara L00) al draw rigido del hueso con el mismo sufijo.
        # El material de cada draw se reescribe en emit() con (tex, rampa) de la fuente.
        rigid_draws = {}
        for i, d in enumerate(draws):
            if not table.skinned(d):
                rigid_draws.setdefault(bone_suffix(table.labels[d["group_bone"]]), []).append(i)
        free = [i for i, d in enumerate(draws) if table.skinned(d)]
        combos = {}
        for g in groups:
            if g["rigid"] and rigid_draws.get(bone_suffix(g["rigid"])):
                di = rigid_draws[bone_suffix(g["rigid"])][0]
                out.setdefault(di, []).append(g)
                continue
            g["rigid"] = None
            combos.setdefault(tuple(g["mat_key"]), []).append(g)
        order = sorted(combos.items(), key=lambda kv: -sum(len(g["tris"]) for g in kv[1]))
        if len(order) > len(free):
            print("[!] %d materiales > %d draws skinneados: se fusionan los ultimos"
                  % (len(order), len(free)))
        for k, (_, gs) in enumerate(order):
            out.setdefault(free[min(k, len(free) - 1)], []).extend(gs)
        return out
    if mode == "multi":
        # Un draw skinneado por TEXTURA distinta de la plantilla (la mayor primero);
        # cada material de la fuente recibe su propia textura. Si hay mas materiales
        # que texturas, el ultimo draw se convierte en atlas con el resto.
        sys.path.insert(0, os.path.join(HERE, "..", "mod center hd"))
        from texture_b3 import parse_azt
        _, texs = parse_azt(bytes(table.avb.data))
        slots, seen = [], set()
        for i, d in enumerate(draws):
            tex = table.materials[d["material"]]["tex"]
            if table.skinned(d) and tex not in seen and tex < len(texs):
                seen.add(tex)
                slots.append((texs[tex]["w"] * texs[tex]["h"], i, tex))
        slots.sort(reverse=True)
        mats = {}
        for g in groups:
            g["rigid"] = None
            mats.setdefault(str(g["mat_key"]), []).append(g)
        order = sorted(mats.values(), key=lambda gs: -sum(len(g["tris"]) for g in gs))
        table.tex_jobs = []
        overflow = len(order) > len(slots)
        # con desbordamiento, el atlas va a la textura MAS GRANDE de la plantilla
        own = slots[1:] if overflow else slots
        for k, gs in enumerate(order):
            if k < len(own):
                _, di, tex = own[k]
                out[di] = gs
                table.tex_jobs.append((tex, gs, False))
            else:
                _, di, tex = slots[0]
                out.setdefault(di, []).extend(gs)
        if overflow:
            _, di, tex = slots[0]
            table.tex_jobs.append((tex, out[di], True))
        return out
    # material: clave de la fuente -> material de la plantilla con la misma (tex, shader)
    by_mat = {}
    for i, d in enumerate(draws):
        m = table.materials[d["material"]]
        by_mat.setdefault((m["tex"], m["shader"]), []).append(i)
    used = set()
    fallback = next(i for i, d in enumerate(draws) if table.skinned(d))
    for g in groups:
        cands = [i for i in by_mat.get(tuple(g["mat_key"]) if isinstance(g["mat_key"], (list, tuple))
                                       else (None,), []) if i not in used]
        want_skin = g["rigid"] is None
        pick = None
        for i in cands:
            d = draws[i]
            if table.skinned(d) == want_skin and (want_skin or table.labels[d["group_bone"]] == g["rigid"]):
                pick = i
                break
        if pick is None and cands:
            pick = next((i for i in cands if table.skinned(draws[i])), None)
            if pick is not None:
                g["rigid"] = None
        if pick is None:
            pick = fallback
            g["rigid"] = None
            print("[!] %s: sin draw con su material -> draw %d" % (g["name"], fallback))
        used.add(pick)
        out.setdefault(pick, []).append(g)
    return out


def emit(template_path, groups, out_path, mode="order", aux="keep", weight1=False,
         atlas_size=None, report=None, src_amt=None):
    avb = AwgVertexBuffer.load(template_path)
    table = DrawTable(avb)
    labels = table.labels
    lab_idx = {}
    for i, l in enumerate(labels):
        lab_idx.setdefault(l, i)
    world, parents = avb.bind_worlds()
    invw = [minv_affine(w) for w in world]
    ss = SkinSlots(avb)

    # Huesos con grupo RIGIDO propio (draws prim 4: manos L00, cara, dientes, cola
    # final...). El nativo NUNCA skinnea vertices de strip a esos huesos aunque
    # tengan flag de slot (Cell: CEL_T_TAIL6 = slot 34, sin uso en el nativo; su
    # entrada de paleta no es fiable -> "lineas" en juego). Se suben al ancestro.
    rigid_bones = {d["group_bone"] for d in table.draws if not table.skinned(d)}

    def skin_bone(b):
        seen = set()
        while b in rigid_bones or b not in ss.slot_of:
            if b in seen or b < 0:
                return 0
            seen.add(b)
            p = parents[b] if 0 <= b < len(parents) else -1
            if p < 0:
                break
            b = p
        return ss.effective_bone(b)

    plan = assign(groups, table, mode)
    tex_images, mat_jobs = [], []
    if mode == "multi":
        sys.path.insert(0, os.path.join(HERE, "..", "mod center hd"))
        from texture_b3 import parse_azt
        from PIL import Image
        _, texs = parse_azt(bytes(avb.data))
        for tex, gs, is_atlas in table.tex_jobs:
            W, H = texs[tex]["w"], texs[tex]["h"]
            if is_atlas:
                tex_images.append((tex, pack_atlas(gs, W, H)))
            else:
                src = next((g["texture"] for g in gs if g.get("texture") and os.path.exists(g["texture"])), None)
                img = Image.open(src).convert("RGBA") if src else Image.new("RGBA", (W, H), (200, 200, 200, 255))
                tex_images.append((tex, img))
        # Rampas toon + flags de iluminacion de la fuente (MTL map_Ka / b3_flags, p.ej.
        # un OBJ exportado de otro bin HD). Cada rampa distinta ocupa una textura de la
        # plantilla que no se use como color (primero las rampas de la plantilla).
        color_tex = {tex for tex, _, _ in table.tex_jobs}
        tmpl_ramps = sorted({m["shader"] for m in table.materials
                             if m["shader"] < len(texs) and m["shader"] not in color_tex})
        ramp_free = tmpl_ramps + [x["idx"] for x in sorted(texs, key=lambda x: x["w"] * x["h"])
                                  if x["idx"] not in color_tex and x["idx"] not in tmpl_ramps]
        ramp_slot = {}
        for di, gs in plan.items():
            g0 = next((g for g in gs if g.get("ramp") or g.get("flags")), None)
            if g0 is None:
                continue
            ramp = None
            if g0.get("ramp") and os.path.exists(g0["ramp"]):
                if g0["ramp"] not in ramp_slot and ramp_free:
                    ramp_slot[g0["ramp"]] = ramp_free.pop(0)
                    tex_images.append((ramp_slot[g0["ramp"]], Image.open(g0["ramp"])))
                ramp = ramp_slot.get(g0["ramp"])
            elif g0.get("flags") and g0["flags"][0] & 0xFFFF == 0x1B4:
                ramp = 0xFFFFFFFF
            mat_jobs.append((table.draws[di]["material"], ramp, g0.get("flags")))
    if mode == "atlas":
        d0 = table.draws[next(iter(plan))]
        tex = table.materials[d0["material"]]["tex"]
        sys.path.insert(0, os.path.join(HERE, "..", "mod center hd"))
        from texture_b3 import parse_azt
        _, texs = parse_azt(bytes(avb.data))
        W, H = texs[tex]["w"], texs[tex]["h"]
        atlas = pack_atlas(plan[next(iter(plan))], W, H)

    windows, ib, ranges = [], [], {}
    stats = {"draws": [], "unmapped_bones": set(), "reassigned_to_slot_ancestor": 0}
    for di in sorted(plan):
        d = table.draws[di]
        a_start, b_start = len(windows), len(ib)
        tris = []
        for g in plan[di]:
            base = len(windows)
            rigid = table.skinned(d) is False
            rb = d["group_bone"] if rigid else None
            for v in g["verts"]:
                if rigid:
                    sk, slot = rb, 0
                else:
                    sk = lab_idx.get(v["bone"])
                    if sk is None:
                        stats["unmapped_bones"].add(v["bone"])
                        sk = 0
                    eff = skin_bone(sk)
                    if eff != sk:
                        stats["reassigned_to_slot_ancestor"] += 1
                    sk, slot = eff, ss.slot_of[eff]
                w = 1.0 if (weight1 or rigid) else v["w"]
                windows.append(AwgVertexBuffer.window_from_model(
                    v["pos"], v["nrm"], slot, w, v["uv"], invw[sk]))
            tris += [(a + base, b + base, c + base) for a, b, c in g["tris"]
                     if len({a, b, c}) == 3]
        # SOLDADURA: la fuente repite vertices (la PS2 los duplica por strip; un OBJ
        # por cara). Sin soldar, Cell PS2 sale con 5148 ventanas para 2948 unicas, y
        # pasar del tope del motor hace que en COMBATE desaparezca el cuerpo
        # skinneado (solo quedan las piezas rigidas); el select no lo nota. Bug
        # 2026-10-03, ver WINDOW_BUDGET.
        uniq, new_w, remap = {}, [], {}
        for k, wv in enumerate(windows[a_start:]):
            key = AwgVertexBuffer.pack_window(wv)
            j = uniq.get(key)
            if j is None:
                j = uniq[key] = len(new_w)
                new_w.append(wv)
            remap[a_start + k] = a_start + j
        windows[a_start:] = new_w
        tris = [t for t in ((remap[a], remap[b], remap[c]) for a, b, c in tris)
                if len(set(t)) == 3]
        if d["prim"] == 5:
            seq = stripify(tris)
            ok, miss, extra = check_strip(seq, tris)
            if not ok:
                raise SystemExit("[X] stripify perdió %d triángulos en el draw %d" % (miss, di))
        else:
            seq = [i for t in tris for i in t]
        # B_count = Nº DE PRIMITIVAS (no de indices): strip lee B_count+2 indices,
        # lista lee 3*B_count. Verificado en el nativo: entre strips consecutivos
        # quedan exactamente 2 indices (0+108 -> 110) y las listas ocupan 3*B.
        # Escribir el nº de indices hace que el guest lea el IB del draw siguiente
        # -> triangulos "linea" entre partes (bug visto en juego 2026-10-03).
        n_prim = max(0, len(seq) - 2) if d["prim"] == 5 else len(seq) // 3
        ib += seq
        ranges[di] = (a_start, len(windows) - a_start, b_start, n_prim)
        stats["draws"].append({"draw": di, "label": d["label"], "material": d["material"],
                               "prim": d["prim"], "groups": [g["name"] for g in plan[di]],
                               "verts": len(windows) - a_start, "idx": len(seq)})

    if len(windows) > WINDOW_BUDGET:
        print("[!] %d ventanas en el AWG0 > %d (maximo nativo): en COMBATE el cuerpo "
              "puede desaparecer. Decima la malla de origen." % (len(windows), WINDOW_BUDGET))
    obj = avb
    if len(windows) > avb.n or len(ib) > avb.n_ib:
        obj = avb.grow(max(len(windows), avb.n), max(len(ib), avb.n_ib))
        print("[*] grow: N %d->%d n_ib %d->%d" % (avb.n, obj.n, avb.n_ib, obj.n_ib))
    table = DrawTable(obj)  # offsets de draws: anteriores a la region crecida -> iguales
    for di, d in enumerate(table.draws):
        if di in ranges:
            table.set_range(d, *ranges[di])
        else:
            table.set_range(d, d["A"][0], 0, d["B"][0], 0)
    if aux == "hide":
        n = hide_aux_awgs(obj.data)
        print("[*] AWG auxiliares ocultos: %d" % n)
    if mode == "atlas":
        w, h = write_texture(obj.data, tex, atlas)
        stats["atlas"] = {"texture": tex, "w": w, "h": h}
        atlas.save(os.path.splitext(out_path)[0] + "_atlas.png")
    for tex, img in tex_images:
        w, h = write_texture(obj.data, tex, img)
        stats.setdefault("textures", []).append({"texture": tex, "w": w, "h": h})
    for mi, ramp, flags in mat_jobs:
        table.set_material(mi, ramp=ramp, flags=flags)
        stats.setdefault("materials", []).append({"material": mi, "ramp": ramp, "flags": flags})
    if mode == "ps2native" and src_amt is not None:
        # materiales: uno por combinacion (tex, rampa) de la fuente, en los slots de la
        # plantilla; el draw apunta a su slot (u16 alto de +0x24)
        import amt_ps2
        new_azt = amt_ps2.to_azt(src_amt)
        n_tex = be32(new_azt, 0x10)
        slot_of = {}
        for di in sorted(plan):
            key = tuple(plan[di][0]["mat_key"])
            if key not in slot_of:
                if len(slot_of) >= table.n_mat:
                    raise SystemExit("[X] %d combinaciones de material > %d materiales de la plantilla"
                                     % (len(slot_of) + 1, table.n_mat))
                slot_of[key] = len(slot_of)
            mi = slot_of[key]
            d = table.draws[di]
            set32(obj.data, d["abs"] + 0x24, (mi << 16) | (be32(obj.data, d["abs"] + 0x24) & 0xFFFF))
            tex, ramp = key
            table.set_material(mi, tex=tex if tex < n_tex else 0,
                               ramp=ramp if ramp < n_tex else 0xFFFFFFFF)
        stats["materials_ps2"] = {str(k): v for k, v in slot_of.items()}
        obj.data = replace_azt(obj.data, new_azt)
        clamp_awg_textures(obj.data, n_tex)
        print("[*] #AZT de la fuente: %d texturas, %d materiales" % (n_tex, len(slot_of)))
    obj.emit(out_path, vertices=windows, indices=ib)
    stats["windows"], stats["ib"] = len(windows), len(ib)
    stats["unmapped_bones"] = sorted(str(x) for x in stats["unmapped_bones"])
    print("OK -> %s (ventanas=%d, IB=%d, draws usados=%d/%d, reasignados a ancestro con slot=%d)"
          % (out_path, len(windows), len(ib), len(ranges), len(table.draws),
             stats["reassigned_to_slot_ancestor"]))
    if stats["unmapped_bones"]:
        print("[!] huesos sin equivalente en la plantilla (-> raiz):", stats["unmapped_bones"][:10])
    if report:
        json.dump(stats, open(report, "w"), indent=1)
    return stats


def export_obj(bin_path, obj_path):
    """Exporta el AWG0 de un bin HD a OBJ+MTL+PNG en model-space (bind), un grupo por
    draw y un material por textura. Pensado para editar en Blender y re-importar con
    --obj (ida y vuelta). Usa la semántica verificada (bone = slot, rígidos por grupo)."""
    sys.path.insert(0, os.path.join(HERE, "..", "mod center hd"))
    from texture_b3 import parse_azt
    from PIL import Image
    import io
    avb = AwgVertexBuffer.load(bin_path)
    t = DrawTable(avb)
    world, _ = avb.bind_worlds()
    ss = SkinSlots(avb)
    V, I = avb.vertices(), avb.indices()
    base = os.path.splitext(obj_path)[0]
    name = os.path.basename(base)
    azt_abs, texs = parse_azt(bytes(avb.data))
    used_mat = sorted({d["material"] for d in t.draws if d["B"][1]})
    saved = set()

    def save_tex(ti):
        if ti in saved or ti >= len(texs):
            return
        tx = texs[ti]
        dds = bytes(avb.data[azt_abs + tx["data_off"]:azt_abs + tx["data_off"] + tx["size"]])
        Image.open(io.BytesIO(dds)).convert("RGBA").save("%s_tex%02d.png" % (base, ti))
        saved.add(ti)
    with open(base + ".mtl", "w") as m:
        for mi in used_mat:
            mat = t.materials[mi]
            save_tex(mat["tex"])
            m.write("newmtl m%02d\nKd 1 1 1\nmap_Kd %s_tex%02d.png\n" % (mi, name, mat["tex"]))
            # Extensiones B3 (las lee --obj): rampa toon (textura 64x64 que indica
            # material+0x34) y flags de iluminacion (+0x38/+0x3C; 0x1b4 = sin rampa).
            if mat["shader"] != 0xFFFFFFFF:
                save_tex(mat["shader"])
                m.write("map_Ka %s_tex%02d.png\n" % (name, mat["shader"]))
            m.write("# b3_flags 0x%x 0x%x\n\n" % mat["flags"])
    out = ["mtllib %s.mtl" % name]
    vt = 0
    for di, d in enumerate(t.draws):
        a, n = d["A"]
        s, c = d["B"]
        if not c:
            continue
        seq = I[s:s + c + 2] if d["prim"] == 5 else I[s:s + 3 * c]
        tris = [strip_tri(seq, i) for i in range(len(seq) - 2)] if d["prim"] == 5 else \
            [tuple(seq[i:i + 3]) for i in range(0, len(seq) - 2, 3)]
        tris = [x for x in tris if len(set(x)) == 3]
        used = sorted({k for x in tris for k in x})
        loc = {}
        out.append("g d%02d_%s\nusemtl m%02d" % (di, d["label"], d["material"]))
        for k in used:
            w = V[k]
            sk = ss.bone_of.get(w["bone"] & 0xFF, 0) if d["prim"] == 5 else d["group_bone"]
            p = mvec(world[sk], [w["pos"][0], w["pos"][1], w["pos"][2], 1.0])
            R = world[sk]
            nn = [sum(R[i][j] * w["nrm"][j] for j in range(3)) for i in range(3)]
            out.append("v %.6f %.6f %.6f" % tuple(p[:3]))
            out.append("vt %.6f %.6f" % (w["uv"][0], 1.0 - w["uv"][1]))
            out.append("vn %.6f %.6f %.6f" % tuple(nn))
            vt += 1
            loc[k] = vt
        for x in tris:
            out.append("f " + " ".join("%d/%d/%d" % (loc[k], loc[k], loc[k]) for k in x))
    open(obj_path, "w").write("\n".join(out) + "\n")
    print("OBJ -> %s (%d vértices, materiales %s, texturas %s)" % (obj_path, vt, used_mat, sorted(saved)))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "export-obj":
        export_obj(sys.argv[2], sys.argv[3])
        return 0
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--template", required=True)
    ap.add_argument("--out", required=True)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--ps2")
    src.add_argument("--obj")
    src.add_argument("--gltf")
    ap.add_argument("--assign", choices=["order", "material", "multi", "atlas", "ps2native"])
    ap.add_argument("--textures-from", help="AMB PS2 de la fuente: su #AMT pasa a ser el #AZT "
                    "(modo ps2native, otro personaje con sus texturas)")
    ap.add_argument("--aux", choices=["keep", "hide"], default=None)
    ap.add_argument("--up", choices=["y", "z"], default="y")
    ap.add_argument("--yaw", type=float, default=0.0)
    ap.add_argument("--scale", type=float)
    ap.add_argument("--fit-height", type=float)
    ap.add_argument("--skin", choices=["source", "nearest"], default=None,
                    help="source = huesos de la fuente por label; nearest = transferir de la plantilla")
    ap.add_argument("--bonemap", help="JSON {hueso_fuente: label_plantilla}")
    ap.add_argument("--weight1", action="store_true")
    ap.add_argument("--report")
    a = ap.parse_args()

    src_amt = None
    if a.ps2:
        groups = load_ps2(a.ps2)
        mode, aux, skin = a.assign or "order", a.aux or "keep", a.skin or "source"
        if a.textures_from:
            import amt_ps2
            raw = open(a.textures_from, "rb").read()
            src_amt = raw[amt_ps2.find_amt(raw):]
            mode = a.assign or "ps2native"
            aux = a.aux or "hide"
        tl = AwgVertexBuffer.load(a.template).bone_labels()
        ex = json.load(open(a.ps2))
        if any(l not in tl for l in ex["labels"]) and not a.bonemap:
            bm = suffix_bonemap(ex["labels"], ex.get("parents", []), tl)
            for g in groups:
                if g["rigid"]:
                    g["rigid"] = bm.get(g["rigid"], g["rigid"])
                for v in g["verts"]:
                    v["bone"] = bm.get(v["bone"], v["bone"])
            print("[*] huesos por sufijo: %d/%d con equivalente directo"
                  % (sum(1 for l in ex["labels"] if bone_suffix(l) in {bone_suffix(t) for t in tl}),
                     len(ex["labels"])))
    else:
        groups = load_obj(a.obj) if a.obj else load_gltf(a.gltf)
        mode, aux = a.assign or "multi", a.aux or "hide"
        skin = a.skin or ("source" if a.bonemap else "nearest")
    face_normals(groups)
    print("fuente: %d grupos, %d vértices, %d triángulos"
          % (len(groups), sum(len(g["verts"]) for g in groups), sum(len(g["tris"]) for g in groups)))

    avb = AwgVertexBuffer.load(a.template)
    world, _ = avb.bind_worlds()
    ss = SkinSlots(avb)
    tpts, tbones = template_surface(avb, world, ss)
    if not a.ps2:
        th = float(tpts[:, 1].max() - tpts[:, 1].min())
        sc = transform_groups(groups, a.up, a.yaw, a.scale,
                              a.fit_height or (None if a.scale else th), tpts)
        print("[*] encaje: escala=%.4f (altura plantilla %.2f)" % (sc, th))
    if a.bonemap:
        bm = json.load(open(a.bonemap))
        for g in groups:
            for v in g["verts"]:
                v["bone"] = bm.get(v["bone"], v["bone"])
    if skin == "nearest":
        skin_by_nearest(groups, tpts, tbones, avb.bone_labels())
    emit(a.template, groups, a.out, mode, aux, a.weight1, report=a.report, src_amt=src_amt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
