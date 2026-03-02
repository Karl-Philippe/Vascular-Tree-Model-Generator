import cadquery as cq
import math
import os
import json
from copy import deepcopy

# =============================================================================
# CONFIG SELECTION (no argparse, simple and explicit)
# =============================================================================

CONFIG_DIR = "configs"
CONFIG_FILE = "vascular_tree_3D.json"  # Change this to switch presets
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


def _expand_angles(value, n, name):
    """
    Allow config to specify:
      - missing -> handled elsewhere
      - scalar number -> expanded to length n
      - list -> validated length n
    """
    if isinstance(value, (int, float)):
        return [float(value)] * n
    if isinstance(value, list):
        if len(value) != n:
            raise ValueError(f"{name} length must match angles length (expected {n}, got {len(value)})")
        return [float(v) for v in value]
    raise TypeError(f"{name} must be a number or a list of numbers")


def normalize_and_validate_config(cfg, source="<config>"):
    cfg = deepcopy(cfg)

    # Backward-compatible defaults
    cfg.setdefault("add_adapter", True)
    cfg.setdefault("add_secondary_branches", False)

    # New backward-compatible default (helps booleans not fail on “just touching”)
    cfg.setdefault("junction_overlap", 0.3)  # mm of overlap pushed into parent at each junction

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
    if cfg["junction_overlap"] < 0:
        raise ValueError("junction_overlap must be >= 0")

    # Validate primary branch arrays
    n_primary = len(primary_branch_params["angles"])
    if len(primary_branch_params["relative_positions"]) != n_primary:
        raise ValueError("primary_branch_params.relative_positions length must match angles length")
    if len(primary_branch_params["diameters"]) != n_primary:
        raise ValueError("primary_branch_params.diameters length must match angles length")
    if n_primary == 0:
        raise ValueError("primary_branch_params must contain at least one branch")

    # NEW: optional radial angles (azimuth) for primary branches
    if "radial_angles" not in primary_branch_params:
        primary_branch_params["radial_angles"] = [0.0] * n_primary
    else:
        primary_branch_params["radial_angles"] = _expand_angles(
            primary_branch_params["radial_angles"], n_primary, "primary_branch_params.radial_angles"
        )

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

        # NEW: optional radial angles for secondary branches
        if "radial_angles" not in secondary_branch_params:
            secondary_branch_params["radial_angles"] = [0.0] * n_secondary
        else:
            secondary_branch_params["radial_angles"] = _expand_angles(
                secondary_branch_params["radial_angles"], n_secondary, "secondary_branch_params.radial_angles"
            )

        for i, rp in enumerate(secondary_branch_params["relative_positions"]):
            if not (0.0 <= rp <= 1.0):
                raise ValueError(f"secondary_branch_params.relative_positions[{i}]={rp} must be between 0 and 1")
    else:
        # Still normalize radial_angles if present (harmless)
        if "radial_angles" in secondary_branch_params:
            n_secondary = len(secondary_branch_params["angles"])
            secondary_branch_params["radial_angles"] = _expand_angles(
                secondary_branch_params["radial_angles"], n_secondary, "secondary_branch_params.radial_angles"
            )

    # Precompute absolute positions of primary branches along MAIN LENGTH (we use +Z as main axis)
    primary_branch_params["positions"] = [
        pos * main_branch_params["length"] for pos in primary_branch_params["relative_positions"]
    ]

    return cfg


# =============================================================================
# 3D VECTOR / ORIENTED WORKPLANE HELPERS
# =============================================================================

def _v_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

def _v_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

def _v_mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)

def _v_dot(a, b):
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]

def _v_cross(a, b):
    return (
        a[1]*b[2] - a[2]*b[1],
        a[2]*b[0] - a[0]*b[2],
        a[0]*b[1] - a[1]*b[0],
    )

def _v_norm(a):
    return math.sqrt(_v_dot(a, a))

