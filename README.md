# Caprini

Caprini is a set of third-party tooling for downloading data off a
Rigol DS4000E oscilloscope on the local network.

(Caprini is also the scientific name for the "tribe" of animals
containing goats, sheep, ibex, and, of course, tahrs.)

Copyright (c) 2021-2022 Josh Myer <josh@joshisanerd.com>
License: CC0 v1.0

## How to use caprini

At the moment, caprini is intended to be used to transcribe data off
manual captures.  That is, you set the scope to single trigger, then
run a command to download the captured waveform.  This includes all
the raw data points the scope is displaying, as well as the
configuration of the channels.  This enables you to recreate the plots
in whatever style you wish, as well as to do analysis of the data.
The captured data is also able to be serialized out to disk (as JSON)
and then re-loaded for subsequent re-analysis.


## Examples

It is recommended to use caprini in a semi-interactive environment.
My preference is Jupyter notebooks, but other environments may suit
you better.  In any environment, the idea is to couple data capture
with a quick plot of that data.  This lets you ensure that settings
are as you expected with each waveform captured.  Nobody should fully
trust caprini for a while yet: trust, but verify!

Additionally, since caprini captures off a stopped oscilloscope, you
can run multiple captures of the same result if needed.  This is
particularly helpful if you have a setup that requires a lot of
handheld probing to get a result.  If the first capture isn't good
enough (say you want to zoom out on a high-amplitude waveform), you
can twiddle the knobs on the scope and re-run the caprini capture.

## A note on reliability

Both of my Rigol scopes' "raw" control channels (USB or port 5555)
will hang when given malformed (or sometimes even not-currently-valid)
queries.  The `vxi11` driver seems to make things much more reliable,
but it can still hang from time to time.  I would not advise using
this code as part of an unattended setup for that reason.


## Future work / Known limitations

In the future, it's easy to see caprini being used to set the scope up
for captures.  This functionality isn't currently needed, so it's not
included.

We currently support gathering data from the four input channels as
well as the `MATH` channel.  The FFT channel could also be supported
if needed (but it probably makes more sense to just do your own FFT?).

This scope captures at 4GSa/s (or 2GSa/s if you're using 1&2 or 3&4),
with up to 140M points of data: we only pull in the 1400 displayed
datapoints.  If you wanted to use it as a full-on analog frontend for
DAQ, it would need some extension, but could be supported.  Note that
your JSON files will get very large very quickly in this case (we save
raw binary as b64, so it's only an 8:5 expansion, but that's still
~300MB a capture at full depth).

On-scope measurements are not currently captured.

Capturing the actual scope display isn't working quite right (it seems
to give 3-channel RGB bitmaps of grayscale data).

Unit testing: what a concept!  We don't currently have any because
it's a big open set problem, and caprini is intended for applications
where a human immediately reviews all data captured with it.  If
someone wants to set up the mocking of `vxi11` and start chasing down
weird cases, I'd be happy to work with them on merging that in.

Support for more scopes: it seems likely that the DS1000Z and DS2000
series scopes are easy enough to support with this framework.  They
have meaningfully different command sets, so they will require their
own SCPI implementations, but it could be done without a huge amount
of hassle.  If you attempt to do this, please simply add your own
`DS2000_SCPI` class that's just a copypasta of the `DS4024_SCPI`
class.  Once we have three implementations, we can start to generalize
out the common bits of code (or if we radically rework the waveform
capture semantics).

## Adding more functionality

A lot of the interface definitions have been automagically extracted
from the PDF programming guide (Publication Number PGA21101-1110).
See the included notebook `ds4024_automagic_api_extraction.ipynb` for
how that extraction was done, and to see if you can use it to quickly
bootstrap the subsystem you're interested in capturing.

Of particular note: this library is very keen on data fidelity and
traceability.  Anything that gets parsed from the scope should also be
surfaced as raw data from the scope somehow.  This allows any user to
verify that the captured data accurately matches the scope's
interpretation of that data.  There is nothing worse than spending a
day chasing a problem with your design, only to find out that your
test equipment wasn't configured the way you thought it was.  By
parsing the data coming from the oscilloscop,e caprini basically
becomes a part of the test equipment itself.
