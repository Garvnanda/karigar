"""Generates the Karigar brag composition (index.html + compositions/*.html).

Run from brag-output/:  python build.py
Scene timing is driven by the narration clips in composition/assets/vo (see vo-timing.json).
"""
import json, os, struct, subprocess, math

HERE = os.path.dirname(os.path.abspath(__file__))
COMP = os.path.join(HERE, "composition")
VO = os.path.join(COMP, "assets", "vo")

# ---------------------------------------------------------------- timing
DUR = [17, 17, 14, 14, 29, 20, 17, 19, 12, 18, 26, 11]
VO_LEAD = [2.5] + [1.0] * 11
STARTS = [sum(DUR[:i]) for i in range(len(DUR))]
TOTAL = sum(DUR)
VOT = json.load(open(os.path.join(HERE, "vo-timing.json")))


def vo_len(i):
    out = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0",
                          os.path.join(VO, f"s{i:02d}.wav")], capture_output=True, text=True).stdout
    return float(out.strip())


VOLEN = [vo_len(i + 1) for i in range(12)]


def off(scene, k):
    """Local time (in scene) when sentence k of scene's narration starts."""
    return round(VO_LEAD[scene - 1] + VOT[f"{scene:02d}"]["offsets"][k], 2)


# ---------------------------------------------------------------- palette
GROUND, INK, GOLD, GOLD_D, RUBY, EMERALD, MUTED = ("#120D0A", "#F3E9D6", "#E0B25A", "#9C7230",
                                                    "#C24B58", "#3FA37C", "#A89A84")

SHARED_CSS = f"""
  #root {{ position:absolute; inset:0; color:{INK}; font-family:'EB Garamond', serif; }}
  .stage {{ position:absolute; inset:0; }}
  .hero {{ font-family:'Playfair Display', serif; font-weight:900; text-transform:uppercase;
           letter-spacing:0.02em; color:{INK}; text-align:center; line-height:1.04; }}
  .gold {{ color:{GOLD}; }}
  .ruby {{ color:{RUBY}; }}
  .emerald {{ color:{EMERALD}; }}
  .mono {{ font-family:'IBM Plex Mono', monospace; }}
  .kicker {{ font-family:'IBM Plex Mono', monospace; font-size:28px; letter-spacing:0.28em;
             text-transform:uppercase; color:{GOLD}; text-align:center; }}
  .lead {{ font-family:'EB Garamond', serif; font-style:italic; font-size:44px; color:{INK};
           text-align:center; }}
  .abs {{ position:absolute; }}
  .cx {{ left:0; right:0; }}
  .bubble {{ position:absolute; border-radius:28px; padding:28px 40px; font-family:'IBM Plex Mono', monospace;
             font-size:38px; line-height:1.35; }}
  .b-cust {{ background:#2A211A; color:{INK}; border:2px solid #4A3B2C; }}
  .b-bot {{ background:#1B1511; color:{INK}; border:2px solid {GOLD_D}; }}
  .who {{ font-family:'IBM Plex Mono', monospace; font-size:28px; letter-spacing:0.2em; text-transform:uppercase;
          color:{MUTED}; margin-bottom:10px; }}
  .chip {{ display:inline-block; padding:14px 30px; border-radius:999px; border:2px solid {GOLD_D};
           font-family:'IBM Plex Mono', monospace; font-size:28px; color:{INK}; background:#1B1511; }}
"""

# ---------------------------------------------------------------- svg art


def grad(p):
    return f"""<defs>
  <linearGradient id="{p}-g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#FFE7A8"/><stop offset="0.35" stop-color="{GOLD}"/>
    <stop offset="0.7" stop-color="{GOLD_D}"/><stop offset="1" stop-color="#F6CF77"/>
  </linearGradient>
  <radialGradient id="{p}-orb" cx="0.4" cy="0.35" r="0.7">
    <stop offset="0" stop-color="#FFF4CF"/><stop offset="0.45" stop-color="{GOLD}"/><stop offset="1" stop-color="#6B4A1C"/>
  </radialGradient>
</defs>"""


def kangan(p, cx, cy, r, sid, w=16):
    c = 2 * math.pi * r
    return (f'<g id="{sid}"><circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="url(#{p}-g)" stroke-width="{w}" '
            f'stroke-dasharray="{c:.1f}" stroke-dashoffset="{c:.1f}" class="draw" stroke-linecap="round"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r - w * 0.55}" fill="none" stroke="#FFE7A8" stroke-opacity="0.35" '
            f'stroke-width="2"/></g>')


def beaded_kada(p, cx, cy, r, sid, n=28, bead=13, band=20, beads_cls="bead"):
    out = [f'<g id="{sid}"><circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="url(#{p}-g)" stroke-width="{band}"/>']
    for k in range(n):
        a = 2 * math.pi * k / n
        out.append(f'<circle class="{beads_cls}" cx="{cx + (r + band * 0.2) * math.cos(a):.1f}" '
                   f'cy="{cy + (r + band * 0.2) * math.sin(a):.1f}" r="{bead}" fill="url(#{p}-orb)"/>')
    out.append("</g>")
    return "".join(out)


def chain(p, x0, y0, length, sid, links=22):
    out = [f'<g id="{sid}">']
    for k in range(links):
        x = x0 + k * length / links
        y = y0 + 60 * math.sin(k / links * math.pi * 1.6)
        rot = 30 if k % 2 else -30
        out.append(f'<ellipse class="link" cx="{x:.1f}" cy="{y:.1f}" rx="16" ry="9" fill="none" stroke="url(#{p}-g)" '
                   f'stroke-width="5" transform="rotate({rot} {x:.1f} {y:.1f})"/>')
    out.append("</g>")
    return "".join(out)


def solitaire(p, cx, cy, s, sid):
    return (f'<g id="{sid}"><ellipse cx="{cx}" cy="{cy + 40 * s}" rx="{90 * s}" ry="{34 * s}" fill="none" '
            f'stroke="url(#{p}-g)" stroke-width="{14 * s}"/>'
            f'<polygon points="{cx - 34 * s},{cy - 8 * s} {cx},{cy - 48 * s} {cx + 34 * s},{cy - 8 * s} {cx},{cy + 22 * s}" '
            f'fill="#EAF4FF" stroke="#BFD8F0" stroke-width="{2 * s}"/>'
            f'<polyline points="{cx - 34 * s},{cy - 8 * s} {cx},{cy - 2 * s} {cx + 34 * s},{cy - 8 * s}" fill="none" '
            f'stroke="#9DBAD6" stroke-width="{2 * s}"/>'
            f'<path d="M{cx - 26 * s},{cy + 8 * s} L{cx - 14 * s},{cy + 24 * s} M{cx + 26 * s},{cy + 8 * s} '
            f'L{cx + 14 * s},{cy + 24 * s}" stroke="url(#{p}-g)" stroke-width="{6 * s}"/></g>')