def _v_unit(a):
    n = _v_norm(a)
    if n <= 1e-12:
        raise ValueError("Zero-length direction vector")
    return (a[0]/n, a[1]/n, a[2]/n)


def direction_from_signed_deflection_and_radial(deflection_deg, radial_deg):
    """
    Main trunk axis is +Z.

    deflection_deg is SIGNED like your existing config:
      +angle  => one side of the reference plane
      -angle  => the opposite side

    radial_deg rotates that reference plane around the trunk axis (+Z).
    """
    elev = abs(float(deflection_deg))  # tilt away from +Z
    base_azim = 0.0 if deflection_deg >= 0 else 180.0
    azim = base_azim + float(radial_deg)

    e = math.radians(elev)
    a = math.radians(azim)

    # Spherical coords around +Z:
    # x = sin(e)*cos(a), y = sin(e)*sin(a), z = cos(e)
    return _v_unit((
        math.sin(e) * math.cos(a),
        math.sin(e) * math.sin(a),
        math.cos(e),
    ))


def oriented_workplane(origin, normal):
    """
    Create a workplane whose normal points along `normal` and whose origin is `origin`.
    We pick a stable xDir perpendicular to normal.
    """
    n = _v_unit(normal)

    # Pick a reference axis not (almost) parallel to n
    ref = (1.0, 0.0, 0.0) if abs(_v_dot(n, (1.0, 0.0, 0.0))) < 0.9 else (0.0, 1.0, 0.0)
    xdir = _v_unit(_v_cross(ref, n))

    plane = cq.Plane(
        origin=cq.Vector(*origin),
        xDir=cq.Vector(*xdir),
        normal=cq.Vector(*n),
    )
    return cq.Workplane(plane)


def make_cylinder(origin, direction, radius, length, overlap_back=0.0):
    """
    Cylinder starts slightly 'inside' the parent (overlap_back) to make unions/cuts happier.
    It extrudes FORWARD along `direction`.
    """
    d = _v_unit(direction)
    o = _v_sub(origin, _v_mul(d, overlap_back))
    return oriented_workplane(o, d).circle(radius).extrude(length + overlap_back)


