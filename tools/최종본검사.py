# -*- coding: utf-8 -*-
"""캡컷에서 내보낸 최종본(001·003)을 검사하고 보고서를 쓴다. 읽기만 한다.

  python tools/최종본검사.py <001.mp4> [--003 <003.mp4>] [--드래프트 <이름>] [--오프닝 8.0-30.6] [--출력 <폴더>]

재는 것
  규격        해상도·프레임·코덱·길이·파일명 (lecture-cut check_guidelines + profiles/vivasam.json)
  음량        인트로·오프닝·본편 구간별 통합 LUFS. 오프닝 목소리가 본편보다 작지 않은가
  본편 말자막  1초마다 가운데 아래 말자막 상자를 찾는다. 본편에서 잡힌 곳은 그림으로 모아 사람이 본다
  싱크        (--드래프트) 본편 여러 곳에서 화면이 소재와 같은지, 목소리가 원래 녹음과 몇 ms 어긋나는지
              AAC 앞 지연 때문에 20~25ms 늦게 재지는 것은 정상이다
  워터마크    (faster-whisper 가 있으면) 인트로·오프닝 앞뒤·영상 끝을 받아 적는다. 낯선 말이 있으면 알린다
  배경음악    (--드래프트) 배경음악 구간의 쉼 바닥이 소리로 채워졌는지
  장면 모음    앞부분·끝부분·003 을 그림으로. 표지·차시명·참고문헌·차시 예고는 사람이 읽고 확인한다
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

from _팩 import LECTURE_CUT, PACK, US, load, main_track, mindex, win

W, H = 480, 270


def _opt(a, k, default=None):
    return a[a.index(k) + 1] if k in a else default


def dur_s(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                capture_output=True, text=True).stdout)


def lufs(p, a=None, b=None):
    cmd = ["ffmpeg", "-hide_banner", "-nostats"] + (["-ss", f"{a}", "-t", f"{b - a}"] if a is not None else []) + \
          ["-i", p, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"]
    e = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}).stderr
    s = e[e.rfind("Summary:"):]
    m = re.search(r"I:\s+(-?[\d.]+) LUFS", s)
    return float(m.group(1)) if m else None


def audio(p, t, d, sr=16000):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t):.4f}", "-t", f"{d:.4f}", "-i", p, "-vn", "-ac", "1",
                        "-ar", str(sr), "-f", "f32le", "-"], capture_output=True).stdout
    return np.frombuffer(r, np.float32).astype(np.float64)


def gray(p, t):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.4f}", "-i", p, "-frames:v", "1", "-vf", f"scale={W}:{H}",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    return np.frombuffer(r, np.uint8).reshape(H, W).astype(np.int16) if len(r) == W * H else None


# ── 말자막 상자 ──────────────────────────────────────
def sub_box(f):
    """가운데 아래(1080 기준 y 904~984) 어두운 반투명 상자 + 흰 글자. 있으면 (x0, x1)."""
    band = f[226:246]
    dark = (band < 90).mean(axis=0)
    pad = np.pad(dark, 4, mode="edge")
    mask = np.array([pad[i:i + 9].max() for i in range(W)]) > 0.5
    idx = np.nonzero(mask)[0]
    for i, j in zip(idx[:-1], idx[1:]):
        if 1 < j - i <= 5:
            mask[i:j] = True
    c = W // 2
    if not mask[c - 20:c + 21].any():
        return None
    k = c - 20 + int(np.argmax(mask[c - 20:c + 21]))
    a = z = k
    while a > 0 and mask[a - 1]:
        a -= 1
    while z < W - 1 and mask[z + 1]:
        z += 1
    if not (30 <= z - a <= 420) or a < 8 or z > W - 9 or abs((a + z) / 2 - c) > 30:
        return None
    side = np.r_[dark[max(0, a - 14):max(0, a - 5)], dark[z + 5:z + 14]]
    if side.mean() > 0.3 or (band[:, a:z] > 200).mean() < 0.03:
        return None
    return a * 4, z * 4


def scan_subs(p):
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", p, "-vf", f"fps=1,scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                            stdout=subprocess.PIPE)
    hits, n = [], 0
    while True:
        b = proc.stdout.read(W * H)
        if len(b) < W * H:
            break
        if sub_box(np.frombuffer(b, np.uint8).reshape(H, W)):
            hits.append(n)
        n += 1
    proc.wait()
    return hits


# ── 그림 ─────────────────────────────────────────────
def sheet(p, times, out, cols=6):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    tiles = []
    for t in times:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", p, "-frames:v", "1", "-vf", f"scale={W}:{H}",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        im = Image.frombytes("RGB", (W, H), raw) if len(raw) == W * H * 3 else Image.new("RGB", (W, H), (60, 0, 0))
        dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, 118, 26], fill=(255, 255, 0))
        dr.text((4, 2), f"{int(t // 60)}:{t % 60:05.2f}", fill=(0, 0, 0), font=font)
        tiles.append(im)
    rows = max(1, (len(tiles) + cols - 1) // cols)
    s = Image.new("RGB", (cols * W + (cols - 1) * 4, rows * H + (rows - 1) * 4), (255, 255, 255))
    for i, im in enumerate(tiles):
        s.paste(im, ((i % cols) * (W + 4), (i // cols) * (H + 4)))
    s.save(out)
    return out


# ── 드래프트에서 구간 ─────────────────────────────────
def spans_from_draft(name):
    _, d = load(name)
    idx = mindex(d)
    v = main_track(d)["segments"]
    intro_end = (v[0]["target_timerange"]["start"] + v[0]["target_timerange"]["duration"]) / US
    tr = next((t for t in d["tracks"] if t.get("name") == "인트로 말자막" and t["segments"]), None)
    open_end = None
    if tr:
        last = max(s["target_timerange"]["start"] + s["target_timerange"]["duration"] for s in tr["segments"]) / US
        c = next((s for s in v if s["target_timerange"]["start"] / US <= last - 0.01 <
                  (s["target_timerange"]["start"] + s["target_timerange"]["duration"]) / US), None)
        open_end = (c["target_timerange"]["start"] + c["target_timerange"]["duration"]) / US if c else last
    bgm = []
    for t in d["tracks"]:
        if t["type"] != "audio":
            continue
        for s in t["segments"]:
            m = idx.get(s["material_id"], (None, {}))[1]
            if t.get("name") == "배경음악" or "BGM" in (m.get("path") or "").upper() or (0 < (s.get("volume") or 0) < 0.6):
                a = s["target_timerange"]["start"] / US
                bgm.append((a, a + s["target_timerange"]["duration"] / US))
    return intro_end, open_end, bgm, d, idx


def sync(p, d, idx, lect0):
    from collections import Counter
    v = main_track(d)["segments"]
    names = Counter((idx.get(s["material_id"], (None, {}))[1].get("path") or "") for s in v)
    mat = names.most_common(1)[0][0]
    clips = [(s["target_timerange"]["start"] / US, (s["target_timerange"]["start"] + s["target_timerange"]["duration"]) / US,
              (s.get("source_timerange") or {}).get("start", 0) / US) for s in v
             if (idx.get(s["material_id"], (None, {}))[1].get("path") or "") == mat]
    end = clips[-1][1]
    rows = []
    long = [(a, b, s0) for a, b, s0 in clips if b - a >= 3.4 and a >= lect0]
    if not long:
        return []
    for T0 in np.linspace(lect0 + 20, end - 20, 12):
        a, b, s0 = min(long, key=lambda c: abs((c[0] + c[1]) / 2 - T0))
        T = (a + b) / 2
        s = s0 + (T - a)
        fa, fb = gray(p, T), gray(win(mat), s)
        fd = float(np.abs(fa - fb).mean()) if fa is not None and fb is not None else -1
        m, r = audio(p, T - 1.5, 3.0), audio(win(mat), s - 1.7, 3.4)
        best, lag = -1.0, 0
        if len(m) > 100 and len(r) > len(m) and m.std() > 1e-4:
            mm = (m - m.mean()) / m.std()
            for step in (8, 1):
                rng = range(0, len(r) - len(m) + 1, 8) if step == 8 else range(max(0, lag - 8), min(len(r) - len(m), lag + 8) + 1)
                for k in rng:
                    seg = r[k:k + len(m)]
                    sd = seg.std()
                    if sd < 1e-6:
                        continue
                    cc = float(np.dot(mm, seg - seg.mean()) / (sd * len(m)))
                    if cc > best:
                        best, lag = cc, k
        rows.append((T, fd, best, (0.2 - lag / 16000) * 1000))
    return rows


def bgm_floor(p, a, b):
    x = audio(p, a, b - a)
    n = 1600
    if len(x) < n * 5:
        return None
    rms = np.sqrt(np.mean(x[:len(x) // n * n].reshape(-1, n) ** 2, axis=1))
    return float(np.percentile(20 * np.log10(rms + 1e-9), 5))


def transcribe(p, windows):
    try:
        sys.path.insert(0, str(LECTURE_CUT / "src"))
        import cuda_dlls  # noqa: F401
        from faster_whisper import WhisperModel
        m = WhisperModel("small", device="auto", compute_type="int8")
    except Exception as e:  # 없으면 건너뛴다
        return None, str(e)[:80]
    import os
    import tempfile
    out = []
    for a, b in windows:
        tmp = tempfile.mktemp(suffix=".wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a}", "-t", f"{b - a}", "-i", p, "-vn", "-ac", "1", "-ar", "16000", tmp])
        segs, info = m.transcribe(tmp, language=None, beam_size=5)
        out.append((a, b, info.language, info.language_probability, " ".join(s.text.strip() for s in segs)))
        os.remove(tmp)
    return out, ""


def main(a):
    p1 = win(a[0])
    p3 = win(_opt(a, "--003")) if "--003" in a else None
    draft = _opt(a, "--드래프트")
    outdir = Path(win(_opt(a, "--출력", str(Path(p1).parent / "최종본검사"))))
    outdir.mkdir(parents=True, exist_ok=True)
    stem = Path(p1).stem
    rep = [f"# 최종본 검사 · {Path(p1).name}" + (f" · {Path(p3).name}" if p3 else ""), ""]
    D = dur_s(p1)

    # 규격
    prof = PACK / "profiles" / "vivasam.json"
    files = [p1] + ([p3] if p3 else [])
    r = subprocess.run([sys.executable, str(LECTURE_CUT / "src" / "check_guidelines.py"), *files, "--프로필", str(prof),
                        "--보고서", str(outdir / f"{stem}_규격점검.md")], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    head = [x for x in r.stdout.splitlines() if "실패" in x or "[실패]" in x or "[확인]" in x][:8]
    rep += ["## 규격", "", *[f"- {x.strip()}" for x in head], f"- 자세한 표: `{stem}_규격점검.md`", ""]

    # 구간
    intro_end, open_end, bgm, d, idx = (8.0, None, [], None, None)
    if draft:
        intro_end, open_end, bgm, d, idx = spans_from_draft(draft)
    if "--오프닝" in a:
        x, y = _opt(a, "--오프닝").split("-")
        intro_end, open_end = float(x), float(y)
    hits = scan_subs(p1)
    if open_end is None:
        early = [h for h in hits if h < 150]
        open_end = (max(early) + 1.0) if early else intro_end
    body = [h for h in hits if h > open_end + 0.5]
    rep += ["## 구간", "", f"- 인트로 0~{intro_end:.1f}초 · 오프닝 {intro_end:.1f}~{open_end:.1f}초 · 본편 {open_end:.1f}~{D:.1f}초", ""]

    # 음량
    li = lufs(p1)
    lo = lufs(p1, intro_end + 0.1, open_end - 0.1) if open_end - intro_end > 3 else None
    lb = lufs(p1, open_end + 0.5, min(D, open_end + 300))
    l3 = lufs(p3) if p3 else None
    rep += ["## 음량 (통합 LUFS)", "", f"- 전체 {li} · 인트로 {lufs(p1, 0, intro_end)} · 오프닝 {lo} · 본편 앞 5분 {lb}" +
            (f" · 003 {l3}" if p3 else "")]
    if lo is not None and lb is not None and lb - lo > 3:
        rep.append(f"- ⚠ 오프닝이 본편보다 {lb - lo:.1f} LU 작다. 오프닝 목소리도 보정했는지 본다")
    rep.append("")

    # 말자막
    rep += ["## 말자막", "", f"- 오프닝에서 말자막이 보인 초: {sum(1 for h in hits if intro_end <= h <= open_end)} / {int(open_end - intro_end)}"]
    if body:
        img = sheet(p1, [float(h) for h in body[:36]], str(outdir / f"{stem}_본편말자막후보.png"))
        rep.append(f"- ⚠ 본편에서 말자막처럼 보인 {len(body)}초 → `{Path(img).name}` 를 보고 판단한다(앱 단추 같은 것도 잡힌다)")
    else:
        rep.append("- 본편에서 말자막 상자 없음")
    rep.append("")

    # 싱크
    if d is not None:
        rows = sync(p1, d, idx, open_end)
        rep += ["## 화면·목소리 싱크 (드래프트 기준)", "", "| 편집 시각 | 화면 차(0~255) | 상관 | 목소리 어긋남 |", "|---|---|---|---|"]
        rep += [f"| {int(t // 60)}:{t % 60:05.2f} | {fd:.2f} | {c:.2f} | {ms:+.0f}ms |" for t, fd, c, ms in rows]
        if rows:
            ms = [r[3] for r in rows if r[2] > 0.5]
            if ms:
                rep.append(f"\n- 어긋남 {min(ms):+.0f}~{max(ms):+.0f}ms. 20~25ms 는 AAC 앞 지연이라 정상. 차이가 커지면 밀린 것이다")
        rep.append("")

    # 배경음악
    if bgm:
        rep += ["## 배경음악 구간 쉼 바닥", ""]
        for a0, b0 in bgm:
            f = bgm_floor(p1, a0 + 0.5, b0 - 0.5)
            rep.append(f"- {a0:.1f}~{b0:.1f}초: 하위 5% {f:.1f} dB" + ("" if f is None or f > -50 else "  ⚠ 거의 무음. 배경음악이 안 들어갔을 수 있다"))
        rep.append("")

    # 받아 적기
    wins = [(0, intro_end + 0.3), (max(0, intro_end - 0.2), intro_end + 4), (max(0, open_end - 4), open_end + 4), (max(0, D - 12), D)]
    tr, err = transcribe(p1, wins)
    rep += ["## 경계 받아 적기 (워터마크·낯선 말)", ""]
    if tr is None:
        rep.append(f"- 건너뜀 (faster-whisper 없음: {err})")
    else:
        for a0, b0, lang, pr, txt in tr:
            flag = "  ⚠ 한국어가 아니다. 들어 본다" if lang != "ko" and a0 > 1 else ""
            rep.append(f"- {a0:.1f}~{b0:.1f}초 [{lang} {pr:.2f}] {txt[:120]}{flag}")
        rep.append("- 인트로(음악)는 받아 적기가 영어 한 줄을 지어낼 때가 있다. 오프닝·끝에서 나온 영어가 워터마크 의심이다")
    rep.append("")

    # 장면 모음
    front = sheet(p1, list(np.arange(0, min(D, open_end + 22), 2.0)), str(outdir / f"{stem}_앞.png"))
    end = sheet(p1, list(np.arange(max(0, D - 40), D - 0.2, 2.0)), str(outdir / f"{stem}_끝.png"))
    rep += ["## 사람이 보고 확인할 것", "", f"- `{Path(front).name}`: 인트로 → 오프닝(말자막) → 표지 → 학습 목표 순서, 표지의 과정명·차시명",
            f"- `{Path(end).name}`: 마무리 표지의 차시명이 교안·공식 목록과 같은가, 검은 화면으로 끝나지 않는가"]
    if p3:
        s3 = sheet(p3, list(np.arange(0, dur_s(p3) - 0.2, 1.5)), str(outdir / f"{Path(p3).stem}_장면.png"))
        rep.append(f"- `{Path(s3).name}`: 003 이 차시 예고로 끝나는가, 참고문헌 형식·책 제목 띄어쓰기가 다른 차시와 같은가")
    rep.append("")
    out = outdir / f"{stem}_최종본검사.md"
    out.write_text("\n".join(rep), encoding="utf-8")
    print("\n".join(rep))
    print(f"\n보고서: {out}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    else:
        main(sys.argv[1:])
