# Cápsulas de Budokai 3 HD (US) — formato y uso en los personajes nuevos

RE del 2026-10-04 (imagen US, `default.xex`). Solo describe estructuras; no contiene datos
del juego. Código: `mod center hd/capsulas.py`, `mod center hd/roster_build.py`
(clase `Capsules`) y `src/roster_ext.cpp`.

## Catálogo `#SKC` (data_usi 4; en PS2 `skill.ska`, `#SKA`, little-endian)

Cabecera de 0x20 B (`+0x10` n = 596, `+0x14` inicio = 0x20) y n registros de 40 B (BE en la
HD). El ID de cápsula es el índice del registro.

| Offset | Tipo | Significado |
|---|---|---|
| +0 | u64 | dueños: bit k = ID de personaje k (0–63). Objetos comunes = bits 0–43 |
| +8 | u8 | clase: 0x11 habilidad/transformación, 0x21 ataque, 0x17 fusión/despertar, 0x00 derivada (sale al cumplirse algo: X10 Kamehameha…) |
| +10 | u8 | rareza (nibble alto 0–3) |
| +14 | u8 | máscara de formas desde las que se puede usar |
| +15 | u8 | coste / nivel |
| +16 | u32 | cápsula requerida (SSJ2 pide SSJ…) |
| +20..+35 | | efecto (objetos) / número de ataque; +30 u16 tipo de sustitución, +32 cápsula base |
| +38 | u16 | precio / 100 |

En memoria: el juego carga el `#SKC` en 0x824A60E8 y lo usa por dos punteros,
`0x82375608` (cabecera) y `0x8237560C` (registros). Varias rutinas de menú recorren hasta
595/596 con constantes fijas; el combate indexa por ID directo.

## Dónde se usa el ID de cápsula

- **Lista por defecto** (custom «Original»): `char96` (0x8234ABB8 + 96·ID) `+80` u16 n,
  `+82` 7 × u16.
- **Transformaciones**: `char372` (0x82329CF0 + 372·ID) `+0xD0` u32 nº de formas,
  `+212 + 20·forma` u16 = cápsula que exige esa forma (`+214` = ID cuyo modelo carga).
- **Golpes**: bloque de 64 B del `#CCM` (BCM) del personaje, palabra 8 (u16 `+16`).
  En la HD la palabra 4 es el tipo de especial y la 5 la condición (en el `#BCM` de PS2 van al
  revés): 0x0400 modo hiper, 0x0004 transformar, 0x0008 definitiva, 0x0002 especial con
  cápsula, 0x0001 cuesta ki; 0x8000 / 0x4000 son de Infinite World (ver abajo).
- **Nombres en los menús**: data_usi 2663 (cortos) y 2684 (largos), `#AZT` indexado por ID.
  Por personaje: tabla u16 en 0x82373D68 → entrada data_usi con los nombres de sus cápsulas
  (`#AZT`, cabecera `+0x18` = primer ID).
- **Ficha de habilidades** (lista de la pausa y rótulo de la cápsula al usarla en combate):
  data_usi 5–52 (`SCM<código>.amb`: `#AZT` nombre + condición por cápsula y `#CFC` con los
  glifos de los botones; filas de 16 B: u32 cápsula, `0xFFFFFFFF` = transformarse). El juego
  la elige con la tabla de 16 B de 0x82324468 (ID, trajes, cara del HUD en data_cmn, índice;
  termina en ID −1) → registro `0x82373A00[índice + 1]` (u32 fid, ptr ataques u16, ptr
  transformaciones u16, nº, nº). Lo lee `sub_820E6D70` al empezar el combate y lo carga
  `sub_821B5FC0`.

## Inventario, lista «Custom» y «Edit Skills» (RE 2026-10-04, segunda parte)

- **Inventario** (u8 = cuántas tienes, por ID de cápsula): partida en memoria 0x824BA110
  `+0x2AFE9`, **2048 B** (el juego solo usa 1..594, pero la partida guarda 2048: las cápsulas
  nuevas caben sin cambiar el formato). La selección trabaja con una copia (bloque de la
  partida del jugador, puntero en estado del jugador `+120`): `+1094` inventario (2048 B),
  `+68` listas «Custom». Copia ida/vuelta: `sub_82179C20` / `sub_82179880` (por puntero).
