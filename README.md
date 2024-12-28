
# Vascular Tree Model Generator

This repository contains a Python script that generates a 3D model of a vascular tree structure using CadQuery. The model consists of a main branch, primary branches, and secondary branches, with configurable parameters for dimensions, angles, and positions.

![Example Vascular Tree Model](data/vessel_example.png)

## Features

- Create a main cylindrical branch as the base structure.
- Add primary and secondary branches with custom angles, diameters, and relative positions.
- Automatically subtract holes to ensure realistic connections between branches.
- Export the final model as an STL file.

## Requirements

- Python 3.7 or higher
- [CadQuery](https://cadquery.readthedocs.io/en/latest/) library

## Installation

1. Clone the repository:
   ```bash
   git clone <repository_url>
   cd <repository_name>
   ```
2. Install the required Python libraries:
   ```bash
   pip install cadquery
   ```

## Usage

1. Configure the parameters for the main, primary, and secondary branches in the script:
   - `main_branch_params`: Dimensions of the main branch.
   - `primary_branch_params`: Angles, positions, diameters, and lengths for primary branches.
   - `secondary_branch_params`: Angles, positions, diameters, and lengths for secondary branches.
   - `wall_thickness`: Thickness of the vascular walls.

2. Run the script:
   ```bash
   python generate_vascular_tree.py
   ```

3. The generated STL file will be saved in the `output` folder as `vascular_tree.stl`.

## Output

The script generates:
- A 3D STL model of the vascular tree with realistic connections and branching structure.

## Example Parameters

The default configuration creates:
- A main branch with a diameter of 20 mm and a length of 200 mm.
- Six primary branches with varying angles, positions, and diameters.
- Secondary branches connected to each primary branch, with alternating angles and positions.

## Customization

Modify the branch parameters in the script to customize:
- Branch dimensions (diameter and length).
- Angles for branch rotation.
- Positions along the parent branch.
- Wall thickness of the vascular structure.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Acknowledgments

- Built using [CadQuery](https://cadquery.readthedocs.io/en/latest/), a Python-based parametric CAD library.