def lotus(p, cx, cy, s, sid):
    petals = []
    for ang in (-60, -30, 0, 30, 60):
        petals.append(f'<path d="M{cx},{cy} C{cx - 26 * s},{cy - 50 * s} {cx - 14 * s},{cy - 96 * s} {cx},{cy - 110 * s} '
                      f'C{cx + 14 * s},{cy - 96 * s} {cx + 26 * s},{cy - 50 * s} {cx},{cy} Z" fill="url(#{p}-g)" '
                      f'fill-opacity="0.92" stroke="#FFE7A8" stroke-opacity="0.5" stroke-width="{1.5 * s}" '
                      f'transform="rotate({ang} {cx} {cy})"/>')
    return (f'<g id="{sid}"><circle cx="{cx}" cy="{cy - 150 * s}" r="{14 * s}" fill="none" stroke="url(#{p}-g)" '
            f'stroke-width="{6 * s}"/>{"".join(petals)}'
            f'<circle cx="{cx}" cy="{cy - 6 * s}" r="{13 * s}" fill="{RUBY}"/></g>')


def scale_svg(p, cx, cy, sid):
    return (f'<g id="{sid}-base"><path d="M{cx},{cy} L{cx},{cy + 300}" stroke="{GOLD}" stroke-width="10"/>'
            f'<path d="M{cx - 110},{cy + 310} L{cx + 110},{cy + 310}" stroke="{GOLD}" stroke-width="14" '
            f'stroke-linecap="round"/><circle cx="{cx}" cy="{cy}" r="16" fill="url(#{p}-orb)"/></g>'
            f'<g id="{sid}-beam">'
            f'<path d="M{cx - 330},{cy} L{cx + 330},{cy}" stroke="{GOLD}" stroke-width="10" stroke-linecap="round"/>'
            f'<path d="M{cx - 330},{cy} L{cx - 400},{cy + 170} M{cx - 330},{cy} L{cx - 260},{cy + 170}" '
            f'stroke="{GOLD_D}" stroke-width="3"/>'
            f'<path d="M{cx + 330},{cy} L{cx + 260},{cy + 170} M{cx + 330},{cy} L{cx + 400},{cy + 170}" '
            f'stroke="{GOLD_D}" stroke-width="3"/>'
            f'<path d="M{cx - 420},{cy + 170} Q{cx - 330},{cy + 240} {cx - 240},{cy + 170} Z" fill="url(#{p}-g)"/>'
            f'<path d="M{cx + 240},{cy + 170} Q{cx + 330},{cy + 240} {cx + 420},{cy + 170} Z" fill="url(#{p}-g)"/>'
            f'</g>')


ICONS = {
    "chat": '<path d="M20 22 h80 a12 12 0 0 1 12 12 v40 a12 12 0 0 1 -12 12 h-46 l-20 18 v-18 h-14 a12 12 0 0 1 -12 -12 v-40 a12 12 0 0 1 12 -12z" fill="none" stroke="currentColor" stroke-width="6"/>',
    "scale": '<path d="M60 20 v80 M30 104 h60 M14 40 h92 M14 40 l-10 30 h20 z M106 40 l-10 30 h20 z" fill="none" stroke="currentColor" stroke-width="6" stroke-linejoin="round"/>',
    "pen": '<path d="M24 96 l10 -30 l50 -50 l20 20 l-50 50 z M74 26 l20 20" fill="none" stroke="currentColor" stroke-width="6" stroke-linejoin="round"/>',
    "fire": '<path d="M60 108 c-26 0 -40 -18 -40 -38 c0 -22 20 -30 22 -52 c14 12 18 26 16 38 c8 -6 10 -14 10 -22 c14 12 32 30 32 40 c0 22 -14 34 -40 34z" fill="none" stroke="currentColor" stroke-width="6" stroke-linejoin="round"/>',
    "camera": '<path d="M14 38 h22 l10 -14 h28 l10 14 h22 v62 h-92 z" fill="none" stroke="currentColor" stroke-width="6" stroke-linejoin="round"/><circle cx="60" cy="68" r="18" fill="none" stroke="currentColor" stroke-width="6"/>',
    "shop": '<path d="M16 50 l10 -30 h68 l10 30 M20 50 v54 h80 v-54 M16 50 h88 M48 104 v-30 h24 v30" fill="none" stroke="currentColor" stroke-width="6" stroke-linejoin="round"/>',
    "heart": '<path d="M60 104 l-40 -40 a22 22 0 0 1 40 -30 a22 22 0 0 1 40 30 z" fill="none" stroke="currentColor" stroke-width="6" stroke-linejoin="round"/>',
    "anvil": '<path d="M14 36 h76 c0 14 10 22 22 22 v8 h-36 l-8 16 h14 v16 h-60 v-16 h14 l-8 -16 h-14 z" fill="none" stroke="currentColor" stroke-width="6" stroke-linejoin="round"/>',
    "room": '<circle cx="60" cy="62" r="22" fill="none" stroke="currentColor" stroke-width="6"/><circle cx="60" cy="20" r="8" fill="currentColor"/><circle cx="102" cy="52" r="8" fill="currentColor"/><circle cx="86" cy="100" r="8" fill="currentColor"/><circle cx="34" cy="100" r="8" fill="currentColor"/><circle cx="18" cy="52" r="8" fill="currentColor"/>',
    "phone": '<rect x="32" y="10" width="56" height="100" rx="10" fill="none" stroke="currentColor" stroke-width="6"/><circle cx="60" cy="60" r="14" fill="none" stroke="currentColor" stroke-width="5"/><path d="M50 50 l10 -10 l10 10" fill="none" stroke="currentColor" stroke-width="4"/>',
    "feather": '<path d="M30 100 l60 -60 M86 14 c-40 4 -60 30 -60 70 c40 0 66 -20 70 -60 z" fill="none" stroke="currentColor" stroke-width="6" stroke-linejoin="round"/>',
    "dial": '<path d="M16 86 a44 44 0 0 1 88 0" fill="none" stroke="currentColor" stroke-width="6"/><path d="M60 86 l26 -30" stroke="currentColor" stroke-width="6" stroke-linecap="round"/><circle cx="60" cy="86" r="7" fill="currentColor"/>',
    "gear": '<circle cx="60" cy="60" r="20" fill="none" stroke="currentColor" stroke-width="6"/><path d="M60 14 v16 M60 90 v16 M14 60 h16 M90 60 h16 M27 27 l11 11 M82 82 l11 11 M27 93 l11 -11 M82 38 l11 -11" stroke="currentColor" stroke-width="7" stroke-linecap="round"/>',
    "file": '<path d="M28 12 h44 l22 22 v74 h-66 z M72 12 v22 h22" fill="none" stroke="currentColor" stroke-width="6" stroke-linejoin="round"/>',
    "card": '<rect x="16" y="24" width="88" height="72" rx="8" fill="none" stroke="currentColor" stroke-width="6"/><path d="M30 46 h44 M30 62 h60 M30 78 h36" stroke="currentColor" stroke-width="5"/>',
    "cube": '<path d="M60 12 l42 22 v50 l-42 22 l-42 -22 v-50 z M18 34 l42 22 l42 -22 M60 56 v50" fill="none" stroke="currentColor" stroke-width="6" stroke-linejoin="round"/>',
}


