#!/usr/bin/env python3
import argparse, math, wave
from pathlib import Path
import numpy as np

SR = 48000
BPM = 131.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT
BARS = 24
DURATION = BARS * BAR

NOTE = {
    'D2': 73.416, 'F2': 87.307, 'G2': 97.999, 'A2': 110.000, 'Bb2': 116.541, 'C3': 130.813,
    'D3': 146.832, 'F3': 174.614, 'G3': 195.998, 'A3': 220.000, 'Bb3': 233.082, 'C4': 261.626,
    'D4': 293.665, 'F4': 349.228, 'G4': 391.995, 'A4': 440.000, 'Bb4': 466.164, 'C5': 523.251,
    'D5': 587.330, 'F5': 698.456, 'G5': 783.991, 'A5': 880.000,
}


def adsr(n, attack=.01, decay=.08, sustain=.55, release=.12):
    env = np.ones(n, dtype=np.float32) * sustain
    a = min(n, int(attack * SR)); d = min(max(0, n-a), int(decay*SR)); r = min(n, int(release*SR))
    if a: env[:a] = np.linspace(0, 1, a, endpoint=False)
    if d: env[a:a+d] = np.linspace(1, sustain, d, endpoint=False)
    if r: env[-r:] *= np.linspace(1, 0, r, endpoint=False)
    return env


def saw(freq, n, phase=0.0):
    t = np.arange(n, dtype=np.float64) / SR
    x = np.zeros(n, dtype=np.float64)
    for h in range(1, 10):
        x += np.sin(2*np.pi*freq*h*t + phase) / h
    return (2/np.pi * x).astype(np.float32)


def sine(freq, n, phase=0.0):
    t = np.arange(n, dtype=np.float64) / SR
    return np.sin(2*np.pi*freq*t + phase).astype(np.float32)


def softclip(x, drive=1.0):
    return np.tanh(x * drive).astype(np.float32)


def add(buf, x, start, gain=1.0, pan=0.0):
    i = max(0, int(round(start * SR)))
    if i >= len(buf): return
    n = min(len(x), len(buf)-i)
    if n <= 0: return
    l = math.sqrt((1-pan)*0.5); r = math.sqrt((1+pan)*0.5)
    buf[i:i+n,0] += x[:n] * gain * l
    buf[i:i+n,1] += x[:n] * gain * r


def kick(dur=.30):
    n=int(dur*SR); t=np.arange(n)/SR
    f=48 + 105*np.exp(-t*32)
    phase=2*np.pi*np.cumsum(f)/SR
    body=np.sin(phase)*np.exp(-t*11)
    click=np.sin(2*np.pi*2200*t)*np.exp(-t*70)
    return softclip((body + .16*click).astype(np.float32), 1.7)


def snare(dur=.24, seed=1):
    n=int(dur*SR); t=np.arange(n)/SR; rng=np.random.default_rng(seed)
    noise=rng.normal(0,1,n).astype(np.float32)
    tone=np.sin(2*np.pi*190*t).astype(np.float32)
    env=np.exp(-t*17).astype(np.float32)
    return softclip((.55*noise+.45*tone)*env,1.1)


def hat(dur=.065, seed=1):
    n=int(dur*SR); t=np.arange(n)/SR; rng=np.random.default_rng(seed)
    noise=rng.normal(0,1,n).astype(np.float32)
    # crude high-pass by first difference
    hp=np.concatenate([[0], np.diff(noise)]).astype(np.float32)
    return (hp*np.exp(-t*48)).astype(np.float32)


def bass(freq, dur=.42, slide_to=None):
    n=int(dur*SR); t=np.arange(n)/SR
    if slide_to:
        f=np.linspace(freq, slide_to, n)
        phase=2*np.pi*np.cumsum(f)/SR
        x=np.sin(phase)
    else:
        x=np.sin(2*np.pi*freq*t)
    sub=np.sin(2*np.pi*(freq/2)*t)
    env=np.exp(-t*2.4)
    return softclip(((.86*x+.28*sub)*env).astype(np.float32),2.15)


def cowbell(freq, dur=.22):
    n=int(dur*SR); t=np.arange(n)/SR
    x=(np.sin(2*np.pi*freq*t)+.55*np.sin(2*np.pi*freq*1.48*t)+.28*np.sin(2*np.pi*freq*2.03*t))
    env=np.exp(-t*8.5)
    return softclip((x*env).astype(np.float32),1.4)


def pad(freqs, dur):
    n=int(dur*SR); x=np.zeros(n,dtype=np.float32)
    for j,f in enumerate(freqs):
        x += .24*saw(f,n,phase=j*.7) + .18*sine(f/2,n,phase=j*.4)
    # slow envelope + gentle low-pass by moving average
    e=np.sin(np.linspace(0,np.pi,n)).astype(np.float32)**.7
    x*=e
    k=41
    cs=np.cumsum(np.pad(x,(k,0)))
    lp=(cs[k:]-cs[:-k])/k
    return softclip(lp[:n].astype(np.float32),.8)


