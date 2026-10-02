"""Writes index.html, the family's page, from page.html and the table below (02.10.2026).

    python make_page.py [--vraudio G:/Tools/VRAudio]

Each instrument: its logo and the poster of its demo video are copied from its repository into img/ (the poster is
work/demos/<video>.jpg, written by its Tools/demo/make_demos.py); the video and the MP3s are not copied -- they stay on
each repository's release "demos", and the page plays them from there.
"""
import argparse
import html
import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OWNER = 'https://github.com/reneweller-coding'

# name, repository folder, genre, logo (in its repository), text, the video demo, the MP3 demos (file, title)
FAMILY = [
    ('Noctuary', 'AmbientSynth', 'Ambient and drone', 'docs/logo-128.png',
     'A drone-ambient synthesizer for slowly breathing clusters: just intonation, a conductor that plays all night, '
     'distance as the one number that shapes every voice, 24 source types, three reverb tiers, and 14592 presets '
     'measured by rendering them.',
     ('consonant_expanse', 'Consonant Expanse'),
     [('consonant_expanse', 'Consonant Expanse'), ('somnus_field', 'Somnus Field'), ('harmonic_hours', 'Harmonic Hours')]),
    ('Ephemeris', 'BerlinSchoolGenerator', 'Berlin School', 'docs/logo-128.png',
     'Sequenced modular voices and a composer that plays whole pieces and night sets: eight rows orbiting a root, '
     'circuit-modelled filters and VCOs, tape keys, strings and a poly synth, envelopes, LFOs and a modulation matrix '
     'on every synth, the room of a tape echo and a long hall.',
     ('cosmic', 'Cosmic'),
     [('cosmic', 'Cosmic'), ('doom', 'Doom'), ('melodic', 'Melodic'), ('modern', 'Modern'), ('drift', 'Drift')]),
    ('Phosphene', 'PsytranceGenerator', 'Psytrance', 'docs/logo/lid/icon.png',
     'Complete psytrance sets from a seed, a style and an energy arc — Goa, Full-On, Progressive, Dark Forest and '
     'Hi-Tech: key, tempo and form, kick and rolling bass, 303 acid, leads, arpeggios, pads and effects, played through '
     'its own synthesizers, mixer and mastering chain.',
     ('goa', 'Goa'),
     [('goa', 'Goa'), ('fullon', 'Full-On'), ('progressive', 'Progressive'), ('darkforest', 'Dark Forest'),
      ('hitech', 'Hi-Tech')]),
    ('Totality', 'TechnoGenerator', 'Hypnotic techno', 'docs/logo-128.png',
     'Hypnotic Berlin techno: tracks of 32-bar plateaus and whole DJ sets — a kick that hands its phase to the rumble '
     'under it, a twelve-lane kit, a bass and a 303 through circuit-modelled filters, the dub chord in its echoes, and a '
     'DJ who mixes the tracks into one long recomposition.',
     ('ostgut', 'Ostgut'),
     [('hypnotic', 'Hypnotic'), ('ostgut', 'Ostgut'), ('dub', 'Dub'), ('rawpeak', 'Raw Peak')]),
    ('Parhelion', 'TranceGenerator', 'Trance', 'docs/logo-128.png',
     'Trance tracks and DJ sets: the JP-8000 supersaw, a physical piano, a synthesised orchestra, the pump of the ghost '
     'kick on every bus — and motifs checked against known tracks, so what it writes is its own.',
     ('uplifting', 'Uplifting'),
     [('uplifting', 'Uplifting'), ('progressive', 'Progressive'), ('dream', 'Dream House'), ('acid', 'Acid'),
      ('deep', 'Deep')]),
]


def logo(src, dst):
    """The logo at 128 pixels (ffmpeg scales one that is larger)."""
    if shutil.which('ffmpeg'):
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-vf', "scale='min(128,iw)':-1", dst], check=True)
    else:
        shutil.copyfile(src, dst)


def section(name, genre, text, video, demos):
    e = html.escape
    rel = '%s/%s/releases' % (OWNER, name)
    dl = '%s/download/demos' % rel
    tracks = '\n'.join(
        '      <div class="track"><span>%s</span><audio controls preload="none" src="%s/%s.mp3"></audio></div>'
        % (e(t), dl, f) for f, t in demos)
    return '''  <section class="inst" id="%(id)s">
    <div>
      <div class="head"><img src="img/%(id)s.png" alt=""><div><h2>%(name)s</h2><div class="genre">%(genre)s</div></div></div>
      <p>%(text)s</p>
      <div class="links">
        <a class="primary" href="%(rel)s/latest">Download</a>
        <a href="%(repo)s">Source and manual</a>
        <a href="%(rel)s/tag/demos">All demos</a>
      </div>
    </div>
    <div>
      <video controls preload="none" poster="img/%(id)s-demo.jpg" src="%(dl)s/%(vf)s.mp4"></video>
      <div class="caption">%(vt)s, rendered by %(name)s; pictures by KaleidoscopeEnhanced. <a href="%(dl)s/%(vf)s.mp4">Open the video</a></div>
      <div class="tracks">
%(tracks)s
      </div>
    </div>
  </section>
''' % {'id': name.lower(), 'name': e(name), 'genre': e(genre), 'text': e(text), 'rel': rel, 'repo': '%s/%s' % (OWNER, name),
       'dl': dl, 'vf': video[0], 'vt': e(video[1]), 'tracks': tracks}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--vraudio', default=os.path.dirname(HERE), help='the folder holding the five repositories')
    a = ap.parse_args()
    img = os.path.join(HERE, 'img')
    os.makedirs(img, exist_ok=True)
    parts = []
    for name, folder, genre, logo_rel, text, video, demos in FAMILY:
        repo = os.path.join(a.vraudio, folder)
        logo(os.path.join(repo, logo_rel), os.path.join(img, name.lower() + '.png'))
        poster = os.path.join(repo, 'work', 'demos', video[0] + '.jpg')
        if os.path.exists(poster):
            shutil.copyfile(poster, os.path.join(img, name.lower() + '-demo.jpg'))
        parts.append(section(name, genre, text, video, demos))
    # The preview for links to the page (og:image): a strip of each poster side by side, 1200 x 630.
    posters = [os.path.join(img, n.lower() + '-demo.jpg') for n, *_ in FAMILY]
    if all(os.path.exists(p) for p in posters) and shutil.which('ffmpeg'):
        cmd = ['ffmpeg', '-v', 'error', '-y']
        for p in posters:
            cmd += ['-i', p]
        strips = ';'.join('[%d:v]scale=-2:630,crop=240:630[s%d]' % (i, i) for i in range(len(posters)))
        cmd += ['-filter_complex', strips + ';' + ''.join('[s%d]' % i for i in range(len(posters)))
                + 'hstack=inputs=%d' % len(posters), '-q:v', '3', os.path.join(img, 'og.jpg')]
        subprocess.run(cmd, check=True)
    page = open(os.path.join(HERE, 'page.html'), encoding='utf-8').read()
    with open(os.path.join(HERE, 'index.html'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(page.replace('@SECTIONS@\n', ''.join(parts)))
    print('wrote index.html (%d instruments)' % len(parts))


if __name__ == '__main__':
    main()
