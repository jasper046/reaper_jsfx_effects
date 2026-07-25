# reaper_js_effects

Custom [JSFX](https://www.reaper.fm/sdk/js/js.php) plugins for REAPER, focused on
mastering: analysis, limiting, and spectral processing. Each effect lives in its
own directory as a `.jsfx` file; drop a directory into your REAPER `Effects`
folder (or point REAPER at this repo) to use it.

| Effect | Type | Summary |
|---|---|---|
| [Spectral Dynamics Analyzer](#spectral-dynamics-analyzer) | Analysis | Mid/side spectral dynamics over time |
| [Hyrax Limiter](#hyrax-limiter) | Dynamics | Smooth brickwall limiter, ported from Matchering |
| [Tonal/Noise Splitter](#tonalnoise-splitter) | Spectral / routing | Splits a mix into a tonal stream and a noise & transients stream |
| [Delay Isolator](#delay-isolator) | Spectral / restoration | Ducks a wet signal's spectrum wherever a paired dry signal is present, isolating a delay/effects return |

The [`tools/`](#tools) directory holds a Python simulator for developing and
validating FFT-based JSFX effects offline.

---

## Spectral Dynamics Analyzer

A mid/side spectral dynamics analyzer for mastering. Rather than showing you an instantaneous spectrum, it tracks how the energy at each frequency behaves over time — revealing the spectral character and dynamic range of a mix in a way that a standard spectrum analyzer cannot.

### What it shows

The display is split into two panels: **MID** on top and **SIDE** on the bottom. Each panel shows three lines:

- **Peak** — the highest level reached at each frequency band, decaying slowly downward
- **Avg** — a long-term exponential moving average, showing the sustained spectral balance
- **Min** — the lowest the average has reached, decaying slowly back upward

The gap between peak and min is the spectral dynamic range: wide gaps mean the mix breathes and has transient life in that region; narrow gaps mean it is compressed or consistently dense.

### Controls

All settings are in the **Settings** menu. There are no sliders.

| Setting | Description |
|---|---|
| Time Constant | How slowly peak and min decay (3s – 60s). 20s is a good starting point for a full mix. |
| Tilt | Spectral tilt applied to the display, pivoting around 1kHz. 3 dB/oct compensates for the natural pink-noise slope of most music. |
| Ceiling / Floor | Display range in dB. |

**Snapshot** — freezes the current peak/avg/min as a reference overlay (shown in orange). Useful for comparing two mixes or two stages of a mastering chain.

**Clr Ref** — removes the reference overlay.

**Reset** — clears the live envelopes and starts fresh from the next incoming audio.

### How to use it for mastering

Insert the plugin on your master bus and let it run for at least one full pass through the track before drawing conclusions. The 20-second time constant means the curves settle into a representative picture of the mix over time rather than reacting to individual transients.

Things to look for:

- **Spectral balance of the avg line** — does it follow a sensible curve, or are there frequency regions that stick out or dip?
- **Peak-to-min spread** — is it consistent across the spectrum, or are some bands much more compressed than others?
- **Mid vs side balance** — is the side channel energy appropriately low at the low end? Is the high-frequency air present in the side?

Use Snapshot to capture a reference mix and then compare your work against it band by band.

### Technical details

- Fixed 4096-point FFT with a Blackman-Harris window (~93ms frame at 44.1kHz)
- 1/9-octave log-frequency binning (~90 bands across 10 Hz – 22 kHz)
- 3-band moving average spectral smoothing applied after binning
- Single time constant drives all three envelopes: peak decays down, avg is an EMA, min tracks the minimum of avg and decays back up
- Settings and reference snapshots persist with the REAPER project via `@serialize`

---

## Hyrax Limiter

A real-time brickwall limiter modeled on the offline "Hyrax" limiter from
**[Matchering](https://github.com/sergree/matchering)** by Sergey Grishakov
(sergree), which produces unusually smooth, natural-sounding limiting on masters.
Huge thanks to sergree for that wonderful work — the whole reason this limiter
exists is that Matchering's sounded better than anything else we had, and we
wanted it live in REAPER. The original is a non-causal, whole-file algorithm;
this is a causal look-ahead approximation of its structure suitable for a live
insert, with the host compensating for the look-ahead latency.

### Controls

| Slider | Description |
|---|---|
| Threshold (dB) | Level above which limiting begins. |
| Ceiling (dB) | Output ceiling; the signal is normalized so the threshold maps here. |
| Look Ahead (ms) | Delay applied to the audio path so gain reduction ramps in before transients. Matchering's attack window is 1 ms; higher values give smoother, more transparent limiting. Reported to the host for latency compensation. |
| Release (ms) | Release time. Unlike a single-pole release, this shapes the recovery through a hold stage and two cascaded one-pole low-pass sections, giving a gradual, natural release. |
| Stereo Link (%) | 100% applies identical gain to both channels (as Matchering does). Lower values let each channel limit closer to its own peak. |
| True Peak Detection | When on, estimates inter-sample peaks in the detection sidechain to reduce overshoots. This is a linear-interpolation estimate, not a certified true-peak ceiling. |
| Target LUFS (short-term) | The loudness target for the SENSE loop (short-term, 3 s). |
| SENSE (auto threshold) | When on, slowly rides the Threshold to bring the output's short-term LUFS toward the target. When off, the Threshold is frozen at its current value and manually adjustable again. |

### LUFS metering and SENSE

The plugin measures its **output** loudness as short-term LUFS (BS.1770 K-weighting, a 3-second window) and displays it on the graphical panel. With **SENSE** enabled, a slow, damped feedback loop rides the Threshold slider so the output loudness approaches the Target LUFS — lowering the threshold increases limiting and makeup gain, raising loudness, and vice versa. The loop is intentionally gentle (it takes several seconds to settle) to stay stable against the 3-second measurement window and avoid pumping. Turning SENSE off leaves the threshold wherever the loop left it, handing manual control back to you. The Ceiling is never touched by SENSE, so your true-peak headroom stays put. To read the input loudness, set the Threshold to 0 dB (no limiting) — the output reading then equals the input.

### Interface

The graphical panel shows a horizontal **gain-reduction meter** (full scale −6 dB, since a mastering-grade limiter rarely needs to pull more than ~3 dB), the **output short-term LUFS** as a large number with the target beneath it, and clickable **TRUE PEAK** and **SENSE** buttons (these mirror their sliders, so host automation and preset recall still work).

### How it works

The gain envelope is computed in Matchering's "flipped" reduction domain (`1 - gain`, where larger means more reduction) and combines three stages, keeping the most reduction at each sample:

- **Hard-clip** — the instantaneous reduction needed to bring the windowed peak to threshold.
- **Attack** — a one-pole smoothing of the hard-clip reduction, fed by the look-ahead delay so the ramp lands before the transient (a causal stand-in for Matchering's zero-phase `filtfilt`).
- **Release** — a hold stage followed by two cascaded one-pole low-passes, with cutoffs derived from Matchering's Butterworth constants (7 Hz hold, `800 / release_ms` Hz release).

Peak detection uses a sliding maximum over the look-ahead window. The audio path itself is never oversampled, matching Matchering's clean sample-domain gain stage.

### Fidelity notes

This is an approximation, not a bit-exact port. Matchering's attack is zero-phase (it looks both forward and backward in time), which a causal plugin cannot reproduce; the look-ahead delay approximates it. For bit-exact Matchering output, run audio through Matchering offline. The true-peak option underestimates real inter-sample peaks and should not be relied on for a hard true-peak delivery spec.

---

## Tonal/Noise Splitter

Splits a stereo signal into two streams — a **tonal** stream (harmonic, pitched,
sustained content) and a **noise & transients** stream (percussive, transient,
broadband content) — so you can process each independently with any tools you
like, then recombine. It is the audio equivalent of a mid/side split, but along
the harmonic-vs-percussive axis instead of the stereo axis.

Onsets and transients land in the noise & transients stream because the harmonic
estimate is a *trailing* time median: at an onset the median lags the sudden
energy spike, so the tonal stream only reclaims the pitched content once it has
been stable across roughly half the window. This is useful — you can tame
harshness on the noise & transients stream without dulling the clarity of the
attacks — and the **Transient Hold** control shapes how long each onset lingers
there.

### Routing

The plugin has two inputs and four outputs:

```
in:  L, R
out: 1/2 = tonal L/R
     3/4 = noise & transients L/R
```

Put the splitter on a 4-channel track, then process channels 1–2 (tonal) and 3–4
(noise & transients) however you want — EQ the tonal part with one curve and the
noise & transients part with another, compress only the noise, brighten only the
tonal, and so on.

To recombine, use REAPER's stock **Channel Mapper – Downmixer** (or any summing
utility) to fold the four channels back to stereo. Because the noise & transients
stream is formed as `latency-matched input − tonal`, summing all four outputs at
unity reconstructs the original signal **exactly** (a perfect null), so the split
is lossless when you are not processing anything.

### Controls

| Slider | Description |
|---|---|
| Split Character | Biases the balance between the two streams. 8 is neutral; lower sends more energy to the noise & transients stream, higher sends more to the tonal stream. |
| Mask Sharpness | How hard the decision is between tonal and noise per frequency bin. Higher values separate more aggressively; lower values keep the split softer. |
| Transient Hold | Length of the trailing time-median window, short → long. Higher holds each onset in the noise & transients stream longer before the tonal stream reclaims it; lower lets onsets rejoin the tonal stream sooner. The midpoint (9) matches the classic behaviour. |
| Noise Floor (dB) | Absolute magnitude baseline below which a bin is faded fully into the noise & transients stream, keeping low-level hiss out of the tonal part. Calibrated to a full-scale reference; −120 dB is off. The fade is smooth, and reconstruction stays exact. |

### How it works

This is a real-time implementation of median-filtering **Harmonic-Percussive
Source Separation** (HPSS). On a spectrogram, harmonic energy forms horizontal
ridges (stable in frequency, extended in time) while percussive/noise energy
forms vertical ridges (broadband, brief). The plugin:

1. Runs a short-time FFT (4096-point, 4× overlap, Hann window).
2. Estimates the harmonic part with a **median across the last N frames** (per bin), where N is set by Transient Hold (5–33 frames).
3. Estimates the percussive part with a **median across frequency** (per frame).
4. Builds a soft Wiener-style mask from the ratio of the two, applies Noise Floor to fade sub-threshold bins toward the noise & transients stream, and applies the result to get the tonal spectrum.
5. Resynthesizes the tonal stream by inverse FFT and overlap-add, and forms the noise & transients stream by subtracting it from a latency-matched copy of the input.

Detection is stereo-linked (both channels share one mask from `max(|L|,|R|)`), so
the stereo image stays stable. One FFT frame of latency (4096 samples) is reported
to the host for compensation.

### A note on verification

The separation algorithm was developed and validated offline with the simulator
in [`tools/`](#tools) — it reconstructs to better than −300 dB and passes the
impulse test. When loading a new build in REAPER, the quickest sanity check is
to sum the four outputs back to stereo and confirm a clean null against the dry
signal (with plugin delay compensation on).

---

## Delay Isolator

Recovers a delay/effects return from an old mix as a separate track, so it can
be blended in under a freshly remixed dry vocal. Given the **dry** vocal and the
**wet** (dry + delay effects) vocal from the old mix, it ducks the wet signal's
spectrum wherever the dry signal currently has energy, leaving mostly what the
dry signal didn't already account for — the delay tails, swells, and movement
that were printed into the old wet track.

This is deliberately **not** deconvolution. An adaptive filter that tries to
learn a fixed dry→wet mapping only works if that mapping is linear and
time-invariant; a heavily automated delay send (feedback swells, panning,
pitch-shifting, filter sweeps) is neither, so no fixed filter converges well on
it — in testing, an NLMS adaptive-filter approach left obvious artifacts and
ate into the delay tail. Per-frame spectral ducking has no convergence to fail:
every frame is ducked independently against the current dry level in that
band, so it tracks arbitrarily automated sends without trying to model them.

The separation is intentionally imprecise — the goal is to get the delay layer
"out of the way" of the new dry mix, not a perfect null. Expect to still ride
the isolated track's volume by hand or cut sections that clash.

### Routing

The plugin has four inputs and four outputs:

```
in:  1/2 = dry L/R
     3/4 = wet L/R
out: 1/2 = isolated delay/effects L/R  ( = wet, ducked wherever dry is present )
     3/4 = removed L/R                ( = wet - isolated, i.e. what the duck
                                          took out. isolated + removed = wet
                                          exactly, so it's useful for
                                          auditioning how much the duck is
                                          pulling out at the current settings. )
```

Route the old dry and wet vocal stems into a 4-channel track (e.g. with
REAPER's Channel Mapper — Upmixer, or by routing both source tracks to a bus
with the appropriate channel offsets) feeding this plugin. The plugin declares
4 out_pins (not 2) even though only channels 1/2 are the useful output in
normal use — with fewer out_pins than in_pins, REAPER's JSFX host did not
route the second output channel to the track correctly.

### Controls

| Slider | Description |
|---|---|
| Duck Amount (dB) | How aggressively wet is attenuated in bins where dry is present. Higher pulls the direct-sound bleed down harder, at the cost of also thinning the delay tail where it overlaps with new dry energy. |
| Mask Floor (dB) | Minimum attenuation applied to any bin, so the ducked signal never hits a hard, un-natural null — some delay texture always survives even where dry is momentarily very loud. |
| Learn Rate (slow↔fast) | How quickly the per-band level-match gain curve adapts. Slower is more stable against a single loud phrase skewing the curve; faster tracks a drifting mix balance more closely. |
| Hold Level Match | Freezes the level-match curve. Use it to stop adaptation during a passage that's throwing the curve off (e.g. an unusually loud or heavily processed line), then release it once past that section. |
| Dry Active Threshold (dB) | Absolute level below which the dry signal is treated as silent — the level-match curve stops updating below this, and (with dry at true silence) the mask relaxes toward passthrough, letting the exposed delay tail ring through unducked. |

### How it works

1. Runs a short-time FFT (2048-point, 4× overlap, Hann window) on both the dry
   and wet inputs.
2. Maintains a per-frequency-band **level-match gain curve**, learned online as
   a running average of wet ÷ dry magnitude over frames where dry is active.
   This corrects for the EQ/compression that typically sits between a dry
   vocal and its delay send — without it, a single broadband gain assumption
   leaves the duck aggressiveness wildly inconsistent across the spectrum (and,
   in testing, across different takes of the same vocal).
3. Builds a soft Wiener-style mask per bin from wet power vs. level-matched dry
   power, scaled by Duck Amount and clamped to Mask Floor.
4. Splits the wet spectrum into `wet * mask` (isolated) and `wet * (1 - mask)`
   (removed), magnitude only, preserving wet's own phase in both, and
   resynthesizes each by inverse FFT and overlap-add.

Detection and masking are stereo-linked (both channels share one mask from
`max(|L|,|R|)`), so the stereo image of the isolated delay stays stable. One
FFT frame of latency is reported to the host for compensation.

### A note on verification

The framing was validated offline with
[`tools/jsfx_delay_isolator_sim.py`](#toolsjsfx_delay_isolator_simpy), which
reproduces the plugin's exact ring-buffer/overlap-add logic and passes the
impulse test (a wet impulse with dry silent reproduces exactly, since with no
dry energy the mask is passthrough) and a reconstruction check (isolated +
removed nulls against wet to better than −300 dB). The ducking behavior itself
was tuned against real dry/wet vocal stems (checked in under
[`media/`](#media)) before porting to JSFX — see that script's `--dry`/`--wet`
mode to reproduce:

```
python tools/jsfx_delay_isolator_sim.py \
  --dry media/vocal_a_dry.wav --wet media/vocal_a_wet.wav \
  --out /tmp/isolated.wav --removed-out /tmp/removed.wav
```

---

## Tools

### `tools/jsfx_stft_sim.py`

A Python simulator for developing FFT-based JSFX effects (STFT → modify spectrum
→ inverse FFT → overlap-add). REAPER's JSFX cannot run headless, so the usual way
to debug an FFT effect is to reload REAPER and listen — slow, and framing bugs
(wrong latency, off-by-a-frame overlap-add, ring-index arithmetic errors) are
easy to miss by ear.

This tool reproduces the exact per-sample ring-buffer and overlap-add logic a
JSFX plugin uses, so the **framing** can be validated offline. The FFT itself
uses numpy; what the tool validates is the code around it — the window, the COLA
normalization, the ring indices, the overlap-add write position, and the reported
latency.

**The impulse test is the key check.** Feed a single Dirac impulse: a correct
effect emits a single clean impulse delayed by exactly the reported latency, with
zero energy elsewhere. This reveals both the true latency and any reconstruction
error at a glance — far more reliable than an RMS-over-music residual, which
conflates warm-up and flush-tail error with real bugs.

```
# self-test the framing with an impulse
python tools/jsfx_stft_sim.py --impulse

# run the tonal/noise split on a file and write tonal/noise/sum stems
python tools/jsfx_stft_sim.py --wav mix.wav --out-prefix /tmp/split

# passthrough (mask = 1) framing test: tonal should equal the input, noise ~ 0
python tools/jsfx_stft_sim.py --wav mix.wav --flat
```

Requires `numpy` (and `soundfile` for the `--wav` modes).

### `tools/jsfx_delay_isolator_sim.py`

The same simulator approach applied to the [Delay Isolator](#delay-isolator).
Since this effect takes two inputs (dry, wet) rather than one, its impulse test
holds dry silent and feeds wet a single impulse — with no dry energy the duck
mask is forced to passthrough, so a correct effect still reproduces the
impulse exactly at the reported latency.

```
# self-test the framing with an impulse
python tools/jsfx_delay_isolator_sim.py --impulse

# run the ducking on a real dry/wet pair and write the isolated result
python tools/jsfx_delay_isolator_sim.py --dry dry.wav --wet wet.wav --out isolated.wav
```

### `media/`

Short dry/wet vocal excerpts used to develop and validate the Delay Isolator
against real material (see [its verification note](#a-note-on-verification)).
`vocal_a`/`vocal_b` are two different takes, each with a `_dry` (no delay
effects) and `_wet` (delay effects printed in, from an old mix) version.

Framing lessons baked into the tool and the Tonal/Noise Splitter:

- Apply the Hann window on **both** analysis and synthesis, then divide by the
  COLA overlap sum (1.5 for Hann² at 4× overlap).
- Take the analysis frame from the window **ending** at the current write
  position, overlap-add the resynthesized frame **forward** from there, and read
  output one frame behind the write pointer. Report `pdc_delay = FFT_SIZE`.
- Use a **trailing** median (last N frames), not a centered one — centered
  look-ahead adds a delay offset that is easy to double-count and produces a
  comb/echo artifact.
- Never do absolute-time arithmetic on ring-buffer indices; keep everything
  ring-relative with a fixed offset from the current pointer.

---

## Credits

- **Hyrax Limiter** is a port of the limiter from
  [Matchering](https://github.com/sergree/matchering) by sergree — see that
  project for the original (and excellent) offline mastering algorithm.
- Several effects follow conventions and idioms from the JSFX community,
  including LOSER's dynamics plugins and Geraint Luff's spectral effects.

## License

See [LICENSE](LICENSE).