def icon(name, size=96, color=GOLD, extra=""):
    return (f'<svg viewBox="0 0 120 120" width="{size}" height="{size}" style="color:{color}" {extra}>'
            f'{ICONS[name]}</svg>')


# ---------------------------------------------------------------- scene helpers


def scene(sid, dur, body, script, css=""):
    return f"""<template>
  <style>
{SHARED_CSS}
{css}
  </style>
  <div id="root" data-composition-id="{sid}" data-width="1920" data-height="1080">
    <div id="{sid}-stage" class="stage">
{body}
    </div>
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    const S = "#{sid}-stage";
    // scene in: slow scale settle (cinematic), out: blur + fade
    tl.fromTo(S, {{ opacity: 0, scale: 0.97 }}, {{ opacity: 1, scale: 1, duration: 0.9, ease: "power2.out" }}, 0);
{script}
    tl.to(S, {{ opacity: 0, filter: "blur(8px)", duration: 0.5, ease: "power3.in" }}, {dur - 0.6});
    window.__timelines["{sid}"] = tl;
  </script>
</template>
"""


def words_in(sel, t, dur=0.5):
    """Blur-in of a whole line."""
    return (f'    tl.fromTo("{sel}", {{ opacity: 0, filter: "blur(10px)" }}, '
            f'{{ opacity: 1, filter: "blur(0px)", duration: {dur}, ease: "expo.out" }}, {t});\n')


def rise_in(sel, t, dy=30, dur=0.7):
    return (f'    tl.fromTo("{sel}", {{ opacity: 0, y: {dy} }}, '
            f'{{ opacity: 1, y: 0, duration: {dur}, ease: "expo.out" }}, {t});\n')


def fade_out(sel, t, dur=0.35):
    return f'    tl.to("{sel}", {{ opacity: 0, filter: "blur(6px)", duration: {dur}, ease: "power3.in" }}, {t});\n'


def per_word(container_id, text, cls=""):
    return "".join(f'<span class="w {cls}" style="display:inline-block;opacity:0">{w}&nbsp;</span>'
                   for w in text.split())


def word_stagger(container_id, t, step=0.09):
    return (f'    tl.fromTo("#{container_id} .w", {{ opacity: 0, filter: "blur(6px)" }}, '
            f'{{ opacity: 1, filter: "blur(0px)", duration: 0.25, ease: "power4.out", stagger: {step} }}, {t});\n')


def typed(text):
    # chars of a word stay together; real spaces between words let the line wrap
    return " ".join('<span style="white-space:nowrap">' + "".join(f'<span class="ch" style="opacity:0">{c}</span>' for c in w)
                    + "</span>" for w in text.split(" "))


def type_on(container_id, t0, t1):
    return (f'    tl.fromTo("#{container_id} .ch", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.01, '
            f'stagger: {{ amount: {round(t1 - t0, 2)} }} }}, {t0});\n')


SFX = []  # (abs_time, file, vol)


def flen(f):
    out = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0",
                          os.path.join(COMP, "assets", "sfx", f)], capture_output=True, text=True).stdout
    return round(float(out.strip()) - 0.005, 2)


def sfx(scene_i, t, f, vol=0.55):
    SFX.append((round(STARTS[scene_i - 1] + t, 2), f, vol))


def typing_sfx(scene_i, t0, t1, n=10):
    keys = ["keypress-003.wav", "keypress-007.wav", "keypress-012.wav", "keypress-018.wav", "keypress-025.wav"]
    for k in range(n):
        sfx(scene_i, t0 + (t1 - t0) * k / n, keys[k % len(keys)], 0.32)


# ---------------------------------------------------------------- scenes
scenes = {}

# 1 — Drawer (hook)
p = "s1"
c1 = 2 * math.pi * 170
body = f"""
      <div id="s1-t" class="hero abs cx" style="top:380px;font-size:104px">In every home,<br/><span class="gold">there is a drawer.</span></div>
      <svg class="abs" style="left:0;top:0" width="1920" height="1080" viewBox="0 0 1920 1080">{grad(p)}
        {kangan(p, 640, 470, 170, "s1-kangan")}
        {chain(p, 1080, 430, 560, "s1-chain")}
      </svg>
      <div id="s1-l1" class="lead abs" style="left:390px;width:500px;top:700px">a grandmother's kangan</div>
      <div id="s1-l2" class="lead abs" style="left:1060px;width:600px;top:700px">a chain from a wedding, long ago</div>
      <div id="s1-story" data-hold class="hero abs cx" style="top:860px;font-size:58px">Gold that carries <span class="gold">a story.</span></div>
"""
script = (words_in("#s1-t", 0.8, 0.9) + fade_out("#s1-t", 6.3, 0.5)
          + f'    tl.fromTo("#s1-kangan .draw", {{ attr: {{ "stroke-dashoffset": {c1:.1f} }} }}, '
            f'{{ attr: {{ "stroke-dashoffset": 0 }}, duration: 1.6, ease: "power2.inOut" }}, 6.8);\n'
          + rise_in("#s1-l1", 7.6)
          + '    tl.fromTo("#s1-chain .link", { opacity: 0, scale: 0.4, transformOrigin: "50% 50%" }, '
            '{ opacity: 1, scale: 1, duration: 0.35, ease: "expo.out", stagger: 0.045 }, 8.5);\n'
          + rise_in("#s1-l2", 9.3)
          + words_in("#s1-story", 10.6, 0.8))
scenes["s1"] = scene("s1", DUR[0], body, script)
sfx(1, 0.8, "impactSoft_medium_000.ogg", 0.5)
sfx(1, 6.8, "impactGlass_light_002.ogg", 0.4)

