import base64
import json

import numpy as np

class Waveform:
    '''Container for a captured waveform with relevant configuration data

    The Waveform class contains all the data gathered from a single
    retrieval from the oscilloscope.  This is generally a single
    triggering (or of multiple triggerings, if you like to live an
    exciting life and don't set the scope to single capture mode
    before triggering).

    This can be written to disk as JSON, then restored from there in
    the future.  All the metadata collected will be included.


    Note that we don't capture the trigger settings when the trigger
    goes off, but at the time of retrieval.  So, if those settings are
    tweaked between the actual waveform capture on the scope and its
    retrieval via the library, the *new* settings will show up in this
    object, not the settings at the time of the capture.  There is no
    way to force those together in the existing firmwares,
    unfortunately.

    This class contains a revision number (`version`) in all its
    forms.  Currently, only version 1 is used.

    '''
    def __init__(self, preamble: dict, rawbuf: bytes, channel_settings: dict, idn_line: str, trigger_settings: dict, version=1):
        '''Create a Waveform from all the pieces

        Please note that you are not intended to use this initializer
        from outside of caprini code.  There's a lot of cruft in this
        class, and it's hard to keep it all together.

        Parameters:

        preamble: the dictionary form of the preamble (p2-243 of guide)
        rawbuf: the raw buffer of data for this channel's data
        channel_settings: The channel settings (volts per division etc)
        idn_line: The `*IDN` identifier of the scope, for traceability
        trigger_settings: The trigger settings in use at time of retrieval


        Most of the values above are directly tied to what's on-screen
        at the moment of retrieval.  The one exception is the trigger
        settings.  See the note on trigger settings in the class-level
        documentation for more on possible pitfalls there.  (Super
        short version: this retrieves the current trigger settings,
        not necessarily those settings that led to the waveform we
        retrieve.)

        '''
        self.version = version  # revision of the dictionary contents
        self.preamble = preamble
        self.rawbuf = rawbuf  # Hang on to this for serdes
        self.channel_settings = channel_settings
        self.idn_line = idn_line
        self.trigger_settings = trigger_settings

        if self.preamble["format"] != 0:
            raise ValueError(f"Unhandled buffer format in {preamble}")
        dtype = "B"
        # Ignore the header and trailing newline
        self.readings = np.frombuffer(rawbuf[11:-1], dtype=dtype)

        dx = self.preamble["x_step"]
        x0 = self.preamble["x_origin"]

        dy = self.preamble["y_step"]
        y0 = self.preamble["y_origin"] - self.preamble["y_reference"]

        self.Fs = 1.0/dx
        self.t = x0 + dx*np.arange(len(self.readings))
        self.y = (y0 + self.readings) * dy

    def _json_dict(self):
        '''Convert to a dictionary for JSON serialization

        Note that this is internal, but is also used by other caprini
        classes when bundling up a full scope state in a
        WaveformBundle.
        '''
        result = {
            "version": self.version,
            "idn_line": self.idn_line,
            "channel_settings": self.channel_settings,
            "trigger_settings": self.trigger_settings,
            "preamble": self.preamble,
            "buf_b64": base64.b64encode(self.rawbuf).decode('iso8859-1')
        }
        return result

    def to_jsons(self):
        '''Internal: Serialize a waveform to a string

        This is analogous to json.dumps(), with some custom handling of binary
        blobs.
        '''
        return json.dumps(self._json_dict())

    @classmethod
    def _from_json_dict(cls, d: dict):
        '''Internal: Reconstitute a JSON dictionary into a Waveform
        '''
        rawbuf = base64.b64decode(d["buf_b64"])

        # Make a copy to tweak around:
        dp = d.copy()
        del(dp['buf_b64'])
        dp['rawbuf'] = rawbuf

        return cls(**dp)

    @classmethod
    def from_jsons(cls, s):
        '''Deserialize a Waveform from a JSON dump in the string s

        This is directly analogous to json.loads(), as you can see below.
        '''
        d = json.loads(s)
        return cls._from_json_dict(d)

    def to_json(self, fh):
        '''Serialize a Waveform to a JSON dump in the file handle fh

        This is directly analogous to json.dump()
        '''
        fh.write(self.to_jsons())

    @classmethod
    def from_json(cls, fh):
        '''Deserialize a Waveform from a JSON dump in the file handle fh

        This is directly analogous to json.load(), but possibly slower.
        '''
        return cls.from_jsons(fh.read())



