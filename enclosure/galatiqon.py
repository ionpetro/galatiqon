#!/usr/bin/env python3
"""Galatiqon enclosure: a rounded teal puck for a Raspberry Pi, matching the product render.

    python3 galatiqon.py            -> stl/*.stl (print orientation), previews/*.png,
                                       ../web/public/models/galatiqon.glb (for the web viewer)

Geometry is built with manifold3d (CSG) and exported with trimesh, like muse-bike/enclosure.
Parts: body (back shell, holds the Pi), face (front cap with the screen window, eye slots,
speaker grille, mic hole and the G mark) and the button cap on top. The Pi 3B+ / 4 stands
upright behind the face on four standoffs; a slim USB power bank sits under it.

Coordinates: X across the face, Y up, Z depth. The back is at Z = 0, the face at Z = D.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import trimesh
from manifold3d import CrossSection as CS, JoinType, Manifold as M

HERE = os.path.dirname(os.path.abspath(__file__))
STL = os.path.join(HERE, "stl")
PNG = os.path.join(HERE, "previews")
GLB = os.path.join(HERE, "stl", "galatiqon-rounded.glb")  # the print-simple script owns web/public/models/galatiqon.glb

# ----------------------------------------------------------------- parameters (mm)
W, H, D = 112.0, 104.0, 58.0       # outer width, height, depth
R_FACE = 30.0                      # corner radius seen from the front (the squircle)
R_EDGE = 11.0                      # round-over of the face and back edges
WALL = 2.4
SEAM = 24.0                        # face cap depth from the front; the seam is at Z = D - SEAM
TONGUE_H, TONGUE_T, TONGUE_CLR = 3.0, 1.6, 0.25
SEG = 64

SCREEN_W, SCREEN_H, SCREEN_R = 66.0, 17.0, 8.5     # pill window for a 1.9" bar display
SCREEN_Y = -30.0                                   # window centre, relative to the face centre
EYE_W, EYE_L, EYE_TILT = 11.0, 24.0, 22.0          # the two slanted slots (mic + light ring)
EYES = [(27.0, 24.0), (44.0, 32.0)]                # slot centres (x, y)
LOGO_C, LOGO_RO, LOGO_RI, LOGO_GAP = (-31.0, 24.0), 11.5, 7.0, 70.0   # the G mark: ring + gap (deg)
MARK_DEPTH = 0.8
GRILLE_N, GRILLE_D, GRILLE_PITCH, GRILLE_Y = 7, 2.2, 4.6, -46.0      # speaker dots along the bottom
MIC_D, MIC_XY = 1.6, (-32.0, -45.0)
BTN_W, BTN_H, BTN_R, BTN_LIP = 46.0, 28.0, 13.0, 1.2                  # top button cap (oval)
BTN_CAP_T, BTN_CLR = 4.0, 0.4
PI_HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]      # Pi mounting pattern, 58 x 49
STANDOFF_H, STANDOFF_OD, STANDOFF_HOLE = 6.0, 6.5, 2.4
BANK = (92.0, 60.0, 13.0)          # slim power bank behind the Pi

TEAL = (36, 199, 143, 255)
TEAL_DARK = (24, 160, 114, 255)
BLACK = (14, 16, 18, 255)
PI_GREEN = (40, 120, 70, 110)


# ----------------------------------------------------------------- helpers
def puck(w, h, d, r_face, r_edge):
    """Rounded box: hull of spheres (radius r_edge) along the four face-corner arcs, front and back."""
    pts = []
    rc = max(r_face - r_edge, 0.01)
    cx, cy = w / 2 - r_face, h / 2 - r_face
    for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
        a0 = {(1, 1): 0, (-1, 1): 90, (-1, -1): 180, (1, -1): 270}[(sx, sy)]
        for k in range(13):
            a = math.radians(a0 + 90 * k / 12)
            for z in (r_edge, d - r_edge):
                pts.append((sx * cx + rc * math.cos(a), sy * cy + rc * math.sin(a), z))
    spheres = [M.sphere(r_edge, 40).translate(p) for p in pts]
    return M.batch_hull(spheres)


def rrect(w, h, r, cx=0.0, cy=0.0):
    return CS.square((w, h), True).offset(0, 0).translate((cx, cy)) if r <= 0 else \
        CS.square((w - 2 * r, h - 2 * r), True).offset(r, JoinType.Round, 0.0, SEG).translate((cx, cy))


def slab(cs, z0, z1):
    return M.extrude(cs, z1 - z0).translate((0, 0, z0))


def cyl(r, z0, z1, cx=0.0, cy=0.0):
    return M.cylinder(z1 - z0, r, r, SEG).translate((cx, cy, z0))


def to_trimesh(man):
    mm = man.to_mesh()
    t = trimesh.Trimesh(np.asarray(mm.vert_properties)[:, :3], np.asarray(mm.tri_verts), process=False)
    t.merge_vertices(digits_vertex=4)
    t.update_faces(t.nondegenerate_faces(height=1e-6))
    t.remove_unreferenced_vertices()
    return t


# ----------------------------------------------------------------- build
def build():
    outer = puck(W, H, D, R_FACE, R_EDGE)
    inner = puck(W - 2 * WALL, H - 2 * WALL, D - 2 * WALL, R_FACE - WALL, R_EDGE - WALL).translate((0, 0, WALL))
    shell = outer - inner

    z_seam = D - SEAM
    big = 400.0
    back_half = M.cube((big, big, big), True).translate((0, 0, z_seam - big / 2))
    front_half = M.cube((big, big, big), True).translate((0, 0, z_seam + big / 2))
    body = shell ^ back_half
    face = shell ^ front_half

    # tongue on the face cap (inner lip that sits inside the body rim)
    lip_out = puck(W - 2 * WALL - 2 * TONGUE_CLR, H - 2 * WALL - 2 * TONGUE_CLR, D, R_FACE - WALL, R_EDGE - WALL)
    lip_in = puck(W - 2 * WALL - 2 * TONGUE_CLR - 2 * TONGUE_T, H - 2 * WALL - 2 * TONGUE_CLR - 2 * TONGUE_T, D,
                  R_FACE - WALL - TONGUE_T, max(R_EDGE - WALL - TONGUE_T, 1.0))
    tongue = (lip_out - lip_in) ^ M.cube((big, big, TONGUE_H), True).translate((0, 0, z_seam - TONGUE_H / 2))
    face = face + tongue

    # face features (all cut through the front wall, which is at Z in [D - WALL - R_EDGE .. D])
    zf0, zf1 = D - R_EDGE - WALL - 1, D + 1
    face -= slab(rrect(SCREEN_W, SCREEN_H, SCREEN_R, 0, SCREEN_Y), zf0, zf1)
    for (ex, ey) in EYES:
        face -= slab(rrect(EYE_W, EYE_L, EYE_W / 2).rotate(-EYE_TILT).translate((ex, ey)), zf0, zf1)
    for i in range(GRILLE_N):
        x = (i - (GRILLE_N - 1) / 2) * GRILLE_PITCH
        face -= cyl(GRILLE_D / 2, zf0, zf1, x, GRILLE_Y)
    face -= cyl(MIC_D / 2, zf0, zf1, *MIC_XY)
    # the G mark: a ring with a gap, recessed into the face
    ring = CS.circle(LOGO_RO, SEG) - CS.circle(LOGO_RI, SEG)
    gap = CS.square((LOGO_RO * 2.2, LOGO_RO * 0.55), True).translate((LOGO_RO * 1.1, 0)).rotate(-LOGO_GAP / 2)
    bar = CS.square((LOGO_RO * 0.9, LOGO_RO * 0.32), True).translate((LOGO_RO * 0.45, -LOGO_RO * 0.12))
    mark = ((ring - gap) + bar).translate(LOGO_C)
    face -= slab(mark, D - MARK_DEPTH, D + 1)

    # push-to-talk button: oval opening in the top of the body, with a ledge the cap rests on
    top = H / 2
    btn_open = rrect(BTN_W, BTN_H, BTN_R, 0, D / 2 - 4)       # (x, z) footprint, built in XZ then rotated
    btn_hole = M.extrude(btn_open, 30).rotate((90, 0, 0)).translate((0, top + 10, 0))
    ledge_cs = rrect(BTN_W + 2 * BTN_LIP + 2, BTN_H + 2 * BTN_LIP + 2, BTN_R + 2, 0, D / 2 - 4)
    ledge = M.extrude(ledge_cs, BTN_CAP_T + 1).rotate((90, 0, 0)).translate((0, top + 0.2, 0)) - \
        M.extrude(btn_open, 40).rotate((90, 0, 0)).translate((0, top + 20, 0))
    body = (body - btn_hole) + (ledge ^ outer)
    cap_cs = rrect(BTN_W - 2 * BTN_CLR, BTN_H - 2 * BTN_CLR, BTN_R - BTN_CLR, 0, D / 2 - 4)
    button = M.extrude(cap_cs, BTN_CAP_T).rotate((90, 0, 0)).translate((0, top + 0.6, 0))
    button = button + (M.extrude(rrect(BTN_W + 2 * BTN_LIP, BTN_H + 2 * BTN_LIP, BTN_R + BTN_LIP, 0, D / 2 - 4), 1.4)
                       .rotate((90, 0, 0)).translate((0, top - BTN_CAP_T + 0.6 + 1.4, 0)))

    # Pi standoffs on the back wall: the board stands upright, parallel to the face
    z_board = WALL + BANK[2] + 3.0 + STANDOFF_H
    pi_x0, pi_y0 = -85 / 2, -56 / 2 + 2
    for (hx, hy) in PI_HOLES:
        body += cyl(STANDOFF_OD / 2, WALL - 0.5, z_board, pi_x0 + hx, pi_y0 + hy) - \
            cyl(STANDOFF_HOLE / 2, z_board - 5, z_board + 1, pi_x0 + hx, pi_y0 + hy)
    # power bank cradle: two rails on the back wall
    for sx in (-1, 1):
        body += M.cube((4, BANK[1] + 6, 6), True).translate((sx * (BANK[0] / 2 + 3), 0, WALL + 2))

    # ghosts for the viewer
    pi = M.cube((85, 56, 1.6), True).translate((0, 2, z_board + 0.8))
    bank = M.cube(BANK, True).translate((0, 0, WALL + BANK[2] / 2))
    screen = slab(rrect(SCREEN_W + 6, SCREEN_H + 6, SCREEN_R + 3, 0, SCREEN_Y), D - WALL - R_EDGE - 2.0, D - WALL - R_EDGE - 0.5)

    return dict(body=body, face=face, button=button, pi=pi, bank=bank, screen=screen, z_seam=z_seam)


def export(parts):
    os.makedirs(STL, exist_ok=True); os.makedirs(PNG, exist_ok=True); os.makedirs(os.path.dirname(GLB), exist_ok=True)
    meshes = {k: to_trimesh(v) for k, v in parts.items() if isinstance(v, M)}

    # print orientation: body back-down (as built); face cap front-down; button cap top-down
    def drop(m):
        m = m.copy(); m.apply_translation(-m.bounds[0]); return m
    face_print = meshes["face"].copy(); face_print.apply_transform(trimesh.transformations.rotation_matrix(math.pi, (1, 0, 0)))
    btn_print = meshes["button"].copy(); btn_print.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, (1, 0, 0)))
    for name, m in (("galatiqon-body", meshes["body"]), ("galatiqon-face", face_print), ("galatiqon-button", btn_print)):
        mm = drop(m)
        mm.export(os.path.join(STL, name + ".stl"))
        print(f"{name:18s} watertight={mm.is_watertight!s:5s} {mm.extents.round(1)} mm  vol={mm.volume/1000:.1f} cm3  tris={len(mm.faces)}")

    # GLB for the web: assembled, Y up, metres, centred. Mesh names drive the materials in the viewer.
    scene = trimesh.Scene()
    colors = dict(body=TEAL, face=TEAL, button=TEAL_DARK, pi=PI_GREEN, bank=(60, 60, 64, 120), screen=BLACK)
    for name, m in meshes.items():
        mm = m.copy()
        mm.apply_scale(0.001)  # bake mm -> m into the vertices (a scene scale would only become a node transform)
        mm.visual.face_colors = colors[name]
        scene.add_geometry(mm, node_name=name, geom_name=name)
    # Axes: X right, Y up, Z toward the viewer (the face), the same as three.js.
    scene.export(GLB)
    print("glb ->", os.path.relpath(GLB, HERE), os.path.getsize(GLB) // 1024, "kB")
    return meshes


@np.errstate(all="ignore")  # macOS Accelerate BLAS emits spurious matmul warnings
def preview(meshes, z_seam):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    light = np.array([0.4, 0.6, 0.7]); light /= np.linalg.norm(light)

    def draw(ax, items, elev, azim, title):
        e, a = np.radians(elev), np.radians(azim)
        eye = np.array([np.cos(e) * np.cos(a), np.cos(e) * np.sin(a), np.sin(e)])
        allt, allc = [], []
        for m, rgba, off in items:
            n = m.face_normals; keep = (n @ eye > 0) if rgba[3] > 0.99 else np.ones(len(n), bool)
            tris = m.vertices[m.faces[keep]] + off
            shade = 0.45 + 0.55 * np.clip(n[keep] @ light, 0, 1)
            col = np.tile(np.asarray(rgba, float), (len(tris), 1)); col[:, :3] *= shade[:, None]
            allt.append(tris); allc.append(col)
        tris, cols = np.concatenate(allt), np.concatenate(allc)
        pc = Poly3DCollection(tris, facecolors=cols, edgecolors=np.where(cols[:, 3:] > 0.99, cols, 0), linewidths=0.2)
        ax.add_collection3d(pc)
        pts = tris.reshape(-1, 3); lo, hi = pts.min(0), pts.max(0)
        ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1]); ax.set_zlim(lo[2], hi[2]); ax.set_box_aspect(hi - lo)
        ax.view_init(elev=elev, azim=azim); ax.set_axis_off(); ax.set_title(title, fontsize=10)

    teal = np.array(TEAL) / 255; dark = np.array(TEAL_DARK) / 255; blk = np.array(BLACK) / 255; green = np.array(PI_GREEN) / 255
    fig = plt.figure(figsize=(15, 7.5), dpi=110, facecolor="#101214")
    ax1 = fig.add_subplot(1, 2, 1, projection="3d"); ax1.set_facecolor("#101214")
    draw(ax1, [(meshes["body"], teal, (0, 0, 0)), (meshes["face"], teal, (0, 0, 45)), (meshes["button"], dark, (0, 25, 0)),
               (meshes["pi"], green, (0, 0, 0)), (meshes["bank"], (0.3, 0.3, 0.32, 0.5), (0, 0, 0))], 24, -50, "exploded")
    ax2 = fig.add_subplot(1, 2, 2, projection="3d"); ax2.set_facecolor("#101214")
    draw(ax2, [(meshes["body"], teal, (0, 0, 0)), (meshes["face"], teal, (0, 0, 0)), (meshes["button"], dark, (0, 0, 0)),
               (meshes["screen"], blk, (0, 0, 0))], 18, -62, "assembled")
    for ax in (ax1, ax2):
        ax.title.set_color("#cfd6d3")
    fig.suptitle("Galatiqon enclosure", color="#e8ecea", fontsize=13)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=0.92, wspace=0)
    out = os.path.join(PNG, "galatiqon.png"); fig.savefig(out, facecolor=fig.get_facecolor()); plt.close(fig)
    print("preview ->", os.path.relpath(out, HERE))


if __name__ == "__main__":
    parts = build()
    meshes = export(parts)
    if "--no-render" not in sys.argv:
        preview(meshes, parts["z_seam"])
