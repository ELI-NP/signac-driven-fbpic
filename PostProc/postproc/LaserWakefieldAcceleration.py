"""
Code that estimates bunch properties (charge, energy, etc.), based on
Lu, W. et al., Phys. Rev. ST Accel. Beams 10 (6): 061301.
"""

# %% [markdown]
# Need to resolve the smallest length scale: 20-30 cells/wavelength.
# * plasma length scale: skin depth $c/\omega_p$
# * laser length scale: laser wavelength $\lambda_L = 0.8\, \mu$m
# %% [markdown]
# We measure charges in units of $e$, masses in units of $m_e$, lengths in
# units of $l_p = c/\omega_p$, times in units of $t_p = 1 /\omega_p$. Momenta
# will then be measured in $m_e c$, velocities in units of $c$, electric fields
# in units of $m_e c \omega_p / e$, magnetic fields in units of $m_e \omega_p /
# e$. Scalar potential $\Phi$ in units of $m_e c^2 / e$ and vector potential
# $\vec{A}$ in units of $m_e c /e$. We will use SI units throughout.

# %%
from numpy import pi as π
import numpy as np
import unyt as u


# %% [markdown]
# ## Constants

# %%
# classical electron radius
r_e = (1 / (4 * π * u.eps_0) * u.qe**2 / (u.me * u.clight**2)).to('micrometer')

# %% [markdown]
# ## Utility functions

# %%


def w0_to_FWHM(w0):
    """Computes Gaussian laser FWHM from its beam waist.

    Args:
        w0 (float, length): beam waist @ 1/e^2 intensity

    Returns:
        fwhm (float, length): beam FWHM @ 1/2 intensity
    """
    return 2 * w0 / np.sqrt(2 / np.log(2))


# %%
def FWHM_to_w0(FWHM):
    """Computes Gaussian laser beam waist from its FWHM.

    Args:
        fwhm (float, length): beam FWHM @ 1/2 intensity

    Returns:
        w0 (float, length): beam waist @ 1/e^2 intensity
    """
    return 1 / 2 * np.sqrt(2 / np.log(2)) * FWHM


# %%
def intensity_from_a0(a0, λL=0.8*u.micrometer):
    """Compute peak laser intensity in the focal plane.

    Args:
        a0 (float, dimensionless): normalized laser vector potential
        λL (float, length): laser wavelength

    Returns:
        I0 (float, energy/time/area): peak laser intensity in the focal plane
    """
    return π / 2 * u.clight / r_e * u.me * u.clight**2 / λL**2 * a0**2


# %%
def a0_from_intensity(I0, λL=0.8*u.micrometer):
    """Compute laser normalized vector potential.

    Args:
        I0 (float, energy/time/area): peak laser intensity in the focal plane
        λL (float, length): laser wavelength

    Returns:
        a0 (float, dimensionless): normalized laser vector potential
    """
    return np.sqrt(I0 / (π / 2 * u.clight / r_e * u.me * u.clight**2 / λL**2))

# %% [markdown]
# ## Class abstractions
# %% [markdown]
# ### Gaussian Beam

# %%