# 2 — The guess
p = "s2"
body = f"""
      <div id="s2-k" class="kicker abs cx" style="top:110px">Old gold &rarr; new piece</div>
      <svg class="abs" style="left:0;top:0" width="1920" height="1080" viewBox="0 0 1920 1080">{grad(p)}
        {scale_svg(p, 960, 250, "s2-sc")}
      </svg>
      <div id="s2-q1" class="chip abs" style="left:300px;top:560px">+ add more gold?</div>
      <div id="s2-q2" class="chip abs" style="left:1340px;top:560px">&minus; take some back?</div>
      <div id="s2-guess" class="lead abs cx" style="top:680px;color:{MUTED}">The new design weighs whatever it weighs.</div>
      <div id="s2-t" class="hero abs cx" style="top:780px;font-size:96px">Gold is exact.<br/><span class="gold">Design never was.</span></div>
"""
script = (words_in("#s2-k", 0.6)
          + '    tl.fromTo("#s2-sc-base, #s2-sc-beam", { opacity: 0 }, { opacity: 1, duration: 0.8, ease: "power2.out" }, 1.0);\n'
          + rise_in("#s2-guess", 5.2)
          # back-and-forth tilts (no loops: explicit tweens)
          + '    tl.fromTo("#s2-sc-beam", { rotation: 0, svgOrigin: "960 250" }, { rotation: -9, svgOrigin: "960 250", duration: 1.0, ease: "power2.inOut" }, 7.8);\n'
          + '    tl.to("#s2-sc-beam", { rotation: 7, svgOrigin: "960 250", duration: 1.1, ease: "power2.inOut" }, 8.9);\n'
          + '    tl.to("#s2-sc-beam", { rotation: -5, svgOrigin: "960 250", duration: 1.1, ease: "power2.inOut" }, 10.0);\n'
          + '    tl.to("#s2-sc-beam", { rotation: 3, svgOrigin: "960 250", duration: 1.0, ease: "power2.inOut" }, 11.1);\n'
          + rise_in("#s2-q1", 10.0) + rise_in("#s2-q2", 10.9)
          + fade_out("#s2-guess", 11.8, 0.3)
          + words_in("#s2-t", 12.2, 0.7))
scenes["s2"] = scene("s2", DUR[1], body, script)
sfx(2, 10.0, "drop_001.ogg", 0.45)
sfx(2, 10.9, "drop_002.ogg", 0.45)
sfx(2, 12.2, "impactSoft_medium_002.ogg", 0.5)

# 3 — Reveal
letters = "".join(f'<span class="L" style="display:inline-block;opacity:0">{c}</span>' for c in "KARIGAR")
body = f"""
      <div id="s3-until" class="lead abs cx" style="top:300px">Until now.</div>
      <div id="s3-word" class="hero abs cx gold" style="top:390px;font-size:220px;letter-spacing:0.08em">{letters}</div>
      <div id="s3-rule" class="abs" style="left:660px;top:660px;width:600px;height:3px;background:{GOLD};transform-origin:50% 50%"></div>
      <div id="s3-tag" class="lead abs cx" style="top:700px;font-size:52px">An AI artisan for anything that gets made.</div>
      <div id="s3-pack" class="kicker abs cx" style="top:820px">Flagship pack &middot; The Jeweller's Shop</div>
"""
script = (words_in("#s3-until", 1.0) + fade_out("#s3-until", 2.0, 0.3)
          + '    tl.fromTo("#s3-word .L", { opacity: 0.0, filter: "blur(14px)", y: 20 }, '
            '{ opacity: 1, filter: "blur(0px)", y: 0, duration: 0.6, ease: "expo.out", stagger: 0.1 }, 2.3);\n'
          + '    tl.fromTo("#s3-rule", { scaleX: 0 }, { scaleX: 1, duration: 0.9, ease: "power2.inOut" }, 3.4);\n'
          + words_in("#s3-tag", 4.2, 0.8) + rise_in("#s3-pack", 6.4))
scenes["s3"] = scene("s3", DUR[2], body, script)
sfx(3, 2.3, "impactBell_heavy_000.ogg", 0.55)

# 4 — The request
REQ = "Nani ka purana 18.4g 22K kangan hai, naya beaded kada banana hai"
body = f"""
      <div id="s4-k" class="kicker abs cx" style="top:150px">At the counter</div>
      <div id="s4-b" class="bubble b-cust" style="left:310px;top:300px;width:1300px">
        <div class="who">Customer</div><div id="s4-type">{typed(REQ)}</div>
      </div>
      <div id="s4-tr" class="lead abs cx" style="top:600px;color:{MUTED}">&ldquo;Nani's old 22K kangan &mdash; make it into a new beaded kada.&rdquo;</div>
      <div id="s4-no" class="hero abs cx" style="top:760px;font-size:76px">No forms. No menus.<br/><span class="gold">Just a sentence.</span></div>
"""
script = (words_in("#s4-k", 0.6) + rise_in("#s4-b", 1.4, 24, 0.6) + type_on("s4-type", 2.0, 5.8)
          + words_in("#s4-tr", 6.2, 0.7) + words_in("#s4-no", 8.0, 0.7))
scenes["s4"] = scene("s4", DUR[3], body, script)
sfx(4, 1.4, "select_008.ogg", 0.4)
typing_sfx(4, 2.0, 5.8, 14)

# 5 — Five agents
AGENTS = [("Sakhi", "Counter", "chat", "Understands the request. Asks when something is missing."),
          ("Jauhari", "Gold desk", "scale", "Turns old gold into one target weight. Refuses the impossible."),
          ("Naqqash", "Design studio", "pen", "Proposes three design variants."),
          ("Karigar", "Workshop", "anvil", "Shapes each design to the gold. Checks it can be cast."),
          ("Chitrakar", "Photo studio", "camera", "Catalog renders and a model for AR.")]
cards = []
for i, (n, z, ic, job) in enumerate(AGENTS):
    x = 110 + i * 350
    cards.append(f"""      <div id="s5-c{i}" class="abs agent" style="left:{x}px;top:300px;width:320px;height:480px">
        <div class="ag-in">
          {icon(ic, 104)}
          <div class="ag-zone">{z}</div>
          <div class="ag-name">{n}</div>
          <div class="ag-job">{job}</div>
        </div>
      </div>""")
