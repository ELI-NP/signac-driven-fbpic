"""
Module for parsing data out of signac_statepoints.json files.
These files are generated via init.py by the signac project.
"""
import json
import pathlib
import unyt as u


def to_cm_minus_three(n_e):
    """Converts density from m^(-3) to cm^(-3)."""
    return (n_e / u.meter ** 3).to(1 / u.centimeter ** 3)


def main():
    """Main entry point."""
    statepoints_path = pathlib.Path.home() / "tmp" / "runs" / "signac_statepoints.json"
    statepoints = json.loads(statepoints_path.read_bytes())

    # The end-goal is to get a dictionary of the form
    # final_bunch_{job.id:.6}.txt -> density
    # str -> float

    # intermediate steps
    # 2. 8a6943 -> 4e+23
    # 3. final_bunch_8a6943.txt -> 4e+17 cm^(-3)
    # 4. final_bunch_8a6943.txt -> 4e+17 cm^(-3)

    id_to_density = {}
    for signac_job_id, job_state_point in statepoints.items():
        id_to_density[signac_job_id] = job_state_point["n_e"]

    short_id_to_density_cm3 = {
        f"{id:.6}": to_cm_minus_three(density) for id, density in id_to_density.items()
    }

    bunch_fn_to_density = {
        f"final_bunch_{id}.txt": density
        for id, density in short_id_to_density_cm3.items()
    }

    runs_dir = pathlib.Path.home() / "tmp" / "runs"
    txt_files = runs_dir.glob("final_bunch_*.txt")

    for fn in txt_files:
        print(f"{fn.name}: {bunch_fn_to_density[fn.name]:.1e}")


if __name__ == "__main__":
    main()
