#!/usr/bin/env python3
"""
JSFX ring-buffer / overlap-add simulator for the Delay Isolator effect.

Reproduces the exact per-sample ring/overlap-add logic in
delay_isolator/delay_isolator.jsfx, in Python, so the STFT framing (window,
COLA normalization, ring indices, overlap-add position, reported latency) can be
validated offline before loading the plugin in REAPER. See
tools/jsfx_stft_sim.py for the same approach applied to the Tonal/Noise
Splitter, and the framing lessons in README.md -- they apply unchanged here.

The impulse test uses a WET impulse with DRY silent: with no dry energy the
duck mask must equal 1 everywhere (nothing to duck against), so a correct
effect reproduces the wet impulse exactly at latency = FFT_SIZE, with zero
energy elsewhere. This validates framing independently of the level-match
learning logic.

Usage:
  python jsfx_delay_isolator_sim.py --impulse
  python jsfx_delay_isolator_sim.py --dry dry.wav --wet wet.wav --out isolated.wav
"""

import argparse
import numpy as np

try:
    import soundfile as sf
except ImportError:
    sf = None

FFT_SIZE = 2048
HOP = FFT_SIZE // 4
NBINS = FFT_SIZE // 2 + 1
COLA = 1.5
FS_REF = FFT_SIZE * 0.25
BUFLEN = FFT_SIZE * 4
LATENCY = FFT_SIZE


def hann(n):
    return 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)


def smooth5(x):
    n = len(x)
    out = np.empty(n)
    for bn in range(n):
        lo = max(0, bn - 2)
        hi = min(n, bn + 3)
        out[bn] = np.mean(x[lo:hi])
    return out


def process(dry, wet, duck_db=6.0, mask_floor_db=-26.0, learn_rate=6,
            hold=False, dry_active_db=-50.0):
    n = len(dry)
    assert len(wet) == n
    win = hann(FFT_SIZE)

    duck_amount = 10 ** (duck_db / 10)
    mask_floor = 10 ** (mask_floor_db / 20)
    active_mag = FS_REF * 10 ** (dry_active_db / 20)
    alpha = 0.5 ** (11 - learn_rate)

    in_d = np.zeros(BUFLEN)
    in_w = np.zeros(BUFLEN)
    ola = np.zeros(BUFLEN)
    ola_rem = np.zeros(BUFLEN)

    avg_dry = np.zeros(NBINS)
    avg_wet = np.zeros(NBINS)
    gain_lm = np.ones(NBINS)

    out = np.zeros(n)
    removed = np.zeros(n)

    bidx = 0
    ctr = 0
    warm = 0

    for si in range(n + LATENCY + 2 * FFT_SIZE):
        vd = dry[si] if si < n else 0.0
        vw = wet[si] if si < n else 0.0
        in_d[bidx] = vd
        in_w[bidx] = vw

        ctr += 1
        if ctr >= HOP:
            ctr = 0
            bi = bidx - FFT_SIZE
            idx = (bi + np.arange(FFT_SIZE)) % BUFLEN
            seg_d = in_d[idx] * win
            seg_w = in_w[idx] * win

            Zd = np.fft.rfft(seg_d)
            Zw = np.fft.rfft(seg_w)
            md = np.abs(Zd)
            mw = np.abs(Zw)

            frame_energy = np.sum(md * md)
            dry_active = frame_energy > (active_mag * active_mag * 0.1)

            if dry_active and not hold:
                a = 0.3 if warm < 40 else alpha
                avg_dry[:] = (1 - a) * avg_dry + a * md
                avg_wet[:] = (1 - a) * avg_wet + a * mw
                warm += 1
                ratio = (avg_wet + 1e-10) / (avg_dry + 1e-10)
                gain_lm[:] = np.sqrt(smooth5(ratio))

            dry_matched = md * gain_lm
            wp = mw * mw
            dp = dry_matched * dry_matched
            mask = wp / (wp + duck_amount * dp + 1e-10)
            mask = np.clip(mask, mask_floor, 1.0)

            Zout = Zw * mask
            Zrem = Zw * (1.0 - mask)
            rec = np.fft.irfft(Zout, n=FFT_SIZE) * win / COLA
            rec_rem = np.fft.irfft(Zrem, n=FFT_SIZE) * win / COLA
            for fi in range(FFT_SIZE):
                ola[(bi + fi) % BUFLEN] += rec[fi]
                ola_rem[(bi + fi) % BUFLEN] += rec_rem[fi]

        op = (bidx - LATENCY) % BUFLEN
        osamp = si - LATENCY
        if 0 <= osamp < n:
            out[osamp] = ola[op]
            removed[osamp] = ola_rem[op]
        ola[op] = 0.0
        ola_rem[op] = 0.0
        bidx = (bidx + 1) % BUFLEN

    return out, removed


