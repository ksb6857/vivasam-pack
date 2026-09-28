# -*- coding: utf-8 -*-
"""효과: 오래 멈춘 화면 찾기 · 개인정보 찾기 · 강조 상자 · 작은 글씨 확대 · 가림

  python tools/효과.py 정지화면 <드래프트> [--초 50]                  50초 넘게 그대로인 화면(편집 시각·원본 시각)
  python tools/효과.py 개인정보 <드래프트> [--출력 가림계획.json] [--간격 1.5]     (20분 강의에 30~40분, 백그라운드로)
                                                                  화면에 보인 이메일·API 키를 글자 인식으로 찾아 가림 계획을 쓴다
  python tools/효과.py 상자 <드래프트> <계획.json> [--dry]          강조 상자(사람이 그린 도형 본을 복제, 페이드 인·아웃)
  python tools/효과.py 확대 <드래프트> <계획.json> [--dry]          작은 글씨 확대(최대 2배, 들어가고 나올 때 0.4초)
  python tools/효과.py 가림 <드래프트> <계획.json> [--dry]          흐림으로 가리기

계획 파일: {"items": [{"src": [원본 시작초, 끝초], "rect": [x0, y0, x1, y1], "why": "무엇"}]}
  시각은 강의 소재(원본) 기준이라 컷을 고쳐도 다시 붙이면 제자리로 간다. rect 는 1920x1080 픽셀.

확대·가림은 소재에서 그 구간을 구워 만든 짧은 영상(소리 없음)을 위쪽 영상 줄(「확대」「가림」)에 겹친다.
구운 파일은 강의 소재와 같은 폴더의 `<드래프트>_효과/` 에 둔다. 옮기지 않는다.
강조 상자는 50초 넘게 그대로인 화면에서 「첫째·둘째」처럼 말하는 순간에 맞춰 띄운다. 처음부터 떠 있으면 지적된다.
"""
import copy
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from _팩 import LECTURE_CUT, TEMPLATES, US, clone_material, gid, load, main_track, mindex, save, win

import timemap  # noqa: E402

RAMP = 0.4


def _opt(a, k, default=None):
    return a[a.index(k) + 1] if k in a else default


def _material(d, idx):
    c = Counter((idx.get(s["material_id"], (None, {}))[1].get("path") or "") for s in main_track(d)["segments"])
    return c.most_common(1)[0][0]


def _gray(path, t, w=160, h=90):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t):.3f}", "-i", win(path), "-frames:v", "1", "-vf", f"scale={w}:{h}",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    return np.frombuffer(r, np.uint8).reshape(h, w).astype(np.int16) if len(r) == w * h else None


def _edit_samples(tl, step):
    """편집 시각을 step 간격으로 걸으며 (편집 시각, 원본 시각)."""
    out = []
    for t0, t1, s0 in tl:
        t = t0 + 0.05
        while t < t1 - 0.05:
            out.append((t, s0 + (t - t0)))
            t += step
    return out


def cmd_정지화면(name, sec=50.0):
    _, d = load(name)
    idx = mindex(d)
    tl = timemap.timeline(d)
    mat = _material(d, idx)
    runs, cur, prev = [], None, None
    for t, s in _edit_samples(tl, 1.0):
        f = _gray(mat, s)
        if f is None:
            continue
        still = prev is not None and float(np.abs(f - prev).mean()) < 3.0
        prev = f
        if still:
            cur[1] = (t, s)
        else:
            if cur and cur[1][0] - cur[0][0] >= sec:
                runs.append(cur)
            cur = [(t, s), (t, s)]
    if cur and cur[1][0] - cur[0][0] >= sec:
        runs.append(cur)
    print(f"{name}: {sec:.0f}초 넘게 그대로인 화면 {len(runs)}곳")
    for (ta, sa), (tb, sb) in runs:
        print(f"  편집 {int(ta // 60)}:{ta % 60:04.1f}~{int(tb // 60)}:{tb % 60:04.1f} ({tb - ta:.0f}초) · 원본 {sa:.1f}~{sb:.1f}")
    print("이 화면들에 말에 맞춰 강조 상자·확대·나타내기를 넣는다. 계획은 src(원본 시각)와 rect 로 쓴다")


EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
KEY = re.compile(r"(AIza[0-9A-Za-z_-]{16,}|sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{16,}|xox[bp]-[A-Za-z0-9-]{10,})")


def _mask(s):
    return s[:2] + "***" + s[s.find("@"):] if "@" in s else s[:4] + "***"


