#!/usr/bin/env python3
"""Initialize the project's data space.

Iterates over all defined state points and initializes
the associated job workspace directories."""
import logging
import pathlib
import math
import numpy as np

import unyt as u
import signac

# The number of output hdf5 files, such that Nz * Nr * NUMBER_OF_H5 * size(float64)
# easily fits in RAM
NUMBER_OF_H5 = 200


def main():
    """Main function, for defining the parameter(s) to be varied in the simulations."""
    project = signac.init_project(
        "fbpic-project",
        workspace="/scratch/berceanu/runs/signac-driven-fbpic/workspace/",
    )
    # TODO compare with betatron input
    for _ in range(1):
        sp = dict(
            # The simulation box
            Nz=2425,  # Number of gridpoints along z
            zmin=-100.0e-6,  # Left end of the simulation box (meters)
            zmax=0.0e-6,  # Right end of the simulation box (meters)
            Nr=420,  # Number of gridpoints along r
            rmax=150.0e-6,  # Length of the box along r (meters)
            Nm=2,  # Number of modes used
            # The particles
            # Position of the beginning of the plasma (meters)
            p_zmin=0.0e-6,
            # Maximal radial position of the plasma (meters)
            p_rmax=100.0e-6,
            n_e=5.307e18 * 1.0e6,  # Density (electrons.meters^-3)
            p_nz=2,  # Number of particles per cell along z
            p_nr=2,  # Number of particles per cell along r
            p_nt=6,  # Number of particles per cell along theta
            # The laser
            a0=2.4,         # Laser amplitude
            w0=18.7e-6,     # Laser waist
            ctau=7.495e-6,  # Laser duration
            z0=-10.e-6,     # Laser centroid
            zfoc=0.e-6,     # Focal position
            lambda0=0.8e-6, # Laser wavelength
            # The density profile
            flat_top_dist=1000.0e-6,  # plasma flat top distance
            sigma_right=500.0e-6,
            center_left=1000.0e-6,
            sigma_left=500.0e-6,
            power=4.0,
            # do not change below this line ##############
            center_right=None,
            p_zmax=None,  # Position of the end of the plasma (meters)
            L_interact=None,
            # Period in number of timesteps
            diag_period=None,
            # Timestep (seconds)
            dt=None,
            # Interaction time (seconds) (to calculate number of PIC iterations)
            # (i.e. the time it takes for the moving window to slide across the plasma)
            T_interact=None,
            # Number of iterations to perform
            N_step=None,
        )

        sp["center_right"] = sp["center_left"] + sp["flat_top_dist"]
        sp["p_zmax"] = sp["center_right"] + 2 * sp["sigma_right"]
        sp["L_interact"] = sp["p_zmax"] - sp["p_zmin"]
        sp["dt"] = (sp["zmax"] - sp["zmin"]) / sp["Nz"] / u.clight.to_value("m/s")
        sp["T_interact"] = (
            sp["L_interact"] + (sp["zmax"] - sp["zmin"])
        ) / u.clight.to_value("m/s")
        sp["N_step"] = int(sp["T_interact"] / sp["dt"])
        sp["diag_period"] = math.ceil(sp["N_step"] / NUMBER_OF_H5)

        project.open_job(sp).init()

    project.write_statepoints()

    for job in project:
        p = pathlib.Path(job.ws)
        pathlib.Path(p / "rhos").mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
