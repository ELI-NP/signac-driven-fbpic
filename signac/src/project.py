##!/usr/bin/env python3
"""This module contains the operation functions for this project.

The workflow defined in this file can be executed from the command
line with

    $ python src/project.py run [job_id [job_id ...]]

See also: $ python src/project.py --help

Note: All the lines marked with the CHANGEME comment contain customizable parameters.
"""
import logging
import math
import sys
from typing import Union
import pathlib
from multiprocessing import Pool
from functools import partial

import numpy as np
import sliceplots
from flow import FlowProject, directives
from flow.environment import DefaultSlurmEnvironment
from matplotlib import pyplot
from openpmd_viewer import addons
import unyt as u
from peak_detection import plot_electron_energy_spectrum
from util import ffmpeg_command, shell_run
from sim_diags import particle_energy_histogram, laser_density_plot
from signac.contrib.job import Job

logger = logging.getLogger(__name__)
log_file_name = "fbpic-project.log"

# strip units
c_light = u.clight.to_value("m/s")
m_e = u.electron_mass.to_value("kg")
m_p = u.proton_mass.to_value("kg")
q_e = u.electron_charge.to_value("C")  # negative sign
q_p = u.proton_charge.to_value("C")  # positive sign


class OdinEnvironment(DefaultSlurmEnvironment):
    """Environment profile for the LGED cluster.
    https://docs.signac.io/projects/flow/en/latest/supported_environments/comet.html#flow.environments.xsede.CometEnvironment
    """

    hostname_pattern = r".*\.ra5\.eli-np\.ro$"
    template = "odin.sh"
    cores_per_node = 16
    mpi_cmd = "mpiexec"

    @classmethod
    def add_args(cls, parser):
        super(OdinEnvironment, cls).add_args(parser)
        parser.add_argument(
            "--partition",
            choices=["cpu", "gpu"],
            default="gpu",
            help="Specify the partition to submit to.",
        )
        parser.add_argument(
            "-w",
            "--walltime",
            type=float,
            default=36,
            help="The wallclock time in hours.",
        )
        parser.add_argument(
            "--job-output",
            help=(
                "What to name the job output file. "
                "If omitted, uses the system default "
                '(slurm default is "slurm-%%j.out").'
            ),
        )


class Project(FlowProject):
    """
    Placeholder for ``FlowProject`` class.
    """

    pass


ex = Project.make_group(name="ex")


@Project.label
def progress(job) -> str:
    # get last iteration based on input parameters
    number_of_iterations = math.ceil((job.sp.N_step - 0) / job.sp.diag_period)

    h5_path = pathlib.Path(job.ws) / "diags" / "hdf5"
    if not h5_path.is_dir():
        # {job_dir}/diags/hdf5 not present, ``fbpic`` didn't run
        return "0/%s" % number_of_iterations

    h5_files = list(h5_path.glob("*.h5"))

    return f"{len(h5_files)}/{number_of_iterations}"


def fbpic_ran(job: Job) -> bool:
    """
    Check if ``fbpic`` produced all the output .h5 files.

    :param job: the job instance is a handle to the data of a unique statepoint
    :return: True if all output files are in {job_dir}/diags/hdf5, False otherwise
    """
    h5_path: Union[bytes, str] = pathlib.Path(job.ws) / "diags" / "hdf5"
    if not h5_path.is_dir():
        # {job_dir}/diags/hdf5 not present, ``fbpic`` didn't run
        did_it_run = False
        return did_it_run

    time_series = addons.LpaDiagnostics(h5_path, check_all_files=True)
    iterations: np.ndarray = time_series.iterations

    # estimate iteration array based on input parameters
    estimated_iterations = np.arange(0, job.sp.N_step, job.sp.diag_period, dtype=np.int)

    # check if iterations array corresponds to input params
    did_it_run = np.array_equal(estimated_iterations, iterations)

    return did_it_run


def are_rho_pngs(job: Job) -> bool:
    """
    Check if all the {job_dir}/rhos/rho{it:06d}.png files are present.

    :param job: the job instance is a handle to the data of a unique statepoint
    :return: True if .png files are there, False otherwise
    """
    p = pathlib.Path(job.ws) / "rhos"
    files = p.iterdir()

    # estimate iteration array based on input parameters
    iterations = np.arange(0, job.sp.N_step, job.sp.diag_period, dtype=np.int)

    pngs = (f"rho{it:06d}.png" for it in iterations)

    return set(files) == set(pngs)


