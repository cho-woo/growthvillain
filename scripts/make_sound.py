"""Original, seamless 24-second stereo ambient pad; no sampled or reference music."""
from pathlib import Path
from array import array
import math, wave, json

root=Path(__file__).resolve().parents[1]
out=root/'audio';out.mkdir(exist_ok=True)
duration=24;rate=22050
frequencies=[round(f*duration)/duration for f in [55,82.4069,110,164.8138,196]]
samples=array('h')
for i in range(duration*rate):
    t=i/rate
    channels=[]
    for side in [0,1]:
        value=0
        for n,f in enumerate(frequencies):
            phase=n*.7+side*.21
            tremolo=.75+.25*math.sin(2*math.pi*(n%3+1)*t/duration+n)
            value+=math.sin(2*math.pi*f*t+phase)*tremolo*[.14,.065,.04,.025,.015][n]
        bell_phase=(t%6)/6
        bell=math.sin(2*math.pi*(round(329.6276*duration)/duration)*t+side*.3)*(math.sin(math.pi*bell_phase)**8)*.012
        channels.append(int(max(-1,min(1,value+bell))*32767))
    samples.extend(channels)
with wave.open(str(out/'decision-field-ambient.wav'),'wb') as f:
    f.setnchannels(2);f.setsampwidth(2);f.setframerate(rate);f.writeframes(samples.tobytes())
(out/'source.json').write_text(json.dumps({'title':'Decision Field — Ambient 01','method':'Original programmatic additive synthesis','duration_seconds':24,'sample_rate':rate,'channels':2,'loop':'Seamless integer-cycle oscillators and periodic envelopes','reference_music_sampled':False,'source_code':'scripts/make_sound.py','ui_tones_source':'js/sound.js'},indent=2)+'\n',encoding='utf-8')
print('Created original 24-second ambient loop.')