# =============================================================================
# CADQUERY HELPERS
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

    wall_thickness = float(cfg["wall_thickness"])
    add_adapter = cfg.get("add_adapter", True)
    add_secondary_branches = cfg["add_secondary_branches"]
    overlap = float(cfg.get("junction_overlap", 0.3))

    external_intersection_rounding = cfg["rounding"]["external_intersection_rounding"]
    external_micro_rounding = cfg["rounding"]["external_micro_rounding"]
    internal_intersection_rounding = cfg["rounding"]["internal_intersection_rounding"]
    internal_micro_rounding = cfg["rounding"]["internal_micro_rounding"]

    output_folder = cfg["output"]["folder"]
    output_file = os.path.join(output_folder, cfg["output"]["filename"])

    print(f"Using config: {CONFIG_PATH}")
    print(f"Output file: {output_file}")
    print(f"add_adapter={add_adapter}, add_secondary_branches={add_secondary_branches}")
    print(f"junction_overlap={overlap:.3f} mm")

    # -------------------------------------------------------------------------
    # Coordinate convention:
    # - Main trunk is along +Z
    # - Main trunk base is at z=0, top at z=main_length
    # - Radial angles rotate around +Z
    # -------------------------------------------------------------------------

    # Main outer solid
    print("Generating the main branch...")
    main_outer_r = main_branch_params["diameter"] / 2 + wall_thickness
    main_len = main_branch_params["length"]

    main_branch = cq.Workplane("XY").circle(main_outer_r).extrude(main_len)
    main_branch = safe_clean(main_branch, "main branch")

    holes = []

    # Main lumen
    print("Generating main lumen...")
    main_inner_r = main_branch_params["diameter"] / 2
    main_lumen = cq.Workplane("XY").circle(main_inner_r).extrude(main_len)
    holes.append(main_lumen)

    # Optional adapter geometry (extends toward -Z)
    if add_adapter:
        print("Generating the adapter cap...")
        cap = (
            cq.Workplane("XY")
            .workplane(offset=-wall_thickness)
            .circle(main_outer_r)
            .extrude(wall_thickness, clean=True)
        )
        main_branch = main_branch.union(cap, clean=True)

        print("Generating the adapter tube...")
        adapter_outer_diam = adapter_params["external_diameter"]
        adapter_len = adapter_params["length"]
        adapter_tube = (
            cq.Workplane("XY")
            .workplane(offset=-(adapter_len + wall_thickness))
            .circle(adapter_outer_diam / 2)
            .extrude(adapter_len, clean=True)
        )
        main_branch = main_branch.union(adapter_tube, clean=True)

        print("Generating adapter lumen...")
        adapter_hole = (
            cq.Workplane("XY")
            .workplane(offset=-(adapter_len + wall_thickness))
            .circle(adapter_params["internal_diameter"] / 2)
            .extrude(adapter_len + wall_thickness)
        )
        holes.append(adapter_hole)
    else:
        print("Adapter disabled (add_adapter=false) -> skipping cap/tube/lumen.")

    # Primary + optional secondary branches
    secondary_index = 0
    n_primary = len(primary_branch_params["angles"])

    for i in range(n_primary):
        defl = float(primary_branch_params["angles"][i])
        radial = float(primary_branch_params["radial_angles"][i])
        branch_position_z = float(primary_branch_params["positions"][i])
        branch_diameter = float(primary_branch_params["diameters"][i])
        branch_len = float(primary_branch_params["length"])

        # Attachment point on main trunk (x=0,y=0,z=position)
        P = (0.0, 0.0, branch_position_z)

        # 3D direction with radial “twist” around trunk
        d_primary = direction_from_signed_deflection_and_radial(defl, radial)

        print(f"Adding primary branch {i + 1}/{n_primary} (angle={defl}°, radial={radial}°)...")

        # Outer branch solid
        primary_outer = make_cylinder(
            origin=P,
            direction=d_primary,
            radius=branch_diameter / 2 + wall_thickness,
            length=branch_len,
            overlap_back=overlap,
        )
        main_branch = main_branch.union(primary_outer, clean=True)

        # Primary lumen
        primary_hole = make_cylinder(
            origin=P,
            direction=d_primary,
            radius=branch_diameter / 2,
            length=branch_len,
            overlap_back=overlap,
        )
        holes.append(primary_hole)

        # Secondary branches
        if add_secondary_branches:
            for _ in range(2):
                sec_angle_rel = float(secondary_branch_params["angles"][secondary_index])
                sec_defl = defl - sec_angle_rel  # preserve your original semantics
                sec_diam = float(secondary_branch_params["diameters"][secondary_index])
                sec_len = float(secondary_branch_params["length"])
                sec_rel = float(secondary_branch_params["relative_positions"][secondary_index])

                # Secondary radial is relative “twist” added to the parent’s radial
                sec_radial_rel = float(secondary_branch_params["radial_angles"][secondary_index])
                sec_radial = radial + sec_radial_rel

                # Attach along the primary branch direction
                offset_distance = sec_rel * branch_len
                Psec = _v_add(P, _v_mul(d_primary, offset_distance))

                d_secondary = direction_from_signed_deflection_and_radial(sec_defl, sec_radial)

                print(
                    f"  Adding secondary (idx {secondary_index}) "
                    f"(rel_angle={sec_angle_rel}°, abs_angle={sec_defl}°, radial={sec_radial}°)..."
                )

                sec_outer = make_cylinder(
                    origin=Psec,
                    direction=d_secondary,
                    radius=sec_diam / 2 + wall_thickness,
                    length=sec_len,
                    overlap_back=overlap,
                )
                main_branch = main_branch.union(sec_outer, clean=True)

                sec_hole = make_cylinder(
                    origin=Psec,
                    direction=d_secondary,
                    radius=sec_diam / 2,
                    length=sec_len,
                    overlap_back=overlap,
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