#!/usr/bin/env python3
"""
JSFX STFT / overlap-add simulator and framing validator.

REAPER's JSFX cannot be run headless, so debugging an FFT-based effect (STFT ->
modify spectrum -> inverse FFT -> overlap-add) means reloading REAPER and
listening. That is slow, and framing bugs (wrong latency, off-by-a-frame
overlap-add, ring-index arithmetic errors) are easy to miss by ear.

This tool reproduces the exact per-sample ring-buffer / overlap-add logic a JSFX
plugin uses, in Python, so the framing can be validated OFFLINE before loading
the plugin. The FFT itself uses numpy (assumed correct); what this validates is
YOUR code around it: the window, the COLA normalization, the ring indices, the
overlap-add write position, and the reported latency.

The most reliable check is the impulse test (`--impulse`): feed a single Dirac
impulse, and a correct effect emits a single clean impulse delayed by exactly the
reported latency, with zero energy elsewhere. This reveals both the true latency
and any reconstruction error in one glance — far better than an RMS-over-music
residual, which conflates warm-up / flush-tail error with real bugs.

Key framing facts (see the tonal_noise_splitter effect for a worked example):
  - Apply the Hann window on BOTH analysis and synthesis, divide by the COLA
    overlap sum (1.5 for Hann^2 at 4x overlap, HOP = FFT/4).
  - Take the analysis frame from the window ENDING at the current write position
    (bi = write_index - FFT), overlap-add the resynthesized frame FORWARD from bi,
    and read output at write_index - FFT. Report pdc_delay = FFT.
  - Use a TRAILING median (last N frames) for HPSS, not a centered one: centered
    look-ahead adds a delay offset that is easy to double-count and produces a
    comb/echo artifact.
  - NEVER do absolute-time arithmetic on ring indices; keep everything
    ring-relative with a fixed offset from the current pointer.

Usage:
  python jsfx_stft_sim.py --impulse
  python jsfx_stft_sim.py --wav input.wav --out-prefix /tmp/split
  python jsfx_stft_sim.py --wav input.wav --flat        # passthrough framing test
"""

import argparse
import numpy as np

try:
    import soundfile as sf
except ImportError:
    sf = None

# ---- fixed framing (must match the JSFX under test) ----
FFT_SIZE = 4096
HOP = 1024                        # 4x overlap
NBINS = FFT_SIZE // 2 + 1
COLA = 1.5                        # Hann^2 overlap sum at HOP = FFT/4
T_MEDIAN = 17                     # trailing frames for the harmonic (time) median
F_MEDIAN = 17                     # bins for the percussive (frequency) median
BUFLEN = FFT_SIZE * 4
LATENCY = FFT_SIZE                # reported pdc_delay


def hann(n):
    return 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)


def process(x, mode="split", split_character=8, mask_sharpness=2.0):
    """
    Run one channel through the exact JSFX ring/overlap-add logic.

    mode: "split"  -> HPSS tonal/noise, returns (tonal, noise)
          "flat"   -> mask = 1 (passthrough), returns (tonal, noise) where
                      tonal should equal the delayed input and noise ~ 0
    Returns tonal and noise arrays aligned to the input (latency compensated).
    """
    n = len(x)
    win = hann(FFT_SIZE)
    harm_bias = 2.0 ** ((split_character - 8) / 8)
    f_half = (F_MEDIAN - 1) // 2

    in_buf = np.zeros(BUFLEN)
    dly = np.zeros(BUFLEN)
    ola = np.zeros(BUFLEN)
    magring = np.zeros((T_MEDIAN, NBINS))

    tonal = np.zeros(n)
    noise = np.zeros(n)

    bidx = 0
    ctr = 0
    frames = 0

    for si in range(n + LATENCY + 2 * FFT_SIZE):
        v = x[si] if si < n else 0.0
        in_buf[bidx] = v
        dly[bidx] = v

        ctr += 1
        if ctr >= HOP:
            ctr = 0
            bi = bidx - FFT_SIZE
            seg = np.empty(FFT_SIZE)
            for fi in range(FFT_SIZE):
                seg[fi] = in_buf[(bi + fi) % BUFLEN]
            Z = np.fft.rfft(seg * win)

            head = frames % T_MEDIAN
            magring[head] = np.abs(Z)
            frames += 1

            if mode == "flat":
                mask = np.ones(NBINS)
            else:
                harm = np.median(magring, axis=0) * harm_bias
                cur = magring[head]
                p = np.pad(cur, f_half, mode="reflect")
                perc = np.array([np.median(p[i:i + F_MEDIAN]) for i in range(NBINS)])
                hp = harm ** mask_sharpness
                pp = perc ** mask_sharpness
                mask = hp / (hp + pp + 1e-10)

            rec = np.fft.irfft(Z * mask, n=FFT_SIZE) * win / COLA
            for fi in range(FFT_SIZE):
                ola[(bi + fi) % BUFLEN] += rec[fi]

        op = (bidx - LATENCY) % BUFLEN
        osamp = si - LATENCY
        if 0 <= osamp < n:
            tonal[osamp] = ola[op]
            noise[osamp] = dly[op] - ola[op]
        ola[op] = 0.0
        bidx = (bidx + 1) % BUFLEN

    return tonal, noise