css5 = f"""
  .agent {{ border:2px solid #3A2E22; border-radius:26px; background:#18120E; }}
  .ag-in {{ padding:44px 30px; display:flex; flex-direction:column; align-items:flex-start; gap:18px; }}
  .ag-zone {{ font-family:'IBM Plex Mono', monospace; font-size:28px; letter-spacing:0.08em; text-transform:uppercase; color:{GOLD}; }}
  .ag-name {{ font-family:'Playfair Display', serif; font-weight:900; font-size:52px; }}
  .ag-job {{ font-family:'EB Garamond', serif; font-size:30px; line-height:1.3; color:{INK}; }}
"""
body = f"""
      <div id="s5-k" data-hold class="kicker abs cx" style="top:120px">One order &middot; five agents</div>
      <div id="s5-t" class="hero abs cx" style="top:170px;font-size:64px">The shop floor</div>
{chr(10).join(cards)}
      <div id="s5-line" class="abs" style="left:110px;top:840px;width:1720px;height:4px;background:{GOLD};transform-origin:0 50%"></div>
      <div id="s5-dot" class="abs" style="left:96px;top:828px;width:28px;height:28px;border-radius:50%;background:{GOLD}"></div>
"""
script = words_in("#s5-k", 0.6) + words_in("#s5-t", 1.0)
script += '    tl.fromTo("#s5-stage .agent", { opacity: 0, y: 40 }, { opacity: 0.28, y: 0, duration: 0.7, ease: "expo.out", stagger: 0.08 }, 1.6);\n'
script += '    tl.fromTo("#s5-line", { scaleX: 0 }, { scaleX: 0, duration: 0.01 }, 0);\n'
for i in range(5):
    t = off(5, i + 1) - 0.15
    script += (f'    tl.to("#s5-c{i}", {{ opacity: 1, y: -14, borderColor: "{GOLD}", duration: 0.6, ease: "expo.out" }}, {t});\n'
               f'    tl.to("#s5-line", {{ scaleX: {(i + 1) / 5:.2f}, duration: 0.8, ease: "power2.inOut" }}, {t});\n'
               f'    tl.to("#s5-dot", {{ x: {(i + 1) / 5 * 1720 - 14:.0f}, duration: 0.8, ease: "power2.inOut" }}, {t});\n')
    sfx(5, t, "drop_001.ogg" if i % 2 == 0 else "drop_002.ogg", 0.42)
scenes["s5"] = scene("s5", DUR[4], body, script, css5)

# 6 — The magic
p = "s6"
body = f"""
      <div id="s6-t" class="hero abs cx" style="top:110px;font-size:72px">The design bends <span class="gold">to the gold.</span></div>
      <svg class="abs" style="left:0;top:0" width="1920" height="1080" viewBox="0 0 1920 1080">{grad(p)}
        {kangan(p, 960, 500, 190, "s6-old", 14)}
        <circle id="s6-orb" cx="960" cy="500" r="90" fill="url(#{p}-orb)"/>
        {beaded_kada(p, 960, 500, 200, "s6-new", 30, 15, 26, "s6b")}
      </svg>
      <div id="s6-lab" class="kicker abs cx" style="top:740px">your gold</div>
      <div id="s6-bars" class="abs" style="left:560px;top:790px;width:800px">
        <div class="barrow"><span class="bl">Old gold</span><div class="bar"><div id="s6-b1" class="fill"></div></div></div>
        <div class="barrow"><span class="bl">New kada</span><div class="bar"><div id="s6-b2" class="fill"></div></div></div>
      </div>
      <div id="s6-g" class="hero abs cx gold" style="top:830px;font-size:110px">Gram for gram.</div>
"""
css6 = f"""
  .barrow {{ display:flex; align-items:center; gap:24px; margin:12px 0; }}
  .bl {{ width:220px; font-family:'IBM Plex Mono', monospace; font-size:28px; color:{MUTED}; text-transform:uppercase; letter-spacing:0.15em; }}
  .bar {{ flex:1; height:22px; border-radius:11px; background:#2A211A; overflow:hidden; }}
  .fill {{ width:100%; height:100%; background:{GOLD}; transform-origin:0 50%; }}
"""
c6 = 2 * math.pi * 190
script = (f'    tl.fromTo("#s6-old .draw", {{ attr: {{ "stroke-dashoffset": {c6:.1f} }} }}, {{ attr: {{ "stroke-dashoffset": 0 }}, duration: 1.0, ease: "power2.inOut" }}, 0.5);\n'
          + '    tl.fromTo("#s6-orb", { scale: 0, opacity: 0, svgOrigin: "960 500" }, { scale: 0, opacity: 0, svgOrigin: "960 500", duration: 0.01 }, 0);\n'
          + '    tl.fromTo("#s6-new", { opacity: 0 }, { opacity: 0, duration: 0.01 }, 0);\n'
          + '    tl.fromTo("#s6-lab, #s6-bars, #s6-g", { opacity: 0 }, { opacity: 0, duration: 0.01 }, 0);\n'
          + words_in("#s6-t", off(6, 1), 0.8)
          # melt: kangan collapses into an orb
          + f'    tl.to("#s6-old", {{ scale: 0.3, opacity: 0, svgOrigin: "960 500", duration: 1.2, ease: "power3.in" }}, {off(6, 1) + 0.6});\n'
          + f'    tl.to("#s6-orb", {{ scale: 1, opacity: 1, svgOrigin: "960 500", duration: 1.0, ease: "expo.out" }}, {off(6, 1) + 1.5});\n'
          + f'    tl.to("#s6-lab", {{ opacity: 1, duration: 0.5 }}, {off(6, 1) + 1.9});\n'
          # reshape: orb flows into the new kada
          + f'    tl.to("#s6-lab", {{ opacity: 0, duration: 0.3 }}, {off(6, 2) - 0.2});\n'
          + f'    tl.to("#s6-new", {{ opacity: 1, duration: 0.6 }}, {off(6, 2)});\n'
          + f'    tl.fromTo("#s6-new circle", {{ opacity: 0, scale: 0.3, transformOrigin: "50% 50%" }}, {{ opacity: 1, scale: 1, duration: 0.4, ease: "expo.out", stagger: 0.04 }}, {off(6, 2)});\n'
          + f'    tl.to("#s6-orb", {{ scale: 0.15, opacity: 0, svgOrigin: "960 500", duration: 1.4, ease: "power2.in" }}, {off(6, 2) + 0.3});\n'
          + f'    tl.to("#s6-bars", {{ opacity: 1, duration: 0.4 }}, {off(6, 2) + 1.6});\n'
          + f'    tl.fromTo("#s6-b1", {{ scaleX: 0 }}, {{ scaleX: 1, duration: 1.0, ease: "power2.out" }}, {off(6, 2) + 1.8});\n'
          + f'    tl.fromTo("#s6-b2", {{ scaleX: 0 }}, {{ scaleX: 1, duration: 1.6, ease: "power3.out" }}, {off(6, 2) + 2.4});\n'
          + f'    tl.to("#s6-bars", {{ opacity: 0, filter: "blur(6px)", duration: 0.3 }}, {off(6, 3) - 0.4});\n'
          + f'    tl.fromTo("#s6-g", {{ opacity: 0, filter: "blur(12px)", scale: 1.06 }}, {{ opacity: 1, filter: "blur(0px)", scale: 1, duration: 0.7, ease: "expo.out" }}, {off(6, 3) + 1.6});\n')
scenes["s6"] = scene("s6", DUR[5], body, script, css6)
sfx(6, off(6, 1) + 1.5, "impactSoft_medium_000.ogg", 0.45)
sfx(6, off(6, 2), "impactGlass_light_002.ogg", 0.4)
sfx(6, off(6, 3) + 1.6, "impactBell_heavy_000.ogg", 0.45)