class GaussianBeam(object):
    """Contains the (geometric) parameters for a Gaussian laser beam.

    Attributes:
        w0 (float, length): beam waist @ 1/e^2 intensity
        fwhm (float, length): beam FWHM @ 1/2 intensity
        λL (float, length): wavelength
        zR (float, length): Rayleigh length
    """

    def __init__(self, w0=None, fwhm=None, λL=0.8*u.micrometer):
        """Default beam constructor.
        Can take *either* `w0` or `fwhm` as parameters.
        """
        self.λL = λL.to('micrometer')

        if w0 and not fwhm:
            self.w0 = w0.to('micrometer')
            self.fwhm = w0_to_FWHM(self.w0).to('micrometer')
        elif fwhm and not w0:
            self.fwhm = fwhm.to('micrometer')
            self.w0 = FWHM_to_w0(self.fwhm).to('micrometer')
        elif w0 and fwhm:
            assert np.isclose(w0.to_value('micrometer'),
                              FWHM_to_w0(fwhm).to_value('micrometer'))
            self.w0 = w0.to('micrometer')
            self.fwhm = fwhm.to('micrometer')
        else:  # both None
            self.w0 = None
            self.fwhm = None

        if self.w0:
            self.zR = (π * self.w0**2 / self.λL).to('milimeter')
        else:
            self.zR = None

    @classmethod
    def from_f_number(class_object, f_number, λL=0.8*u.micrometer):
        """Construct beam by giving the OAP's f/#.

        Args:
            f_number (float, dimensionless): f/# of the off-axis parabolic mirror
        """
        w0 = 2 * np.sqrt(2) / π * λL * f_number
        return class_object(w0=w0, λL=λL)

    @classmethod
    def from_focal_distance(class_object, f, D, λL=0.8*u.micrometer):
        """Constuct beam from OAP's focal distance and beam diameter.

        Args:
            f (float, units of length): focal distance of the off-axis parabolic mirror
            D (float, units of length): beam diameter after compressor
        """
        return class_object.from_f_number(f_number=f/D, λL=λL)

    def __repr__(self):
        return "<{0.__class__.__name__}({0.w0}, {0.λL})>".format(self)

    def __str__(self):
        msg = 'beam with λL={0.λL:.2f}'.format(self)
        if self.w0 and self.fwhm:
            msg = 'beam with w0={0.w0:.1f} (FWHM={0.fwhm:.1f}), zᵣ={0.zR:.2f}, λL={0.λL:.2f}'.format(
                self)
        return msg

# %% [markdown]
# Example usage


# %%
beam = GaussianBeam()
beam = GaussianBeam(w0=7.202530529256849*u.micrometer)
beam = GaussianBeam(fwhm=8.4803316326207*u.micrometer)
beam = GaussianBeam(w0=7.202530529256849*u.micrometer,
                    fwhm=8.4803316326207*u.micrometer)
beam = GaussianBeam.from_f_number(f_number=10.)
beam = GaussianBeam.from_focal_distance(f=1*u.meter, D=10*u.cm)
print(beam)

# %% [markdown]
# ### Laser, without matching

# %%


