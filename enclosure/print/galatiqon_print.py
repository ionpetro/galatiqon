#!/usr/bin/env python3
"""Galatiqon, print-simple edition: three parts, no supports, no screws.

    python3 galatiqon_print.py            -> stl/galatiqon-body.stl, stl/galatiqon-face.stl,
                                             stl/galatiqon-button.stl (print orientation),
                                             ../../web/public/models/galatiqon.glb, previews/galatiqon-print.png

Why this version is simpler to print than the first one:
  * The back of the body is flat with a 45 deg chamfer, so the body prints back-down with
    vertical walls and nothing overhanging.
  * The face cap keeps the rounded front, but the part of the round-over that would be steeper
    than 45 deg (the last few millimetres at the face plane) is replaced by a 45 deg chamfer, so
    it prints face-down without supports.
  * The halves locate with a plain tongue (friction fit, 0.25 mm clearance); no inserts, no screws.
  * The Pi sits on four M2.5 standoffs on the flat back wall. Everything else is a through-cut.

Coordinates: X across the face, Y up, Z depth. Back at Z = 0, face at Z = D. All in millimetres.
Built with manifold3d (CSG) and trimesh (export + checks), like muse-bike/enclosure.
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
WEB_MODELS = os.path.join(HERE, "..", "..", "web", "public", "models")   # the site links these as downloads
GLB = os.path.join(WEB_MODELS, "galatiqon.glb")

# ----------------------------------------------------------------- parameters (mm)
W, H, D = 112.0, 104.0, 58.0       # outer width, height, depth
R_FACE = 30.0                      # corner radius seen from the front (the squircle)
R_EDGE = 9.0                       # round-over of the face edge
FACE_CHAMFER = 0.586 * R_EDGE      # 45 deg chamfer tangent to the round-over (prints face-down)
BACK_CHAMFER = 2.0                 # 45 deg chamfer on the back edge (prints back-down)
WALL = 2.4                         # 4 perimeters at 0.6 mm line width... or 6 at 0.4
SEAM = 24.0                        # face cap depth; the seam is at Z = D - SEAM
TONGUE_H, TONGUE_T, TONGUE_CLR = 3.0, 1.6, 0.25
SEG = 64

SCREEN_W, SCREEN_H, SCREEN_R = 66.0, 17.0, 8.5     # pill window for a 1.9" bar display
SCREEN_Y = -30.0
EYE_W, EYE_L, EYE_TILT = 11.0, 24.0, 22.0          # the two slanted slots (mic + light ring)
EYES = [(27.0, 24.0), (44.0, 32.0)]
LOGO_C, LOGO_RO, LOGO_RI, LOGO_GAP = (-31.0, 24.0), 11.5, 7.0, 70.0   # the G mark recess: ring + gap
MARK_DEPTH = 0.8
GRILLE_N, GRILLE_D, GRILLE_PITCH, GRILLE_Y = 7, 2.2, 4.6, -46.0      # speaker dots along the bottom
MIC_D, MIC_XY = 1.6, (-32.0, -45.0)
BTN_W, BTN_H, BTN_R = 46.0, 28.0, 13.0             # top button cap (oval)
BTN_CAP_T, BTN_LIP, BTN_CLR = 3.0, 1.5, 0.4
PI_HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]      # Pi mounting pattern, 58 x 49
STANDOFF_H, STANDOFF_OD, STANDOFF_HOLE = 6.0, 6.5, 2.4
BANK = (92.0, 60.0, 13.0)          # slim power bank behind the Pi
BANK_RAIL = True

TEAL = (19, 179, 127, 255)
TEAL_DARK = (15, 148, 105, 255)
BLACK = (14, 16, 18, 255)
PI_GREEN = (40, 120, 70, 110)


# ----------------------------------------------------------------- helpers
def rrect(w, h, r, cx=0.0, cy=0.0):
    r = min(r, w / 2 - 0.01, h / 2 - 0.01)
    return CS.square((w - 2 * r, h - 2 * r), True).offset(r, JoinType.Round, 0.0, SEG).translate((cx, cy))


def slab(cs, z0, z1):
    return M.extrude(cs, z1 - z0).translate((0, 0, z0))


def cyl(r, z0, z1, cx=0.0, cy=0.0):
    return M.cylinder(z1 - z0, r, r, SEG).translate((cx, cy, z0))


def shell_outer(w, h, d, r_face, r_edge, back_ch, face_ch):
    """The puck: flat chamfered back, vertical walls, rounded front clipped to 45 deg at the face.
    Built as a convex hull, so every section is a squircle and the whole thing is printable."""
    cs = rrect(w, h, r_face)
    parts = [slab(rrect(w - 2 * back_ch, h - 2 * back_ch, r_face - back_ch), 0, 0.01),
             slab(cs, back_ch, max(back_ch + 0.01, d - r_edge))]
    # spheres along the corner arcs give the front round-over
    rc = max(r_face - r_edge, 0.01)
    cx, cy = w / 2 - r_face, h / 2 - r_face
    for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
        a0 = {(1, 1): 0, (-1, 1): 90, (-1, -1): 180, (1, -1): 270}[(sx, sy)]
        for k in range(13):
            a = math.radians(a0 + 90 * k / 12)
            parts.append(M.sphere(r_edge, 40).translate((sx * cx + rc * math.cos(a), sy * cy + rc * math.sin(a), d - r_edge)))
    outer = M.batch_hull(parts)
    # clip the front to a 45 deg chamfer so nothing is steeper than 45 deg when printed face-down
    clip = M.batch_hull([slab(cs, 0, d - face_ch * 1.2), slab(rrect(w - 2 * face_ch, h - 2 * face_ch, r_face - face_ch), d - 0.01, d)])
    return outer ^ clip


def to_trimesh(man):
    mm = man.to_mesh()
    t = trimesh.Trimesh(np.asarray(mm.vert_properties)[:, :3], np.asarray(mm.tri_verts), process=False)
    if not t.is_watertight:  # manifold output is always closed; only weld if it is not already clean
        t.merge_vertices(digits_vertex=5)
    return t


# ----------------------------------------------------------------- build
def build():
    outer = shell_outer(W, H, D, R_FACE, R_EDGE, BACK_CHAMFER, FACE_CHAMFER)
    inner = shell_outer(W - 2 * WALL, H - 2 * WALL, D - 2 * WALL, R_FACE - WALL, max(R_EDGE - WALL, 1.0),
                        max(BACK_CHAMFER - WALL, 0.01), max(FACE_CHAMFER - WALL, 0.5)).translate((0, 0, WALL))
    shell = outer - inner

    z_seam = D - SEAM
    big = 400.0
    body = shell ^ M.cube((big, big, big), True).translate((0, 0, z_seam - big / 2))
    face = shell ^ M.cube((big, big, big), True).translate((0, 0, z_seam + big / 2))

    # tongue on the face cap: a plain lip that slides inside the body's wall (friction fit)
    cs = rrect(W, H, R_FACE)
    lip_in = cs.offset(-(WALL + TONGUE_CLR + TONGUE_T), JoinType.Round, 0.0, SEG)
    lip = cs.offset(-(WALL + TONGUE_CLR), JoinType.Round, 0.0, SEG) - lip_in          # proud part, clears the body wall
    root_cs = cs.offset(-(WALL - 0.4), JoinType.Round, 0.0, SEG) - lip_in              # overlaps the face wall by 0.4 mm
    # the root is a wedge: full width at the seam, tapering to nothing 3 mm into the cap, so its
    # inner face slopes ~37 deg from vertical and prints without support (face-down)
    w_in, h_in = W - 2 * (WALL + TONGUE_CLR + TONGUE_T), H - 2 * (WALL + TONGUE_CLR + TONGUE_T)
    taper = M.extrude(lip_in, TONGUE_H + 0.02, 1, 0.0, ((W - 2 * (WALL - 0.4)) / w_in, (H - 2 * (WALL - 0.4)) / h_in)).translate((0, 0, z_seam - 0.01))
    root = slab(root_cs, z_seam, z_seam + TONGUE_H) - taper
    face = face + slab(lip, z_seam - TONGUE_H, z_seam + 0.01) + root

    # face features: through-cuts in the front wall
    zf0, zf1 = D - R_EDGE - WALL - 1, D + 1
    face -= slab(rrect(SCREEN_W, SCREEN_H, SCREEN_R, 0, SCREEN_Y), zf0, zf1)
    for (ex, ey) in EYES:
        face -= slab(rrect(EYE_W, EYE_L, EYE_W / 2).rotate(-EYE_TILT).translate((ex, ey)), zf0, zf1)
    for i in range(GRILLE_N):
        face -= cyl(GRILLE_D / 2, zf0, zf1, (i - (GRILLE_N - 1) / 2) * GRILLE_PITCH, GRILLE_Y)
    face -= cyl(MIC_D / 2, zf0, zf1, *MIC_XY)
    ring = CS.circle(LOGO_RO, SEG) - CS.circle(LOGO_RI, SEG)
    gap = CS.square((LOGO_RO * 2.2, LOGO_RO * 0.55), True).translate((LOGO_RO * 1.1, 0)).rotate(-LOGO_GAP / 2)
    bar = CS.square((LOGO_RO * 0.9, LOGO_RO * 0.32), True).translate((LOGO_RO * 0.45, -LOGO_RO * 0.12))
    face -= slab(((ring - gap) + bar).translate(LOGO_C), D - MARK_DEPTH, D + 1)

    # push-to-talk button: oval opening in the top wall of the body, cap drops in from above
    top = H / 2
    zc = D / 2 - 4
    hole_cs = rrect(BTN_W, BTN_H, BTN_R, 0, zc)                      # drawn in the X-Z plane
    body -= M.extrude(hole_cs, 30).rotate((90, 0, 0)).translate((0, top + 10, 0))
    cap = M.extrude(rrect(BTN_W - 2 * BTN_CLR, BTN_H - 2 * BTN_CLR, BTN_R - BTN_CLR, 0, zc), BTN_CAP_T)
    lip_cap = M.extrude(rrect(BTN_W + 2 * BTN_LIP, BTN_H + 2 * BTN_LIP, BTN_R + BTN_LIP, 0, zc), 1.2)
    # the cap sits in the hole with its lip under the top wall (it is pushed from below by the switch)
    button = (cap.rotate((90, 0, 0)).translate((0, top + 0.6, 0)) +
              lip_cap.rotate((90, 0, 0)).translate((0, top + 0.6 - BTN_CAP_T + 0.01, 0)))

    # Pi standoffs on the flat back wall (board upright, parallel to the face)
    z_board = WALL + BANK[2] + 3.0 + STANDOFF_H
    pi_x0, pi_y0 = -85 / 2, -56 / 2 + 2
    for (hx, hy) in PI_HOLES:
        body += cyl(STANDOFF_OD / 2, WALL - 0.5, z_board, pi_x0 + hx, pi_y0 + hy) - \
            cyl(STANDOFF_HOLE / 2, z_board - 5, z_board + 1, pi_x0 + hx, pi_y0 + hy)
    if BANK_RAIL:
        for sx in (-1, 1):
            body += M.cube((4, BANK[1] + 6, 6), True).translate((sx * (BANK[0] / 2 + 3), 0, WALL + 2))

    # ghosts for the web viewer
    pi = M.cube((85, 56, 1.6), True).translate((0, 2, z_board + 0.8))
    bank = M.cube(BANK, True).translate((0, 0, WALL + BANK[2] / 2))
    screen = slab(rrect(SCREEN_W + 6, SCREEN_H + 6, SCREEN_R + 3, 0, SCREEN_Y), zf0 - 1.5, zf0 - 0.2)
    return dict(body=body, face=face, button=button, pi=pi, bank=bank, screen=screen), z_seam


def overhang_area(mesh, limit_deg=45.0, bed_tol=1.0):
    """Down-facing area steeper than `limit_deg` from vertical, ignoring the first millimetre above the bed
    (the bed face itself, and the 0.8 mm G-mark pocket whose ceiling is a short bridge) (mm^2)."""
    n = mesh.face_normals
    zc = mesh.triangles_center[:, 2]
    sel = (n[:, 2] < -math.sin(math.radians(90 - limit_deg)) - 2e-3) & (zc > bed_tol)
    return float(mesh.area_faces[sel].sum())


def export(parts):
    for d in (STL, PNG, os.path.dirname(GLB)):
        os.makedirs(d, exist_ok=True)
    meshes = {k: to_trimesh(v) for k, v in parts.items()}

    def drop(m):
        m = m.copy(); m.apply_translation(-m.bounds[0]); return m
    face_print = meshes["face"].copy(); face_print.apply_transform(trimesh.transformations.rotation_matrix(math.pi, (1, 0, 0)))
    btn_print = meshes["button"].copy(); btn_print.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, (1, 0, 0)))  # lip plate on the bed
    print(f"{'part':18s} {'watertight':10s} {'size (mm)':22s} {'volume':>8s} {'tris':>6s} {'overhang>45':>12s}")
    for name, m in (("galatiqon-body", meshes["body"]), ("galatiqon-face", face_print), ("galatiqon-button", btn_print)):
        mm = drop(m)
        assert mm.body_count == 1, f"{name}: {mm.body_count} separate bodies"
        mm.export(os.path.join(STL, name + ".stl"))
        mm.export(os.path.join(WEB_MODELS, name + ".stl"))
        print(f"{name:18s} {str(mm.is_watertight):10s} {str(mm.extents.round(1)):22s} {mm.volume/1000:6.1f}cc {len(mm.faces):6d} {overhang_area(mm):9.0f} mm2")
        if overhang_area(mm) > 50 and "--where" in sys.argv:
            n = mm.face_normals; zc = mm.triangles_center
            sel = (n[:, 2] < -math.sin(math.radians(45)) - 2e-3) & (zc[:, 2] > 1.0)
            c = zc[sel]; a = mm.area_faces[sel]
            print("   overhang z-range %.1f..%.1f, |x| max %.1f, y-range %.1f..%.1f, n=%d" % (c[:, 2].min(), c[:, 2].max(), abs(c[:, 0]).max(), c[:, 1].min(), c[:, 1].max(), len(c)))
            for z in np.linspace(c[:, 2].min(), c[:, 2].max(), 6):
                band = (abs(c[:, 2] - z) < 1.5)
                print("     z~%.1f: %.0f mm2" % (z, a[band].sum()))

    scene = trimesh.Scene()
    colors = dict(body=TEAL, face=TEAL, button=TEAL_DARK, pi=PI_GREEN, bank=(60, 60, 64, 120), screen=BLACK)
    for name, m in meshes.items():
        mm = m.copy(); mm.apply_scale(0.001); mm.visual.face_colors = colors[name]
        scene.add_geometry(mm, node_name=name, geom_name=name)
    scene.export(GLB)
    print("glb ->", os.path.relpath(GLB, HERE), os.path.getsize(GLB) // 1024, "kB")
    return meshes


@np.errstate(all="ignore")
def preview(meshes):
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
        ax.add_collection3d(Poly3DCollection(tris, facecolors=cols, edgecolors=np.where(cols[:, 3:] > 0.99, cols, 0), linewidths=0.2))
        pts = tris.reshape(-1, 3); lo, hi = pts.min(0), pts.max(0)
        ax.set_xlim(lo[0], hi[0]); ax.set_ylim(lo[1], hi[1]); ax.set_zlim(lo[2], hi[2]); ax.set_box_aspect(hi - lo)
        ax.view_init(elev=elev, azim=azim); ax.set_axis_off(); ax.set_title(title, fontsize=10, color="#cfd6d3")

    teal = np.array(TEAL) / 255; dark = np.array(TEAL_DARK) / 255; blk = np.array(BLACK) / 255; green = np.array(PI_GREEN) / 255
    fig = plt.figure(figsize=(15, 7.5), dpi=110, facecolor="#000")
    ax1 = fig.add_subplot(1, 2, 1, projection="3d"); ax1.set_facecolor("#000")
    draw(ax1, [(meshes["body"], teal, (0, 0, 0)), (meshes["face"], teal, (0, 0, 45)), (meshes["button"], dark, (0, 25, 0)),
               (meshes["pi"], green, (0, 0, 0)), (meshes["bank"], (0.3, 0.3, 0.32, 0.5), (0, 0, 0))], 24, -50, "exploded")
    ax2 = fig.add_subplot(1, 2, 2, projection="3d"); ax2.set_facecolor("#000")
    draw(ax2, [(meshes["body"], teal, (0, 0, 0)), (meshes["face"], teal, (0, 0, 0)), (meshes["button"], dark, (0, 0, 0)),
               (meshes["screen"], blk, (0, 0, 0))], 18, -62, "assembled")
    fig.suptitle("Galatiqon enclosure, print-simple", color="#e8ecea", fontsize=13)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=0.92, wspace=0)
    out = os.path.join(PNG, "galatiqon-print.png"); fig.savefig(out, facecolor="#000"); plt.close(fig)
    print("preview ->", os.path.relpath(out, HERE))


if __name__ == "__main__":
    parts, _ = build()
    meshes = export(parts)
    if "--no-render" not in sys.argv:
        preview(meshes)
