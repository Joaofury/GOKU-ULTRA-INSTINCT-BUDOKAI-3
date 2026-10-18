# Sombreado toon de los personajes HD y brillo HD de borde

RE del 2026-10-04/06 sobre los volcados de shaders (`dump_shaders` → `D:\DBZ3HD\shaders_dump`, con el
desensamblado del ucode) y calibrado contra los 38 iconos y retratos oficiales. Render offline
equivalente: `mod center hd/model_render.py`.

## El shader toon (PS `5F27AACEB38B1088`)

```
u = ½·(N·L) + ½              (izquierda = sombra, derecha = luz)
v = c1.x                     (fila de la rampa: la elige el ALFA de la textura base)
color = base − rampa[u, v]   (RESTA)
si base.a > c255.z  ->  color = base          ("sin sombrear")
color += c39.x · ( ½·(1 − |N·V|)²  +  escalón((1 − |N·V|)⁶ ≥ ½) )     (brillo HD de borde)
```

- **Resta, no multiplica.** La fórmula antigua de las notas, `base × (1 − rampa)`, solo coincide con
  bases blancas. Con bases de color (las de PSP) la diferencia se ve.
- **Material del AWG0** (0x50 B): `+0x00` color difuso RGB, `+0x30` textura base, `+0x34` **rampa**
  64×64. Textura `FFFFFFFF` = color plano (masa de pelo de Goku/Goten); bandera `0x80000000` =
  translúcido.
- **La rampa guarda el complementario del tono**: piel humana = rampa azulada, Ginyu = rampa verde.
- **Filas de la rampa:** bandas de 4 filas elegidas por el alfa DXT3 de la base (16 niveles). Las
  filas 56–63 están reservadas (negro/blanco); falta confirmar si el contorno las usa.
- **Nativos:** bases casi blancas con las líneas dibujadas, el color sale de la rampa; **alfa 0** en
  todo salvo el blanco de los ojos (alfa 255 = sin sombrear).

## Consecuencias para los modelos importados

| Origen | Estado | Qué hacer |
|---|---|---|
| PSP (Shin Budokai, `psp_amo.py`) | texturas de 16 colores con la sombra **pintada** y **alfa 255 en todo** → en el juego sale **plano**, solo con el brillo de borde; normales peores (manchas en el brillo) | alfa 0 + rampa por material; normales suaves. **Ojo:** la rampa neutra `psp_ramp.npy` se pensó para multiplicar: restada, oscurecería el modelo |
| Heroes World Mission (`sdbh_model.py`) | bases con color + rampas toon propias | usa las **rampas nativas** de la plantilla (piel = la de Gohan, ropa y pelo = gris), alfa 0 en las bases y 255 solo en ojos, boca y dientes |
| Comunidad PS2 (`ps2hd`, `amo2awo`) | según el modelo | revisar el alfa de las texturas si sale plano |

Si un personaje sale **negro**: rampa demasiado oscura para una base de color (la resta satura).
Si sale **plano**: alfa alto en la base.

## Brillo HD de borde (rim light)

- Su intensidad viene del vertex shader: **`o2.w = c39.x`**, solo si la normal no es cero (los
  nativos ponen normal nula en lo que no se ilumina). Todos los VS de modelo tienen esa línea.
- **Interruptor nativo** (2026-10-06): el SDK escala `c39.x` al subirlo, solo en los shaders cuyo
  ucode contiene `o2.___w, c39.x`.
  - Variable del juego: **`dbz3_hd_rim_light`** (0–1). Del SDK: `dbz3_rim_light_scale`.
  - Launcher → pestaña «Mods nativos» → **«Brillo HD de los personajes»** (casilla + 5–100 %).
  - En el juego: menú rápido **F1** → «Brillo HD». Se aplica al momento.
- Afecta a todos los personajes por igual (nativos y nuevos): no es una propiedad del mod.
- Con normales malas, el brillo dibuja manchas: es la forma más rápida de ver si un modelo
  importado necesita normales suaves (pon el brillo al 100 %).

## Comprobación sin juego

`mod center hd/model_render.py` (iconos y retratos de los personajes nuevos, vista previa del Mod Kit
y del Studio) usa todavía la forma **producto** `base × (1 − rampa)`: exacta con las bases blancas de
los nativos, aproximada con bases de color (PSP). Pasarla a resta está pendiente.