class Laser(object):
    """Class containing laser parameters.

    Attributes:
        beam (:obj:`GaussianBeam`): class instance containing beam params 
        ɛL (float, energy): pulse energy on target (after compressor 
                            and beam transport, focused into the FWHM@intensity spot) 
        τL (float, time): pulse duration at FWHM in intensity
        kL (float, 1/length): wavenumber
        ωL (float, 1/time): angular frequency
        ncrit (float, 1/volume): critical plasma density for this laser
        P0 (float, energy/time): power
        I0 (float, energy/time/area): peak intensity in the focal plane
        a0 (float, dimensionless): normalized vector potential
        E0 (float, energy/charge/length): peak electric field
    """

    def __init__(self, ɛL, τL, beam=GaussianBeam()):
        """Creates laser with given parameters."""
        self.beam = beam
        self.kL = (2 * π / self.beam.λL).to('1/micrometer')
        self.ωL = (u.clight * self.kL).to('1/femtosecond')
        self.ncrit = (π / (r_e * self.beam.λL**2)).to('1/cm**3')

        self.ɛL = ɛL.to('joule')
        self.τL = τL.to('femtosecond')
        self.P0 = (2 * np.sqrt(np.log(2) / π) *
                   self.ɛL / self.τL).to('terawatt')

        if self.beam.w0:
            self.I0 = (2 / π * np.sqrt(4 * np.log(2) / π) * self.ɛL /
                       (self.τL * self.beam.w0**2)).to('watt/cm**2')
            self.a0 = a0_from_intensity(
                I0=self.I0, λL=self.beam.λL).to_value('dimensionless')
            self.E0 = (u.clight * u.me * self.ωL / np.abs(u.qe)
                       * self.a0).to('megavolt/mm')
        else:
            self.I0 = None
            self.a0 = None
            self.E0 = None

    @classmethod
    def from_a0(class_object, a0, ɛL=None, τL=None, beam=GaussianBeam()):
        """Construct laser by giving its normalized vector potential a0.
        Must supply either (ɛL,τL), (ɛL,beam) or (τL,beam).
        """
        prefactor = (4 * np.log(2) / π)**(3/2)
        I0 = intensity_from_a0(a0=a0, λL=beam.λL).to('watt/cm**2')

        if ɛL and τL and (not beam.fwhm):
            fwhm = np.sqrt((prefactor * ɛL) / (I0 * τL))
        elif ɛL and beam.fwhm and (not τL):
            fwhm = beam.fwhm
            τL = (prefactor * ɛL) / (I0 * fwhm**2)
        elif τL and beam.fwhm and (not ɛL):
            fwhm = beam.fwhm
            ɛL = I0 * τL * fwhm**2 / prefactor
        else:
            raise TypeError(
                'Must supply either (ɛL,τL), (ɛL,beam) or (τL,beam).')

        return class_object(ɛL=ɛL, τL=τL, beam=GaussianBeam(fwhm=fwhm))

    @classmethod
    def from_intensity(class_object, I0, ɛL=None, τL=None, beam=GaussianBeam()):
        """Construct laser by giving its intensity I0.
        Must supply either (ɛL,τL), (ɛL,beam) or (τL,beam).
        """
        a0 = a0_from_intensity(I0=I0, λL=beam.λL)
        return class_object.from_a0(a0=a0, ɛL=ɛL, τL=τL, beam=beam)

    @classmethod
    def from_power(class_object, P0, beam, ɛL=None, τL=None):
        """Construct laser by giving its power P0 and beam size.
        Must supply either ɛL or τL.
        """
        prefactor = 2 * np.sqrt(np.log(2) / π)

        if ɛL and (not τL):
            τL = prefactor * ɛL / P0
        elif τL and (not ɛL):
            ɛL = P0 * τL / prefactor
        else:  # either both or none
            raise TypeError('Must supply either ɛL or τL.')

        return class_object(ɛL=ɛL, τL=τL, beam=beam)

    def __repr__(self):
        return "<{0.__class__.__name__}({0.ɛL}, {0.τL}, {1})>".format(self, repr(self.beam))

    def __str__(self):
        msg = 'laser {0.beam}, kL={0.kL:.3f}, ωL={0.ωL:.3f}, ɛL={0.ɛL:.1f}, τL={0.τL:.1f}, P₀={0.P0:.1f}'.format(
            self)
        if self.beam.w0:
            msg += '\nI₀={0.I0:.1e}, a₀={0.a0:.1f}, E₀={0.E0:.1e}'.format(self)
        return msg

# %% [markdown]
# Example usage


# %%
# CETAL params
laser = Laser(ɛL=7.7*u.joule,
              τL=40*u.femtosecond,
              beam=GaussianBeam(w0=18*u.micrometer))
laser = Laser.from_a0(a0=4.076967454355432,
                      ɛL=7.7*u.joule,
                      τL=40*u.femtosecond)
laser = Laser.from_a0(a0=4.076967454355432,
                      ɛL=7.7*u.joule,
                      beam=GaussianBeam(w0=18*u.micrometer))
laser = Laser.from_a0(a0=4.076967454355432,
                      τL=40*u.femtosecond,
                      beam=GaussianBeam(w0=18*u.micrometer))
laser = Laser.from_intensity(I0=3.553314404474785e19*u.watt/u.cm**2,
                             ɛL=7.7*u.joule,
                             τL=40*u.femtosecond)
laser = Laser.from_intensity(I0=3.553314404474785e19*u.watt/u.cm**2,
                             ɛL=7.7*u.joule,
                             beam=GaussianBeam(w0=18*u.micrometer))
laser = Laser.from_intensity(I0=3.553314404474785e19*u.watt/u.cm**2,
                             τL=40*u.femtosecond,
                             beam=GaussianBeam(w0=18*u.micrometer))
laser = Laser.from_power(P0=180.84167614968285*u.terawatt,
                         beam=GaussianBeam(w0=18*u.micrometer),
                         τL=40*u.femtosecond)