@ex.with_directives(directives=dict(ngpu=1))
@directives(ngpu=1)
@Project.operation
@Project.post(fbpic_ran)
@Project.post.isfile("initial_density_profile.npz")
def run_fbpic(job: Job) -> None:
    """
    This ``signac-flow`` operation runs a ``fbpic`` simulation.

    :param job: the job instance is a handle to the data of a unique statepoint
    """
    from fbpic.main import Simulation
    from fbpic.lpa_utils.laser import add_laser_pulse, FlattenedGaussianLaser
    from fbpic.openpmd_diag import (
        FieldDiagnostic,
        ParticleDiagnostic,
        ParticleChargeDensityDiagnostic,
    )

    def ramp(z, *, center, sigma, p):
        """Gaussian-like function."""
        return np.exp(-(((z - center) / sigma) ** p))

    # The density profile
    def dens_func(z, r):
        """
        User-defined function: density profile of the plasma

        It should return the relative density with respect to n_plasma,
        at the position x, y, z (i.e. return a number between 0 and 1)

        Parameters
        ----------
        z, r: 1darrays of floats
            Arrays with one element per macroparticle
        Returns
        -------
        n : 1d array of floats
            Array of relative density, with one element per macroparticles
        """

        # Allocate relative density
        n = np.ones_like(z)

        # before up-ramp
        n = np.where(z < 0.0, 0.0, n)

        # Make up-ramp
        n = np.where(
            z < job.sp.center_left,
            ramp(z, center=job.sp.center_left, sigma=job.sp.sigma_left, p=job.sp.power),
            n,
        )

        # Make down-ramp
        n = np.where(
            (z >= job.sp.center_right)
            & (z < job.sp.center_right + 2 * job.sp.sigma_right),
            ramp(
                z, center=job.sp.center_right, sigma=job.sp.sigma_right, p=job.sp.power
            ),
            n,
        )

        # after down-ramp
        n = np.where(z >= job.sp.center_right + 2 * job.sp.sigma_right, 0, n)

        return n

    # save density profile for subsequent plotting
    all_z = np.linspace(job.sp.zmin, job.sp.L_interact, 1000)
    dens = dens_func(all_z, 0.0)
    np.savez(job.fn("initial_density_profile.npz"), density=dens, z_meters=all_z)

    # redirect stdout to "stdout.txt"
    orig_stdout = sys.stdout
    f = open(job.fn("stdout.txt"), "w")
    sys.stdout = f

    # Initialize the simulation object
    sim = Simulation(
        Nz=job.sp.Nz,
        zmax=job.sp.zmax,
        Nr=job.sp.Nr,
        rmax=job.sp.rmax,
        Nm=job.sp.Nm,
        dt=job.sp.dt,
        zmin=job.sp.zmin,
        boundaries={"z": "open", "r": "open"},
        n_order=-1,
        use_cuda=True,
        verbose_level=2,
    )
    # 'r': 'open' can also be used, but is more computationally expensive

    # Add the plasma electrons
    plasma_elec = sim.add_new_species(
        q=q_e,
        m=m_e,
        n=job.sp.n_e,
        dens_func=dens_func,
        p_zmin=job.sp.p_zmin,
        p_zmax=job.sp.p_zmax,
        p_rmax=job.sp.p_rmax,
        p_nz=job.sp.p_nz,
        p_nr=job.sp.p_nr,
        p_nt=job.sp.p_nt,
    )

    # Create a Gaussian laser profile
    laser_profile = FlattenedGaussianLaser(
        a0=job.sp.a0,
        w0=job.sp.w0,
        tau=job.sp.tau,
        z0=job.sp.z0,
        N=6,
        zf=job.sp.zfoc,
        lambda0=job.sp.lambda0,
    )
    # Add it to the simulation
    add_laser_pulse(
        sim=sim,
        laser_profile=laser_profile,
    )

    # Configure the moving window
    sim.set_moving_window(v=c_light)

    # Add diagnostics
    write_dir = pathlib.Path(job.ws) / "diags"
    sim.diags = [
        FieldDiagnostic(
            period=job.sp.diag_period,
            fldobject=sim.fld,
            comm=sim.comm,
            write_dir=write_dir,
            fieldtypes=["rho", "E"],
        ),
        ParticleDiagnostic(
            period=job.sp.diag_period,
            species={"electrons": plasma_elec},
            # select={"uz": [40.0, None]},
            comm=sim.comm,
            write_dir=write_dir,
        ),
        # Since rho from `FieldDiagnostic` is 0 almost everywhere
        # (neutral plasma), it is useful to see the charge density
        # of individual particles
        ParticleChargeDensityDiagnostic(
            period=job.sp.diag_period,
            sim=sim,
            species={"electrons": plasma_elec},
            write_dir=write_dir,
        ),
    ]
    # TODO add electron tracking

    # set deterministic random seed
    np.random.seed(0)

    # Run the simulation
    sim.step(job.sp.N_step, show_progress=False)

    # redirect stdout back and close "stdout.txt"
    sys.stdout = orig_stdout
    f.close()