# 7 — What comes out
p = "s7"
var_cards = []
for i, (nb, bead, band) in enumerate([(28, 13, 20), (40, 8, 14), (18, 18, 26)]):
    x = 300 + i * 460
    var_cards.append(f"""      <div id="s7-v{i}" class="abs vcard" style="left:{x}px;top:250px;width:400px;height:380px">
        <svg width="400" height="300" viewBox="0 0 400 300">{grad(f"s7v{i}")}{beaded_kada(f"s7v{i}", 200, 150, 95, f"s7-k{i}", nb, bead, band, "b")}</svg>
        <div class="vlab">Variant {i + 1}</div>
      </div>""")
DELIV = [("camera", "Catalog renders"), ("file", "Casting file"), ("phone", "AR model"), ("card", "Job card")]
chips = "".join(f'<div id="s7-d{i}" class="dchip">{icon(ic, 44)}<span>{lab}</span></div>' for i, (ic, lab) in enumerate(DELIV))
css7 = f"""
  .vcard {{ border:2px solid #3A2E22; border-radius:26px; background:#18120E; text-align:center; }}
  .vlab {{ font-family:'IBM Plex Mono', monospace; font-size:28px; letter-spacing:0.25em; text-transform:uppercase; color:{GOLD}; }}
  #s7-row {{ position:absolute; left:0; right:0; top:720px; display:flex; justify-content:center; gap:28px; }}
  .dchip {{ display:flex; align-items:center; gap:16px; padding:18px 32px; border-radius:999px; border:2px solid {GOLD_D};
            background:#1B1511; font-family:'IBM Plex Mono', monospace; font-size:30px; }}
"""
body = f"""
      <div id="s7-t" class="hero abs cx" style="top:110px;font-size:64px">In minutes, the shop has <span class="gold">everything.</span></div>
{chr(10).join(var_cards)}
      <div id="s7-row">{chips}</div>
      <div id="s7-sub" class="lead abs cx" style="top:880px;color:{MUTED}">every variant solved to the same gold</div>
"""
script = words_in("#s7-t", off(7, 0), 0.7)
for i in range(3):
    t = off(7, 1) + i * 0.35
    script += f'    tl.fromTo("#s7-v{i}", {{ opacity: 0, x: 120, rotation: 4 }}, {{ opacity: 1, x: 0, rotation: 0, duration: 0.7, ease: "expo.out" }}, {t});\n'
    sfx(7, t, "card-slide-2.ogg" if i == 0 else f"card-place-{i}.ogg", 0.45)
for i in range(4):
    t = off(7, i + 2) - 0.1
    script += rise_in(f"#s7-d{i}", t, 24, 0.6)
    sfx(7, t, f"card-place-{(i % 3) + 1}.ogg", 0.4)
script += words_in("#s7-sub", off(7, 5) + 1.6, 0.7)
scenes["s7"] = scene("s7", DUR[6], body, script, css7)

# 8 — It says no
REQ8 = "purani 22K chain 3g se naya kangan banao"
body = f"""
      <div id="s8-k" class="kicker abs cx" style="top:110px;color:{RUBY}">When it can't be made</div>
      <div id="s8-t" class="hero abs cx" style="top:160px;font-size:64px">It says so.</div>
      <div id="s8-b1" class="bubble b-cust" style="left:260px;top:320px;width:1000px"><div class="who">Customer</div><div id="s8-type">{typed(REQ8)}</div></div>
      <div id="s8-b2" class="bubble b-bot" style="left:560px;top:520px;width:1100px;border-color:{RUBY}">
        <div class="who" style="color:{RUBY}">Jauhari</div>
        <div style="font-family:'EB Garamond',serif;font-size:42px">That leaves too little gold for a bangle that survives daily wear.</div>
      </div>
      <div id="s8-opts" class="abs cx" style="top:800px;text-align:center">
        <span class="kicker" style="margin-right:18px;color:{MUTED}">Closest options</span>
        <span id="s8-o0" class="chip">a pendant</span>&nbsp;&nbsp;
        <span id="s8-o1" class="chip">14K gold</span>&nbsp;&nbsp;
        <span id="s8-o2" class="chip">add a little gold</span>
      </div>
"""
script = (words_in("#s8-k", off(8, 0)) + words_in("#s8-t", off(8, 0) + 1.6, 0.6)
          + rise_in("#s8-b1", off(8, 1) - 0.4, 20, 0.5) + type_on("s8-type", off(8, 1), off(8, 1) + 2.3)
          + f'    tl.fromTo("#s8-b2", {{ opacity: 0, x: -30 }}, {{ opacity: 1, x: 0, duration: 0.6, ease: "expo.out" }}, {off(8, 2)});\n'
          + f'    tl.to("#s8-b2", {{ keyframes: [{{ x: -10 }}, {{ x: 9 }}, {{ x: -5 }}, {{ x: 0 }}], duration: 0.35 }}, {off(8, 2) + 0.6});\n'
          + words_in("#s8-opts .kicker", off(8, 3), 0.5))
for i in range(3):
    t = off(8, 3) + 2.6 + i * 1.1
    script += rise_in(f"#s8-o{i}", t, 20, 0.5)
    sfx(8, t, "drop_001.ogg", 0.38)
scenes["s8"] = scene("s8", DUR[7], body, script)
typing_sfx(8, off(8, 1), off(8, 1) + 2.3, 9)
sfx(8, off(8, 2), "impactWood_medium_001.ogg", 0.5)

# 9 — It asks
REQ9 = "kuch sundar sa bana do"
body = f"""
      <div id="s9-k" class="kicker abs cx" style="top:110px;color:{EMERALD}">When it's unclear</div>
      <div id="s9-t" class="hero abs cx" style="top:160px;font-size:64px">It asks.</div>
      <div id="s9-b1" class="bubble b-cust" style="left:300px;top:310px;width:720px"><div class="who">Customer</div><div id="s9-type">{typed(REQ9)}</div></div>
      <div id="s9-b2" class="bubble b-bot" style="left:520px;top:500px;width:1100px;border-color:{EMERALD}">
        <div class="who" style="color:{EMERALD}">Sakhi</div>
        <div>Aap anguthi, choodi ya pendant mein se kya banwana chahenge?</div>
      </div>
      <div id="s9-tr" class="lead abs" style="left:520px;width:1100px;top:770px;text-align:left;color:{MUTED};font-size:36px">A ring, a bangle or a pendant &mdash; which would you like?</div>
      <div id="s9-opts" class="abs cx" style="top:870px;text-align:center">
        <span id="s9-o0" class="chip">anguthi</span>&nbsp;&nbsp;<span id="s9-o1" class="chip">choodi</span>&nbsp;&nbsp;<span id="s9-o2" class="chip">pendant</span>
      </div>
"""
script = (words_in("#s9-k", 0.5) + rise_in("#s9-b1", 0.9, 20, 0.5) + type_on("s9-type", 1.2, 2.4)
          + words_in("#s9-t", 3.4, 0.6)
          + f'    tl.fromTo("#s9-b2", {{ opacity: 0, x: -30 }}, {{ opacity: 1, x: 0, duration: 0.6, ease: "expo.out" }}, 3.8);\n'
          + words_in("#s9-tr", 5.2, 0.6))