laser = Laser.from_power(P0=180.84167614968285*u.terawatt,
                         beam=GaussianBeam(w0=18*u.micrometer),
                         ɛL=7.7*u.joule)
print(laser)

# %%


class Simulation(object):
    """Class for estimating the recommended simulation parameters.
    Attributes:
        Δx (float, length): transverse spatial resolution
        Δy (float, length): transverse spatial resolution
        Δz (float, length): longitudinal spatial resolution
        nx (int, dimensionless): transverse number of cells
        ny (int, dimensionless): transverse number of cells
        nz (int, dimensionless): longitudinal number of cells
        L (float, length): length of cubic simulation box
        ppc (int, dimensionless): number of particles per cell
        npart (int, dimensionless): total number of (macro-)particles in the
            simulation box
        dt (float, time): simulation time step per iteration
        t_interact (float, time): time it takes for the moving window to slide
            across the plasma
        nstep (int, dimensionless): number of iterations to perform
    Note:
        Here longitudinal means along the laser propagation direction.
        Recommended number of particles per cell: 64 (1D), 10 (2D), 8 (3D).
    """

    def __init__(self, plasma, box_length=None, ppc=None):
        """Estimate recommended simulation params for given plasma (and laser).
        Args:
            plasma (:obj:`Plasma`): instance containing laser and plasma params
            box_length (float, length, optional): length of the cubic
                simulation box. Defaults to 4λₚ.
            ppc (int, dimensionless, optional): number of particles per cell.
                Defaults to 8 (3D).
        """
        if not plasma.laser:
            raise TypeError(
                'Given `Plasma` instance must contain `Laser` instance.')
        else:
            self.plasma = plasma
        if not box_length:
            self.L = 4 * self.plasma.λp
        else:
            self.L = box_length.to('micrometer')
        if not ppc:
            self.ppc = 8
        else:
            self.ppc = ppc

        self.Δx = self.plasma.lp / 10
        self.Δy = self.Δx
        self.Δz = self.plasma.laser.beam.λL / 20

        self.nx = int((self.L / self.Δx).to_value('dimensionless'))
        self.ny = self.nx
        self.nz = int((self.L / self.Δz).to_value('dimensionless'))

        self.npart = self.nx * self.ny * self.nz * self.ppc

        self.dt = (self.Δz/u.clight).to('femtosecond')
        self.t_interact = ((self.plasma.Lacc + self.L) /
                           u.clight).to('femtosecond')

        self.nstep = int(
            (self.t_interact / self.dt).to_value('dimensionless'))

    def __repr__(self):
        return "<{0.__class__.__name__}({0}, {1.L}, {1.ppc})>".format(repr(self.plasma), self)

    def __str__(self):
        msg = 'simulation with box size ({0.L:.1f})³, Δx={0.Δx:.3f}, Δy={0.Δy:.3f}, Δz={0.Δz:.3f}, nx={0.nx}, ny={0.ny}, nz={0.nz}, {0.npart:e} macro-particles, {0.nstep:e} time steps'.format(
            self)
        return msg

# %% [markdown]
# ### Plasma, without matching

# %%


