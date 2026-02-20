import cadquery as cq
import math
import os

# =============================================================================
# PARAMETERS
# =============================================================================

adapter_params = {
    "internal_diameter": 10,   # mm
    "extermal_diameter": 17,  # mm (kept original key spelling)
    "length": 50,             # mm
}

main_branch_params = {
    "diameter": 12,  # mm
    "length": 150,   # mm
}

primary_branch_params = {
    "angles": [70, -60, 40, -50, 30, -20],
    "relative_positions": [0.10, 0.20, 0.30, 0.40, 0.50, 0.60],
    "diameters": [6, 8, 9, 7, 11, 7],  # mm
    "length": 50,  # mm
}

secondary_branch_params = {
    "angles": [40, -40] * 6,  # degrees
    "relative_positions": [0.4, 0.7, 0.7, 0.4, 0.7, 0.4, 0.7, 0.4, 0.7, 0.4, 0.4, 0.7],
    "diameters": [8, 7, 7, 8, 10, 9, 7, 9, 8, 9, 10, 7],  # mm
    "length": 40,  # mm
}

wall_thickness = 0.5
add_secondary_branches = False

# --- Organic rounding (mm) ---
# Outer junction blends (EXTERIOR)
external_intersection_rounding = 2.0
external_micro_rounding        = 0.5

# Inner junction blends (LUMEN)
internal_intersection_rounding = 2.0
internal_micro_rounding        = 0.5

# Output
output_folder = "output"
output_file = os.path.join(output_folder, "vascular_tree.stl")

# Precompute absolute positions of primary branches
primary_branch_params["positions"] = [
    pos * main_branch_params["length"] for pos in primary_branch_params["relative_positions"]
]

# =============================================================================
# HELPERS
# =============================================================================

def safe_clean(wp, label=""):
    """Attempt to heal geometry; ignore if not supported/needed."""
    try:
        wp = wp.clean()
        if label:
            print(f"  ✔ Cleaned: {label}")
    except Exception:
        pass
    return wp

def create_branch(position, angle, diameter, length):
    """Create a single branch (solid only)."""
    outer_circle = cq.Sketch().circle(diameter / 2 + wall_thickness)
    return (
        cq.Workplane("XZ")
        .workplane(offset=position)
        .transformed(rotate=(0, angle, 0))
        .placeSketch(outer_circle)
        .extrude(length)
    )

def create_secondary_branch(parent_position, parent_angle, offset_percent, angle, diameter, length):
    """Create a secondary branch (solid only)."""
    offset_distance = offset_percent * primary_branch_params["length"]
    angle_rad = math.radians(parent_angle)

    outer_circle = cq.Sketch().circle(diameter / 2 + wall_thickness)
    return (
        cq.Workplane("XZ")
        .workplane(offset=parent_position)
        .transformed(
            rotate=(0, angle, 0),
            offset=(
                offset_distance * math.sin(angle_rad),
                0,
                offset_distance * math.cos(angle_rad),
            ),
        )
        .placeSketch(outer_circle)
        .extrude(length)
    )

def select_non_circular_edges(wp):
    """
    Return a list of edges that are NOT perfect circles.
    This excludes the cylinder extremity rims (what you don't want rounded).
    """
    edges = []
    for e in wp.edges().vals():
        try:
            gt = e.geomType()
            if gt != "CIRCLE":
                edges.append(e)
        except Exception:
            # if geomType fails, ignore that edge rather than crashing
            continue
    return edges

def fillet_non_circular_edges(wp, target_radius, label=""):
    """
    Apply fillet only on non-circular edges.
    This tends to hit union seams / intersection edges, and avoids cylinder rims.
    """
    if target_radius <= 0:
        return wp

    edges = select_non_circular_edges(wp)
    if not edges:
        if label:
            print(f"  ↪ {label}: no non-circular edges found to fillet.")
        return wp

    # Try decreasing radii until something works
    for scale in (1.0, 0.8, 0.6, 0.4, 0.3, 0.2):
        r = target_radius * scale
        try:
            out = wp.newObject(edges).fillet(r)
            if label:
                print(f"  ✔ {label} fillet (non-circular edges) OK at r={r:.3f} mm")
            return out
        except Exception:
            continue

    if label:
        print(f"  ✖ {label} fillet failed (target r={target_radius:.3f} mm)")
    return wp

# =============================================================================
# BUILD MODEL
# =============================================================================

print("Generating the main branch...")
main_outer = cq.Sketch().circle(main_branch_params["diameter"] / 2 + wall_thickness)
main_branch = cq.Workplane("XZ").placeSketch(main_outer).extrude(main_branch_params["length"])
main_branch = safe_clean(main_branch, "main branch")

holes = []

print("Generating main lumen...")
main_branch_hole = (
    cq.Workplane("XZ")
    .circle(main_branch_params["diameter"] / 2)
    .extrude(main_branch_params["length"])
)
holes.append(main_branch_hole)

