import cadquery as cq
import math

# Parameters
main_branch_diameter = 20  # mm
main_branch_length = 210  # mm (20 cm long)
branch_diameter_range = (10, 15)  # mm
branch_length = 50  # mm (5 cm long)

branch_angles = [120, -140, 80, -70, 30, -40]  
branch_positions = [40, 70, 90, 120, 140, 170]
branch_diameters = [10, 12, 13, 11, 15, 11]

num_branches = len(branch_angles)

# Create the main branch
main_branch = cq.Workplane("XZ").circle(main_branch_diameter / 2).extrude(main_branch_length)

# Add branches
branches = []
for i, branch_angle in enumerate(branch_angles):
    branch_position = branch_positions[i]
    branch_diameter = branch_diameters[i]
    
    # Convert angle to radians
    branch_angle_rad = math.radians(branch_angle)
    
    # Create the branch
    branch = (
        cq.Workplane("XZ")
        .workplane(offset=branch_position)
        .transformed(rotate=(0, branch_angle, 0))
        .circle(branch_diameter / 2)
        .extrude(branch_length)
    )
    
    # Combine with the main branch
    main_branch = main_branch.union(branch)
    branches.append(branch)

# Export as an STL file
cq.exporters.export(main_branch, "vascular_tree.stl")