class Plasma(object):
    """Class containing plasma parameters.
    Attributes:
        npe (float, 1/volume): plasma electron (number) density
        ωp (float, 1/time): plasma frequency
        lp (float, length): unit of length
        tp (float, time): unit of time
        λp (float, length): plasma skin depth
        kp (float, 1/length): plasma wavenumber
        Ewb (float, energy/charge/length): cold, 1D wave-breaking field
        laser (:obj:`Laser`): instance containing laser params
        γp (float, dimensionless): plasma γ factor
        Pc (float, energy/time): critical power for self-focusing
        dephasing (float, length): electron dephasing length
        depletion (float, length): pump depletion length
        Ez_avg (float, energy/charge/length): average accelerating field
                                    in the direction of electron propagation 
        R (float, length): radius of the plasma bubble
        Lacc (float, length): distance over which laser propagates
        N (float, dimensionless): estimated number of electrons in the bunch
        Q (float, charge): estimated total electron bunch charge
        ΔE (float, energy): maximum energy gained by one electron
                        propagating for Lacc
                        see Lu et al., 2007 Phys. Rev. ST. Accel. Beams
        η (float, dimensionless): energy transfer efficiency, defined as
                        total bunch energy `N` * `ΔE` / laser energy `ɛL`
            under matching conditions, `η` ~ 1 / (2 * a0)

    """

    def __init__(self, n_pe, laser=None, bubble_radius=None, propagation_distance=None):
        """Creates plasma with given density.
        Args:
            n_pe (float, 1/volume): plasma electron (number) density
            laser (:obj:`Laser`, optional): instance containing laser params
            bubble_radius (float, length, optional): radius of the plasma bubble
            propagation_distance (float, length, optional): length of plasma region
                                                    defaults to `dephasing`
        """
        self.npe = n_pe.to('1/cm**3')
        self.λp = np.sqrt(π / (r_e * self.npe)).to('micrometer')
        self.kp = (2 * π / self.λp).to('1/micrometer')
        self.ωp = (u.clight * self.kp).to('1/femtosecond')

        self.Ewb = (u.me * u.clight * self.ωp / np.abs(u.qe)).to('megavolt/mm')

        self.lp = (u.clight / self.ωp).to('micrometer')
        self.tp = (1 / self.ωp).to('femtosecond')

        if laser:
            self.laser = laser

            self.γp = (self.laser.ωL / self.ωp).to_value('dimensionless')
            self.Pc = (17 * self.γp**2 * u.gigawatt).to('terawatt')

            self.dephasing = (4 / 3 * self.γp**2 *
                              np.sqrt(self.laser.a0) / self.kp).to('mm')
            self.depletion = (self.γp**2 * u.clight * self.laser.τL).to('mm')

            self.Ez_avg = self.Ewb * np.sqrt(self.laser.a0) / 2

            if propagation_distance:
                self.Lacc = propagation_distance.to('mm')
            else:
                self.Lacc = self.dephasing

            self.ΔE = (np.abs(u.qe) * self.Ez_avg *
                       self.Lacc).to('megaelectronvolt')

            if bubble_radius:
                self.R = bubble_radius

                self.N = (1 / 30 * (self.kp * self.R)**3 /
                          (self.kp * r_e)).to_value('dimensionless')
                self.Q = (self.N * np.abs(u.qe)).to('picocoulomb')

                self.η = (self.N * self.ΔE /
                          self.laser.ɛL).to_value('dimensionless')
            else:
                self.R = None
        else:
            self.laser = None

    def __repr__(self):
        return "<{0.__class__.__name__}({0.npe}, {1}, {0.R})>".format(self, repr(self.laser))

    def __str__(self):
        msg = 'Plasma with nₚ={0.npe:.1e}, ωₚ={0.ωp:.3f}, kₚ={0.kp:.3f}, λₚ={0.λp:.1f}, Ewb={0.Ewb:.1f}'.format(
            self)
        if self.laser:
            n_ratio = (self.npe / self.laser.ncrit).to_value('dimensionless')
            msg = 'Plasma with nₚ={0.npe:.1e} ({1:.2e} nc), ωₚ={0.ωp:.3f}, kₚ={0.kp:.3f}, λₚ={0.λp:.1f}, Ewb={0.Ewb:.1f}'.format(
                self, n_ratio)
            msg += '\nPc={0.Pc:.1f}, Ldeph={0.dephasing:.2f}, Ldepl={0.depletion:.2f}, ΔE={0.ΔE:.1f} over Lacc={0.Lacc:.2f}'.format(
                self)
            msg += '\nfor {0.laser}'.format(self)
            if self.R:
                msg += '\nN={0.N:.1e} electrons, Q={0.Q:.1f}, η={0.η:.3f}'.format(
                    self)
        return msg

# %% [markdown]
# Example usage
# %% [markdown]
# CETAL laser


