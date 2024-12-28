import cadquery as cq
import math

# Parameters
main_branch_diameter = 20  # mm
main_branch_length = 210  # mm (20 cm long)
#branch_diameter_range = (10, 15)  # mm
branch_length = 80  # mm (5 cm long)

branch_angles = [120, -140, 80, -70, 30, -40] 
relative_branch_positions = [0.25, 0.35, 0.45, 0.55, 0.65, 0.75] 
branch_positions = [i * main_branch_length for i in relative_branch_positions]
branch_diameters = [10, 12, 13, 11, 15, 11] # 10-15 mm

secondary_branch_positions = [
    0.4,0.8,
    0.8,0.4,
    0.8,0.4,
    0.8,0.4,
    0.8,0.4,
    0.4,0.8,
]  # in % branch length
secondary_branch_angles = [
    30, -30,
    30, -30,
    30, -30,
    30, -30,
    30, -30,
    30, -30,    
] # Range 30 - 70 degreess
secondary_branch_diameters = [8, 7, 7, 8, 10, 9, 7, 9, 8, 9, 10, 7] # 5 - 10 mm
secondary_branch_length = 50

def create_branch(position, angle, diameter, length):
    """Create a single branch."""
    return (
        cq.Workplane("XZ")
        .workplane(offset=position)
        .transformed(rotate=(0, angle, 0))
        .circle(diameter / 2)
        .extrude(length)
    )

def create_secondary_branch(parent_position, parent_angle, offset_percent, angle, diameter, length):
    """Create a secondary branch off a main or primary branch."""
    offset_distance = offset_percent * branch_length
    angle_rad = math.radians(parent_angle)

    return (
        cq.Workplane("XZ")
        .workplane(offset=parent_position)
        .transformed(
            rotate=(0, angle, 0),
            offset=(
                offset_distance * math.sin(angle_rad),
                0,
                offset_distance * math.cos(angle_rad)
            )
        )
        .circle(diameter / 2)
        .extrude(length)
    )

# Create the main branch
main_branch = cq.Workplane("XZ").circle(main_branch_diameter / 2).extrude(main_branch_length)

# Add primary and secondary branches
j = 0
for i, branch_angle in enumerate(branch_angles):
    branch_position = branch_positions[i]
    branch_diameter = branch_diameters[i]

    # Create primary branch
    branch = create_branch(branch_position, branch_angle, branch_diameter, branch_length)
    main_branch = main_branch.union(branch)

    # Create secondary branches
    for _ in range(2):  # Each primary branch has two secondary branches
        secondary_branch_angle = branch_angle - secondary_branch_angles[j]
        secondary_branch_diameter = secondary_branch_diameters[j]
        secondary_branch_position = secondary_branch_positions[j]

        secondary_branch = create_secondary_branch(
            branch_position, branch_angle, 
            secondary_branch_position, secondary_branch_angle, 
            secondary_branch_diameter, secondary_branch_length
        )
        main_branch = main_branch.union(secondary_branch)
        j += 1

# Export as an STL file
cq.exporters.export(main_branch, "vascular_tree.stl")
