bl_info = {
    "name": "Exact Mesh Selector V2",
    "author": "Salih Kılıç (kilicsalih.com)",
    "version": (2, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Tools",
    "description": "Selects all objects sharing the same mesh topology as the active selection. Hash-based, fast, with tolerance and mode options.",
    "doc_url": "https://kilicsalih.com",
    "tracker_url": "mailto:salihkilic@live.com",
    "support": "COMMUNITY",
    "category": "Object",
}

import bpy
import bmesh
import hashlib
import struct
import numpy as np
from bpy.props import FloatProperty, BoolProperty, EnumProperty, IntProperty


# ─────────────────────────────────────────────
#  CORE: Mesh fingerprint üretimi
# ─────────────────────────────────────────────

def _pack_floats(values, precision):
    """Float listesini verilen hassasiyette yuvarla ve bytes'a çevir."""
    factor = 10 ** precision
    rounded = [round(v * factor) for v in values]
    return struct.pack(f"{len(rounded)}i", *rounded)


def get_mesh_fingerprint(obj, mode='TOPOLOGY', precision=4, use_world_space=False):
    """
    Bir objenin mesh'ini temsil eden deterministik bir hash döndürür.

    mode:
      'TOPOLOGY'  - vertex sayısı + edge sayısı + face sayısı + sorted vertex coords
      'STRICT'    - topology + sorted edge vertex index pairs + face vertex counts
      'FAST'      - sadece vert/edge/face sayıları (hızlı ama kaba)

    use_world_space:
      True  - world matrix uygulanmış koordinatlar (scale/rotation bağımsız karşılaştırma)
      False - local space (linked duplicate'ları yakalar, transform farklı olabilir)
    """
    mesh = obj.data
    vert_count = len(mesh.vertices)
    edge_count = len(mesh.edges)
    face_count = len(mesh.polygons)

    hasher = hashlib.blake2b(digest_size=20)

    # Temel topoloji sayıları — her modda var
    hasher.update(struct.pack("3i", vert_count, edge_count, face_count))

    if mode == 'FAST':
        return hasher.hexdigest()

    # Vertex koordinatları
    if use_world_space:
        mat = obj.matrix_world
        coords = [mat @ v.co for v in mesh.vertices]
        flat = [c for v in coords for c in (v.x, v.y, v.z)]
    else:
        flat = [c for v in mesh.vertices for c in (v.co.x, v.co.y, v.co.z)]

    # Sırala (transform-order bağımsız hale getir)
    verts_np = np.array(flat, dtype=np.float64).reshape(-1, 3)
    verts_np = np.round(verts_np, precision)
    verts_sorted = verts_np[np.lexsort(verts_np.T[::-1])]
    hasher.update(verts_sorted.tobytes())

    if mode == 'STRICT':
        # Edge bağlantıları
        edge_pairs = sorted((e.vertices[0], e.vertices[1]) for e in mesh.edges)
        for v0, v1 in edge_pairs:
            hasher.update(struct.pack("2i", v0, v1))

        # Face vertex sayıları (n-gon topolojisi)
        face_sizes = sorted(len(p.vertices) for p in mesh.polygons)
        hasher.update(struct.pack(f"{len(face_sizes)}i", *face_sizes))

        # Face normal yönleri (sorted)
        normals = sorted(
            (round(p.normal.x, 3), round(p.normal.y, 3), round(p.normal.z, 3))
            for p in mesh.polygons
        )
        for n in normals:
            hasher.update(_pack_floats(n, 3))

    return hasher.hexdigest()


# ─────────────────────────────────────────────
#  OPERATOR: Select Similar Meshes
# ─────────────────────────────────────────────

class OBJECT_OT_SelectSimilarMeshes(bpy.types.Operator):
    bl_idname = "object.select_similar_meshes_v2"
    bl_label = "Select Similar Meshes"
    bl_description = (
        "Selects all objects in the scene that share the same mesh topology "
        "as the currently selected object(s)"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.exact_mesh_selector_props
        mode = props.comparison_mode
        precision = props.precision
        use_world = props.use_world_space
        extend = props.extend_selection

        selected = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if not selected:
            self.report({'WARNING'}, "No mesh object selected.")
            return {'CANCELLED'}

        # Seçili objelerin fingerprint'lerini al
        target_hashes = set()
        for obj in selected:
            try:
                fp = get_mesh_fingerprint(obj, mode=mode, precision=precision, use_world_space=use_world)
                target_hashes.add(fp)
            except Exception as e:
                self.report({'WARNING'}, f"Could not fingerprint '{obj.name}': {e}")

        if not target_hashes:
            self.report({'ERROR'}, "Could not generate fingerprints for selected objects.")
            return {'CANCELLED'}

        # Tüm sahneyi tara
        selected_set = set(selected)
        found = []
        skipped = 0

        for obj in context.view_layer.objects:
            if obj.type != 'MESH':
                continue
            if obj in selected_set:
                continue
            if not obj.visible_get():
                skipped += 1
                continue

            try:
                fp = get_mesh_fingerprint(obj, mode=mode, precision=precision, use_world_space=use_world)
                if fp in target_hashes:
                    found.append(obj)
            except Exception:
                pass

        # Seçimi güncelle
        if not extend:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in selected:
                obj.select_set(True)

        for obj in found:
            obj.select_set(True)

        # Kullanıcıya bildir
        hidden_note = f" ({skipped} hidden object(s) skipped)" if skipped else ""
        if found:
            self.report(
                {'INFO'},
                f"Found {len(found)} matching mesh(es) — {len(target_hashes)} unique fingerprint(s) searched.{hidden_note}"
            )
        else:
            self.report(
                {'WARNING'},
                f"No matching meshes found.{hidden_note} Try lowering Precision or switching to FAST mode."
            )

        return {'FINISHED'}


# ─────────────────────────────────────────────
#  OPERATOR: Select by Shared Mesh Data-Block
# ─────────────────────────────────────────────

class OBJECT_OT_SelectLinkedMeshes(bpy.types.Operator):
    bl_idname = "object.select_linked_meshes_v2"
    bl_label = "Select Linked (Same Data)"
    bl_description = (
        "Selects all objects that share the exact same mesh data-block "
        "(linked duplicates — Alt+D). Instant, no hashing needed."
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if not selected:
            self.report({'WARNING'}, "No mesh object selected.")
            return {'CANCELLED'}

        target_data = {obj.data for obj in selected}
        found = []

        for obj in context.view_layer.objects:
            if obj.type == 'MESH' and obj not in selected and obj.data in target_data:
                found.append(obj)

        for obj in found:
            obj.select_set(True)

        self.report({'INFO'}, f"{len(found)} linked duplicate(s) selected.")
        return {'FINISHED'}


# ─────────────────────────────────────────────
#  OPERATOR: Deselect Non-Matching
# ─────────────────────────────────────────────

class OBJECT_OT_DeselectNonMatching(bpy.types.Operator):
    bl_idname = "object.deselect_non_matching_v2"
    bl_label = "Deselect Non-Matching"
    bl_description = (
        "From the current selection, keeps only objects that share "
        "the same topology as the ACTIVE object. Deselects the rest."
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.exact_mesh_selector_props
        active = context.active_object

        if not active or active.type != 'MESH':
            self.report({'WARNING'}, "Active object must be a mesh.")
            return {'CANCELLED'}

        target_fp = get_mesh_fingerprint(
            active,
            mode=props.comparison_mode,
            precision=props.precision,
            use_world_space=props.use_world_space
        )

        deselected = 0
        for obj in context.selected_objects:
            if obj == active or obj.type != 'MESH':
                continue
            fp = get_mesh_fingerprint(
                obj,
                mode=props.comparison_mode,
                precision=props.precision,
                use_world_space=props.use_world_space
            )
            if fp != target_fp:
                obj.select_set(False)
                deselected += 1

        self.report({'INFO'}, f"{deselected} non-matching object(s) deselected.")
        return {'FINISHED'}


# ─────────────────────────────────────────────
#  OPERATOR: Scene Report
# ─────────────────────────────────────────────

class OBJECT_OT_MeshReport(bpy.types.Operator):
    bl_idname = "object.mesh_topology_report_v2"
    bl_label = "Scene Topology Report"
    bl_description = "Scans the entire scene and groups all mesh objects by unique topology"
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.exact_mesh_selector_props
        mode = props.comparison_mode
        precision = props.precision

        groups = {}  # hash -> [obj names]

        for obj in context.view_layer.objects:
            if obj.type != 'MESH':
                continue
            try:
                fp = get_mesh_fingerprint(obj, mode=mode, precision=precision)
                groups.setdefault(fp, []).append(obj.name)
            except Exception:
                pass

        unique = len(groups)
        total = sum(len(v) for v in groups.values())
        duplicated = sum(len(v) for v in groups.values() if len(v) > 1)
        unique_singles = sum(1 for v in groups.values() if len(v) == 1)

        lines = [
            "─" * 42,
            f"  EXACT MESH SELECTOR — Scene Report",
            "─" * 42,
            f"  Total mesh objects  : {total}",
            f"  Unique topologies   : {unique}",
            f"  Objects with copies : {duplicated}",
            f"  One-of-a-kind       : {unique_singles}",
            "─" * 42,
            "  Top duplicate groups:",
        ]

        sorted_groups = sorted(groups.values(), key=len, reverse=True)
        for i, names in enumerate(sorted_groups[:8]):
            if len(names) < 2:
                break
            lines.append(f"  [{len(names):3d}x]  {names[0]}  ...and {len(names)-1} more")

        report_text = "\n".join(lines)
        print(report_text)

        self.report(
            {'INFO'},
            f"Scene: {total} meshes | {unique} unique topologies | {duplicated} have copies — see Console for full report"
        )
        return {'FINISHED'}


# ─────────────────────────────────────────────
#  PROPERTIES
# ─────────────────────────────────────────────

class ExactMeshSelectorProperties(bpy.types.PropertyGroup):

    comparison_mode: EnumProperty(
        name="Mode",
        description="How strictly to compare mesh topology",
        items=[
            ('FAST',     "Fast",     "Compare only vertex/edge/face counts. Fastest, least accurate."),
            ('TOPOLOGY', "Topology", "Compare sorted vertex positions. Accurate for most cases."),
            ('STRICT',   "Strict",   "Compare positions + edge connections + face normals. Most accurate, slower on large meshes."),
        ],
        default='TOPOLOGY',
    )

    precision: IntProperty(
        name="Precision",
        description="Decimal places used when comparing vertex coordinates. Lower = more tolerant (catches near-identical meshes). Higher = more exact.",
        default=4,
        min=1,
        max=8,
    )

    use_world_space: BoolProperty(
        name="World Space",
        description=(
            "Compare vertices in world space (ignores object transforms). "
            "Useful for finding duplicates regardless of scale/rotation/position. "
            "Disable to match only objects with the same local mesh shape."
        ),
        default=False,
    )

    extend_selection: BoolProperty(
        name="Extend Selection",
        description="Add found objects to current selection instead of replacing it",
        default=True,
    )


# ─────────────────────────────────────────────
#  PANEL
# ─────────────────────────────────────────────

class OBJECT_PT_ExactMeshSelectorPanel(bpy.types.Panel):
    bl_label = "Exact Mesh Selector"
    bl_idname = "OBJECT_PT_exact_mesh_selector_v2"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Tools"

    def draw(self, context):
        layout = self.layout
        props = context.scene.exact_mesh_selector_props
        active = context.active_object

        # ── Aktif obje bilgisi ──
        box = layout.box()
        if active and active.type == 'MESH':
            row = box.row()
            row.label(text=active.name, icon='MESH_DATA')
            mesh = active.data
            col = box.column(align=True)
            col.label(text=f"Verts: {len(mesh.vertices):,}   Edges: {len(mesh.edges):,}   Faces: {len(mesh.polygons):,}", icon='INFO')
        else:
            box.label(text="No mesh selected", icon='ERROR')

        layout.separator(factor=0.5)

        # ── Ayarlar ──
        col = layout.column(align=True)
        col.label(text="Comparison Settings", icon='SETTINGS')
        col.prop(props, "comparison_mode", text="Mode")
        col.prop(props, "precision", text="Precision")
        col.prop(props, "use_world_space")
        col.prop(props, "extend_selection")

        layout.separator(factor=0.5)

        # ── Ana butonlar ──
        col = layout.column(align=True)
        col.scale_y = 1.5

        op_row = col.row(align=True)
        op_row.enabled = active is not None and active.type == 'MESH'
        op_row.operator(
            "object.select_similar_meshes_v2",
            text="Select Similar Meshes",
            icon='RESTRICT_SELECT_OFF'
        )

        col.separator(factor=0.3)
        col.operator(
            "object.select_linked_meshes_v2",
            text="Select Linked (Same Data)",
            icon='LINKED'
        )

        col.separator(factor=0.3)
        col.operator(
            "object.deselect_non_matching_v2",
            text="Deselect Non-Matching",
            icon='X'
        )

        layout.separator(factor=0.5)

        # ── Rapor ──
        layout.operator(
            "object.mesh_topology_report_v2",
            text="Scene Topology Report",
            icon='ZOOM_ALL'
        )

        layout.separator(factor=0.3)

        # ── Seçim durumu ──
        sel_meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if sel_meshes:
            info = layout.box()
            info.label(text=f"{len(sel_meshes)} mesh(es) selected", icon='CHECKMARK')

        layout.separator(factor=0.8)

        # ── Credit ──
        col = layout.column(align=True)
        col.scale_y = 0.8
        col.label(text="Salih Kılıç", icon='USER')
        col.label(text="kilicsalih.com", icon='URL')
        col.label(text="salihkilic@live.com", icon='INTERNET')


# ─────────────────────────────────────────────
#  REGISTER
# ─────────────────────────────────────────────

_classes = [
    ExactMeshSelectorProperties,
    OBJECT_OT_SelectSimilarMeshes,
    OBJECT_OT_SelectLinkedMeshes,
    OBJECT_OT_DeselectNonMatching,
    OBJECT_OT_MeshReport,
    OBJECT_PT_ExactMeshSelectorPanel,
]


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.exact_mesh_selector_props = bpy.props.PointerProperty(
        type=ExactMeshSelectorProperties
    )


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.exact_mesh_selector_props


if __name__ == "__main__":
    register()
