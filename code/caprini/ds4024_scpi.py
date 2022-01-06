import warnings

import vxi11

import numpy as np

from .waveform import Waveform, WaveformBundle

class DS4024_SCPI:
    '''Interface to the DS4000E series oscilloscope

    This is the main interface for caprini.  It will connect to the
    scope over VXI and fetch data as caprini objects (eg Waveforms).
    It encapsulates a lot of the tedious/repetitive bits of talking to
    the scope, and interfaces with it consistently.  That consistency
    seems to be key: it's not too hard to wind up hanging the
    interface to the scope if you send malformed commands.

    For example usage, see the included Jupyter notebooks.

    This class contains many internal methods; these are prefixed with
    underscores.  The API for those is not guaranteed to be stable in
    any way, shape or form.

    The API for all non-internal methods is also not guaranteed to be
    stable, but it's a lot less likely that those will change without
    very good reasons.

    A lot of the interface definitions have been automagically
    extracted from the PDF manual.  See the included notebook
    `ds4024_automagic_api_extraction.ipynb` for how that was done.  In
    particular, if you want to add capture of another subsystem's
    configuration, this should be your first stop.

    Not all internal functions have docstrings; those without
    docstrings are either blatantly obvious, or very small wrappers
    around other methods that have docstrings.
    '''
    RET_NONE = 'none'
    RET_LINE = 'line'
    RET_WAVEFORM = 'waveform'

    def __init__(self, hostname: str):
        self.hostname = hostname

        self.instrument = vxi11.Instrument(hostname)

        self.serial_no = None  # Can be optionally included for traceability

    def _cmd(self, cmdline: str, ret_type):
        '''INTERNAL: Send a full command and return its result

        cmdline is the entire line without a newline (we consider that
        newline part of the protocol framing)

        ret_type is one of the RET_FOO values above.  Different
        commands return different sorts of values; the key thing here
        is that waveforms return a length-prefixed buffer

        This API is an awful holdover from my original USB serial
        version, which was unusably flaky on the scope side.  It needs
        to be meaningfully reworked in the new VXI universe.

        '''
        actual_cmdline = cmdline.strip() #.split()

        if ret_type == self.RET_NONE:
            return self.instrument.write(actual_cmdline)

        if ret_type == self.RET_LINE:
            return self.instrument.ask(actual_cmdline)

        return self.instrument.ask_raw(actual_cmdline.encode("ISO8859-1"))

    def _idn(self):
        '''Get the device identifier (serial no, along with versions)'''
        return self._cmd('*IDN?', DS4024_SCPI.RET_LINE)

    def _parse_preamble(self, preamble: str):
        '''Parses the :WAVeform:PREamble? result

        This goes from the documentation in PGA21101-1110, which is
        supposed to document the 00.02.03 firmwares.

        It returns a dictionary with the
        '''
        fmt,modeno,n_points,n_avgs,xinc,xorig,xref, yinc,yorig,yref = map(float, preamble.split(','))
        result = {
            'format': fmt,
            'mode': modeno,
            'n_points': n_points,
            'n_avgs': n_avgs,
            'x_step': xinc,
            'x_origin': xorig,
            'x_reference': xref,  # Literally always zero, pg247
            'y_step': yinc,
            'y_origin': yorig,
            'y_reference': yref,  # Literally always 127, pg248
        }
        return result

    def _fetch_preamble(self):
        '''Run :WAV:PRE" to get the current channel's settings'''
        preamble_s = self._cmd(':WAV:PRE?', DS4024_SCPI.RET_LINE)
        return self._parse_preamble(preamble_s)

    def _fetch_settings(self, prefix: str, settings: list):
        '''Runs a bunch of :foo:bar? queries into a dictionary

        This is used to collect lots of state in one go, for channels,
        triggers, etc.

        prefix: the first portion of the query
        settings: a list of the commands to run

        These two items are appended to each other, with the raw query
        results being stored in a dictionary that matches each entry
        in settings to its reply value.
        '''
        result = {}
        for s in settings:
            result[s] = self._cmd(f':{prefix}:{s}?', DS4024_SCPI.RET_LINE)
        return result

    def _fetch_channel_settings(self, channel: str):
        if channel == "MATH":
            return self._fetch_calc_settings()

        if channel == "FFT":
            raise Exception("FFT Settings capture not yet implemented")

        settings = ["BVOL", "BWL", "COUP", "DISP", "IMP", "INV",
                    "OFFS", "PEND", "PROB", "SCAL", "TCAL", "TYPE",
                    "UNIT", "VERN"]

        return self._fetch_settings(channel, settings)

    def _fetch_trigger_settings(self):
        settings = ['STAT', 'COUP', 'HOLD', 'MODE', 'STAT', 'STAT', 'SWE', 'NREJ']

        subfam_settings = {
            'CAN':  ['BAUD', 'BUS', 'FTYP', 'LEV', 'SOUR', 'SPO', 'STYP', 'WHEN'],
            'EDGE':  ['LEV', 'SLOP', 'SOUR'],
            'IIC':  ['ADDR', 'AWID', 'CLEV', 'DATA', 'DIR', 'DLEV', 'SCL', 'SDA', 'WHEN'],
            'PATT': ['LEV', 'PATT', 'SOUR'],
            'PULS': ['LEV', 'LWID', 'SOUR', 'UWID', 'WHEN'],
            'RUNT': ['ALEV', 'BLEV', 'POL', 'SOUR', 'WHEN', 'WLOW', 'WUPP'],
            'NEDG': ['EDGE', 'IDLE', 'LEV', 'SLOP', 'SOUR'],
            'RS232': ['BAUD', 'BUS', 'DATA', 'LEV', 'PAR', 'SOUR', 'STOP', 'WHEN', 'WIDT'],
            'SLOP': ['ALEV', 'BLEV', 'SOUR', 'TLOW', 'TUPP', 'WHEN', 'WIND'],
            'SPI':  ['CLEV', 'CS', 'DATA', 'DLEV', 'MODE', 'SCL',
                     'SDA', 'SLEV', 'SLOP', 'TIM', 'WHEN', 'WIDT'],
            'USB':  ['DMIN', 'DPL', 'MLEV', 'PLEV', 'SPE', 'WHEN'],
            'VID':  ['LEV', 'LINE', 'MODE', 'POL', 'SOUR', 'STAN'],
            'FLEX': ['BAUD', 'LEV', 'SOUR', 'WHEN'],
        }

        top_level = self._fetch_settings("TRIG", settings)
        subfam = top_level["MODE"]
        if subfam not in ["EDGE",]:
            warnings.warn(f"Capturing state of trigger mode {subfam} is untested")
        sublevel = self._fetch_settings(f"TRIG:{subfam}", subfam_settings[subfam])
        top_level[subfam] = sublevel
        return top_level

    def _fetch_calc_settings(self):
        settings = ['MODE']
        subfam_settings = {
            'ADV': {'EXPR', 'INV', 'VAR1', 'VAR2', 'VOFF', 'VSC'},
            'ADD': {'INV', 'SA', 'SB', 'VOFF', 'VSC'},
            'DIV': {'INV', 'SA', 'SB', 'VOFF', 'VSC'},
            'FFT': {'HCEN', 'HOFF', 'HSC', 'HSP', 'SOUR', 'SPL', 'VOFF', 'VSC', 'VSM', 'WIND'},
            'LOG': {'ATHR', 'BTHR', 'INV', 'OPER', 'SA', 'SB', 'VOFF', 'VSC'},
            'MULT': {'INV', 'SA', 'SB', 'VOFF', 'VSC'},
            'SUB': {'INV', 'SA', 'SB', 'VOFF', 'VSC'}
        }
        top_level = self._fetch_settings("CALC", settings)
        subfam = top_level["MODE"]
        if subfam not in ["SUB",]:
            warnings.warn(f"Capturing state of calc mode {subfam} is untested")
        sublevel = self._fetch_settings(f"CALC:{subfam}", subfam_settings[subfam])
        top_level[subfam] = sublevel
        return top_level

    def _set_channel(self, channel_name):
        return self._cmd(f':WAV:SOUR {channel_name}', DS4024_SCPI.RET_NONE)

    def _get_channel(self):
        return self._cmd(":WAV:SOUR?", DS4024_SCPI.RET_LINE)

    def _set_points(self, n):
        return self._cmd(f':WAV:POIN {n}', )

    def fetch_waveform(self, channel="CHAN1", trigger_settings=None):
        '''Fetch a single waveform, with optional pre-captured trigger settings

        This returns a Waveform object.  That said, you probably want
        to use fetch_waveforms() to get multiple channels all in one
        go.

        The trigger_settings here does not set the trigger: it's just
        a way to avoid having to run 5 different trigger settings
        captures when pulling in all the channels at once.  Doing
        those repeated trigger settings fetches burns through a bit of
        time with the generally slow pace we take with the scope's
        control link.

        '''
        self._set_channel(channel)
        preamble = self._fetch_preamble()

        if preamble["mode"] != 0:
            warnings.warn(f"Preamble mode {mode} unsupported")

        buf = self._cmd(':WAV:DATA?', DS4024_SCPI.RET_WAVEFORM)

        cset = self._fetch_channel_settings(channel)
        idn = self._idn()

        if trigger_settings is None:
            trigger_settings = self._fetch_trigger_settings()

        return Waveform(preamble, buf, cset, idn, trigger_settings)

    def fetch_display(self):
        '''(Broken in firmware?) Fetch a bitmap of the screen

        Don't use this: the scope gives you a 3 channel grayscale
        bitmap, which seems broken.
        '''
        self.instrument.timeout = 30
        buf = self.instrument.ask_raw(b':DISP:DATA?', 11)
        print(f'>> {buf}')
        # Parse the TMC header
        if buf[0] != ord('#'):
            raise ValueError(f"Wrong magic: got {buf[0]}")

        # Get the length of the length field (sheesh)
        n = buf[0] - ord('0')
        bodylen_b = buf[2:]
        print(f'>> {bodylen_b}')
        bodylen_s = bodylen_b.decode('iso8859-1') # ISO8859-1 always decodes.
        print(f'>> {bodylen_s}')
        bodylen = int(bodylen_s)
        body = self.instrument.read_raw(bodylen+1) # gotta get that newline
        return body[:-1]

    def fetch_waveforms(self, channels):
        '''Collect a Waveform for every channel in the given list

        channels: list of oscilloscope channel names ("CHAN1", "CHAN4", "MATH")

        This returns a dictionary with the channel names as keys and
        Waveform objects as the values.
        '''
        results = {}
        trigger_settings = self._fetch_trigger_settings()

        for c in channels:
            wf_c = self.fetch_waveform(c, trigger_settings=trigger_settings)
            results[c] = wf_c
        return results

    def start(self):
        return self._cmd(":WAV:STAR", DS4024_SCPI.RET_LINE)
