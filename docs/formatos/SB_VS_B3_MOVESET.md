# Movesets de Shin Budokai 1/2 (PSP) frente a Budokai 3

RE del 2026-10-06 (exploración `docs/07_ports/GOHAN_FUTURO_EXPLORACION_2026-10-06/01_moveset`,
oráculo Gohan adulto: `BCGHL` de SB2 contra el ID 4 de B3). Conversor: `awo_tools/sbport.py`
(tablas en `awo_tools/sb_tablas.py`); lo llama el importador (`importar.py importar sb2 GHF …`).

Mismo motor que B3 (`#AMB` v3, `#BSK` v4, `#AMM` v2, `#BCM`, `#SPX 0.01`) con disposiciones
distintas por dentro. Copiar los hijos de SB tal cual (como el port comunitario `ghf_365/367`) **no
funciona**: B3 lee golpes, daño y efectos desalineados desde la 2.ª línea.

## Dónde están los datos (ISO PSP, `USRDIR/data_btl_cmn.afs`, con nombres de 48 B)

| Fichero | Contenido |
|---|---|
| `BC<XXX>.amb` | moveset: `#AMB` [AMC vacío, SPX, BCM, BSK, —, AMM propio, AMM 2 (víctima), AMM 3] |
| `BC<XXX>B0n.amb` | modelos (formas o trajes): [`#AMO`, `#AMT`, `#RPT` (física del cinturón)] |
| `BC<XXX>M<n>.amb` | el mismo moveset + un 2.º `#BSK` que redefine códigos sueltos de una forma |
| `BSP_<XXX>.amb` | efectos de técnicas (`#AME` de otra versión: 0x00020000, cabecera 0x40) |
| `BCCMN.AMB` | común: AMM global (265 animaciones) |

Códigos de 3 letras: GOK, VGT, PIC, KLL, GHM, GHL, **GHF**, TRX, TRF, FRZ, CEL, COO, BRL, 18G,
BUS, BUL, BUM, BDK, DBR, GGT, VTO, GTX, JNB, PKH (SB2 tiene 24; SB1, 18). Super Dragon Ball Heroes
World Mission usa los mismos (`model/bc<xxx>/bc<xxx>bNN`).

## Diferencias y cómo se convierten

| Parte | Shin Budokai | Budokai 3 | Conversión |
|---|---|---|---|
| Líneas AP (`#BSK`) | **20 B** | **16 B** | copiar `[0:16]`; en las de golpe (tipo 1) la caja cambia: radio +11 → +12, posición 3 × s16 en +12/14/16 → 3 × s8 en +13/14/15 |
| Bloques HR | **160 B** (8 × 20) | **128 B** (8 × 16) | truncar cada línea a 16 B |
| Daño | — | **0,85 × SB** (mediana de 8 847 golpes; 0,71–1,0 según personaje) | multiplicar por 0,85 (`--dano`) |
| Sub-bloque de 48 B | bits 0x80/0x100/0x200 en +0x10 | nunca pasa de 0x7F | quitar los bits |
| Códigos del motor | suelo 0x000–0x1FF, aire **+0x200** | suelo 0x000–0x0FF, aire **+0x100** | tabla por animación casada (`ENGINE_SB`) |
| Ataques del BCM | **0x4xx** suelo / **0x6xx** aire | **0x2xx** / **0x3xx** | conservar el desplazamiento; lo que choca, a un hueco libre (pareja +0x100) |
| Transformación | 0x500 / 0x700 (abajo+E, cuesta 4000 de ki) | **0x2E0 / 0x3E0** (P+K+G) | se quita la de SB; P+K+G del donante (`transformacion = "donante"`) |
| Agarre | BASE **0x800** | BASE **0x480** | del donante (con su víctima en el AMM 2) |
| Modo hiper, Dragon Rush, definitiva cinemática | no existen | 0x259, 0x280…, ranura SPX 0 | se injertan del donante |
| Almacén global (anim. comunes) | 265, otro índice | 359 | 206 casan por pose al 0,0° (`sb_tablas.GLOBAL`); el resto se copia al AMM propio |
| AMM propio | comprimido, tabla de 8 B | tabla de 16 B | `sb_amm.py`; el 74–90 % de las animaciones son idénticas a las de B3 |
| AP tipo 7 (efectos) | clases 0–11+ | clases 0–9 | clase 0 igual al 97 %; 1 sonido, 2 chispa, 3 grito: tablas por mayoría; 4 = enlace al BSP; 10 (ranura SPX de SB) y 11+: se quitan |
| BCM: direcciones | 0x10 (↑) y 0x20 (↓) | no existen | ↑+E definitiva → P+K+G+E en hiper; ↑ normal → P+K; ↓ → K+G |
| BCM: ki | especiales 1000, definitivas 5000 | 0 (el coste va en la cápsula) | poner 0 y pasar el coste a la cápsula |
| BCM: variantes de aura | w6 0x8000 / w3 0x7530 / w6 0x100 | no existen | se quitan |
| BCM: cond 4 | especial cuerpo a cuerpo | **transformarse** | 4 → 2 (especial) |
| `#SPX` | funciones nativas **renumeradas** | — | se usa el SPX del donante (y su `#AMC`: los definitivos de SB no tienen cámara propia; se hacen con el Studio) |
| Cámaras `#AMC` | vacías (32 B) | ~26 clips | las del donante |
| Física del cinturón | `#RPT` en el modelo | tabla del XEX por modelo | `fisica = "donante"` (ver `FORMAS_Y_KI.md`) |

## Comprobaciones (sin juego)

- `python awo_tools/sbport.py --oraculo --juego sb2`: convierte GHL de SB2 y lo compara con Gohan
  adulto de B3.
- `python awo_tools/sbport.py --prueba`: autocomprobación sin ISO.
- Cada conversión termina con `comprobacion: OK` (todo código del motor cubierto, sin líneas de
  20 B, índices de almacén válidos). Si no, el importador usa los golpes del donante y lo dice.

## Pendiente de confirmar en el juego

Golpes y daño frente a Gohan adulto, agarre, hiper y Dragon Rush; entradas ↑/↓ convertidas;
qué forma usa `BC<XXX>M<n>`; sonidos y gritos por tabla.