def cmd_개인정보(name, out, step=1.5):
    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR()
    _, d = load(name)
    idx = mindex(d)
    tl = timemap.timeline(d)
    mat = _material(d, idx)
    hits = []
    last_g, last_res, n_ocr = None, [], 0
    for t, s in _edit_samples(tl, step):
        g = _gray(mat, s)
        if g is not None and last_g is not None and float(np.abs(g - last_g).mean()) < 0.8:
            res = last_res                                   # 화면이 그대로면 앞 결과를 쓴다(글자 인식이 느리다)
        else:
            r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{s:.3f}", "-i", win(mat), "-frames:v", "1", "-f", "image2pipe",
                                "-vcodec", "png", "-"], capture_output=True).stdout
            if not r:
                continue
            res, _ = ocr(r)
            last_g, last_res = g, res
            n_ocr += 1
        for box, text, conf in res or []:
            m = EMAIL.search(text) or KEY.search(text)
            if not m:
                continue
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            hits.append((s, [int(min(xs)) - 8, int(min(ys)) - 6, int(max(xs)) + 8, int(max(ys)) + 6], m.group(0)))
    items = []
    for s, rect, txt in sorted(hits, key=lambda h: (h[2], h[0])):
        last = items[-1] if items else None
        if last and last["_txt"] == txt and s - last["src"][1] <= step * 2 + 0.1 and abs(last["rect"][1] - rect[1]) < 40:
            last["src"][1] = s + 0.5
            last["rect"] = [min(last["rect"][0], rect[0]), min(last["rect"][1], rect[1]), max(last["rect"][2], rect[2]), max(last["rect"][3], rect[3])]
        else:
            items.append({"src": [max(0.0, s - step), s + 0.5], "rect": rect, "why": f"개인정보 {_mask(txt)}", "_txt": txt})
    for it in items:
        it.pop("_txt")
    Path(out).write_text(json.dumps({"items": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{name}: 글자 인식 {n_ocr}장 · 이메일·키로 보이는 것 {len(items)}곳 → {out}")
    for it in items:
        e = timemap.span_to_edit(tl, it["src"][0], it["src"][1])
        where = f"편집 {int(e[0] // 60)}:{e[0] % 60:04.1f}" if e else "편집에 없음"
        print(f"  {where} · 원본 {it['src'][0]:.1f}~{it['src'][1]:.1f} · {it['rect']} · {it['why']}")
    print("글자 인식은 흐린 글씨·작은 글씨를 놓칠 수 있다. 창이 다시 뜨는 곳(계정 칩·배포 창)은 사람이 한 번 더 본다. 앞뒤는 넉넉히 늘린다")


def cmd_상자(name, plan_p, dry):
    import apply_highlights
    plan = json.loads(Path(plan_p).read_text(encoding="utf-8"))
    plan["draft"] = name
    _, d = load(name)
    old = next((t for t in d["tracks"] if t.get("name") == "lecture_autocut_highlights" and t["segments"]), None)
    if old and "--덮어쓰기" not in sys.argv:
        raise SystemExit(f"이미 강조 상자 줄에 {len(old['segments'])}개가 있다. 다시 넣으면 그 줄을 지우고 새로 만든다. 그래도 하려면 --덮어쓰기")
    tmp = Path(plan_p).with_suffix(".드래프트.json")
    tmp.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    apply_highlights.run(str(tmp), str(TEMPLATES / "강조상자_본.json"), dry=dry)


def _pieces(tl, a, b):
    """원본 구간 [a,b] 가 편집에 남은 조각들: (편집 시작, 원본 시작, 원본 끝)."""
    out = []
    for t0, t1, s0 in tl:
        s1 = s0 + (t1 - t0)
        lo, hi = max(a, s0), min(b, s1)
        if hi - lo > 0.05:
            out.append((t0 + (lo - s0), lo, hi))
    return out


def _render(mat, sa, sb, out, kind, rect, ramp_in, ramp_out):
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0
    D = sb - sa
    if kind == "확대":
        Z = max(1.0, min(2.0, 1920 / (w * 1.15), 1080 / (h * 1.15)))
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        t = "(in/30)"
        up = f"min(1,{t}/{RAMP})" if ramp_in else "1"
        dn = f"min(1,({D:.3f}-{t})/{RAMP})" if ramp_out else "1"
        P = f"max(0,min({up},{dn}))"
        vf = (f"fps=30,scale=1920:1080,zoompan=z='1+({Z:.4f}-1)*{P}':"
              f"x='max(0,min(iw-iw/zoom,({cx:.1f}-iw/zoom/2)*{P}))':y='max(0,min(ih-ih/zoom,({cy:.1f}-ih/zoom/2)*{P}))':"
              f"d=1:s=1920x1080:fps=30")
    else:
        r = max(2, min(20, int(min(w, h) / 2) - 1))
        cr = max(1, min(10, int(min(w, h) / 4) - 1))
        vf = (f"fps=30,scale=1920:1080,split[a][b];[b]crop={w}:{h}:{x0}:{y0},boxblur=luma_radius={r}:chroma_radius={cr}:luma_power=3[bb];"
              f"[a][bb]overlay={x0}:{y0}")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{sa:.4f}", "-i", win(mat), "-t", f"{D:.4f}", "-an", "-vf", vf,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(out)], check=True)


def cmd_굽기(name, plan_p, kind, dry):
    plan = json.loads(Path(plan_p).read_text(encoding="utf-8"))
    fs, d = load(name)
    idx = mindex(d)
    tl = timemap.timeline(d)
    mat = _material(d, idx)
    folder = Path(win(mat)).parent / f"{name}_효과"
    tmpl = next(s for s in main_track(d)["segments"] if (idx[s["material_id"]][1].get("path") or "") == mat)
    tmat = idx[tmpl["material_id"]][1]
    track = next((t for t in d["tracks"] if t.get("name") == kind), None)
    todo = []
    for k, it in enumerate(plan["items"]):
        ps = _pieces(tl, float(it["src"][0]), float(it["src"][1]))
        if not ps:
            print(f"  [건너뜀] 원본 {it['src']} 는 편집에 없다")
            continue
        for j, (at, sa, sb) in enumerate(ps):
            todo.append((k, j, at, sa, sb, it["rect"], j == 0, j == len(ps) - 1, it.get("why", "")))
    print(f"{name}: {kind} {len(plan['items'])}개 계획 → 겹칠 조각 {len(todo)}개 · 구운 파일 {folder}")
    for k, j, at, sa, sb, rect, ri, ro, why in todo:
        print(f"  편집 {int(at // 60)}:{at % 60:04.1f} · {sb - sa:.1f}초 · {rect} · {why}")
    if dry:
        print("(시험 · 쓰지 않음)")
        return
    folder.mkdir(parents=True, exist_ok=True)
    if track is None:
        track = {"id": gid(), "type": "video", "flag": 2, "attribute": 0, "name": kind, "is_default_name": False, "segments": []}
        d["tracks"].append(track)
    for k, j, at, sa, sb, rect, ri, ro, why in todo:
        out = folder / f"{kind}_{k + 1:02d}_{j + 1}_{int(sa * 1000)}.mp4"
        _render(mat, sa, sb, out, kind, rect, ri, ro)
        from _팩 import duration_us
        dur = duration_us(out)
        m = copy.deepcopy(tmat)
        m.update({"id": gid(), "path": str(out).replace("\\", "/"), "material_name": out.name, "duration": dur,
                  "width": 1920, "height": 1080, "has_audio": False, "local_material_id": ""})
        d["materials"]["videos"].append(m)
        s = copy.deepcopy(tmpl)
        n = min(dur, int(round((sb - sa) * US)))
        s.update({"id": gid(), "material_id": m["id"], "volume": 0.0, "last_nonzero_volume": 1.0, "render_index": 2,
                  "source_timerange": {"start": 0, "duration": n}, "target_timerange": {"start": int(round(at * US)), "duration": n}})
        s["extra_material_refs"] = [clone_material(d, idx[r][0], idx[r][1]) for r in tmpl.get("extra_material_refs", [])
                                    if r in idx and idx[r][0] != "transitions"]
        s["clip"] = {"scale": {"x": 1.0, "y": 1.0}, "rotation": 0.0, "transform": {"x": 0.0, "y": 0.0},
                     "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0}
        s["common_keyframes"] = []
        track["segments"].append(s)
    save(name, fs, d, f"{kind}_전")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == "정지화면":
        cmd_정지화면(a[1], float(_opt(a, "--초", 50)))
    elif a[0] == "개인정보":
        cmd_개인정보(a[1], _opt(a, "--출력", f"{a[1]}_가림계획.json"), float(_opt(a, "--간격", 1.5)))
    elif a[0] == "상자":
        cmd_상자(a[1], a[2], "--dry" in a)
    elif a[0] in ("확대", "가림"):
        cmd_굽기(a[1], a[2], a[0], "--dry" in a)
    else:
        raise SystemExit(__doc__)