for i in range(3):
    script += rise_in(f"#s9-o{i}", 6.6 + i * 0.25, 20, 0.5)
script += f'    tl.to("#s9-o1", {{ backgroundColor: "{EMERALD}", borderColor: "{EMERALD}", color: "{GROUND}", scale: 1.08, duration: 0.25, ease: "power2.out" }}, 8.6);\n'
scenes["s9"] = scene("s9", DUR[8], body, script)
typing_sfx(9, 1.2, 2.4, 6)
sfx(9, 3.8, "select_008.ogg", 0.42)
sfx(9, 8.6, "drop_002.ogg", 0.45)

# 10 — Why it matters
WHY = [("shop", "The jeweller", ["No guesswork.", "No haggling over grams."]),
       ("heart", "The customer", ["An heirloom, reborn.", "Seen before a gram is melted."]),
       ("anvil", "The workshop", ["A design that can", "actually be cast."])]
cols = []
for i, (ic, role, lines) in enumerate(WHY):
    x = 150 + i * 560
    ls = "".join(f'<div class="wl">{l}</div>' for l in lines)
    cols.append(f"""      <div id="s10-c{i}" class="abs wcol" style="left:{x}px;top:300px;width:500px;height:520px">
        {icon(ic, 120)}<div class="wr">{role}</div>{ls}</div>""")
css10 = f"""
  .wcol {{ border-top:4px solid {GOLD}; padding-top:50px; display:flex; flex-direction:column; align-items:center; text-align:center; gap:16px; }}
  .wr {{ font-family:'Playfair Display', serif; font-weight:900; font-size:58px; margin:16px 0 10px; }}
  .wl {{ font-family:'EB Garamond', serif; font-size:40px; line-height:1.25; }}
"""
body = f"""
      <div id="s10-k" class="kicker abs cx" style="top:130px">Why it matters</div>
{chr(10).join(cols)}
"""
script = words_in("#s10-k", 0.5)
for i in range(3):
    t = off(10, i) - 0.1
    script += (f'    tl.fromTo("#s10-c{i}", {{ opacity: 0, y: 50 }}, {{ opacity: 1, y: 0, duration: 0.9, ease: "expo.out" }}, {t});\n'
               f'    tl.fromTo("#s10-c{i} .wl", {{ opacity: 0, filter: "blur(6px)" }}, {{ opacity: 1, filter: "blur(0px)", duration: 0.4, stagger: 0.5, ease: "power4.out" }}, {t + 0.6});\n')
    sfx(10, t, "impactSoft_medium_002.ogg", 0.35)
scenes["s10"] = scene("s10", DUR[9], body, script, css10)

# 11 — What's next
NEXT = [("room", "Nonilion rooms", "Every agent gets a seat on the shop floor."),
        ("phone", "AR try-on", "Straight from the chat, at real-world scale."),
        ("feather", "“@Karigar, make it 2 g lighter”", "Re-shaped in seconds."),
        ("dial", "Workshop calibration", "Learns each workshop's real loss, casting by casting."),
        ("cube", "Hardware pack", "The same engine, beyond gold.")]
rows = []
for i, (ic, h, d) in enumerate(NEXT):
    y = 250 + i * 150
    rows.append(f"""      <div id="s11-r{i}" class="abs nrow" style="left:330px;top:{y}px;width:1300px">
        <div class="nnode">{icon(ic, 64)}</div>
        <div><div class="nh">{h}</div><div class="nd">{d}</div></div>
      </div>""")
css11 = f"""
  .nrow {{ display:flex; align-items:center; gap:40px; height:130px; }}
  .nnode {{ width:110px; height:110px; border-radius:50%; border:2px solid {GOLD}; display:flex; align-items:center; justify-content:center; background:#18120E; flex:none; }}
  .nh {{ font-family:'Playfair Display', serif; font-weight:900; font-size:50px; }}
  .nd {{ font-family:'EB Garamond', serif; font-size:34px; color:{MUTED}; }}
"""
body = f"""
      <div id="s11-t" class="hero abs cx" style="top:100px;font-size:72px">Only the <span class="gold">beginning.</span></div>
      <div id="s11-spine" class="abs" style="left:384px;top:310px;width:3px;height:610px;background:{GOLD_D};transform-origin:50% 0"></div>
{chr(10).join(rows)}
"""
script = words_in("#s11-t", off(11, 0), 0.8)
script += f'    tl.fromTo("#s11-spine", {{ scaleY: 0 }}, {{ scaleY: 1, duration: {off(11, 5) - off(11, 1) + 0.6:.2f}, ease: "none" }}, {off(11, 1)});\n'
for i in range(5):
    t = off(11, i + 1) - 0.1
    script += f'    tl.fromTo("#s11-r{i}", {{ opacity: 0, x: 40 }}, {{ opacity: 1, x: 0, duration: 0.7, ease: "expo.out" }}, {t});\n'
    if i:
        script += f'    tl.to("#s11-r{i - 1} .nh, #s11-r{i - 1} .nd", {{ opacity: 0.55, duration: 0.4 }}, {t});\n'
    sfx(11, t, "drop_001.ogg" if i % 2 == 0 else "drop_002.ogg", 0.38)
script += f'    tl.to("#s11-r4 .nh, #s11-r4 .nd, #s11-r0 .nh, #s11-r0 .nd, #s11-r1 .nh, #s11-r1 .nd, #s11-r2 .nh, #s11-r2 .nd, #s11-r3 .nh, #s11-r3 .nd", {{ opacity: 1, duration: 0.6 }}, {off(11, 5) + 3.6});\n'
scenes["s11"] = scene("s11", DUR[10], body, script, css11)

# 12 — Outro
p = "s12"
letters = "".join(f'<span class="L" style="display:inline-block;opacity:0">{c}</span>' for c in "KARIGAR")
body = f"""
      <svg class="abs" style="left:0;top:0" width="1920" height="1080" viewBox="0 0 1920 1080">{grad(p)}
        <g id="s12-p0">{solitaire(p, 690, 230, 1.0, "s12-ring")}</g>
        <g id="s12-p1">{beaded_kada(p, 960, 210, 70, "s12-kada", 20, 8, 12, "b")}</g>
        <g id="s12-p2">{lotus(p, 1230, 270, 0.8, "s12-lotus")}</g>
      </svg>
      <div id="s12-word" class="hero abs cx gold" style="top:360px;font-size:200px;letter-spacing:0.08em">{letters}</div>
      <div id="s12-tag" class="lead abs cx" style="top:640px;font-size:54px">Bring your old gold.<br/>Leave with <span class="gold">exactly that gold</span>, ready to cast.</div>
      <div id="s12-foot" class="kicker abs cx" style="top:880px;color:{MUTED}">Five AI agents &middot; The Jeweller's Shop</div>
"""
script = ('    tl.fromTo("#s12-p0, #s12-p1, #s12-p2", { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.8, ease: "expo.out", stagger: 0.15 }, 0.3);\n'
          + '    tl.fromTo("#s12-word .L", { opacity: 0, filter: "blur(14px)", scale: 1.15 }, { opacity: 1, filter: "blur(0px)", scale: 1, duration: 0.6, ease: "expo.out", stagger: 0.07 }, 1.0);\n'
          + words_in("#s12-tag", 2.2, 0.8) + rise_in("#s12-foot", 5.4))