- **Lista «Custom»** = 7 × s16 por **casilla del select** (38): partida 0x824BA110 `+4928`
  + 4624·casilla; en la copia, `+68 + 14·casilla`. `0xFFFF` = vacía.
- **Menú del select** «Normal / Custom / Edit Skills» (por jugador). Estado del editor:
  `*0x8247971C + 460·jugador + 68`: `+28` ID, `+32` casillas usadas, `+36` pestaña
  (registro `+10 & 3`), `+44` puntero al inventario, `+76 + 28·pestaña` bloque (`+0`
  desplazamiento, `+4` cursor, `+8` 9 × u16 visibles, `+26` total), `+188` lista equipada
  (u32 n + 7 u32).
  - `sub_821B6ED8` (visibles) y `sub_821B6FE8` (total y cursor): bucle fijo de 594 cápsulas.
  - `sub_821B7290` carga una lista en el editor y descarta las ≥ 595.
  - `sub_821B7C50` dibuja la bandeja y se salta las ≥ 595. El nombre lo pide
    `sub_82146430` (r3 sprite, `+24` textura; r4 banco #AZT, r5 ID).
  - `sub_821B8470` dice si una cápsula se puede equipar (0 sí, 1 ya está, 2 sin casillas…).
  - `sub_821B8FC8` dibuja la cara del personaje con la tabla u8 `0x82373D38[ID]` (44
    entradas, `0xFF` en los recortados): con un ID recortado o ≥ 44 → puntero nulo y
    **cierre** (afectaba a todos los personajes nuevos).
  - El panel de descripción (`sub_821BB680`) carga data_usi `2079 + ID` y solo se pide
    para ID < 595.
- **Antes del combate en el modo 5** (`cfg +2018`), `sub_820FE3D8` limpia las listas de la
  selección y borra las ≥ 595. En Versus y Práctica no se llama.

## Cara de la barra de vida (`*_HUD.amt`)

data_cmn (US 452–503), elegida por la tabla de fichas 0x82324468 `+8`. Es un `#AZT` con
**una textura por forma**: DDS 256 × 128 A8R8G8B8, zona útil 192 × 120 px HD (128 × 80
lógicos). Medido sobre las oficiales:
- render del modelo con cámara fija (~30 px por unidad), casi de frente y algo desde arriba;
- centro de la cabeza en x = 91 y barbilla en y = 85;
- alfa 205, hombros recortados por una elipse y las 4 últimas filas fundidas;
- halo azul (48, 137, 192) difuso, con σ ≈ 11 px.

Lo genera `model_render.make_hud` (`roster_build.hud_bin`), o se usa `ui/hud.png`.

## Lo que hace el runtime (`src/roster_ext.cpp`)

- Copia el catálogo a memoria propia con las cápsulas nuevas (`[[capsula]]` de
  `roster.toml`, IDs ≥ 596), añade los bits de dueño de las heredadas y de los objetos
  comunes para los IDs 44–63, y mueve los dos punteros. Se hace en cuanto el `#SKC` está en
  memoria (arranque, select o combate).
- Escribe la lista por defecto (`capsulas`) y la cápsula de cada forma (`capsulas_forma`).
- Fichas: añade las entradas de los personajes nuevos a la tabla de 0x82324468 solo mientras
  corre `sub_820E6D70`; las fichas propias (índice ≥ 1000) se sirven por el hueco 1 de
  0x82373A00 mientras `sub_821B5FC0` las carga.
- «Edit Skills» con el catálogo entero:
  - `sub_821B6ED8` y `sub_821B6FE8` están reescritas para recorrer hasta el final del
    catálogo.
  - `sub_821B7290` rehace la lista equipada.
  - En `sub_821B7C50` (bandeja) y `sub_820FE3D8` (modo 5), cada cápsula nueva usa durante la
    llamada un ID prestado < 595, con el registro intercambiado. `sub_82146430` pide el
    nombre con el ID real.
  - En `sub_821B8FC8` los personajes nuevos usan la cara de su donante.
- Las cápsulas nuevas cuentan como tuyas: el inventario de la copia pasa a 1 si estaba a 0.
  No hacen falta en la tienda.
- Lista «Custom» propia de cada personaje nuevo:
  - `select_ext.cpp` la intercambia con la de la casilla anfitriona mientras se procesa al
    jugador.
  - Si se edita, se guarda en `mods/capsulas_custom.txt`; si no, usa su lista Normal.
  - Mientras está intercambiada, el volcado a la partida (`sub_82179880`) recibe la del
    anfitrión.
  - Antes, «Edit Skills» con un personaje nuevo cambiaba la lista Custom del anfitrión y se
    cerraba (ver la cara, arriba).
- Plazas extra 44–63: `char96`/`char372`/aura/BSP/HUD tienen 105 entradas (64–104 son
  fusiones y formas de combate) y 44–63 están vacías en todas; la máscara de desbloqueo es
  u64. La tabla de encuadre del select (0x82372950) acaba en 44 → hook de `sub_8217FF20`;
  ID → slot (0x82020668) también → hook de `sub_82159A88` (responde la casilla anfitriona).
  Los IDs sin registro de nombre reciben uno (`nombre`).

## Ports de Infinite World

IW no tiene modo hiper: su BCM trae un «aura burst» (botón B, condición 0x4000), los
especiales llevan cápsula de IW con ranura 1/2 (condición 0x8001) y la definitiva es ^E sin
cápsula (0x8009). `capsulas.adapt_iw_bcm()`:

1. «aura burst» → entrada de modo hiper de B3 (P+K+G+E, 0x0400) — en el mando, LT / L2.
2. El modo hiper lo activa la animación de su código de ataque, cuyas propiedades (AP) del
   `#CSK` ponen el estado: se injerta el bloque hiper del donante (todos los de B3 usan la
   animación común del banco 3 con las mismas AP) en los códigos de la entrada convertida
   (`csk_graft`). Validado en juego: el escenario se oscurece y el estado se mantiene.
3. Especiales → condición 0x0002 con las cápsulas nuevas del personaje, en orden; definitiva
   → P+K+G+E en modo hiper (0x000A) con su cápsula. El coste de ki de IW se conserva para el
   texto de la ficha.

## Declararlo en un mod (`personaje.toml`)

```toml
[[capsula]]
nombre = "Hell Gate"
tipo = "especial"          # especial | definitiva | transformacion
[[capsula]]
nombre = "Monster Transformation"
tipo = "transformacion"
forma = 1                  # forma a la que lleva (1 = la primera transformación)
```

**Importar las de un port** (`roster_build.py capsulas --mod X --importar [auto|iw|b1|b2|b3]`,
o el botón «Traer las cápsulas de su juego» del launcher):
- Lee el BCM del port y crea una `[[capsula]]` por cada golpe que pide cápsula, con
  `reemplaza` = el ID original.
- Nombres:
  - IW: por personaje, de la hoja `Dragon Ball Z Infinite World Capsule List.xlsx` (los IDs
    del BCM de IW no coinciden con los de esa hoja).
  - B3: lista `Budokai_3_Capsules_IDs.txt`.
  - Cualquier juego: una lista propia «ID: Nombre» con `--lista`.
- Tipos de B1/B2: catálogo `#SKA` de `Budokai 1 and Budokai 2 Capsule Data` (registros de
  28 B LE; `+4` clase, 0x11 = transformación).
- Port de B3: sus cápsulas ya existen y van a `capsulas_nativas`.
- Si ya había cápsulas, se guarda `personaje.toml.antes_de_importar`.

Sin `[[capsula]]` el personaje usa las del donante (ficha incluida). Con cápsulas propias:
las especiales/definitivas sustituyen en orden a las del donante (o se ligan a los golpes de
un port), y una transformación sustituye a la cápsula de esa forma. También desde el launcher
(Personajes nuevos → editor → «Cápsulas») o `roster_build.py capsulas --mod X --anadir
"Nombre" especial`.

## Pendiente

- La cara de la cabecera de «Edit Skills» es la del donante (tabla de sprites del select).
- El panel de descripción de una cápsula nueva no sale (data_usi `2079 + ID` no existe para
  ID ≥ 596).
- Efectos de cápsulas que no son ataques (objetos verdes/amarillos) para personajes nuevos.
- Nombres de B1/B2: no hay lista en los recursos; el importador pone «Special 1…» si no se
  le da una con `--lista`.
