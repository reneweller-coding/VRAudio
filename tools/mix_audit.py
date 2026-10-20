"""The family's mix audit (20.10.2026): every instrument's demos, rendered by its own renderer, measured one way and
held against the reference recordings each instrument was calibrated on.

    python tools/mix_audit.py                          # every instrument: render (kept), measure, report
    python tools/mix_audit.py --only totality phosphene --fresh
    python tools/mix_audit.py --skip-render            # measure what work/mix_audit/<instrument>/ holds
    python tools/mix_audit.py --tag after              # the reports as <instrument>.after.md, beside the baseline

What a report holds, per demo:

* **The references' own measures**, each taken the way the instrument's Tools/analyze_ref.py takes it from the
  recordings (the same window, the same sample rate, the same band edges) and set against the recordings of the
  demo's style: their 10th, 50th and 90th percentile (Phosphene keeps only quartiles; it says so).
* **The family's measures**, the same for all: integrated loudness, LRA, true peak and the loudest 20 s
  (BS.1770 / EBU R128 by ffmpeg), the peak-to-loudness ratio, the true peak after AAC (320 kbit/s, what Heliacal's
  videos carry) and after Opus (160 kbit/s, what YouTube plays) at the render's own level, the correlation under
  120 Hz and over the whole band, the K-weighted loss of a mono fold-down, the spectral tilt over 100 Hz .. 10 kHz
  and the largest third-octave band's distance from it, the loud part's p90 - p10 short-term range -- the loud
  part being the windows of the middle 80 % in the loudest 40 % of the short-term loudness (Phosphene's mix audit).
* **The norms** every master is held to, with the reason for each number: the ceiling (-2 dBTP for techno, trance
  and psytrance, -1 for the rest), the codec peaks, the correlation, the mono loss.

Noctuary and Empyrean were calibrated on no recordings. They are held against Analemma's 1129 dark-ambient and
ritual recordings, the nearest the family has measured, and the report says so.

All values also go to work/mix_audit/audit.json (and <tag>.json), the third-octave curves with them (the tonal
balance the master stages are tuned to). Needs numpy, scipy and ffmpeg on the PATH (or FFMPEG).
"""
import argparse
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time

import numpy as np
from scipy import signal

HERE = os.path.dirname(os.path.abspath(__file__))
FAMILY = os.path.dirname(HERE)
VRAUDIO = os.path.dirname(FAMILY)
WORK = os.path.join(FAMILY, 'work', 'mix_audit')

#: Third-octave centres for the family's tonal curve, 25 Hz .. 20 kHz (Phosphene's metrics.THIRD_CENTRES).
THIRDS = np.array([1000.0 * 2.0 ** (k / 3.0) for k in range(-16, 14)])

# ------------------------------------------------------------------------------------------------- tools


def ffmpeg():
    exe = os.environ.get('FFMPEG') or shutil.which('ffmpeg')
    if not exe:
        sys.exit('ffmpeg not found: put it on PATH or name it in FFMPEG')
    return exe


def decode(path, sr, mono=False, start=0.0, dur=None):
    """The file at sr, (2, N) float64 (or (N,) mono, ffmpeg's own fold-down as the references were read)."""
    cmd = [ffmpeg(), '-v', 'quiet', '-ss', '%.3f' % start, '-i', path]
    if dur is not None:
        cmd += ['-t', '%.3f' % dur]
    cmd += ['-ac', '1' if mono else '2', '-ar', str(sr), '-f', 'f32le', '-']
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.float32).astype(np.float64)
    return x if mono else x.reshape(-1, 2).T


def ebur128(path, peak=True):
    """Integrated LUFS, LRA, true peak, the loudest 20 s and the short-term series [(t, S)] (every 100 ms)."""
    full = subprocess.run([ffmpeg(), '-hide_banner', '-nostats', '-i', path, '-af',
                           'ebur128=peak=%s' % ('true' if peak else 'none'), '-f', 'null', '-'],
                          capture_output=True, text=True, errors='replace').stderr
    tail = full[-4000:]

    def grab(label):
        m = re.findall(label + r':\s*(-?\d+\.\d+)', tail)
        return float(m[-1]) if m else float('nan')
    series = [(float(t), float(s)) for t, s in re.findall(r'\bt:\s*(\d+\.?\d*)\s+.*?\bS:\s*(-?\d+\.\d+)', full)]
    st = np.array([s for _, s in series])
    loud20 = float('nan')
    if len(st) > 200:
        w = np.convolve(np.power(10.0, st / 10.0), np.ones(200) / 200.0, mode='valid')
        loud20 = 10.0 * math.log10(max(float(w.max()), 1e-30))
    return grab('I'), grab('LRA'), grab('Peak'), loud20, series


