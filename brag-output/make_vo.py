"""Per-sentence Kokoro narration -> one wav per scene + vo-timing.json (sentence offsets).

Run from brag-output/:  python make_vo.py
"""
import json, os, shutil, subprocess, wave

HERE = os.path.dirname(os.path.abspath(__file__))
VO = os.path.join(HERE, "composition", "assets", "vo")
cfg = json.load(open(os.path.join(HERE, "vo_script.json"), encoding="utf-8"))
GAP, SPEED = cfg["gap"], cfg["speed"]
env = dict(os.environ, HYPERFRAMES_NO_TELEMETRY="1")
shutil.rmtree(VO, ignore_errors=True)
os.makedirs(os.path.join(VO, "seg"))
out = {}
for sc, lines in cfg["scenes"].items():
    files, offs, t = [], [], 0.0
    for i, line in enumerate(lines):
        f = os.path.join(VO, "seg", f"s{sc}_{i}.wav")
        subprocess.run(["npx.cmd", "hyperframes", "tts", line, "--voice", "af_heart", "--speed", str(SPEED),
                        "--output", f], check=True, env=env, capture_output=True)
        with wave.open(f) as w:
            d = w.getnframes() / w.getframerate()
        offs.append(round(t, 2)); files.append(f); t += d + GAP
    inputs, filt = [], []
    for i, f in enumerate(files):
        inputs += ["-i", f]
        filt.append(f"[{i}:a]apad=pad_dur={GAP if i < len(files) - 1 else 0}[a{i}]")
    filt.append("".join(f"[a{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=0:a=1[o]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filt),
                    "-map", "[o]", os.path.join(VO, f"s{sc}.wav")], check=True)
    out[sc] = {"offsets": offs, "total": round(t - GAP, 2)}
    print(sc, out[sc], flush=True)
json.dump(out, open(os.path.join(HERE, "vo-timing.json"), "w"), indent=1)