print("Generating the adapter cap...")
cap_outer = cq.Sketch().circle(main_branch_params["diameter"] / 2 + wall_thickness)
cap = (
    cq.Workplane("XZ")
    .workplane(offset=-wall_thickness)
    .placeSketch(cap_outer)
    .extrude(wall_thickness, clean=True)
)
main_branch = main_branch.union(cap, clean=True)

print("Generating the adapter tube...")
adapter_outer_diam = adapter_params.get("external_diameter", adapter_params["extermal_diameter"])
adapter_outer = cq.Sketch().circle(adapter_outer_diam / 2)
adapter_tube = (
    cq.Workplane("XZ")
    .workplane(offset=-adapter_params["length"] - wall_thickness)
    .placeSketch(adapter_outer)
    .extrude(adapter_params["length"], clean=True)
)
main_branch = main_branch.union(adapter_tube, clean=True)

print("Generating adapter lumen...")
adapter_hole = (
    cq.Workplane("XZ")
    .workplane(offset=-adapter_params["length"] - wall_thickness)
    .circle(adapter_params["internal_diameter"] / 2)
    .extrude(adapter_params["length"] + wall_thickness)
)
holes.append(adapter_hole)

secondary_index = 0
for i, branch_angle in enumerate(primary_branch_params["angles"]):
    branch_position = primary_branch_params["positions"][i]
    branch_diameter = primary_branch_params["diameters"][i]

    print(f"Adding primary branch {i + 1}/{len(primary_branch_params['angles'])}...")
    branch = create_branch(branch_position, branch_angle, branch_diameter, primary_branch_params["length"])
    main_branch = main_branch.union(branch, clean=True)

    # Add hole for the primary branch
    hole = (
        cq.Workplane("XZ")
        .workplane(offset=branch_position)
        .transformed(rotate=(0, branch_angle, 0))
        .circle(branch_diameter / 2)
        .extrude(primary_branch_params["length"])
    )
    holes.append(hole)

    if add_secondary_branches:
        for _ in range(2):
            print(f"  Adding secondary branch on primary {i + 1} (idx {secondary_index})...")
            sec_angle = branch_angle - secondary_branch_params["angles"][secondary_index]
            sec_diam  = secondary_branch_params["diameters"][secondary_index]
            sec_len   = secondary_branch_params["length"]
            sec_rel   = secondary_branch_params["relative_positions"][secondary_index]

            secondary_branch = create_secondary_branch(
                branch_position,
                branch_angle,
                sec_rel,
                sec_angle,
                sec_diam,
                sec_len,
            )
            main_branch = main_branch.union(secondary_branch, clean=True)

            offset_distance = sec_rel * primary_branch_params["length"]
            sec_hole = (
                cq.Workplane("XZ")
                .workplane(offset=branch_position)
                .transformed(
                    rotate=(0, sec_angle, 0),
                    offset=(
                        offset_distance * math.sin(math.radians(branch_angle)),
                        0,
                        offset_distance * math.cos(math.radians(branch_angle)),
                    ),
                )
                .circle(sec_diam / 2)
                .extrude(sec_len)
            )
            holes.append(sec_hole)

            secondary_index += 1

main_branch = safe_clean(main_branch, "all unions")

# =============================================================================
# EXTERIOR ROUNDING (junctions only, excludes cylinder rims)
# =============================================================================

print("Applying organic EXTERIOR rounding (junction seams only, no extremities)...")
main_branch = fillet_non_circular_edges(main_branch, external_intersection_rounding, label="EXTERIOR")

print("Applying organic EXTERIOR micro-rounding (junction seams only)...")
main_branch = fillet_non_circular_edges(main_branch, external_micro_rounding, label="EXTERIOR micro")

# =============================================================================
# LUMEN BUILD + ROUNDING (junctions only, excludes end rims)
# =============================================================================

print("Combining lumen geometry...")
lumen = holes[0]
for h in holes[1:]:
    lumen = lumen.union(h, clean=True)
lumen = safe_clean(lumen, "lumen union")

print("Applying organic INTERIOR (lumen) rounding (junction seams only, no extremities)...")
lumen = fillet_non_circular_edges(lumen, internal_intersection_rounding, label="LUMEN")

print("Applying organic INTERIOR micro-rounding (junction seams only)...")
lumen = fillet_non_circular_edges(lumen, internal_micro_rounding, label="LUMEN micro")

# =============================================================================
# SUBTRACT (NO post-cut rim rounding)
# =============================================================================

print("Subtracting lumen from the structure...")
main_branch = main_branch.cut(lumen)
main_branch = safe_clean(main_branch, "after lumen cut")

# =============================================================================
# EXPORT
# =============================================================================

print("Finalizing and exporting the model...")
os.makedirs(output_folder, exist_ok=True)
cq.exporters.export(main_branch, output_file)
print(f"File successfully exported to {output_file}")