def codec_peak(path, work, codec):
    """The true peak of the file after a lossy codec at its own level, decoded as a player decodes it."""
    if codec == 'aac':
        enc = subprocess.run([ffmpeg(), '-hide_banner', '-encoders'], capture_output=True, text=True).stdout
        args, ext = (['-c:a', 'aac_mf', '-b:a', '320000'] if ' aac_mf ' in enc else ['-c:a', 'aac', '-b:a', '320k']), '.m4a'
    else:
        args, ext = ['-c:a', 'libopus', '-b:a', '160k'], '.opus'
    out = os.path.join(work, os.path.splitext(os.path.basename(path))[0] + '.codec' + ext)
    subprocess.run([ffmpeg(), '-v', 'error', '-y', '-i', path, '-ac', '2'] + args + [out], check=True)
    peak = ebur128(out)[2]
    os.remove(out)
    return peak


def kweight(x, sr):
    """BS.1770's K filter (the shelf and the high pass, designed for sr) on each channel."""
    G, Q, fc = 3.99984385397, 0.7071752369554193, 1681.974450955533
    A, w0 = 10.0 ** (G / 40.0), 2.0 * math.pi * fc / sr
    al, c = math.sin(w0) / (2.0 * Q), math.cos(w0)
    b = [A * ((A + 1) + (A - 1) * c + 2 * math.sqrt(A) * al), -2 * A * ((A - 1) + (A + 1) * c),
         A * ((A + 1) + (A - 1) * c - 2 * math.sqrt(A) * al)]
    a = [(A + 1) - (A - 1) * c + 2 * math.sqrt(A) * al, 2 * ((A - 1) - (A + 1) * c),
         (A + 1) - (A - 1) * c - 2 * math.sqrt(A) * al]
    y = signal.lfilter(b, a, x, axis=-1)
    Q, fc = 0.5003270373238773, 38.13547087602444
    w0 = 2.0 * math.pi * fc / sr
    al, c = math.sin(w0) / (2.0 * Q), math.cos(w0)
    return signal.lfilter([1.0, -2.0, 1.0], [1.0 + al, -2.0 * c, 1.0 - al], y, axis=-1) * (1.0 + al)


def db(v):
    return 10.0 * math.log10(max(v, 1e-30))


# ------------------------------------------------------------------------------------- family measures

def loud_part(series, dur):
    """The loud part: the 3 s windows of the middle 80 % whose short-term loudness is in the loudest 40 %."""
    inner = [(t, s) for t, s in series if 0.1 * dur + 3.0 <= t <= 0.9 * dur and s > -60.0]
    if len(inner) < 20:
        inner = [(t, s) for t, s in series if s > -60.0]
    if not inner:
        return [(0.0, dur)], float('nan')
    thr = np.percentile([s for _, s in inner], 60)
    spans = []
    for t, s in inner:
        if s >= thr:
            a, b = t - 3.0, t
            if spans and a <= spans[-1][1]:
                spans[-1] = (spans[-1][0], b)
            else:
                spans.append((a, b))
    sv = np.array([s for _, s in inner])
    return spans, float(np.percentile(sv, 90) - np.percentile(sv, 10))


def gather(x, spans, sr):
    parts = [x[:, int(a * sr):int(b * sr)] for a, b in spans]
    parts = [p for p in parts if p.shape[1] > 0]
    return np.concatenate(parts, axis=1) if parts else x