# %%
npe_cetal = 1.5e18 / u.cm**3
beam_cetal = GaussianBeam(w0=18*u.micrometer)
laser_cetal = Laser(ɛL=7.7*u.joule,
                    τL=40*u.femtosecond,
                    beam=beam_cetal)
plasma_cetal = Plasma(n_pe=npe_cetal)
plasma_cetal = Plasma(n_pe=npe_cetal, laser=laser_cetal)
bubble_R_cetal = (2 * np.sqrt(plasma_cetal.laser.a0) /
                  plasma_cetal.kp).to('micrometer')
plasma_cetal = Plasma(n_pe=npe_cetal, laser=laser_cetal,
                      bubble_radius=bubble_R_cetal)
print(plasma_cetal)

# %% [markdown]
# Gamma blaster laser

# %%
npe_ong = 6.125e18 / u.cm**3
beam_ong = GaussianBeam(w0=10*u.micrometer)
laser_ong = Laser.from_power(
    P0=1570.796*u.terawatt, beam=beam_ong, τL=33*u.femtosecond)
plasma_ong = Plasma(n_pe=npe_ong, laser=laser_ong,
                    propagation_distance=500*u.micrometer)
print(plasma_ong)

# %% [markdown]
# ### Matching conditions

# %%


def matched_laser_plasma(a0, beam=GaussianBeam()):
    """Computes matched laser params and plasma density.

    From condition that dephasing length equals pump depletion length  
    and condition for self-guided propagation
    we get optimal laser pulse duration `τL` and plasma density `n_pe`.
    From matching laser beam waist to plasma (α=1)
    we get the optimal beam waist `w0`.
    We also assume the bubble (blowout) radius to be R = w0 (β=1).

    Args:
        a0 (float, dimensionless): normalized laser vector potential
        beam (:obj:`GaussianBeam`, optional): instance providing laser wavelength 

    Returns:
        :obj:`Plasma` instance with matched params

    Ref: Lu, W. et al., Phys. Rev. ST Accel. Beams 10 (6): 061301
    Note: these scaling laws are valid up to a critical value `a0c`.
    """
    τL = (2 / (3 * π) * beam.λL / u.clight * a0**3).to('femtosecond')
    n_pe = (π / (r_e * beam.λL**2 * a0**5)).to('1/cm**3')
    w0 = np.sqrt(a0 / (π * r_e * n_pe))

    gbeam = GaussianBeam(w0=w0, λL=beam.λL)
    laser = Laser.from_a0(a0=a0, τL=τL, beam=gbeam)

    # critical normalized vector potential
    a0c = (2 * np.sqrt(laser.ncrit / n_pe)).to_value('dimensionless')
    print('Scaling laws valid up to a0c={0:.1f}'.format(a0c))

    return Plasma(n_pe=n_pe, laser=laser, bubble_radius=w0)

# %% [markdown]
# Example usage


# %%
matched_cetal = matched_laser_plasma(a0=4.1)


# %%
print(matched_cetal)


# %% [markdown]
# For $a_0 ≥ 4-5$ we also get self-injection from pure Helium. Helium has the ionization
# energies 24.59 eV (He${}^{+}$) and 54.42 (He${}^{2+}$), corresponding to laser intensities
# $1.4 × 10^{15}$, respectively $8.8 × 10^{15}$ W/cm${}^2$ (Gibbon, "Short pulse
# laser interactions with matter", p. 22), and will therefore be easily ionized by the laser
# prepulse.
# %% [markdown]
# The atomic Coulomb field is on the order of $10^{14}$ W/cm${}^2$ and relativistic effects
# become important for laser intensities above $10^{17}$ W/cm${}^2$ ($a_0 ≥ 1$), while
# QED effects such as radiation reaction only become important for intensities beyond $∼
# 2 × 10^{21}$ W/cm${}^2$.
# %% [markdown]
# For LWFA, we roughly have $w_0 ≈ c \tau_L$ and $\tau_L ≈ \omega_p^{-1}$.
# %% [markdown]
# If we assume the laser energy before the compressor is 20 J, and 30% is lost in the
# compressor and beam transport, we are left with 14 J in the chamber. If 50% of this energy
# can be focused into the FWHM spot of $21 \mu$m, we get 7 J on target.
# %% [markdown]
# Single-shot non-intercepting profile monitor of plasma-accelerated electron beams with nanometric resolution
# Appl. Phys. Lett. 111, 133105 (2017)