@ex
@Project.operation
@Project.pre.isfile("initial_density_profile.npz")
@Project.post.isfile("initial_density_profile.png")
def plot_initial_density_profile(job: Job) -> None:
    """Plot the initial plasma density profile."""

    def mark_on_plot(*, ax, parameter: str, y=1.1):
        ax.annotate(text=parameter, xy=(job.sp[parameter] * 1e6, y), xycoords="data")
        ax.axvline(x=job.sp[parameter] * 1e6, linestyle="--", color="red")
        return ax

    fig, ax = pyplot.subplots(figsize=(30, 4.8))

    npzfile = np.load(job.fn("initial_density_profile.npz"))
    dens = npzfile["density"]
    all_z = npzfile["z_meters"]

    ax.plot(all_z * 1e6, dens)
    ax.set_xlabel(r"$%s \;(\mu m)$" % "z")
    ax.set_ylim(0.0, 1.2)
    ax.set_xlim(job.sp.zmin * 1e6 - 20, job.sp.L_interact * 1e6 + 20)
    ax.set_ylabel("Density profile $n$")

    mark_on_plot(ax=ax, parameter="zmin")
    mark_on_plot(ax=ax, parameter="zmax")
    mark_on_plot(ax=ax, parameter="p_zmin", y=0.9)
    mark_on_plot(ax=ax, parameter="zfoc", y=0.5)
    mark_on_plot(ax=ax, parameter="z0", y=0.5)
    mark_on_plot(ax=ax, parameter="center_left", y=0.7)
    mark_on_plot(ax=ax, parameter="center_right", y=0.7)
    mark_on_plot(ax=ax, parameter="L_interact", y=0.7)
    mark_on_plot(ax=ax, parameter="p_zmax")

    ax.fill_between(all_z * 1e6, dens, alpha=0.5)

    fig.savefig(job.fn("initial_density_profile.png"))
    pyplot.close(fig)


@ex.with_directives(directives=dict(np=3))
@directives(np=3)
@Project.operation
@Project.pre.after(run_fbpic)
@Project.post(are_rho_pngs)
def save_rho_pngs(job: Job) -> None:
    """
    Loop through a whole simulation and, for *each ``fbpic`` iteration*:
    * save a snapshot of the plasma density field ``rho`` to {job_dir}/rhos/rho{it:06d}.png

    :param job: the job instance is a handle to the data of a unique statepoint
    """
    h5_path = pathlib.Path(job.ws) / "diags" / "hdf5"
    rho_path = pathlib.Path(job.ws) / "rhos"
    time_series = addons.LpaDiagnostics(h5_path, check_all_files=False)

    it_laser_density_plot = partial(
        laser_density_plot,
        tseries=time_series,
        rho_field_name="rho_electrons",
        save_path=rho_path,
        n_c=job.sp.n_c,
        E0=job.sp.E0,
    )

    with Pool(3) as pool:
        pool.map(it_laser_density_plot, time_series.iterations.tolist())


@ex
@Project.operation
@Project.pre.after(save_rho_pngs)
@Project.post.isfile("rho.mp4")
def generate_rho_movie(job: Job) -> None:
    """
    Generate a movie from all the .png files in {job_dir}/rhos/

    :param job: the job instance is a handle to the data of a unique statepoint
    """
    command = ffmpeg_command(
        input_files=pathlib.Path(job.ws) / "rhos" / "rho*.png",
        output_file=job.fn("rho.mp4"),
    )
    shell_run(command, shell=True)


@ex
@Project.operation
@Project.pre.after(run_fbpic)
@Project.post.isfile("final_histogram.npz")
def save_final_histogram(job: Job) -> None:
    """Save the histogram corresponding to the last iteration."""

    h5_path = pathlib.Path(job.ws) / "diags" / "hdf5"
    time_series = addons.LpaDiagnostics(h5_path, check_all_files=True)
    last_iteration = time_series.iterations[-1]

    # compute 1D histogram
    energy_hist, bin_edges, _ = particle_energy_histogram(
        tseries=time_series,
        it=last_iteration,
        cutoff=np.inf,  # no cutoff
    )
    np.savez(job.fn("final_histogram.npz"), edges=bin_edges, counts=energy_hist)