def correlation(x, sr, win=0.4):
    """Median over 400 ms windows of the channel correlation below 120 Hz and over 20 Hz .. 20 kHz (Phosphene)."""
    n = int(win * sr)
    f = np.fft.rfftfreq(n, 1 / sr)
    low, full = (f > 20) & (f < 120), (f > 20) & (f < 20000)
    w = np.hanning(n)
    lo, al = [], []
    for s in range(0, x.shape[1] - n, n):
        L, R = np.fft.rfft(x[0, s:s + n] * w), np.fft.rfft(x[1, s:s + n] * w)
        for sel, out in ((low, lo), (full, al)):
            pl, pr = np.sum(np.abs(L[sel]) ** 2), np.sum(np.abs(R[sel]) ** 2)
            if pl > 1e-20 and pr > 1e-20:
                out.append(np.real(np.sum(L[sel] * np.conj(R[sel]))) / np.sqrt(pl * pr))
    return (float(np.median(lo)) if lo else float('nan')), (float(np.median(al)) if al else float('nan'))


def mono_loss(x, sr):
    k = kweight(x, sr)
    stereo = np.mean(k[0] ** 2) + np.mean(k[1] ** 2)
    mono = 2.0 * np.mean((0.5 * (k[0] + k[1])) ** 2)
    return db(mono) - db(stereo)


def power(x, sr, n=1 << 14):
    f, p = signal.welch(x[0], sr, nperseg=n)
    _, p2 = signal.welch(x[1], sr, nperseg=n)
    return f, p + p2


def tilt(f, p):
    """The line through the third-octave means (100 Hz .. 10 kHz) over log2 f, and the largest band's distance."""
    lv, lf = [], []
    for k in range(-10, 11):
        c = 1000.0 * 2.0 ** (k / 3.0)
        sel = (f >= c * 2 ** (-1 / 6)) & (f < c * 2 ** (1 / 6))
        if sel.any():
            lv.append(10.0 * np.log10(np.mean(p[sel]) + 1e-30))
            lf.append(np.log2(c))
    lv, lf = np.array(lv), np.array(lf)
    slope, icpt = np.polyfit(lf, lv, 1)
    return float(slope), float(np.max(np.abs(lv - (slope * lf + icpt))))


def thirds(f, p):
    """The third-octave curve, dB against the 40 .. 140 Hz band (Phosphene's metrics.third_octave)."""
    ref = max(p[(f >= 40.0) & (f < 140.0)].sum(), 1e-300)
    return [round(10.0 * math.log10(max(p[(f >= c / 2 ** (1 / 6)) & (f < c * 2 ** (1 / 6))].sum(), 1e-300) / ref), 2)
            for c in THIRDS]