def pluck(freq, dur=.32):
    n=int(dur*SR); t=np.arange(n)/SR
    x=.7*saw(freq,n)+.3*sine(freq*2,n)
    env=np.exp(-t*9.5)
    return softclip((x*env).astype(np.float32),1.0)


def riser(dur):
    n=int(dur*SR); t=np.arange(n)/SR
    f=120 + 1400*(t/dur)**1.8
    phase=2*np.pi*np.cumsum(f)/SR
    x=np.sin(phase)*(t/dur)**1.6
    return (x*.22).astype(np.float32)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('output'); a=ap.parse_args()
    N=int(round(DURATION*SR)); buf=np.zeros((N,2),dtype=np.float32)

    # D-minor / dark-pop harmonic loop: Dm - Bb - C - Dm
    chords=[['D3','F3','A3'],['Bb2','D3','F3'],['C3','F3','G3'],['D3','F3','A3']]
    roots=['D2','Bb2','C3','D2']
    motif=['D5','F5','A5','G5','F5','D5','C5','D5']

    for bar in range(BARS):
        st=bar*BAR; section=('intro' if bar<4 else 'build' if bar<8 else 'drop1' if bar<16 else 'break' if bar<20 else 'drop2')
        chord=chords[bar%4]
        # harmonic bed in all sections, stronger in intro/break
        p=pad([NOTE[n] for n in chord], BAR*.98)
        add(buf,p,st,gain=.16 if section.startswith('drop') else .24,pan=-.08 if bar%2==0 else .08)

        # recognizable recurring melodic phrase: two-beat call/response motif
        if section in ('intro','build','break'):
            for k,nm in enumerate(motif[:4] if bar%2==0 else motif[4:]):
                add(buf,pluck(NOTE[nm],.30),st+(k*.5)*BEAT,gain=.12,pan=(-.25+.16*k))
        if section.startswith('drop'):
            for k,nm in enumerate(motif):
                add(buf,cowbell(NOTE[nm],.20),st+k*.5*BEAT,gain=.17,pan=(-.18 if k%2==0 else .18))

        # bassline and drums
        for beat in range(4):
            bt=st+beat*BEAT
            if section!='intro' or bar>=2:
                kg=.66 if section.startswith('drop') else .40
                add(buf,kick(),bt,gain=kg)
            if beat in (1,3) and section not in ('intro',):
                add(buf,snare(seed=bar*8+beat),bt,gain=.28 if section=='build' else .38)
            if section.startswith('drop'):
                root=NOTE[roots[bar%4]]
                add(buf,bass(root,.40,slide_to=root*.96 if beat==3 else None),bt,gain=.28)
            elif section=='build' and beat in (0,2):
                add(buf,bass(NOTE[roots[bar%4]],.36),bt,gain=.16)

        # hats: build gradually; full 8ths in drops, 16ths at endings
        if section=='build':
            subdiv=4 if bar>=6 else 2
            for q in range(4*subdiv):
                add(buf,hat(seed=1000+bar*32+q),st+q*(BEAT/subdiv),gain=.035+bar*.003,pan=.18 if q%2 else -.18)
        elif section.startswith('drop'):
            subdiv=4 if bar in (15,23) else 2
            for q in range(4*subdiv):
                add(buf,hat(seed=2000+bar*32+q),st+q*(BEAT/subdiv),gain=.055 if subdiv==2 else .038,pan=.22 if q%2 else -.22)
        elif section=='break' and bar>=18:
            for q in range(8):
                add(buf,hat(seed=3000+bar*16+q),st+q*(BEAT/2),gain=.03,pan=.2 if q%2 else -.2)

        # arrangement accents
        if bar in (7,19):
            add(buf,riser(BAR*.95),st,gain=.65)
        if bar in (8,20):
            add(buf,kick(.42),st,gain=.95)
            add(buf,cowbell(NOTE['D5'],.42),st,gain=.28)

    # Sidechain-like ducking around major kick positions in drop sections.
    # Keep musical transients punchy without random SFX/noise beds.
    peak=np.max(np.abs(buf))
    if peak>0: buf/=peak
    buf=softclip(buf,1.35)
    peak=np.max(np.abs(buf)); buf*=0.86/max(1e-9,peak)

    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    pcm=(np.clip(buf,-1,1)*32767).astype(np.int16)
    with wave.open(str(out),'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    print(f'generated={out} bpm={BPM} bars={BARS} duration={DURATION:.3f}s sr={SR}')

if __name__=='__main__': main()
