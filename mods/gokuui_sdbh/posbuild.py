"""Goku UI (mods/gokuui_sdbh): sons e aura do Heroes reaplicados depois de cada montagem do roster.

O Kit (roster_build.py construir) nao sabe montar bancos de voz nem auras proprias; o gancho que o B3Heroes pos no
fim do construir roda este arquivo:  posbuild.py <pasta _roster> <pasta do mod> <pasta us do jogo>
Usa os dados de extras/ (prontos): os bancos de gritos usa/jpn (fala da ult com os efeitos), as 24 vozes de batalha
(ADX) e a aura (LZX); poe tudo nos primeiros numeros livres de _roster/us e grava as linhas `voces` / `idioma` no bloco
do Goku UI do roster.toml. Tambem roda sozinho:  python -I posbuild.py <pasta _roster>
"""
import json
import os
import re
import shutil
import struct
import sys
import tomllib

ROSTER = os.path.abspath(sys.argv[1])
MOD = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(__file__))
US = sys.argv[3] if len(sys.argv) > 3 else ""
EXTRA = os.path.join(MOD, "extras")
INFO = json.load(open(os.path.join(EXTRA, "sons.json"), encoding="utf-8"))


def count(afs, fallback):
    f = os.path.join(US, afs) if US else ""
    if f and os.path.isfile(f):
        with open(f, "rb") as h:
            head = h.read(8)
        if head[:3] == b"AFS":
            return struct.unpack_from("<I", head, 4)[0]
    return fallback


def next_free(afs, first):
    d = os.path.join(ROSTER, "us", afs)
    used = [int(n) for n in os.listdir(d) if n.isdigit()] if os.path.isdir(d) else []
    return max([first] + [u + 1 for u in used])


def main():
    toml = os.path.join(ROSTER, "roster.toml")
    text = re.sub(r"^(voces|idioma) = .*\n?", "", open(toml, encoding="utf-8").read(), flags=re.M)
    blocks = re.split(r"(?=\n\[\[)", text)            # any [[table]]: the lines must not fall into [[capsula]]
    idx = [i for i, b in enumerate(blocks) if b.lstrip("\n").startswith("[[personaje]]")
           and re.search(r"^id = %d$" % INFO["id"], b, re.M)]
    if not idx:
        print("posbuild Goku UI: id %d nao esta no roster" % INFO["id"])
        return
    n_lang, n_adx = count("lang_usa.afs", INFO["lang"]), count("adx_usa.afs", INFO["adx_first"])
    lang = max(next_free("lang_usa.afs", n_lang), next_free("lang_jpn.afs", n_lang))
    adx = max(next_free("adx_usa.afs", n_adx), next_free("adx_jpn.afs", n_adx))
    for lk in ("usa", "jpn"):
        d = os.path.join(ROSTER, "us", "lang_%s.afs" % lk, str(lang))
        os.makedirs(d, exist_ok=True)
        shutil.copy2(os.path.join(EXTRA, "lang_%s.bin" % lk), os.path.join(d, "geom.bin"))
        for k in range(INFO["adx_count"]):
            d = os.path.join(ROSTER, "us", "adx_%s.afs" % lk, str(adx + k))
            os.makedirs(d, exist_ok=True)
            shutil.copy2(os.path.join(EXTRA, "adx_%s" % lk, "%d.adx" % k), os.path.join(d, "voz.adx"))
    first = INFO["adx_first"]
    voces = [v - first + adx if v >= first else v for v in INFO["voces"]]
    lines = ["voces = [%s]" % ", ".join(str(v) for v in voces), "idioma = [%d, %d]" % (lang, INFO["idioma2"])]
    blocks[idx[0]] = blocks[idx[0]].rstrip("\n") + "\n" + "\n".join(lines) + "\n"
    new = "".join(blocks)
    me = [c for c in tomllib.loads(new)["personaje"] if c.get("id") == INFO["id"]][0]
    assert me.get("idioma") == [lang, INFO["idioma2"]] and len(me.get("voces", [])) == len(voces)
    open(toml, "w", encoding="utf-8").write(new)
    aura = me.get("aura")
    if aura is not None and os.path.isfile(os.path.join(EXTRA, "aura.bin")):
        d = os.path.join(ROSTER, "us", "data_cmn.afs", str(aura))
        os.makedirs(d, exist_ok=True)
        shutil.copy2(os.path.join(EXTRA, "aura.bin"), os.path.join(d, "geom.bin"))
    print("posbuild Goku UI: sons (gritos %d, vozes %d-%d) e aura (%s) aplicados" % (
        lang, adx, adx + INFO["adx_count"] - 1, aura))


main()
