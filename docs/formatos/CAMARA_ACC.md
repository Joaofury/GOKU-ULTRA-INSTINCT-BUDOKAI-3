# Cámaras de técnicas: `#ACC` (HD) / `#AMC` (PS2)

RE del 2026-10-06 (exploración `docs/07_ports/GOHAN_FUTURO_EXPLORACION_2026-10-06/05_studio`).
Código: `mod center hd/studio/studio_core.py` (lectura, escritura, validación, glTF).
Comprobado: los **633 clips** de los 38 personajes, en HD y en PS2, se decodifican y se vuelven a
codificar **byte a byte** (`python studio_core.py selftest`).

## Dónde está

Cada personaje tiene un **CAM bin** en `data_cmn.afs` (columna `cam` de
`mod center hd/roster_db.json`; Goku = 288). Es un `#AMB` con 4 hijos:

| Hijo | Tipo | Contenido |
|---|---|---|
| `#ACC` (PS2 `#AMC`) | 5 | **clips de cámara** (este documento) |
| `#ACL` | 6 | stub de 5 B |
| `#CCM` (PS2 `#BCM`) | 0xFFFFFFFF | tabla de combos y entradas (ver `CAPSULAS_B3.md`) |
| `#SPX` | 8 | **guiones** de las técnicas (máquina virtual; little-endian también en la HD) |

- HD = big-endian; PS2 = little-endian. El `#ACC` pasa de uno a otro girando palabras de 32 bits.
- Alineación de los hijos del `#AMB`: 32 B en HD, 16 B en PS2. La PS2 no rellena el final.

## Formato del `#ACC`

```
+0x00 "#ACC"   +0x04 0x20   +0x0C 2
+0x10 n_clips  +0x14 tabla (0x20)  +0x18 1 (n_huesos)  +0x1C 0
tabla (0x20): n_clips × 16 B  [flags 0x1D][variante 0][n_frames][offset del clip]
clip (alineado a 8): 4 punteros (offsets desde el inicio del #ACC) -> 4 pistas
pista: [u32 0][u32 1][u32 n_claves] + claves
   ojo, objetivo : [u32 frame][f32 x][f32 y][f32 z]     (16 B por clave)
   roll, fov     : [u32 frame][f32 valor en radianes]   (8 B por clave)
final del #ACC alineado a 8
```

| Pista | Qué es | Rango en el juego |
|---|---|---|
| ojo | posición de la cámara | — |
| objetivo | **punto de mira** (no un giro: la guía de la comunidad lo llama "rotación") | distancia ojo-objetivo 3,5–1058 (mediana 32,7) |
| roll | giro de la cámara sobre su eje de vista | −π..π (mediana 0) |
| fov | campo de visión vertical | 0,066–1,306 rad (3,8°–74,8°, mediana 37,8°) |

- **Tiempo:** 1 frame = 1/60 s. La última clave de cada pista está en `n_frames − 1` (633 de 633).
- **Interpolación:** lineal. Lo normal es 1 clave por frame; hay clips dispersos (Zarbon: 46 claves
  para 80 frames) y pistas de 2 claves (roll y fov fijos).
- **Espacio:** Y arriba, unidades del modelo, centrado en el atacante (el objetivo de Goku en el
  clip 0 es (0; 10,5; 0), la altura del pecho). **Falta confirmar en el juego** hacia dónde está el
  rival y si hay espejo izquierda/derecha.
- Gohan del Futuro (SB2) no trae ningún clip: su `#ACC` es un stub vacío.

## Cómo pide los clips el guion `#SPX`

```
mando -> #CCM -> código de ataque -> #CSK (líneas AP) -> golpe HR tipo 3 + ranura
      -> #SPX ranura -> subrutina:  CAMARA_CLIP(0, g[0x60]+K, 0, 0.5, 0, 0, 0)   builtin 0xA7
                                    esperar N frames                                push N; call sub 0
```

- Cabecera del `#SPX`: `+0x14` = base del código (0x74 en casi todos), `+0x18` = n ranuras,
  `+0x20` = tabla de ranuras (u32 relativos a la base; 0xFFFFFFFF = vacía).
- Opcodes seguros: `08 10/20/30` push 8/16/32 bits, `09 30` push float, `08 5c 60` variable global
  0x60, `01 10/20/30` + `02 80 02` llamada a builtin, `01 30` + `02 73 02` llamada a subrutina,
  `12 10 n` desapila, `0b` fin de sentencia.
- El índice del clip suele ser **relativo**: `g[0x60] + K`. La base la pone cada técnica; el
  Studio la **estima** comparando la duración de cada clip con su espera, y se puede cambiar.
- Ranuras: 0 = modo hiper / definitiva (32 de 38 personajes), 20 = agarre (38 de 38), 10 en 5
  personajes.
- **Editar el guion no es seguro todavía** (VM incompleta). Solo se editan los clips; si un clip
  dura más que la espera del guion, se corta; si dura menos, la cámara se queda en su último frame.

## Mods de cámara

| Personaje | Dónde va la cámara editada |
|---|---|
| Nativo (Goku, Vegeta…) | `mods/studio_<personaje>/us/data_cmn.afs/<fid CAM>/geom.bin` |
| Port o personaje nuevo | el `camara.bin` de su mod fuente (lo monta `roster_build` al pulsar JUGAR) |

Reglas del override nativo (las aplica `studio_core.save_native`):
1. LZX `xbcompress /N:2048` (nunca `/N:32`).
2. **Relleno con ceros hasta un tamaño reservado**: `max(to_read del slot, LZX + 64 KB)`,
   redondeado a 0x1000. Se guarda en `studio.json` (`reservado`) y todas las versiones siguientes se
   escriben con ese mismo tamaño. Así la tabla virtual del AFS (que el runtime calcula una vez por
   sesión) sigue siendo válida y la cámara se puede **recargar sin reiniciar** (Pausa →
   «Reelegir personajes»).
3. Si una edición no cabe en lo reservado, se amplía la reserva y hay que **reiniciar el juego**.
   La primera vez que se crea el mod también (la lista de mods se lee al arrancar).
4. En la carpeta de la entrada solo puede haber **un fichero** (el runtime sirve el primero): los
   respaldos van a `mods/<mod>/respaldo/<fecha>/`, nunca dentro de `us/`.
5. `studio.json` guarda los clips editados (claves completas): es la fuente de la verdad y permite
   regenerar el bin.

Validación antes de escribir (si falla, no se escribe nada): frames crecientes, última clave en
`n_frames − 1`, valores finitos, fov 0,05–2,5 rad, roll −π..π, ojo y objetivo separados más de 0,1,
y **no se borran clips** (el guion los pide por número; solo se añaden al final).

## glTF (Blender u otro programa 3D)

- Exportación: nodo cámara con traslación = ojo, rotación = mirar del ojo al objetivo con el roll
  (cámara glTF: mira a −Z, Y arriba) y `yfov` animado con `KHR_animation_pointer`
  (Blender ≥ 4.2). Copia del fov por frame en `extras.fov_rad_por_frame`. Opcional: el personaje
  con su esqueleto y una animación del moveset.
- Importación: se muestrea la cámara a 60 fps; el **objetivo** se reconstruye a la distancia que
  tenía el clip (glTF no guarda punto de mira) y el roll sale de la orientación.
- Ida y vuelta por Blender 5.2.1 sin tocar nada: error ≤ 0,00002 unidades. Con la cámara movida
  +5 en X dentro de Blender, llega exactamente +5 en X.