# %%
print('[...] profile monitor [...]\n')
npe_monitor = 2e19 / u.cm**3
beam_monitor = GaussianBeam(w0=10*u.micrometer)
laser_monitor = Laser(ɛL=1.*u.joule,
                      τL=30*u.femtosecond,
                      beam=beam_monitor)
plasma_monitor = Plasma(
    n_pe=npe_monitor, laser=laser_monitor, propagation_distance=1*u.mm)

print()
print('Parameters for beam monitor paper:')
print(plasma_monitor)

matched_monitor = matched_laser_plasma(a0=3.1)
print()
print('Matching conditions for beam monitor paper:')
print(matched_monitor)

# %% [markdown]
# Trace-space reconstruction of low-emittance electron beams through betatron radiation in laser-plasma accelerators
# Phys. Rev. ST. Accel. Beams 20, 012801 (2017)


# %%
print('Trace-space reconstruction [...]\n')
npe_emittance = 6.14e18 / u.cm**3
beam_emittance = GaussianBeam(w0=6.94*u.micrometer)
laser_emittance = Laser(ɛL=1.*u.joule,
                        τL=30*u.femtosecond,
                        beam=beam_emittance)
plasma_emittance = Plasma(
    n_pe=npe_emittance, laser=laser_emittance, propagation_distance=1.18*u.mm)
bubble_R_emittance = (2 * np.sqrt(plasma_emittance.laser.a0) /
                      plasma_emittance.kp).to('micrometer')  # 9*u.micrometer
print()
print(f'bubble radius R={bubble_R_emittance}')
plasma_emittance = Plasma(n_pe=npe_emittance, laser=laser_emittance, bubble_radius=bubble_R_emittance,
                          propagation_distance=1.18*u.mm)

print()
print('Parameters for emmitance paper:')
print(plasma_emittance)

matched_emittance = matched_laser_plasma(a0=4.4)
print()
print('Matching conditions for emmitance paper:')
print(matched_emittance)


# %% [markdown]
# 1. gas-jet with $L_{\text{acc}} = 3$ mm, $n_{\text{pe}} = (1-3) \times 10^{18}$ cm${}^{-3}$
# 2. capillary with $L_{\text{acc}} = (3-10)$ cm, $n_{\text{pe}} = (3-7) \times 10^{17}$ cm${}^{-3}$

# - $w_0 = 2 \sigma_{\text{rms}}$, and experiments say $\sigma_{\text{rms}} = 7$ $\mu$m, so $w_0 = 14$ $\mu$m
# - $\varepsilon_L = 3$ J, $\tau_L = 30$ fs, $I_0 = 3 \times 10^{19}$ W/cm${}^{2}$, $a_0=3.4$

# %%
print()
print('Frascati future exp [...]\n')

npe_jet = 3e18 / u.cm**3
l_acc_jet = 3 * u.mm

npe_capil = 3e17 / u.cm**3
l_acc_capil = 5 * u.cm

beam_frasc = GaussianBeam(w0=15.56*u.micrometer)
laser_frasc = Laser(ɛL=3.*u.joule,
                    τL=30*u.femtosecond,
                    beam=beam_frasc)

plasma_jet = Plasma(n_pe=npe_jet, laser=laser_frasc,
                    propagation_distance=l_acc_jet)
plasma_capil = Plasma(n_pe=npe_capil, laser=laser_frasc,
                      propagation_distance=l_acc_capil)

print()
print('Parameters for He gas jet:')
print(plasma_jet)
print(Simulation(plasma_jet))

print()
print('Parameters for H capillary:')
print(plasma_capil)
print(Simulation(plasma_capil))

matched_frasc = matched_laser_plasma(a0=3.4)
print()
print('Matching conditions:')
print(matched_frasc)

# %%