scenes["s12"] = scene("s12", DUR[11], body, script)
sfx(12, 1.0, "impactBell_heavy_003.ogg", 0.6)

# ---------------------------------------------------------------- audio bed + ducking
M1, M1LEN = "assets/music/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3", 117.36
M2 = "assets/music/happy-beats-business-moves-vol-9-by-ende-dot-app.mp3"
M2START = 114.5
M2LEN = TOTAL - M2START
VO_ABS = [(STARTS[i] + VO_LEAD[i], STARTS[i] + VO_LEAD[i] + VOLEN[i]) for i in range(12)]
HI, LO = 0.30, 0.12


def duck_lane(clip_start, clip_len):
    pts = [{"t": 0, "v": HI}]
    for a, b in VO_ABS:
        a, b = a - clip_start, b - clip_start
        if b < 0 or a > clip_len:
            continue
        pts += [{"t": round(max(a - 0.4, 0.01), 2), "v": HI}, {"t": round(max(a, 0.02), 2), "v": LO},
                {"t": round(min(b + 0.1, clip_len), 2), "v": LO}, {"t": round(min(b + 0.6, clip_len), 2), "v": HI}]
    # keep monotonic
    clean, last = [], -1
    for q in pts:
        if q["t"] > last:
            clean.append(q); last = q["t"]
    return json.dumps({"version": 1, "lanes": [{"target": "volume", "points": clean}]})


# ---------------------------------------------------------------- audio-reactive glow (music RMS at 4 Hz)
def rms_env(path, start, dur, hz=4):
    raw = subprocess.run(["ffmpeg", "-v", "quiet", "-i", os.path.join(COMP, path), "-ac", "1", "-ar", "8000",
                          "-f", "s16le", "-"], capture_output=True).stdout
    n = len(raw) // 2
    samples = struct.unpack(f"<{n}h", raw[:n * 2])
    step = 8000 // hz
    env = []
    for k in range(int(dur * hz)):
        seg = samples[k * step:(k + 1) * step]
        env.append(math.sqrt(sum(x * x for x in seg) / max(len(seg), 1)) / 32768 if seg else 0)
    return env


e1 = rms_env(M1, 0, min(M1LEN, M2START))
e2 = rms_env(M2, 0, M2LEN)
env = (e1 + e2)[: int(TOTAL * 4)]
mx = max(env) or 1
glow = [round(0.55 + 0.45 * (v / mx), 3) for v in env]
glow_kf = json.dumps([{"opacity": g} for g in glow])

# ---------------------------------------------------------------- write files
os.makedirs(os.path.join(COMP, "compositions"), exist_ok=True)
for sid, html in scenes.items():
    open(os.path.join(COMP, "compositions", f"{sid}.html"), "w", encoding="utf-8").write(html)

hosts = "\n".join(
    f'      <div id="s{i + 1}" data-composition-id="s{i + 1}" data-composition-src="compositions/s{i + 1}.html" '
    f'data-start="{STARTS[i]}" data-duration="{DUR[i]}" data-track-index="1" data-track-kind="graphics" '
    f'data-width="1920" data-height="1080" style="z-index:2"></div>' for i in range(12))
vos = "\n".join(
    f'      <audio id="vo{i + 1}" class="clip" data-start="{VO_ABS[i][0]:.2f}" data-duration="{VOLEN[i]:.2f}" '
    f'data-track-index="3" data-volume="1" src="assets/vo/s{i + 1:02d}.wav"></audio>' for i in range(12))
sfxs = "\n".join(
    f'      <audio id="fx{k}" class="clip" data-start="{t}" data-duration="{flen(f)}" data-track-index="{11 + k % 6}" '
    f'data-volume="{v}" src="assets/sfx/{f}"></audio>' for k, (t, f, v) in enumerate(sorted(SFX)))

index = f"""<!doctype html>
<html lang="en" data-composition-variables='[
  {{"id":"color-ground","type":"color","label":"Background","default":"{GROUND}"}},
  {{"id":"color-ink","type":"color","label":"Text","default":"{INK}"}},
  {{"id":"color-accent","type":"color","label":"Accent","default":"{GOLD}"}}
]'>
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: {GROUND}; }}
      #bg {{ position: absolute; inset: 0; background: {GROUND}; z-index: 0; }}
      #glow {{ position: absolute; inset: 0; z-index: 1;
               background: radial-gradient(ellipse 60% 55% at 50% 48%, rgba(201,151,63,0.22), rgba(201,151,63,0.06) 55%, rgba(18,13,10,0) 75%); }}
      #vign {{ position: absolute; inset: 0; z-index: 3; pointer-events: none;
               background: radial-gradient(ellipse 80% 75% at 50% 50%, rgba(0,0,0,0) 60%, rgba(0,0,0,0.55) 100%); }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{TOTAL}" data-width="1920" data-height="1080">
      <div id="bg"></div>
      <div id="glow"></div>
{hosts}
      <div id="vign"></div>
      <audio id="music1" class="clip" data-start="0" data-duration="{min(M2START + 3, M1LEN - 0.01):.2f}" data-track-index="10" data-volume="1" data-fade-in="1.5" data-fade-out="3" src="{M1}"
        data-automation='{duck_lane(0, min(M2START + 3, M1LEN - 0.01))}'></audio>
      <audio id="music2" class="clip" data-start="{M2START}" data-duration="{M2LEN:.2f}" data-track-index="9" data-volume="1" data-fade-in="3" data-fade-out="4" src="{M2}"
        data-automation='{duck_lane(M2START, M2LEN)}'></audio>
{vos}
{sfxs}
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
      // audio-reactive: background gold glow breathes with music RMS (4 Hz, baked at build time)
      tl.fromTo("#glow", {{ opacity: {glow[0]} }}, {{ keyframes: {glow_kf}, duration: {len(glow) / 4:.2f}, ease: "none" }}, 0);
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""
open(os.path.join(COMP, "index.html"), "w", encoding="utf-8").write(index)
print("total", TOTAL, "starts", STARTS, "sfx", len(SFX))