def rms(a):
    return np.sqrt(np.mean(a ** 2)) if len(a) else 0.0


def db(a):
    return 20 * np.log10(a + 1e-20)


def impulse_test():
    n = 40000
    dry = np.zeros(n)   # dry silent -> mask must be 1 everywhere -> exact passthrough
    wet = np.zeros(n)
    wet[5000] = 1.0
    out, removed = process(dry, wet)
    pk = int(np.argmax(np.abs(out)))
    off_peak = np.sqrt(max(0.0, np.sum(out ** 2) - out[pk] ** 2))
    print("impulse test (dry silent, wet impulse -> mask should be ~1 everywhere):")
    print(f"  input impulse at 5000, output peak at {pk} -> measured delay {pk - 5000}")
    print(f"  (reported pdc_delay = {LATENCY})")
    print(f"  peak value {out[pk]:.6f} (expect ~1.0)")
    print(f"  energy off-peak {off_peak:.2e} (expect ~0)")
    print(f"  removed-channel RMS {db(rms(removed)):.1f} dB (expect very low -- mask ~1 means nothing removed)")
    recon_err = rms((out + removed) - wet)
    print(f"  isolated+removed vs wet reconstruction error: {db(recon_err):.1f} dB (expect very low)")
    ok = abs(out[pk] - 1.0) < 1e-2 and off_peak < 1e-3
    print(f"  => {'PASS' if ok else 'FAIL'}")


def wav_run(dry_path, wet_path, out_path, removed_path=None, **kwargs):
    if sf is None:
        raise SystemExit("soundfile not installed")
    dry, sr = sf.read(dry_path, always_2d=True)
    wet, sr2 = sf.read(wet_path, always_2d=True)
    assert sr == sr2
    n = min(len(dry), len(wet))
    dry, wet = dry[:n], wet[:n]
    out_ch, rem_ch = [], []
    for ch in range(dry.shape[1]):
        o, r = process(dry[:, ch], wet[:, ch], **kwargs)
        out_ch.append(o)
        rem_ch.append(r)
    out = np.stack(out_ch, 1)
    removed = np.stack(rem_ch, 1)
    wet_rms = rms(wet)
    out_rms = rms(out)
    recon_err = rms((out + removed) - wet)
    print(f"wet rms={wet_rms:.5f}  isolated rms={out_rms:.5f}  reduction={db(wet_rms/max(out_rms,1e-20)):.1f} dB")
    print(f"isolated+removed vs wet reconstruction error: {db(recon_err):.1f} dB")
    if out_path:
        sf.write(out_path, out, sr)
        print(f"wrote {out_path}")
    if removed_path:
        sf.write(removed_path, removed, sr)
        print(f"wrote {removed_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--impulse", action="store_true")
    ap.add_argument("--dry", help="dry input wav")
    ap.add_argument("--wet", help="wet input wav")
    ap.add_argument("--out", help="isolated output wav path")
    ap.add_argument("--removed-out", help="removed output wav path")
    ap.add_argument("--duck-db", type=float, default=6.0)
    ap.add_argument("--mask-floor-db", type=float, default=-26.0)
    ap.add_argument("--learn-rate", type=int, default=6)
    ap.add_argument("--dry-active-db", type=float, default=-50.0)
    args = ap.parse_args()

    if args.impulse or not (args.dry and args.wet):
        impulse_test()
    if args.dry and args.wet:
        wav_run(args.dry, args.wet, args.out, args.removed_out,
                duck_db=args.duck_db, mask_floor_db=args.mask_floor_db,
                learn_rate=args.learn_rate, dry_active_db=args.dry_active_db)


if __name__ == "__main__":
    main()