class WaveformBundle:
    '''A full dump of scope data, along with semantics of the capture

    This wraps up a list of Waveform objects, along with a mapping of
    names for each channel and a title for the capture overall.
    Basically, this is everything you need to turn a scope display
    into a reasonable-ish engineer's plot in a notebook.

    In particular, if you're running experiments, this is the best way
    to capture a bunch of data.  As an example, let's say that you're
    testing an audio setup, and troubleshooting some weirdness in the
    left/right fade setting.  You might do something like the
    following to capture data in a series of experiments:

    title: "Audio fader set 50/50 left/right"
    channel_names: { "CHAN1": "input left", "CHAN2": "output left", ... }
    waveforms: { "CHAN1": Waveform, "CHAN2": Waveform, ... }

    You'd then retrieve your data from the oscilloscope as:

    bundle_midpt = WaveformBundle.collect("50/50 left/right", channel_names)

    You could then tweak the knob to be full left, trigger the scope
    however is needed, and then collect a new bundle of data with

    bundle_left = WaveformBundle.collect("100/0 left/right", channel_names)

    This allows you to re-use most of the settings when you capture
    other configurations of the same setup.

    This data can be written out to a JSON string with `.to_jsons()`
    or dumped to a file with `.to_json(fh)`, just like python's
    built-in `json` library.

    '''
    def __init__(self, title: str, channel_names: dict, waveforms: dict, version=1):
        '''Create a WaveformBundle the hard way

        You probably want to use WaveformBundle.collect() or
        WaveformBundle.from_json() instead of this.

        title: the title of this experimental setup/capture
        channel_names: a dictionary of the form scope channel => human name
        waveforms: A dcitionary of the form scope channel => Waveform
        '''
        self.version = version
        self.channel_names = channel_names
        self.waveforms = waveforms
        self.title = title
        
    @classmethod
    def collect(cls, title: str , channel_names: dict, inst):
        '''Given a title and dictionary of channel names, collect the data for a WaveformBundle

        This is the main way to retrieve data from the oscilloscope.

        title: the name for the experiment/setup
        channel_names: a dictionary of the form scope channel => human name
        inst: the actual instrument handle to capture from (instance of DS4024_SCPI)

        This will return a WaveformBundle which encapsulates the state
        of the oscilloscope at the time of retrieval.

        inst = DS4024_SCPI("192.168.0.220")
        channel_names = { "CHAN1": "left in", "CHAN3": "right in", "CHAN 2": "left out" }
        
        # Human fiddles with circuit, sets scope triggers, and then
        # does a single shot.  Once the scope has captured:

        wfb_midpt = WaveformBundle.collect("Fader at midpt", channel_names)
        with open("midpt_capture.json", "w") as f_midpt:
          wfb_midpt.to_json(f_midpt) # Save for posterity


        # Human sets fader knob to full left, then resets for a new
        # single shot capture, possibly with new capture settings

        wfb_left = WaveformBundle.collect("Fader full left", channel_names)
        with open("left_capture.json", "w") as f_left:
          wfb_midpt.to_json(f_left) # Save for posterity


        You can then work with the data captured by using the scope's
        channel names:

        plot(wfb_midpt.waveforms["CHAN1"].t,
             wfb_midpt.waveforms["CHAN1"].y,
             label="midpt: " + wfb.midpt.channel_names["CHAN1"])

        (The example notebooks contain some examples of plotting these
        captures which are less tedious to use than the above.)

        '''
        waveforms = inst.fetch_waveforms(list(channel_names.keys()))
        return cls(title, channel_names, waveforms)

    def _json_dict(self):
        '''Convert to a dictionary for JSON serialization

        Note that this is internal, but is also used by other caprini
        classes when bundling up a full scope state in a
        WaveformBundle.
        '''
        
        d = {
            'version': self.version,
            'title': self.title,
            'channel_names': self.channel_names
        }
        d['waveforms'] = dict([(k,v._json_dict()) for k,v in self.waveforms.items()])
        return d
        
    def to_jsons(self):
        '''Serialize a waveform to a string
        
        This is analogous to json.dumps(), with some custom handling of binary
        blobs.
        '''
        return json.dumps(self._json_dict())
    
    @classmethod
    def _from_json_dict(cls, d):
        '''Internal: Reconstitute a JSON dictionary into a WaveformBundle

        Note that this also reconstitutes the Waveform objects within
        the bundle.
        '''
        dp = d.copy()
        for name, d_wf in dp["waveforms"].items():
            dp["waveforms"][name] = Waveform._from_json_dict(d_wf)
        return cls(**dp)

    @classmethod
    def from_jsons(cls, s):
        '''Deserialize a WaveformBundle from a JSON dump in the string s
        
        This is directly analogous to json.loads(), as you can see below.
        '''
        d = json.loads(s)
        return cls._from_json_dict(d)
        
    def to_json(self, fh):
        '''Serialize a WaveformBundle to a JSON dump in the file handle fh
        
        This is directly analogous to json.dump()
        '''
        fh.write(self.to_jsons())
        
    @classmethod
    def from_json(cls, fh):
        '''Deserialize a WaveformBundle from a JSON dump in the file handle fh
        
        This is directly analogous to json.load(), but possibly slower.
        '''
        return cls.from_jsons(fh.read())
