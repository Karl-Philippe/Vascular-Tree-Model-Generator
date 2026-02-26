import cadquery as cq
import math
import os
import json
from copy import deepcopy

# =============================================================================
# CONFIG SELECTION (no argparse, simple and explicit)
# =============================================================================

CONFIG_DIR = "configs"
CONFIG_FILE = "vascular_tree_25mm.json"  # Change this to switch presets
CONFIG_PATH = os.path.join(CONFIG_DIR, CONFIG_FILE)

# =============================================================================
# CONFIG LOADING / VALIDATION
# =============================================================================

def load_json_config(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    return normalize_and_validate_config(cfg, path)


def require_keys(d, keys, ctx):
    missing = [k for k in keys if k not in d]
    if missing:
        raise KeyError(f"Missing key(s) in {ctx}: {missing}")


def normalize_and_validate_config(cfg, source="<config>"):
    cfg = deepcopy(cfg)

    # Backward-compatible defaults
    cfg.setdefault("add_adapter", True)
    cfg.setdefault("add_secondary_branches", False)

    # Required top-level blocks (adapter_params handled conditionally)
    require_keys(
        cfg,
        [
            "main_branch_params",
            "primary_branch_params",
            "secondary_branch_params",
            "wall_thickness",
            "add_secondary_branches",
            "rounding",
            "output",
        ],
        f"{source} (top-level)",
    )

    adapter_params = cfg.get("adapter_params", None)
    main_branch_params = cfg["main_branch_params"]
    primary_branch_params = cfg["primary_branch_params"]
    secondary_branch_params = cfg["secondary_branch_params"]
    rounding = cfg["rounding"]
    output = cfg["output"]

    # Adapter params are only required if adapter is enabled
    if cfg["add_adapter"]:
        if adapter_params is None:
            raise KeyError("Missing key 'adapter_params' while add_adapter is True")

        # Support both spellings for backward compatibility
        if "external_diameter" not in adapter_params:
            if "extermal_diameter" in adapter_params:
                adapter_params["external_diameter"] = adapter_params["extermal_diameter"]
            else:
                raise KeyError(
                    "adapter_params must contain 'external_diameter' "
                    "(or legacy 'extermal_diameter')."
                )

        require_keys(adapter_params, ["internal_diameter", "external_diameter", "length"], "adapter_params")
    else:
        # If adapter params exist, normalize spelling anyway (harmless)
        if (
            adapter_params is not None
            and "external_diameter" not in adapter_params
            and "extermal_diameter" in adapter_params
        ):
            adapter_params["external_diameter"] = adapter_params["extermal_diameter"]

    require_keys(main_branch_params, ["diameter", "length"], "main_branch_params")
    require_keys(primary_branch_params, ["angles", "relative_positions", "diameters", "length"], "primary_branch_params")
    require_keys(secondary_branch_params, ["angles", "relative_positions", "diameters", "length"], "secondary_branch_params")
    require_keys(
        rounding,
        [
            "external_intersection_rounding",
            "external_micro_rounding",
            "internal_intersection_rounding",
            "internal_micro_rounding",
        ],
        "rounding",
    )
    require_keys(output, ["folder", "filename"], "output")

    # Basic scalar checks
    if cfg["wall_thickness"] < 0:
        raise ValueError("wall_thickness must be >= 0")
    if main_branch_params["diameter"] <= 0 or main_branch_params["length"] <= 0:
        raise ValueError("main_branch_params diameter and length must be > 0")

    # Validate primary branch arrays
    n_primary = len(primary_branch_params["angles"])
    if len(primary_branch_params["relative_positions"]) != n_primary:
        raise ValueError("primary_branch_params.relative_positions length must match angles length")
    if len(primary_branch_params["diameters"]) != n_primary:
        raise ValueError("primary_branch_params.diameters length must match angles length")
    if n_primary == 0:
        raise ValueError("primary_branch_params must contain at least one branch")

    for i, rp in enumerate(primary_branch_params["relative_positions"]):
        if not (0.0 <= rp <= 1.0):
            raise ValueError(f"primary_branch_params.relative_positions[{i}]={rp} must be between 0 and 1")

    # Validate secondary branch arrays (only strictly needed if enabled)
    if cfg["add_secondary_branches"]:
        n_secondary = len(secondary_branch_params["angles"])
        if len(secondary_branch_params["relative_positions"]) != n_secondary:
            raise ValueError("secondary_branch_params.relative_positions length must match angles length")
        if len(secondary_branch_params["diameters"]) != n_secondary:
            raise ValueError("secondary_branch_params.diameters length must match angles length")

        expected_secondary = 2 * n_primary
        if n_secondary < expected_secondary:
            raise ValueError(
                f"Not enough secondary branches configured: need at least {expected_secondary}, got {n_secondary}"
            )

        for i, rp in enumerate(secondary_branch_params["relative_positions"]):
            if not (0.0 <= rp <= 1.0):
                raise ValueError(f"secondary_branch_params.relative_positions[{i}]={rp} must be between 0 and 1")

    # Precompute absolute positions of primary branches
    primary_branch_params["positions"] = [
        pos * main_branch_params["length"] for pos in primary_branch_params["relative_positions"]
    ]

    return cfg


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


def create_branch(position, angle, diameter, length, wall_thickness):
    """Create a single branch (solid only)."""
    outer_circle = cq.Sketch().circle(diameter / 2 + wall_thickness)
    return (
        cq.Workplane("XZ")
        .workplane(offset=position)
        .transformed(rotate=(0, angle, 0))
        .placeSketch(outer_circle)
        .extrude(length)
    )


def create_secondary_branch(
    parent_position,
    parent_angle,
    parent_length,
    offset_percent,
    angle,
    diameter,
    length,
    wall_thickness,
):
    """Create a secondary branch (solid only)."""
    offset_distance = offset_percent * parent_length
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
    Return edges that are NOT perfect circles.
    This excludes most cylinder extremity rims (which you usually don't want rounded).
    """
    edges = []
    for e in wp.edges().vals():
        try:
            if e.geomType() != "CIRCLE":
                edges.append(e)
        except Exception:
            continue
    return edges


def fillet_non_circular_edges(wp, target_radius, label=""):
    """
    Apply fillet only on non-circular edges.
    This tends to hit union seams/intersection edges and avoids cylinder rims.
    """
    if target_radius <= 0:
        return wp

    edges = select_non_circular_edges(wp)
    if not edges:
        if label:
            print(f"  ↪ {label}: no non-circular edges found to fillet.")
        return wp

    for scale in (1.0, 0.8, 0.6, 0.4, 0.3, 0.2):
        r = target_radius * scale
        try:
            out = wp.newObject(edges).fillet(r)
            if label:
                print(f"  ✔ {label} fillet OK at r={r:.3f} mm")
            return out
        except Exception:
            continue

    if label:
        print(f"  ✖ {label} fillet failed (target r={target_radius:.3f} mm)")
    return wp


# =============================================================================
# BUILD MODEL
# =============================================================================

def build_vascular_tree(cfg):
    adapter_params = cfg.get("adapter_params", {})
    main_branch_params = cfg["main_branch_params"]
    primary_branch_params = cfg["primary_branch_params"]
    secondary_branch_params = cfg["secondary_branch_params"]

    wall_thickness = cfg["wall_thickness"]
    add_adapter = cfg.get("add_adapter", True)
    add_secondary_branches = cfg["add_secondary_branches"]

    external_intersection_rounding = cfg["rounding"]["external_intersection_rounding"]
    external_micro_rounding = cfg["rounding"]["external_micro_rounding"]
    internal_intersection_rounding = cfg["rounding"]["internal_intersection_rounding"]
    internal_micro_rounding = cfg["rounding"]["internal_micro_rounding"]

    output_folder = cfg["output"]["folder"]
    output_file = os.path.join(output_folder, cfg["output"]["filename"])

    print(f"Using config: {CONFIG_PATH}")
    print(f"Output file: {output_file}")
    print(f"add_adapter={add_adapter}, add_secondary_branches={add_secondary_branches}")

    # Main outer solid
    print("Generating the main branch...")
    main_outer = cq.Sketch().circle(main_branch_params["diameter"] / 2 + wall_thickness)
    main_branch = cq.Workplane("XZ").placeSketch(main_outer).extrude(main_branch_params["length"])
    main_branch = safe_clean(main_branch, "main branch")

    holes = []

    # Main lumen
    print("Generating main lumen...")
    main_branch_hole = (
        cq.Workplane("XZ")
        .circle(main_branch_params["diameter"] / 2)
        .extrude(main_branch_params["length"])
    )
    holes.append(main_branch_hole)

    # Optional adapter geometry
    if add_adapter:
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
        adapter_outer_diam = adapter_params["external_diameter"]
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
    else:
        print("Adapter disabled (add_adapter=false) -> skipping cap/tube/lumen.")

    # Primary + optional secondary branches
    secondary_index = 0
    n_primary = len(primary_branch_params["angles"])

    for i, branch_angle in enumerate(primary_branch_params["angles"]):
        branch_position = primary_branch_params["positions"][i]
        branch_diameter = primary_branch_params["diameters"][i]

        print(f"Adding primary branch {i + 1}/{n_primary}...")
        branch = create_branch(
            branch_position,
            branch_angle,
            branch_diameter,
            primary_branch_params["length"],
            wall_thickness,
        )
        main_branch = main_branch.union(branch, clean=True)

        # Primary lumen
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
                sec_angle_rel = secondary_branch_params["angles"][secondary_index]
                sec_angle = branch_angle - sec_angle_rel
                sec_diam = secondary_branch_params["diameters"][secondary_index]
                sec_len = secondary_branch_params["length"]
                sec_rel = secondary_branch_params["relative_positions"][secondary_index]

                secondary_branch = create_secondary_branch(
                    branch_position,
                    branch_angle,
                    primary_branch_params["length"],
                    sec_rel,
                    sec_angle,
                    sec_diam,
                    sec_len,
                    wall_thickness,
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

    # Exterior rounding (before lumen cut)
    print("Applying EXTERIOR rounding (junction seams only, if enabled)...")
    main_branch = fillet_non_circular_edges(main_branch, external_intersection_rounding, label="EXTERIOR")
    main_branch = fillet_non_circular_edges(main_branch, external_micro_rounding, label="EXTERIOR micro")

    # Combine lumen and round lumen seams before subtraction
    print("Combining lumen geometry...")
    lumen = holes[0]
    for h in holes[1:]:
        lumen = lumen.union(h, clean=True)
    lumen = safe_clean(lumen, "lumen union")

    print("Applying INTERIOR (lumen) rounding (junction seams only, if enabled)...")
    lumen = fillet_non_circular_edges(lumen, internal_intersection_rounding, label="LUMEN")
    lumen = fillet_non_circular_edges(lumen, internal_micro_rounding, label="LUMEN micro")

    # Subtract lumen
    print("Subtracting lumen from the structure...")
    main_branch = main_branch.cut(lumen)
    main_branch = safe_clean(main_branch, "after lumen cut")

    # Export
    print("Finalizing and exporting the model...")
    os.makedirs(output_folder, exist_ok=True)
    cq.exporters.export(main_branch, output_file)
    print(f"File successfully exported to {output_file}")


if __name__ == "__main__":
    config = load_json_config(CONFIG_PATH)
    build_vascular_tree(config)