import cadquery as cq
import math
import os

# Parameters
adapter_params = {
    "internal_diameter": 5,  # mm
    "extermal_diameter": 17, # mm
    "length": 50,  # mm
}

main_branch_params = {
    "diameter": 20,  # mm
    "length": 180,  # mm
}

primary_branch_params = {
    "angles": [120, -140, 80, -70, 30, -40],
    "relative_positions": [0.25, 0.35, 0.45, 0.55, 0.65, 0.75],
    "diameters": [10, 12, 13, 11, 15, 11],  # mm
    "length": 80,  # mm
}

secondary_branch_params = {
    "angles": [40, -40] * 6,  # degrees
    "relative_positions": [0.4, 0.7, 0.7, 0.4, 0.7, 0.4, 0.7, 0.4, 0.7, 0.4, 0.4, 0.7],  # in % branch length
    "diameters": [8, 7, 7, 8, 10, 9, 7, 9, 8, 9, 10, 7],  # mm
    "length": 40,  # mm
}

wall_thickness = 4
add_secondary_branches = False

# Define the output folder and file path
output_folder = "output"
output_file = os.path.join(output_folder, "vascular_tree.stl")

# Precompute absolute positions of primary branches
primary_branch_params["positions"] = [
    pos * main_branch_params["length"] for pos in primary_branch_params["relative_positions"]
]

# Define main and branch creation functions
def create_branch(position, angle, diameter, length):
    """Create a single branch (solid only)."""
    outer_circle = cq.Sketch().circle(diameter / 2 + wall_thickness)
    branch_sketch = outer_circle
    branch = (
        cq.Workplane("XZ")
        .workplane(offset=position)
        .transformed(rotate=(0, angle, 0))
        .placeSketch(branch_sketch)
        .extrude(length)
    )
    return branch

def create_secondary_branch(parent_position, parent_angle, offset_percent, angle, diameter, length):
    """Create a secondary branch (solid only)."""
    offset_distance = offset_percent * primary_branch_params["length"]
    angle_rad = math.radians(parent_angle)
    outer_circle = cq.Sketch().circle(diameter / 2 + wall_thickness)
    branch_sketch = outer_circle
    secondary_branch = (
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
        .placeSketch(branch_sketch)
        .extrude(length)
    )
    return secondary_branch

# Define the main branch
print("Generating the main branch...")
outer_circle = cq.Sketch().circle(main_branch_params["diameter"] / 2 + wall_thickness)
main_branch = (
    cq.Workplane("XZ")
    .placeSketch(outer_circle)
    .extrude(main_branch_params["length"])
)

# Add primary and secondary branches
holes = []

# Add the main branch hole
main_branch_hole = (
    cq.Workplane("XZ")
    .circle(main_branch_params["diameter"] / 2)
    .extrude(main_branch_params["length"])
)
holes.append(main_branch_hole)

# Create the adapter tube (extruding in the opposite direction)
print("Generating the adapter tube...")

# Create the outer and inner circles for the tube
outer_circle = cq.Sketch().circle(main_branch_params["diameter"] / 2 + wall_thickness)
# Create the tube by subtracting the inner circle from the outer circle
cap = (
    cq.Workplane("XZ")
    .workplane(offset=-wall_thickness)  # Offset in the opposite direction of the main branch
    .placeSketch(outer_circle)
    .extrude(wall_thickness, clean=True)  # Extrude the tube
)

# Union the adapter tube with the main branch
main_branch = main_branch.union(cap)

# Create the outer and inner circles for the tube
outer_circle = cq.Sketch().circle(adapter_params["extermal_diameter"] / 2)
# Create the tube by subtracting the inner circle from the outer circle
adapter_tube = (
    cq.Workplane("XZ")
    .workplane(offset=-adapter_params["length"]-wall_thickness)  # Offset in the opposite direction of the main branch
    .placeSketch(outer_circle)
    .extrude(adapter_params["length"], clean=True)  # Extrude the tube
)

# Union the adapter tube with the main branch
main_branch = main_branch.union(adapter_tube)

# Add the main branch hole
adapter_hole = (
    cq.Workplane("XZ")
    .workplane(offset=-adapter_params["length"]-wall_thickness)  # Offset in the opposite direction of the main branch
    .circle(adapter_params["internal_diameter"]/2)
    .extrude(adapter_params["length"]+wall_thickness)
)
holes.append(adapter_hole)

secondary_index = 0
for i, branch_angle in enumerate(primary_branch_params["angles"]):
    branch_position = primary_branch_params["positions"][i]
    branch_diameter = primary_branch_params["diameters"][i]

    # Create primary branch
    print(f"Adding primary branch {i + 1}/{len(primary_branch_params['angles'])}...")
    branch = create_branch(branch_position, branch_angle, branch_diameter, primary_branch_params["length"])
    main_branch = main_branch.union(branch)

    # Add hole for the primary branch
    hole = (
        cq.Workplane("XZ")
        .workplane(offset=branch_position)
        .transformed(rotate=(0, branch_angle, 0))
        .circle(branch_diameter / 2)
        .extrude(primary_branch_params["length"])
    )
    holes.append(hole)

    # Create secondary branches
    if add_secondary_branches:
        for _ in range(2):
            print(f"    Adding secondary branch connected to primary branch {i + 1}...")
            secondary_branch = create_secondary_branch(
                branch_position,
                branch_angle,
                secondary_branch_params["relative_positions"][secondary_index],
                branch_angle - secondary_branch_params["angles"][secondary_index],
                secondary_branch_params["diameters"][secondary_index],
                secondary_branch_params["length"],
            )
            main_branch = main_branch.union(secondary_branch)

            # Add hole for the secondary branch
            offset_distance = secondary_branch_params["relative_positions"][secondary_index] * primary_branch_params["length"]
            hole = (
                cq.Workplane("XZ")
                .workplane(offset=branch_position)
                .transformed(
                    rotate=(0, branch_angle - secondary_branch_params["angles"][secondary_index], 0),
                    offset=(
                        offset_distance * math.sin(math.radians(branch_angle)),
                        0,
                        offset_distance * math.cos(math.radians(branch_angle)),
                    ),
                )
                .circle(secondary_branch_params["diameters"][secondary_index] / 2)
                .extrude(secondary_branch_params["length"])
            )
            holes.append(hole)

            secondary_index += 1

# Subtract holes from the main structure
print("Subtracting holes from the structure...")
for hole in holes:
    main_branch = main_branch.cut(hole)

# Create the folder if it doesn't exist
print("Finalizing and exporting the model...")
os.makedirs(output_folder, exist_ok=True)

# Export the file
cq.exporters.export(main_branch, output_file)
print(f"File successfully exported to {output_file}")
