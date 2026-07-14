# reaper_js_effects

Custom JSFX plugins for REAPER, focused on mastering analysis.

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

A real-time brickwall limiter modeled on the offline "Hyrax" limiter from [Matchering](https://github.com/sergree/matchering), which produces unusually smooth, natural-sounding limiting on masters. The original is a non-causal, whole-file algorithm; this is a causal look-ahead approximation of its structure suitable for a live insert, with the host compensating for the look-ahead latency.

### Controls

| Slider | Description |
|---|---|
| Threshold (dB) | Level above which limiting begins. |
| Ceiling (dB) | Output ceiling; the signal is normalized so the threshold maps here. |
| Look Ahead (ms) | Delay applied to the audio path so gain reduction ramps in before transients. Matchering's attack window is 1 ms; higher values give smoother, more transparent limiting. Reported to the host for latency compensation. |
| Release (ms) | Release time. Unlike a single-pole release, this shapes the recovery through a hold stage and two cascaded one-pole low-pass sections, giving a gradual, natural release. |
| Stereo Link (%) | 100% applies identical gain to both channels (as Matchering does). Lower values let each channel limit closer to its own peak. |
| True Peak Detection | When on, estimates inter-sample peaks in the detection sidechain to reduce overshoots. This is a linear-interpolation estimate, not a certified true-peak ceiling. |

### How it works

The gain envelope is computed in Matchering's "flipped" reduction domain (`1 - gain`, where larger means more reduction) and combines three stages, keeping the most reduction at each sample:

- **Hard-clip** — the instantaneous reduction needed to bring the windowed peak to threshold.
- **Attack** — a one-pole smoothing of the hard-clip reduction, fed by the look-ahead delay so the ramp lands before the transient (a causal stand-in for Matchering's zero-phase `filtfilt`).
- **Release** — a hold stage followed by two cascaded one-pole low-passes, with cutoffs derived from Matchering's Butterworth constants (7 Hz hold, `800 / release_ms` Hz release).

Peak detection uses a sliding maximum over the look-ahead window. The audio path itself is never oversampled, matching Matchering's clean sample-domain gain stage.

### Fidelity notes

This is an approximation, not a bit-exact port. Matchering's attack is zero-phase (it looks both forward and backward in time), which a causal plugin cannot reproduce; the look-ahead delay approximates it. For bit-exact Matchering output, run audio through the Matchering app offline with the mix ratio at 0%. The true-peak option underestimates real inter-sample peaks and should not be relied on for a hard true-peak delivery spec.
