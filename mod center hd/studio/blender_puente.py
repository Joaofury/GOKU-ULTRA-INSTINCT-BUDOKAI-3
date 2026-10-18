# -*- coding: utf-8 -*-
"""blender_puente.py - Puente Studio <-> Blender sin add-on (lo ejecuta Blender, no Python).

  blender --python blender_puente.py -- abrir CLIP.glb CLIP.blend
      Abre Blender con la toma importada (personaje + camara, 60 fps, frame 0 = inicio del
      clip) y la guarda como CLIP.blend. Edita la camara y guarda con Ctrl+S.
  blender -b CLIP.blend --python blender_puente.py -- exportar SALIDA.glb
      En segundo plano: exporta la escena a glTF (camara con fov animado) para el Studio.

Reglas para el modder: no cambies el frame inicial (0); el final fija la duracion del clip.
El punto de mira (objetivo) se reconstruye a la distancia que tenia el clip.
"""
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
mode = argv[0] if argv else ""


def frame_range():
    ends = [int(a.frame_range[1]) for a in bpy.data.actions]
    return 0, max(ends) if ends else 1


if mode == "abrir":
    glb, blend = argv[1], argv[2]
    for o in list(bpy.data.objects):      # escena vacia sin reiniciar la interfaz (cubo, luz y camara fuera)
        bpy.data.objects.remove(o, do_unlink=True)
    sc = bpy.context.scene
    sc.render.fps = 60
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    bpy.ops.import_scene.gltf(filepath=glb)
    sc.frame_start, sc.frame_end = frame_range()
    cam = next((o for o in sc.objects if o.type == "CAMERA"), None)
    if cam is not None:
        sc.camera = cam
        cam.select_set(True)
        bpy.context.view_layer.objects.active = cam
    for area in (bpy.context.screen.areas if bpy.context.screen else []):
        if area.type == "VIEW_3D":
            area.spaces[0].region_3d.view_perspective = "CAMERA"     # mirar por la camara del clip
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    print("STUDIO_BLENDER abierto", blend, "frames", sc.frame_start, sc.frame_end)
elif mode == "exportar":
    out = argv[1]
    sc = bpy.context.scene
    sc.render.fps = 60
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_cameras=True, export_animations=True,
                              export_force_sampling=True, export_pointer_animation=True, export_yup=True,
                              export_animation_mode="SCENE")
    print("STUDIO_BLENDER exportado", out, "frames", sc.frame_start, sc.frame_end)
else:
    print("uso: abrir CLIP.glb CLIP.blend | exportar SALIDA.glb")
