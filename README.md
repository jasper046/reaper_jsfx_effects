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

- Fixed 8192-point FFT with a Blackman-Harris window
- 1/9-octave log-frequency binning (~90 bands across 10 Hz – 22 kHz)
- 3-band moving average spectral smoothing applied after binning
- Single time constant drives all three envelopes: peak decays down, avg is an EMA, min tracks the minimum of avg and decays back up
- Settings and reference snapshots persist with the REAPER project via `@serialize`