@ex
@Project.operation
@Project.pre.after(save_final_histogram)
@Project.post.isfile("final_histogram.png")
def plot_final_histogram(job: Job) -> None:
    """Plot the electron spectrum corresponding to the last iteration."""

    peak_position, peak_charge = plot_electron_energy_spectrum(
        job.fn("final_histogram.npz"), job.fn("final_histogram.png")
    )

    job.doc["peak_position"] = float("{:.1f}".format(peak_position))  # MeV
    job.doc["peak_charge"] = float("{:.1f}".format(peak_charge))  # pC


@ex
@Project.operation
@Project.pre.after(run_fbpic)
@Project.post.isfile("all_hist.txt")
@Project.post.isfile("hist_edges.txt")
def save_histograms(job: Job) -> None:
    """
    Loop through a whole simulation and, for *each ``fbpic`` iteration*:

    compute the weighted particle energy histogram and save it to "all_hist.txt",
    and the histogram bins to "hist_edges.txt"

    :param job: the job instance is a handle to the data of a unique statepoint
    """
    h5_path = pathlib.Path(job.ws) / "diags" / "hdf5"
    time_series = addons.LpaDiagnostics(h5_path, check_all_files=False)
    number_of_iterations: int = time_series.iterations.size

    # Do a mock histogram in order to get the number of bins
    _, _, nrbins = particle_energy_histogram(
        tseries=time_series,
        it=0,
    )
    all_hist = np.empty(shape=(number_of_iterations, nrbins), dtype=np.float64)
    hist_edges = np.empty(shape=(nrbins + 1,), dtype=np.float64)

    # loop through all the iterations in the job's time series
    for idx, it in enumerate(time_series.iterations):
        # generate 1D energy histogram
        energy_hist, bin_edges, _ = particle_energy_histogram(
            tseries=time_series,
            it=it,
        )
        # build up arrays for 2D energy histogram
        all_hist[idx, :] = energy_hist
        if idx == 0:  # only save the first one
            hist_edges[:] = bin_edges

    np.savetxt(
        job.fn("all_hist.txt"),
        all_hist,
        header="One iteration per row, containing the energy histogram.",
    )
    np.savetxt(job.fn("hist_edges.txt"), hist_edges, header="Energy histogram bins.")


@ex
@Project.operation
@Project.pre.after(save_histograms)
@Project.pre.isfile("initial_density_profile.npz")
@Project.post.isfile("hist2d.png")
def plot_2d_hist(job: Job) -> None:
    """
    Plot the 2D histogram, composed of the 1D slices for each iteration.

    :param job: the job instance is a handle to the data of a unique statepoint
    """
    all_hist = np.loadtxt(
        job.fn("all_hist.txt"), dtype=np.float64, comments="#", ndmin=2
    )
    hist_edges = np.loadtxt(
        job.fn("hist_edges.txt"), dtype=np.float64, comments="#", ndmin=1
    )
    npzfile = np.load(job.fn("initial_density_profile.npz"))
    dens = npzfile["density"]
    all_z = npzfile["z_meters"]

    # compute moving window position for each iteration
    iterations = np.arange(0, job.sp.N_step, job.sp.diag_period, dtype=np.int)
    times = iterations * job.sp.dt * u.second
    positions = times * u.clight
    z_0 = positions.to_value("micrometer")

    # use same z range as the histogram
    mask = (all_z >= z_0[0]) & (all_z <= z_0[-1])
    all_z = all_z[mask] * 1e6  # micrometers
    # rescale for visibility, 1/5th of the histogram y axis
    v_axis_size = hist_edges[-1] - hist_edges[1]
    dens = dens[mask] * v_axis_size / 5
    # upshift density to start from lower limit of histogram y axis
    dens += hist_edges[1] - dens.min()

    fig = pyplot.figure(figsize=(2 * 8, 8))

    # plot 2D energy-charge histogram
    hist2d = sliceplots.Plot2D(
        fig=fig,
        arr2d=all_hist.T,  # 2D data
        h_axis=z_0,  # x-axis
        v_axis=hist_edges[1:],  # y-axis
        xlabel=r"$%s \;(\mu m)$" % "z",
        ylabel=r"E (MeV)",
        zlabel=r"dQ/dE (pC/MeV)",
        vslice_val=z_0[-1],  # can be changed to z_0[iteration]
        extent=(z_0[0], z_0[-1], hist_edges[1], hist_edges[-1]),
    )
    hist2d.ax0.plot(all_z, dens, linewidth=2.5, linestyle="dashed", color="0.75")
    hist2d.canvas.print_figure(job.fn("hist2d.png"))


if __name__ == "__main__":
    logging.basicConfig(
        filename=log_file_name,
        format="%(asctime)s - %(name)s - %(levelname)-8s - %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("==RUN STARTED==")

    Project().main()  # run the whole signac project workflow

    logger.info("==RUN FINISHED==")