def family_measures(wav, work):
    lufs, lra, tp, loud20, series = ebur128(wav)
    dur = series[-1][0] if series else 0.0
    sr = 48000
    x = decode(wav, sr)
    spans, p90p10 = loud_part(series, dur)
    xl = gather(x, spans, sr)
    r = {'lufs': lufs, 'lra': lra, 'true_peak': tp, 'loud20': loud20, 'plr_db': tp - lufs,
         'aac_peak': codec_peak(wav, work, 'aac'), 'opus_peak': codec_peak(wav, work, 'opus')}
    r['corr_low'], r['corr_all'] = correlation(xl, sr)
    r['mono_loss_db'] = mono_loss(xl, sr)
    f, p = power(xl, sr)
    r['tilt_db_oct'], r['tilt_dev_db'] = tilt(f, p)
    r['p90_p10_db'] = p90p10
    mid = x[:, max(0, x.shape[1] // 2 - 30 * sr):x.shape[1] // 2 + 30 * sr]   # Phosphene's middle minute
    f, p = power(mid, sr, 1 << 15)
    r['thirds'] = thirds(f, p)
    r['seconds'] = round(dur, 1)
    return r, series


# ----------------------------------------------------------------------- each instrument's own measures

#: Totality's five bands, dB against 40 .. 140 Hz (its bands_db).
TOT_BANDS = ('db20_60', 'db60_250', 'db250_1k', 'db1k_5k', 'db5k_16k')


def totality_measures(wav, series, dur):
    """TechnoGenerator/Tools/analyze_ref.py: a minute at 44.1 kHz, mid and side, Welch 32768. The references' was their
    middle minute, inside the body of a seven-minute record; a five-minute demo's middle can be its kick-out break, so
    the render's is the minute with the most kick band (40-140 Hz): the body, where the Leveler reads it too (the
    loudest minute of a demo can be a breakdown of pads without a kick, its bands then 20 dB over it)."""
    sr = 44100
    xs = decode(wav, sr, start=kick_minute(wav), dur=60.0)
    mid, side = 0.5 * (xs[0] + xs[1]), 0.5 * (xs[0] - xs[1])
    fw, pm = signal.welch(mid, fs=sr, nperseg=1 << 15)
    _, ps = signal.welch(side, fs=sr, nperseg=1 << 15)

    def bp(p, lo, hi):
        return float(p[(fw >= lo) & (fw < hi)].sum())
    r = {}
    for name, (lo, hi) in zip(TOT_BANDS,
                              [(20, 60), (60, 250), (250, 1000), (1000, 5000), (5000, 16000)]):
        r[name] = db(bp(pm, lo, hi) / max(bp(pm, 40, 140), 1e-30))
    r['width_db'] = db(bp(ps, 200, 16000) / max(bp(pm, 200, 16000), 1e-30))
    r['low_side_db'] = db(bp(ps, 20, 120) / max(bp(pm, 20, 120), 1e-30))
    r['correlation'] = float(np.corrcoef(xs[0], xs[1])[0, 1])
    return r


def kick_minute(wav):
    """Where the minute with the most energy between 40 and 140 Hz begins (the body: the kick and the bass), seconds."""
    sr = 4000
    x = decode(wav, sr, mono=True)
    y = signal.sosfilt(signal.butter(4, [40.0, 140.0], btype='bandpass', fs=sr, output='sos'), x)
    per = np.array([np.sum(y[i:i + sr] ** 2) for i in range(0, len(y) - sr + 1, sr)])
    if len(per) <= 60:
        return 0.0
    run = np.convolve(per, np.ones(60), mode='valid')
    return float(np.argmax(run))


def loudest(series, seconds):
    """Where the loudest stretch of `seconds` begins (the short-term energy's running mean)."""
    t = np.array([a for a, _ in series])
    e = np.power(10.0, np.array([s for _, s in series]) / 10.0)
    n = int(seconds * 10)
    if len(e) <= n:
        return 0.0
    w = np.convolve(e, np.ones(n) / n, mode='valid')
    return max(0.0, float(t[int(np.argmax(w))]) - 3.0)


def parhelion_measures(wav, series, dur):
    """TranceGenerator/Tools/analyze_ref.py's balance in the drop -- here the loudest minute, where the drop is."""
    sr = 44100
    st2 = decode(wav, sr, start=loudest(series, 60.0), dur=60.0)
    m, s2 = 0.5 * (st2[0] + st2[1]), 0.5 * (st2[0] - st2[1])
    f, P = signal.welch(m, fs=sr, nperseg=8192)
    tot = P[(f >= 20) & (f <= 16000)].sum()
    r = {}
    for name, lo, hi in (('b20_60', 20, 60), ('b60_150', 60, 150), ('b150_400', 150, 400), ('b400_2k', 400, 2000),
                         ('b2k_5k', 2000, 5000), ('b5k_16k', 5000, 16000)):
        r[name] = float(P[(f >= lo) & (f < hi)].sum() / tot)
    band = (f >= 20) & (f <= 16000)
    r['centroid'] = float((f[band] * P[band]).sum() / P[band].sum())

    def bpass(x, lo, hi):
        return signal.sosfiltfilt(signal.butter(4, [lo, hi], btype='bandpass', fs=sr, output='sos'), x)
    mh, sh, ml, sl = bpass(m, 200, 16000), bpass(s2, 200, 16000), bpass(m, 30, 120), bpass(s2, 30, 120)
    r['side_hi_db'] = db(np.mean(sh ** 2) / max(np.mean(mh ** 2), 1e-30))
    r['side_lo_db'] = db(np.mean(sl ** 2) / max(np.mean(ml ** 2), 1e-30))
    r['correlation'] = float(np.corrcoef(st2[0], st2[1])[0, 1])
    return r


def analemma_measures(wav, series, dur):
    """RitualGenerator/Tools/analyze_ref.py: floor, centroid, width over the whole piece at 32 kHz."""
    sr = 32000
    st = decode(wav, sr)
    mid, side = 0.5 * (st[0] + st[1]), 0.5 * (st[0] - st[1])
    f, pm = signal.welch(mid, fs=sr, nperseg=8192)
    _, ps = signal.welch(side, fs=sr, nperseg=8192)
    band = (f >= 20) & (f <= 15000)
    tot = pm[band].sum() + 1e-30
    hi = f >= 200
    return {'under150': float(pm[(f >= 20) & (f < 150)].sum() / tot),
            'under60': float(pm[(f >= 20) & (f < 60)].sum() / tot),
            'centroid': float((f[band] * pm[band]).sum() / tot),
            'side_db': db(ps[hi].sum() / max(pm[hi].sum(), 1e-30)),
            'correlation': float(np.dot(st[0], st[1]) / math.sqrt(max(np.dot(st[0], st[0]) * np.dot(st[1], st[1]), 1e-30)))}


def ephemeris_measures(wav, series, dur):
    """BerlinSchoolGenerator/Tools/analyze_ref.py: level and range of 3 s windows, mono at 11025 Hz."""
    sr = 11025
    x = decode(wav, sr, mono=True)
    seg = 3 * sr
    rms = np.sqrt(np.array([np.mean(x[i:i + seg] ** 2) for i in range(0, len(x) - seg, seg)]) + 1e-20)
    return {'rms_db': 10 * math.log10(np.mean(x ** 2) + 1e-20),
            'range_db': 20 * math.log10(np.percentile(rms, 95) / max(np.percentile(rms, 10), 1e-10))}


# ------------------------------------------------------------------------------------------- references

def pct(values):
    v = [float(x) for x in values if x is not None and isinstance(x, (int, float)) and math.isfinite(x)]
    if len(v) < 3:
        return None
    return {'lo': float(np.percentile(v, 10)), 'mid': float(np.median(v)), 'hi': float(np.percentile(v, 90)), 'n': len(v)}


def load(repo, name):
    return json.load(open(os.path.join(VRAUDIO, repo, 'Tools', name), encoding='utf-8'))


def totality_refs(profile):
    rows = [t for t in load('TechnoGenerator', 'ref_stats.json')['tracks'] if t.get('profile') == profile]
    out = {}
    for i, name in enumerate(TOT_BANDS):
        out[name] = pct([r['bands_db'][i] for r in rows])
    for k in ('width_db', 'low_side_db', 'correlation', 'lufs', 'lra', 'true_peak', 'loud20'):
        out[k] = pct([r.get(k) for r in rows])
    return out, '%d %s tracks' % (len(rows), profile)


def parhelion_refs(profile):
    rows = [t for t in load('TranceGenerator', 'ref_stats.json')['rows'] if t.get('profile') == profile]
    keys = ('b20_60', 'b60_150', 'b150_400', 'b400_2k', 'b2k_5k', 'b5k_16k', 'centroid', 'side_hi_db', 'side_lo_db',
            'correlation', 'lufs', 'lra', 'true_peak', 'loud20')
    return {k: pct([r.get(k) for r in rows]) for k in keys}, '%d %s tracks' % (len(rows), profile)


def phosphene_refs(profile):
    m = load('PsytranceGenerator', 'ref_mix_audit.json')
    out = {k: {'lo': m['q1'][k], 'mid': m['median'][k], 'hi': m['q3'][k], 'n': m['files'], 'iqr': True}
           for k in ('corr_low', 'corr_all', 'mono_loss_db', 'tilt_db_oct', 'tilt_dev_db', 'p90_p10_db')}
    return out, '%d psytrance recordings (quartiles only)' % m['files']


AMBIENT_KEYS = ('under150', 'under60', 'centroid', 'side_db', 'correlation', 'lufs', 'lra')


def analemma_refs(profile):
    rows = [t for t in load('RitualGenerator', 'ref_stats.json')['rows'] if profile is None or t.get('profile') == profile]
    what = '%d %s recordings' % (len(rows), profile) if profile else \
        '%d dark-ambient and ritual recordings (Analemma\'s; this instrument has none of its own)' % len(rows)
    return {k: pct([r.get(k) for r in rows]) for k in AMBIENT_KEYS}, what


def ephemeris_refs(profile):
    style = load('BerlinSchoolGenerator', 'ref_stats.json')[profile]
    rows = style['tracks']
    return {k: pct([r.get(k) for r in rows]) for k in ('rms_db', 'range_db')}, '%d %s tracks' % (len(rows), profile)


def phosphene_thirds():
    p = load('PsytranceGenerator', 'ref_profile.json')
    return {'centres': p['third_centres'], 'lo': p['third_q1'], 'mid': p['third_median'], 'hi': p['third_q3']}


# ---------------------------------------------------------------------------------------------- the set

#: Per instrument: its repo, the measures its references were taken with, the references per demo, the ceiling.
INSTRUMENTS = {
    'totality': dict(name='Totality', repo='TechnoGenerator', own=totality_measures, refs=totality_refs,
                     profile={'rawpeak': 'raw'}, ceiling=-2.0, dance=True),
    'parhelion': dict(name='Parhelion', repo='TranceGenerator', own=parhelion_measures, refs=parhelion_refs,
                      profile={}, ceiling=-2.0, dance=True),
    'phosphene': dict(name='Phosphene', repo='PsytranceGenerator', own=None, refs=phosphene_refs,
                      profile={}, ceiling=-2.0, dance=True),
    'ephemeris': dict(name='Ephemeris', repo='BerlinSchoolGenerator', own=ephemeris_measures, refs=ephemeris_refs,
                      profile={'cosmic': 'Cosmic', 'doom': 'Doom', 'melodic': 'Melodic', 'modern': 'Modern',
                               'drift': 'Drift'}, ceiling=-1.0, dance=False),
    'analemma': dict(name='Analemma', repo='RitualGenerator', own=analemma_measures, refs=analemma_refs,
                     profile={}, ceiling=-1.0, dance=False),
    'noctuary': dict(name='Noctuary', repo='AmbientSynth', own=analemma_measures, refs=lambda p: analemma_refs(None),
                     profile={}, ceiling=-1.0, dance=False),
    'empyrean': dict(name='Empyrean', repo='AdditivAmbientSynth', own=analemma_measures,
                     refs=lambda p: analemma_refs(None), profile={}, ceiling=-1.0, dance=False),
}


def norms(inst):
    """What every master is held to, (low, high, why) per family measure."""
    c = inst['ceiling']
    out = {
        'true_peak': (-99.0, c, '%+.0f dBTP: %s' % (c, 'a loud master survives AAC and Opus (AES TD1008)' if inst['dance']
                                                   else 'the streaming services\' ceiling')),
        'aac_peak': (-99.0, -1.0 if not inst['dance'] else -0.5,
                     'the AAC a player decodes clips no more than the ceiling allows (dance: a loud master, -0.5)'),
        'opus_peak': (-99.0, -1.0 if not inst['dance'] else -0.5, 'the same for the Opus YouTube plays'),
        'corr_all': (0.2, 0.97, 'under 0.2 a fold-down loses whole parts, over 0.97 the mix is mono'),
        'mono_loss_db': (-1.0 if inst['dance'] else -3.0, 0.0,
                         'a mono fold-down (club, phone) loses at most %s' % ('1 dB' if inst['dance'] else '3 dB (wide reverbs are the genre)')),
    }
    if inst['dance']:   # a sparse ambient spectrum (a few partials) is spiky by design: no tilt norm there
        out['tilt_dev_db'] = (0.0, 6.0, 'no third-octave band 6 dB off the tilt line (a resonance or a hole)')
        out['corr_low'] = (0.9, 1.0, 'the sub is mono in a club (under 120 Hz)')
    return out


FAMILY_ORDER = ('lufs', 'lra', 'true_peak', 'aac_peak', 'opus_peak', 'loud20', 'plr_db', 'corr_low', 'corr_all',
                'mono_loss_db', 'tilt_db_oct', 'tilt_dev_db', 'p90_p10_db')
FORMAT = {'centroid': '%.0f', 'under150': '%.3f', 'under60': '%.3f', 'correlation': '%.2f', 'corr_low': '%.2f',
          'corr_all': '%.2f'}


def fmt(k, v):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return '-'
    if k.startswith('b') and k[1:2].isdigit():   # Parhelion's band shares
        return '%.3f' % v
    return FORMAT.get(k, '%+.1f' if k not in ('lra', 'p90_p10_db', 'plr_db', 'tilt_dev_db') else '%.1f') % v


# ---------------------------------------------------------------------------------------------- render

def demo_module(repo):
    path = os.path.join(VRAUDIO, repo, 'Tools', 'demo', 'make_demos.py')
    spec = importlib.util.spec_from_file_location('demos_' + repo, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def render_all(key, inst, out, fresh, only_demo):
    mod = demo_module(inst['repo'])
    mod.OUT = out
    os.makedirs(out, exist_ok=True)
    exe = mod.renderer(None)
    done = []
    for demo in mod.DEMOS:
        name, args = demo[0], demo[-1]
        if only_demo and name not in only_demo:
            continue
        wav = os.path.join(out, name + '.wav')
        if fresh or not os.path.exists(wav):
            t0 = time.time()
            try:
                res = mod.render(exe, name, args)
            except SystemExit as e:
                print('  %s/%s: render failed: %s' % (key, name, str(e)[:400]), flush=True)
                continue
            wav = res[0] if isinstance(res, tuple) else res
            print('  %s/%s rendered in %.0f s' % (key, name, time.time() - t0), flush=True)
        done.append((name, wav))
    return exe, done


# ---------------------------------------------------------------------------------------------- report

def verdict(v, band):
    if band is None or v is None or not math.isfinite(v):
        return ''
    if v < band['lo']:
        return 'low'
    if v > band['hi']:
        return 'high'
    return 'in'


def report(key, inst, exe, results, tag):
    lines = ['# Mix audit: %s (%s%s)' % (inst['name'], time.strftime('%d.%m.%Y'), ', ' + tag if tag else ''), '',
             'Renders: the demos of %s/Tools/demo/make_demos.py by `%s`. References: each demo against its own '
             'style\'s recordings, the band the 10th .. 90th percentile (quartiles where noted). Norms: the family\'s, '
             'with their reasons below.' % (inst['repo'], os.path.relpath(exe, os.path.join(VRAUDIO, inst['repo']))), '']
    # Findings: measures off the references or the norms in at least half of the demos.
    count, total = {}, len(results)
    nm = norms(inst)
    for name, r in results.items():
        for k, band in r['ref'].items():
            v = r['own'].get(k, r['family'].get(k))
            d = verdict(v, band)
            if d in ('low', 'high'):
                count.setdefault((k, d, 'references'), []).append(name)
        for k, (lo, hi, _) in nm.items():
            v = r['family'].get(k)
            if v is not None and math.isfinite(v) and not lo <= v <= hi:
                count.setdefault((k, 'low' if v < lo else 'high', 'norm'), []).append(name)
    lines += ['## Findings', '']
    found = sorted(((k, d, w, n) for (k, d, w), n in count.items()), key=lambda x: (-len(x[3]), x[0]))
    if not found:
        lines.append('Every demo within its references and the norms.')
    for k, d, w, names in found:
        lines.append('- **%s** %s against the %s in %d of %d: %s' % (k, 'too low' if d == 'low' else 'too high', w,
                                                                    len(names), total, ', '.join(names)))
    lines += ['']
    for name, r in results.items():
        lines += ['## %s' % name, '', 'Against %s.' % r['what'], '',
                  '| measure | render | p10 | p50 | p90 | |', '|---|---|---|---|---|---|']
        keys = list(r['own'].keys()) + [k for k in r['ref'] if k not in r['own']]
        for k in keys:
            v = r['own'].get(k, r['family'].get(k))
            band = r['ref'].get(k)
            cells = [fmt(k, band[x]) for x in ('lo', 'mid', 'hi')] if band else ['-', '-', '-']
            mark = verdict(v, band)
            if band and band.get('iqr'):
                mark += ' (q1..q3)'
            lines.append('| %s | %s | %s | %s |' % (k, fmt(k, v), ' | '.join(cells), mark))
        lines.append('')
    lines += ['## The family\'s measures', '',
              '| demo | ' + ' | '.join(FAMILY_ORDER) + ' |', '|---' * (len(FAMILY_ORDER) + 1) + '|']
    for name, r in results.items():
        cells = []
        for k in FAMILY_ORDER:
            v = r['family'].get(k)
            s = fmt(k, v)
            if k in nm and v is not None and math.isfinite(v) and not nm[k][0] <= v <= nm[k][1]:
                s = '**' + s + '**'
            cells.append(s)
        lines.append('| %s | %s |' % (name, ' | '.join(cells)))
    lines += ['', 'Bold: outside the norm. The norms:', '']
    for k, (lo, hi, why) in nm.items():
        span = ('<= %+.1f' % hi) if lo < -50 else ('%.2f .. %.2f' % (lo, hi))
        lines.append('- %s %s: %s' % (k, span, why))
    if key == 'phosphene':
        ref = phosphene_thirds()
        lines += ['', '## Third octaves against the references (dB under 40 .. 140 Hz, the middle minute)', '',
                  '| Hz | refs q1 | median | q3 | ' + ' | '.join(results) + ' |', '|---' * (4 + len(results)) + '|']
        for i, c in enumerate(ref['centres']):
            if c < 30 or c > 17000:
                continue
            cells = []
            for r in results.values():
                v = r['family']['thirds'][i]
                cells.append(('%+.1f' % v) + ('' if ref['lo'][i] - 1.0 <= v <= ref['hi'][i] + 1.0 else ' *'))
            lines.append('| %.0f | %+.1f | %+.1f | %+.1f | %s |' % (c, ref['lo'][i], ref['mid'][i], ref['hi'][i],
                                                                  ' | '.join(cells)))
        lines.append('\n`*`: more than 1 dB outside the references\' quartiles.')
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--only', nargs='*', help='instruments (%s)' % ', '.join(INSTRUMENTS))
    ap.add_argument('--demo', nargs='*', help='only these demos')
    ap.add_argument('--fresh', action='store_true', help='render again even where a render is kept')
    ap.add_argument('--skip-render', action='store_true', help='measure the renders kept, render nothing')
    ap.add_argument('--tag', default='', help='name the reports <instrument>.<tag>.md and <tag>.json')
    a = ap.parse_args()
    os.makedirs(WORK, exist_ok=True)
    js = os.path.join(WORK, (a.tag or 'audit') + '.json')
    store = json.load(open(js, encoding='utf-8')) if os.path.exists(js) else {}
    for key in a.only or list(INSTRUMENTS):
        inst = INSTRUMENTS[key]
        out = os.path.join(WORK, key)
        print('== %s' % inst['name'], flush=True)
        if a.skip_render:
            mod = demo_module(inst['repo'])
            exe = mod.renderer(None)
            done = [(d[0], os.path.join(out, d[0] + '.wav')) for d in mod.DEMOS
                    if os.path.exists(os.path.join(out, d[0] + '.wav')) and (not a.demo or d[0] in a.demo)]
        else:
            exe, done = render_all(key, inst, out, a.fresh, a.demo)
        results = {}
        for name, wav in done:
            fam, series = family_measures(wav, out)
            dur = fam['seconds']
            own = inst['own'](wav, series, dur) if inst['own'] else {}
            ref, what = inst['refs'](inst['profile'].get(name, name))
            ref = {k: v for k, v in ref.items() if v is not None}
            for k in ref:   # what the references hold of the family's measures (loudness, Phosphene's mix audit)
                if k not in own and k in fam:
                    own[k] = fam[k]
            results[name] = {'family': fam, 'own': own, 'ref': ref, 'what': what}
            print('  %-24s LUFS %+.1f  TP %+.1f  AAC %+.1f  Opus %+.1f  tilt %+.1f  corr %.2f  mono %+.1f' % (
                name, fam['lufs'], fam['true_peak'], fam['aac_peak'], fam['opus_peak'], fam['tilt_db_oct'],
                fam['corr_all'], fam['mono_loss_db']), flush=True)
        if not results:
            continue
        md = os.path.join(WORK, key + ('.' + a.tag if a.tag else '') + '.md')
        open(md, 'w', encoding='utf-8').write(report(key, inst, exe, results, a.tag))
        store = json.load(open(js, encoding='utf-8')) if os.path.exists(js) else {}   # another run may have written
        store[key] = {n: {'family': r['family'], 'own': r['own'], 'ref': r['ref']} for n, r in results.items()}
        json.dump(store, open(js, 'w', encoding='utf-8'), indent=1)
        print('  report: %s' % md, flush=True)


if __name__ == '__main__':
    main()
