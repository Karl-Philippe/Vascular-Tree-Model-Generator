import cadquery as cq
import math
import random  # Importing random module

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

# Function to add secondary branches to a given branch
def add_secondary_branches(primary_end_point, branch_angle, num_secondary_branches=3):
    secondary_branches = []
    for _ in range(num_secondary_branches):
        # Randomly determine the angle, diameter, and position of the secondary branch
        angle = random.uniform(-45, 45)  # Random angle for secondary branch
        diameter = random.randint(branch_diameter_range[0], branch_diameter_range[1])

        # Calculate position along the branch for secondary branches (relative to the primary end point)
        position = random.uniform(5, 15)  # Distance from the end of the primary branch
        
        # Create the secondary branch
        secondary_branch = (
            cq.Workplane("XZ")
            .workplane(offset=position)  # Offset the secondary branch along the length
            .transformed(rotate=(0, angle, 0))  # Apply rotation
            .circle(diameter / 2)
            .extrude(branch_length)
        )

        # Translate the branch to start from the primary branch's endpoint
        secondary_branch = secondary_branch.translate((primary_end_point[0], primary_end_point[1], primary_end_point[2]))

        secondary_branches.append(secondary_branch)
    
    return secondary_branches

# Add branches
for i, branch_angle in enumerate(branch_angles):
    branch_position = branch_positions[i]
    branch_diameter = branch_diameters[i]
    
    # Convert angle to radians
    branch_angle_rad = math.radians(branch_angle)
    
    # Create the primary branch
    branch = (
        cq.Workplane("XZ")
        .workplane(offset=branch_position)
        .transformed(rotate=(0, branch_angle, 0))
        .circle(branch_diameter / 2)
        .extrude(branch_length)
    )
    
    # Get the endpoint of the current branch (for secondary branch generation)
    branch_end_point = (0, -branch_position + branch_length, 0)
    
    # Add secondary branches at the end of the primary branch
    secondary_branches = add_secondary_branches(branch_end_point, branch_angle)
    
    # Combine the main branch with the primary and secondary branches
    main_branch = main_branch.union(branch)
    for sec_branch in secondary_branches:
        main_branch = main_branch.union(sec_branch)

# Export as an STL file
cq.exporters.export(main_branch, "vascular_tree.stl")
