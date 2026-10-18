# Studio: rehacer las cámaras de las técnicas

El **Studio** es una ventana del Mod Kit para editar las cámaras de las técnicas (definitivas,
agarres, modo hiper). No hace falta tener el juego abierto, ni Blender (es opcional).

- Abrir: Mod Kit → tarjeta **«Studio de cámaras»** (o, en un personaje con moveset propio,
  **«Cámaras (Studio)»**). También `python "mod center hd/studio/studio_gui.py"`.
- Formato y detalles técnicos: `docs/03_formatos/CAMARA_ACC.md`.

## 1. Elegir personaje y técnica

- **Personaje:** los 38 del juego y los personajes nuevos que tengan cámara propia (`camara.bin`).
- **Técnica:** cada «Guion» es una secuencia de clips del guion `#SPX` (ranura 0 = modo hiper /
  definitiva, 20 = agarre). «Todos los clips» enseña los clips sueltos.
- **Primer clip:** el guion pide los clips como «base + K». El Studio estima la base; si los clips
  marcados (▸) no encajan con la técnica, cámbiala.

## 2. Mirar

- **Línea de tiempo:** un bloque por clip, con la espera del guion; la franja gris es el tiempo en
  que la cámara se queda quieta (clip más corto que la espera). Rayas rojas = golpes (aproximado).
- **Desde arriba / De lado:** naranja = ojo (la cámara), azul = objetivo (a dónde mira), gris = el
  personaje en ese frame.
- **Giro y fov:** curvas del clip; pulsa o arrastra para cambiar de frame.
- **Vista previa (toon):** el personaje con el estilo del juego visto desde la cámara. «GIF» guarda
  el clip animado para compartirlo. La pose es orientativa.

## 3. Editar

| Quiero… | Cómo |
|---|---|
| mover la cámara en un momento | arrastra el punto naranja (o el azul) en una vista; «Suavizado ±frames» reparte el cambio a los frames vecinos |
| mover toda la trayectoria | marca «mover toda la trayectoria» y arrastra |
| valores exactos | «Valores en este frame» → «Aplicar en este frame» |
| una cámara nueva | **Plantillas**: Órbita, Travelling / acercamiento, Temblor, Giro (roll) → «Aplicar al clip» |
| alargar o acortar | «Duración» → «Retemporizar» (el guion sigue esperando lo mismo) |
| volver al original | «Deshacer» |
| copiar la cámara de otro personaje | «Copiar…» |
| dar cámaras a un personaje que no tiene | «Añadir» o «Copiar…» (el guion solo usa los clips que pide) |

## 4. Con Blender (opcional)

1. **«Abrir en Blender»**: abre Blender con el personaje y la cámara (60 fps, el frame 0 es el
   inicio del clip). Blender 5.2 está en `C:\Program Files\Blender Foundation\`.
2. Mueve la cámara, cambia su fov, añade claves… y guarda con **Ctrl+S**.
3. **«Traer de Blender»**: el Studio pide a Blender (en segundo plano) que exporte y lee la cámara.

Reglas: no cambies el frame inicial; el final fija la duración. Sirve cualquier programa 3D que
exporte glTF (`.glb`): «Exportar .glb…» / «Importar .glb…».

## 5. Guardar y probar

- **«Guardar como mod»** valida todo antes de escribir (si algo no cuadra, no escribe nada).
  - Personaje del juego: crea `mods/studio_<personaje>/` con la cámara comprimida y un
    `studio.json` (tus clips editados; al reabrir el Studio se cargan solos).
  - Personaje nuevo: reescribe su `moveset/camara.bin`; se monta al pulsar JUGAR.
  - La versión anterior queda en `mods/<mod>/respaldo/<fecha>/`. Nunca se borra nada ni se tocan
    los archivos del juego.
- **Probar:** la primera vez reinicia el juego. Después, con el juego abierto: Pausa → «Reelegir
  personajes» → Entrenamiento → lanza la técnica. Si el Studio avisa de que la cámara creció más
  de lo reservado, reinicia.
- Para quitarla: desactiva el mod `studio_<personaje>` en «Mis mods».

## Pendiente de comprobar en el juego

Orientación de la cámara respecto al rival y espejo izquierda/derecha; si la espera del guion y la
duración del clip coinciden; si «Reelegir personajes» relee la cámara.
