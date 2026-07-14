# reaper_js_effects

Custom [JSFX](https://www.reaper.fm/sdk/js/js.php) plugins for REAPER, focused on
mastering: analysis, limiting, and spectral processing. Each effect lives in its
own directory as a `.jsfx` file; drop a directory into your REAPER `Effects`
folder (or point REAPER at this repo) to use it.

| Effect | Type | Summary |
|---|---|---|
| [Spectral Dynamics Analyzer](#spectral-dynamics-analyzer) | Analysis | Mid/side spectral dynamics over time |
| [Hyrax Limiter](#hyrax-limiter) | Dynamics | Smooth brickwall limiter, ported from Matchering |
| [Tonal/Noise Splitter](#tonalnoise-splitter) | Spectral / routing | Splits a mix into harmonic and percussive/noise streams |

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
sustained content) and a **noise** stream (percussive, transient, broadband
content) — so you can process each independently with any tools you like, then
recombine. It is the audio equivalent of a mid/side split, but along the
harmonic-vs-percussive axis instead of the stereo axis.

### Routing

The plugin has two inputs and four outputs:

```
in:  L, R
out: 1/2 = tonal L/R
     3/4 = noise L/R
```

Put the splitter on a 4-channel track, then process channels 1–2 (tonal) and 3–4
(noise) however you want — EQ the tonal part with one curve and the noise part
with another, compress only the noise, brighten only the tonal, and so on.

To recombine, use REAPER's stock **Channel Mapper – Downmixer** (or any summing
utility) to fold the four channels back to stereo. Because the noise stream is
formed as `latency-matched input − tonal`, summing all four outputs at unity
reconstructs the original signal **exactly** (a perfect null), so the split is
lossless when you are not processing anything.

### Controls

| Slider | Description |
|---|---|
| Split Character | Biases the balance between the two streams. 8 is neutral; lower sends more energy to the noise stream, higher sends more to the tonal stream. |
| Mask Sharpness | How hard the decision is between tonal and noise per frequency bin. Higher values separate more aggressively; lower values keep the split softer. |

### How it works

This is a real-time implementation of median-filtering **Harmonic-Percussive
Source Separation** (HPSS). On a spectrogram, harmonic energy forms horizontal
ridges (stable in frequency, extended in time) while percussive/noise energy
forms vertical ridges (broadband, brief). The plugin:

1. Runs a short-time FFT (4096-point, 4× overlap, Hann window).
2. Estimates the harmonic part with a **median across the last 17 frames** (per bin).
3. Estimates the percussive part with a **median across frequency** (per frame).
4. Builds a soft Wiener-style mask from the ratio of the two and applies it to get the tonal spectrum.
5. Resynthesizes the tonal stream by inverse FFT and overlap-add, and forms the noise stream by subtracting it from a latency-matched copy of the input.

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
