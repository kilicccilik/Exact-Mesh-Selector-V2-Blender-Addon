# Exact Mesh Selector V2

**Blender Addon** — by [Salih Kılıç](https://kilicsalih.com)  
Version 2.0 · Blender 4.0+

---

## What it does

In complex scenes with hundreds or thousands of objects, finding every mesh that shares the same topology as your selection is tedious. This addon solves that in one click — select an object, hit **Select Similar Meshes**, and every geometrically identical mesh in the scene gets selected instantly.

Unlike Blender's built-in "Select Similar" operator, this addon uses **hash-based fingerprinting** that compares actual vertex positions, edge connections, and face normals — not just object properties.

---

## What's new in V2

| Feature | V1 | V2 |
|---|---|---|
| Vertex coordinate comparison | ✅ | ✅ |
| Edge + face topology comparison | ❌ | ✅ Strict mode |
| Hash-based O(1) lookup | ❌ | ✅ |
| World space comparison | ❌ | ✅ |
| Adjustable precision / tolerance | ❌ | ✅ |
| Select linked duplicates (Alt+D) | ❌ | ✅ |
| Deselect non-matching | ❌ | ✅ |
| Scene topology report | ❌ | ✅ |
| User feedback (match count) | ❌ | ✅ |

---

## Comparison modes

**Fast** — compares only vertex, edge, and face counts. Instant on massive scenes, but can produce false positives.

**Topology** *(default)* — compares sorted vertex coordinates. Accurate for the vast majority of use cases and still very fast.

**Strict** — compares vertex positions + edge connectivity + face normals. Maximum accuracy, slightly slower on high-poly meshes.

---

## Precision

Controls how many decimal places are used when comparing vertex coordinates.

| Value | Behavior |
|---|---|
| `1–2` | Tolerant — matches near-identical meshes with minor floating-point differences |
| `4` *(default)* | Balanced — catches real differences while ignoring floating-point noise |
| `7–8` | Strict — near byte-perfect comparison |

---

## Buttons

### Select Similar Meshes
Scans the entire scene and selects all objects whose mesh topology matches the active selection. Supports multi-object selection as source.

### Select Linked (Same Data)
Selects all objects sharing the exact same mesh data-block — i.e. linked duplicates created with `Alt+D`. No hashing required, runs instantly regardless of scene size.

### Deselect Non-Matching
From the current selection, removes any object that doesn't match the active object's topology. Useful for cleaning up mixed selections.

### Scene Topology Report
Scans the full scene and prints a breakdown of unique topologies, duplicate groups, and one-of-a-kind meshes to the Blender system console.

---

## Installation

1. Download the `ExactMeshSelector_V2` folder and compress it as a `.zip`
2. In Blender: `Edit > Preferences > Add-ons > Install` → select the zip
3. Enable **Exact Mesh Selector V2**
4. Find it in `View3D > Sidebar (N) > Tools`

---

## License

MIT — free to use, modify, and distribute. Credit appreciated.

---

## Author

**Salih Kılıç** — Art Director & Creative Developer  
🌐 [kilicsalih.com](https://kilicsalih.com)  
✉️ salihkilic@live.com
