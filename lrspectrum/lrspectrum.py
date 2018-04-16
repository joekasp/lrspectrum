"""
The MIT License (MIT)

Copyright (c) 2018 Andrew Wildman

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
try:
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover
    raise ImportError('Matplotlib is required to run LRSpectrum')

try:
    import numpy as np
except ImportError:  # pragma: no cover
    raise ImportError('Numpy is required to run LRSpectrum')

from . import parsers


class LRSpectrum(object):
    """
    LRSpectrum generates a linear response spectrum from a Gaussian log file

    Attrubutes:
        name:          Name identifier
                       string

        logfile:       Logfiles to be parsed
                       array<string>

        roots:         Poles (key, eV) and oscillator strengths (value,
                            unitless) of linear response
                       dict<string:float>

        freq:          Energy range to be plotted (eV)
                       numpy.ndarray<float>

        spect:         Spectrum generated by convolving each of the roots with
                            a given distribution such that the integral over
                            the distribution gives the oscillator strength
                       numpy.ndarray<float>

        broad:         Broadening parameter. HWHM
                       float

        wlim:          Sets bounds on energy range to generate
                       tuple<float>

        res:           Number of points per eV to evaluate
                       int

    Methods:
        parse_log():
            Parses a gaussian linear response log file. Fills roots dict.
              Called during init, but can be used to regenerate if needed.

        gen_spect(broad,wlim,res,meth):
            Generates a spectrum in the range given by wlim by convolving a
              specified distribution with each of the roots and scaling by the
              oscillator strength. Can be called multiple times to generate
              spectra with different parameters.
            broad:    Same definition as above
            wlim:     Same definition as above
            res:      Same definition as above
            meth:     Type of distribution used to broaden. Currently 'lorentz'
                        or 'gaussian' are supported. Lorentz is for time-energy
                        uncertainty broadening (lifetime) and gaussian is for
                        vibronic broadening.

        plot(xlim,ylim,xLabel,yLabel,show,lines,**kwargs):
            Plots spectrum vs frequency. Built using matplotlib.pyplot, so any
              additional arguments can be passed using kwargs
            xlim:     Limits on x axis                        tuple<float>
            ylim:     Limits on y axis                        tuple<float>
            xLabel:   Label on x axis                         string
            yLabel:   Label on y axis                         string
            show:     Whether or not to call plt.show()       bool
            lines:    Whether or not to plot lines showing    bool
                        the roots with the respective
                        oscillator strengths.

    """

    def __init__(self, *multLogNames, **kwargs):
        # Keyword arguments. Has to be this way for 2.7 compatibility
        name = kwargs.pop('name', None)
        program = kwargs.pop('program', None)

        # Support either one list of logfiles or many logfiles as params
        if isinstance(multLogNames[0], list):
            self.logfile = [self._check_log(nm) for nm in multLogNames[0]]
        elif isinstance(multLogNames[0], str):
            self.logfile = [self._check_log(nm) for nm in multLogNames]
        else:
            raise TypeError(
                'Unexpected type for logfiles: ' +
                '{0}'.format(type(multLogNames[0]))
            )

        # Initialization
        self.name = name
        self.roots = {}
        self.freq = None
        self.spect = None
        self.broad = None
        self.wlim = None
        self.res = None

        # Always call parser when initializing
        self.parse_log(program=program)

    def parse_log(self, program=None):
        """
        Parses the logfiles in self.logfile according to 'program' parser
        """

        for lg in self.logfile:
            if program is not None:
                if not isinstance(program, str):
                    raise TypeError(
                        'Expected string for input "program". ' +
                        'Recieved {0}'.format(type(program))
                    )
                program = program.lower()
                if program not in parsers.progs.keys():
                    raise ValueError(
                        'Specified program {0} not parsable'.format(program)
                    )
            else:  # pragma: no cover
                # We dont consider coverage here; testing of this method occurs
                # separately
                program = parsers.detect(lg)
            # TODO: Break up following line for clarity
            self.roots.update(parsers.progs[program](lg))

    def gen_spect(self, broad=0.5, wlim=None, res=100, meth='lorentz'):
        """ Generates the broadened spectrum and stores it """

        # Input checking
        try:
            broad * 1.5
        except Exception as ex:
            print('Caught exception: {0}'.format(ex))
            raise TypeError('Input "broad" to LRSpectrum.gen_spect: ' +
                            '{0}'.format(type(broad)))
        if wlim is not None:
            try:
                wlim[0] * 1.5
                wlim[1] * 1.5
            except Exception as ex:
                print('Exception for input "wlim"')
                raise ex
        try:
            res * 1.5
        except Exception as ex:
            print('Caught exception: {0}'.format(ex))
            raise TypeError('Input "res" to LRSpectrum.gen_spect: ' +
                            '{0}'.format(type(res)))
        try:
            meth.lower()
        except Exception as ex:
            raise TypeError('Input "meth" to LRSpectrum.gen_spect: ' +
                            '{0}'.format(type(meth)))

        self.broad = broad

        # If wlim isn't given, automatically generate it based on the roots
        if wlim is None:
            print("Spectral range not specified... " +
                  "Automatically generating spectral range")
            percent = 0.930
            mn = None
            mx = None
            for k in self.roots.keys():
                if self.roots[k] != 0:
                    if mn is None or float(k) < mn:
                        mn = float(k)
                    if mx is None or float(k) > mx:
                        mx = float(k)
            # We are going to use the quantile function of the lorentz
            # distribution here, even if the actual distribution is gaussian
            lb = broad*np.tan(((1-percent)-0.5)*np.pi)+mn
            mb = broad*np.tan((percent-0.5)*np.pi)+mx
            wlim = (lb, mb)

        self.wlim = wlim
        self.res = int(res)
        nPts = int((wlim[1]-wlim[0])*res)
        self.freq = np.linspace(wlim[0], wlim[1], nPts)
        self.spect = np.zeros(nPts)

        # Calling .items() is memory inefficent in python2, but this is good
        # for python3
        for root, osc_str in self.roots.items():
            if osc_str != 0:
                root = float(root)
                if meth.lower() == 'lorentz':
                    self.spect += self._lorentz(broad, root, osc_str)
                elif meth.lower() == 'gaussian':
                    self.spect += self._gaussian(broad, root, osc_str)
                else:
                    raise ValueError(
                        'Unsupported distribution "{0}" specified'.format(meth)
                    )

    def plot(self, xlim=None, ylim=None, xLabel='Energy / eV',
             yLabel='Arbitrary Units', show=False, do_spect=True, sticks=True,
             ax=None, xshift=0, xscale=1, yshift=0, yscale=1, **kwargs):
        """ Plots the generated spectrum and roots """

        if self.spect is None and do_spect:
            print('Spectrum must be generated prior to plotting')
            return

        if ax is None:
            ax = plt.gca()

        if xLabel is not None:
            ax.set_xlabel(xLabel)

        if yLabel is not None:
            ax.set_ylabel(yLabel)

        if xscale is not None:
            # Type checking
            try:
                xscale * 1.5
            except Exception as ex:
                print('Caught exception: {0}'.format(ex))
                raise TypeError('Input "xscale" to LRSpectrum.plot: ' +
                                '{0}'.format(type(xscale)))

        if xshift is not None:
            # Type checking
            try:
                xshift * 1.5
            except Exception as ex:
                print('Caught exception: {0}'.format(ex))
                raise TypeError('Input "xshift" to LRSpectrum.plot: ' +
                                '{0}'.format(type(xshift)))

        if xlim is not None:
            # Type checking
            for i in range(2):
                try:
                    xlim[i]
                except TypeError as ex:
                    print('Caught exception: {0}'.format(ex))
                    raise TypeError('Input "xlim" to LRSpectrum.plot: ' +
                                    '{0}'.format(type(xlim)))
                except IndexError as ex:
                    print('Caught exception: {0}'.format(ex))
                    raise IndexError('Length of "xlim" to LRSpectrum.plot: ' +
                                     '{0}'.format(len(xlim)))
                try:
                    xlim[i] * 1.5
                except TypeError as ex:
                    print('Caught exception: {0}'.format(ex))
                    raise TypeError('Elements inside input "xlim" to ' +
                                    'LRSpectrum.plot' +
                                    '{0}'.format(type(xlim[i])))

            # Setting xlim
            xlim_mod = [x * xscale + xshift for x in xlim]
            ax.set_xlim(xlim_mod)

        if yscale is not None:
            # Type checking
            try:
                yscale * 1.5
            except Exception as ex:
                print('Caught exception: {0}'.format(ex))
                raise TypeError('Input "yscale" to LRSpectrum.plot: ' +
                                '{0}'.format(type(yscale)))

        if yshift is not None:
            # Type checking
            try:
                yshift * 1.5
            except Exception as ex:
                print('Caught exception: {0}'.format(ex))
                raise TypeError('Input "yshift" to LRSpectrum.plot: ' +
                                '{0}'.format(type(yshift)))

        if ylim is not None:
            # Type checking
            for i in range(2):
                try:
                    ylim[i]
                except TypeError as ex:
                    print('Caught exception: {0}'.format(ex))
                    raise TypeError('Input "ylim" to LRSpectrum.plot: ' +
                                    '{0}'.format(type(ylim)))
                except IndexError as ex:
                    print('Caught exception: {0}'.format(ex))
                    raise IndexError('Length of "ylim" to LRSpectrum.plot: ' +
                                     '{0}'.format(len(ylim)))
                try:
                    ylim[i] * 1.5
                except TypeError as ex:
                    print('Caught exception: {0}'.format(ex))
                    raise TypeError('Elements inside input "ylim" to ' +
                                    'LRSpectrum.plot' +
                                    '{0}'.format(type(ylim[i])))

            # Setting ylim
            ylim_mod = [y * yscale + yshift for y in ylim]
            ax.set_ylim(ylim_mod)

        # Plot spectrum
        if do_spect:
            x = xscale*self.freq + xshift
            y = yscale*self.spect + yshift
            ax.plot(x, y, **kwargs)

        # Plot poles
        if sticks:
            for root, osc_str in self.roots.items():
                r = float(root)
                ax.plot((r, r), (0, osc_str), 'k-', **kwargs)

        if show:  # pragma: no cover
            plt.show()

        return ax

    def _check_log(self, logname):
        """ Checks that the logfile ends with '.log' """
        if logname.split('.')[-1].lower() != 'log':
            raise ValueError('Non-logfile %s given' % (logname))
        else:
            return logname

    def _lorentz(self, broad, root, osc_str):
        """
        Calculates and returns a lorentzian

        The lorentzian is centered at root, integrates to osc_str, and has a
        half-width at half-max of broad.
        """

        ones = np.ones(self.freq.shape)
        # 1/(pi*broad*(1+((w-root)/broad)^2))
        l_denom = broad*np.pi*(1+np.square((self.freq-root*ones)/broad))
        return osc_str*np.divide(ones, l_denom)

    def _gaussian(self, broad, root, osc_str):
        """
        Calculates and returns a gaussian

        The gaussian is centered at root, integrates to osc_str, and has a
        half-width at half-max of broad.
        """

        ones = np.ones(self.freq.shape)
        # Convert from HWHM to std dev
        stddev = broad/np.sqrt(2.0*np.log(2.0))
        # 1/((2*pi*broad^2)^(1/2))*e^(-(w-root)^2/(2*broad^2)
        g_power = -1*np.square(self.freq-root*ones) / (2*np.square(stddev))
        gauss = 1/(np.sqrt(2*np.pi)*stddev)*np.exp(g_power)
        return osc_str*gauss