def rms(a):
    return np.sqrt(np.mean(a ** 2)) if len(a) else 0.0


def db(a):
    return 20 * np.log10(a + 1e-20)


def impulse_test():
    n = 40000
    x = np.zeros(n)
    x[5000] = 1.0
    tonal, noise = process(x, mode="flat")
    pk = int(np.argmax(np.abs(tonal)))
    off_peak = np.sqrt(max(0.0, np.sum(tonal ** 2) - tonal[pk] ** 2))
    print("impulse test (flat mask):")
    print(f"  input impulse at 5000, output peak at {pk} -> measured delay {pk - 5000}")
    print(f"  (reported pdc_delay = {LATENCY})")
    print(f"  peak value {tonal[pk]:.6f} (expect ~1.0)")
    print(f"  energy off-peak {off_peak:.2e} (expect ~0)")
    print(f"  flat-mask noise RMS {db(rms(noise)):.1f} dB (expect very low)")
    ok = abs(tonal[pk] - 1.0) < 1e-3 and off_peak < 1e-6
    print(f"  => {'PASS' if ok else 'FAIL'}")


def wav_run(path, out_prefix, flat, split_character, mask_sharpness):
    if sf is None:
        raise SystemExit("soundfile not installed; use --impulse or install pysoundfile")
    x, sr = sf.read(path, always_2d=True)
    mode = "flat" if flat else "split"
    tonal_ch, noise_ch = [], []
    for ch in range(x.shape[1]):
        t, nz = process(x[:, ch], mode=mode,
                        split_character=split_character, mask_sharpness=mask_sharpness)
        tonal_ch.append(t)
        noise_ch.append(nz)
    tonal = np.stack(tonal_ch, 1)
    noise = np.stack(noise_ch, 1)
    summed = tonal + noise
    mid = slice(2 * FFT_SIZE, len(x) - FFT_SIZE)
    print(f"reconstruction (tonal+noise vs input, steady region): "
          f"{db(rms(summed[mid] - x[mid]) / (rms(x[mid]) + 1e-20)):.1f} dB")
    if out_prefix:
        sf.write(f"{out_prefix}_tonal.wav", tonal, sr)
        sf.write(f"{out_prefix}_noise.wav", noise, sr)
        sf.write(f"{out_prefix}_sum.wav", summed, sr)
        print(f"wrote {out_prefix}_{{tonal,noise,sum}}.wav")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--impulse", action="store_true",
                    help="run the Dirac impulse latency/reconstruction test")
    ap.add_argument("--wav", help="input wav file to process")
    ap.add_argument("--out-prefix", help="write <prefix>_tonal/noise/sum.wav")
    ap.add_argument("--flat", action="store_true",
                    help="passthrough (mask=1) framing test instead of the split")
    ap.add_argument("--split-character", type=float, default=8)
    ap.add_argument("--mask-sharpness", type=float, default=2.0)
    args = ap.parse_args()

    if args.impulse or not args.wav:
        impulse_test()
    if args.wav:
        wav_run(args.wav, args.out_prefix, args.flat,
                args.split_character, args.mask_sharpness)


if __name__ == "__main__":
    main()
