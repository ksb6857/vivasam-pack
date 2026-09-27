# -*- coding: utf-8 -*-
"""비바샘 오프닝(선생님 얼굴이 나오는 인트로 뒤 30~70초)을 만들어 드래프트에 붙인다.

크로마키 천 없이 찍어도 된다. AI 매팅(Robust Video Matting, CPU)으로 사람만 오려 팀 배경 그림 위에 올린다.
파란 천 앞에서 찍었어도 같은 방법으로 된다.

사용
  python tools/오프닝.py 모델받기                                   매팅 모델(15MB, GitHub 공식 배포)을 models/ 에 받는다
  python tools/오프닝.py 받아적기 <촬영본> <낱말.json> [--모델 small]  낱말 시각 전사(faster-whisper). 테이크 고르기용
  python tools/오프닝.py 컷 <촬영본> <구간.json> <컷.json>            고른 테이크 구간의 가장자리를 조용한 곳으로 옮긴다
  python tools/오프닝.py 합성 <촬영본> <배경.png> <합성본.mp4>        사람만 오려 배경에 올린다(1920x1080 30fps, 원래 소리)
  python tools/오프닝.py 붙이기 <드래프트> --합성본 <mp4> --컷 <컷.json> --말자막 <말자막.json>
                              --자리 인트로뒤|맨앞|바꾸기 [--인트로 <인트로.mp4>] [--바꿀 8.03-90.47] [--dry]

파일 형식
  구간.json   [{"from": 첫 낱말 시작초, "to": 끝 낱말 끝초, "text": "그 구간의 말"}, ...]   촬영본 시각, 쓸 순서대로
  컷.json     컷 이 만든다. [{"from", "to", "text"}] 가장자리를 옮긴 것
  말자막.json [{"text": "화면에 띄울 한 줄", "src": 그 줄 첫 낱말의 촬영본 시각}, ...]

배치: 머리 꼭대기 y400, 머리 가운데 x960, 머리 폭 약 275px(팀 예시 캡처와 같은 크기). --머리 --가운데 --머리폭 으로 바꾼다.
"""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import numpy as np

from _팩 import PACK, US, clone_material, duration_us, gid, load, main_track, mindex, save, template, win
import 말자막

MODEL_URL = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx"
MODEL_SHA256 = "88d4531297118f595bf2fd60f6f566aec2e559393802d1f436c380f0cbbd2828"
MODEL = PACK / "models" / "rvm_mobilenetv3_fp32.onnx"


# ── 모델 ─────────────────────────────────────────────
def cmd_모델받기():
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    if MODEL.exists() and hashlib.sha256(MODEL.read_bytes()).hexdigest() == MODEL_SHA256:
        print(f"이미 있다: {MODEL}")
        return
    print(f"받는 중: {MODEL_URL}")
    urllib.request.urlretrieve(MODEL_URL, MODEL)
    h = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    if h != MODEL_SHA256:
        MODEL.unlink()
        raise SystemExit("받은 파일의 해시가 다르다. 지웠다")
    print(f"받았다: {MODEL} ({MODEL.stat().st_size / 1e6:.1f}MB)")


# ── 받아적기 ─────────────────────────────────────────
def cmd_받아적기(src, out, model="small"):
    from faster_whisper import WhisperModel
    src = win(src)
    tmp = Path(tempfile.mkdtemp()) / "a.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", str(tmp)], check=True)
    m = WhisperModel(model, device="auto", compute_type="int8")
    segs, _ = m.transcribe(str(tmp), language="ko", word_timestamps=True, beam_size=5, vad_filter=False)
    words, lines = [], []
    for s in segs:
        lines.append((s.start, s.end, s.text.strip()))
        for w in s.words:
            words.append({"start": round(w.start, 3), "end": round(w.end, 3), "text": w.word.strip()})
    Path(out).write_text(json.dumps({"words": words}, ensure_ascii=False, indent=1), encoding="utf-8")
    for a, b, t in lines:
        print(f"  {a:7.2f}~{b:7.2f}  {t}")
    print(f"낱말 {len(words)}개 → {out}")
    print("같은 문장을 여러 번 말했으면 마지막 온전한 테이크를 고른다. 위스퍼는 되풀이를 한 번만 적을 때가 있다. 의심스러운 곳은 들어 본다")


# ── 컷 ───────────────────────────────────────────────
LEAD, TAIL_MID, TAIL_END = 0.30, 0.30, 0.45


def cmd_컷(src, plan_p, out):
    import audio_levels as L
    src = win(src)
    plan = json.loads(Path(plan_p).read_text(encoding="utf-8"))
    wav = Path(out).with_suffix(".wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)
    db = L.compute(str(wav), str(Path(out).with_suffix(".levels.npy")))
    H = L.HOP

    def quiet(a, b, late):
        i0, i1 = int(a / H), int(b / H)
        if i1 <= i0 + 2:
            return b if late else a
        k = max(1, int(0.03 / H))
        v = np.convolve(db[i0:i1], np.ones(k) / k, mode="same")
        j = (len(v) - 1 - int(np.argmin(v[::-1]))) if late else int(np.argmin(v))
        return (i0 + j) * H

    keep = []
    for it in plan:
        a, b, text = float(it["from"]), float(it["to"]), it.get("text", "")
        pad = TAIL_END if text.rstrip().endswith((".", "?", "!")) else TAIL_MID
        keep.append({"from": round(quiet(a - LEAD, a - 0.04, True), 3), "to": round(quiet(b + 0.06, b + pad, False), 3), "text": text})
    Path(out).write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    tot = sum(k["to"] - k["from"] for k in keep)
    print(f"조각 {len(keep)}개 · {tot:.1f}초 → {out}")


# ── 합성 ─────────────────────────────────────────────
def _probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:stream_side_data=rotation:stream_tags=rotate", "-of", "json", path],
                       capture_output=True, text=True)
    st = json.loads(r.stdout)["streams"][0]
    w, h = st["width"], st["height"]
    rot = 0
    for sd in st.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    rot = rot or int((st.get("tags") or {}).get("rotate", 0))
    if abs(rot) % 180 == 90:
        w, h = h, w
    return w, h


class Matte:
    def __init__(self, model):
        import onnxruntime as ort
        self.s = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
        self.reset()

    def reset(self):
        self.rec = [np.zeros((1, 1, 1, 1), np.float32)] * 4

    def __call__(self, rgb):
        src = (rgb.astype(np.float32) / 255).transpose(2, 0, 1)[None]
        fgr, pha, *self.rec = self.s.run(None, {"src": src, "r1i": self.rec[0], "r2i": self.rec[1], "r3i": self.rec[2],
                                                "r4i": self.rec[3], "downsample_ratio": np.array([0.25], np.float32)})
        return fgr[0].transpose(1, 2, 0), pha[0, 0]


def _frames(path, W, H, t=None, n=None):
    cmd = ["ffmpeg", "-v", "error"] + (["-ss", f"{t}"] if t is not None else []) + ["-i", path, "-vf",
           f"fps=30,scale={W}:{H}:flags=bicubic", "-f", "rawvideo", "-pix_fmt", "rgb24"] + (["-frames:v", str(n)] if n else [])
    return subprocess.Popen(cmd + ["-"], stdout=subprocess.PIPE)


def _measure(path, m, W, H):
    """가운데 장면에서 머리 꼭대기, 머리 가운데, 머리 폭."""
    dur = duration_us(path) / US
    p = _frames(path, W, H, dur / 2, 8)
    a = None
    for _ in range(8):
        buf = p.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        _, a = m(np.frombuffer(buf, np.uint8).reshape(H, W, 3))
    p.wait()
    m.reset()
    if a is None:
        raise SystemExit("촬영본 가운데 장면을 못 읽었다")
    ys, _ = np.nonzero(a > 0.5)
    if not len(ys):
        raise SystemExit("사람을 못 찾았다(매팅 결과가 비었다)")
    top = int(ys.min())
    band = np.nonzero(a[top + int(H * 0.03):top + int(H * 0.1)] > 0.5)[1]
    return top, int((band.min() + band.max()) / 2), int(band.max() - band.min())


def cmd_합성(src, bg, out, top_y=400, cx_x=960, head_w=275, model=None):
    src, bg, out = win(src), win(bg), win(out)
    model = Path(model) if model else MODEL
    if not model.exists():
        raise SystemExit(f"매팅 모델이 없다: {model}\n  python tools/오프닝.py 모델받기")
    from PIL import Image
    w0, h0 = _probe(src)
    s0 = 1920 / h0 if h0 > w0 else 1080 / h0          # 세로 영상은 높이 1920, 가로 영상은 1080 에서 잰다
    W0, H0 = int(round(w0 * s0 / 2) * 2), int(round(h0 * s0 / 2) * 2)
    m = Matte(model)
    top0, cx0, hw0 = _measure(src, m, W0, H0)
    k = head_w / max(hw0, 1)
    W, H = int(round(W0 * k / 2) * 2), int(round(H0 * k / 2) * 2)
    top, cx = int(round(top0 * H / H0)), int(round(cx0 * W / W0))
    dx, dy = cx_x - cx, top_y - top
    print(f"촬영본 {w0}x{h0} → 작업 {W}x{H} (머리 폭 {hw0}px → {head_w}px) · 머리 꼭대기 {top} · 가운데 {cx} · 이동 ({dx}, {dy})")
    bgi = np.asarray(Image.open(bg).convert("RGB").resize((1920, 1080))).astype(np.float32)
    y0, y1 = max(0, -dy - 40), min(H, 1080 - dy)
    ox0, ox1 = max(0, dx), min(1920, dx + W)
    sx0, sx1 = ox0 - dx, ox1 - dx
    skip = max(0, -(y0 + dy))
    oy0, oy1 = y0 + dy + skip, y1 + dy
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-r", "30",
                            "-i", "-", "-i", src, "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                            "-pix_fmt", "yuv420p", "-g", "30", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest",
                            "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    dec = _frames(src, W, H)
    n, t0 = 0, time.time()
    FB = W * H * 3
    while True:
        buf = dec.stdout.read(FB)
        if len(buf) < FB:
            break
        img = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        fgr, a = m(img[y0:y1])
        comp = bgi.copy()
        a3 = a[skip:, sx0:sx1, None]
        comp[oy0:oy1, ox0:ox1] = comp[oy0:oy1, ox0:ox1] * (1 - a3) + fgr[skip:, sx0:sx1] * 255 * a3
        try:
            enc.stdin.write(np.clip(comp, 0, 255).astype(np.uint8).tobytes())
        except OSError:
            print(f"  인코더가 먼저 끝났다({n} 프레임). 소리가 영상보다 짧으면 -shortest 로 거기서 멈춘다")
            break
        n += 1
        if n % 300 == 0:
            print(f"  {n} 프레임 · {n / (time.time() - t0):.1f} fps", flush=True)
    dec.kill()
    try:
        enc.stdin.close()
    except OSError:
        pass
    enc.wait()
    if enc.returncode:
        raise SystemExit(f"인코더 오류 {enc.returncode}")
    print(f"끝: {n} 프레임 {time.time() - t0:.0f}초 → {out}")


# ── 붙이기 ───────────────────────────────────────────
def _parse_span(s):
    a, b = s.split("-")
    return int(round(float(a) * US)), int(round(float(b) * US))


def cmd_붙이기(name, op, cut_p, subs_p, where, intro=None, old=None, dry=False):
    op = win(op)
    clips = [(int(round(k["from"] * US)), int(round(k["to"] * US))) for k in json.loads(Path(cut_p).read_text(encoding="utf-8"))]
    subs = json.loads(Path(subs_p).read_text(encoding="utf-8"))
    L = sum(b - a for a, b in clips)
    op_dur = duration_us(op)
    if clips[-1][1] > op_dur:
        raise SystemExit("컷 구간이 합성본보다 길다")
    fs, d = load(name)
    idx = mindex(d)
    vt = main_track(d)
    vsegs = sorted(vt["segments"], key=lambda s: s["target_timerange"]["start"])

    def mat(s):
        return idx.get(s["material_id"], (None, {}))[1]

    removed_video, removed_text = [], []
    if where == "인트로뒤":
        first = vsegs[0]
        T0 = T_shift = first["target_timerange"]["start"] + first["target_timerange"]["duration"]
        if T0 > 15 * US:
            raise SystemExit(f"첫 클립이 {T0 / US:.1f}초로 길다. 인트로(8초 안팎)가 맨 앞에 있는 드래프트에만 「인트로뒤」를 쓴다")
        delta = L
    elif where == "맨앞":
        if not intro:
            raise SystemExit("「맨앞」에는 --인트로 <인트로.mp4> 가 필요하다")
        intro = win(intro)
        intro_len = -(-duration_us(intro) * 30 // US) * US // 30        # 30fps 프레임으로 올림(캡컷이 8.008초 인트로를 8.033초로 놓는다)
        T0, T_shift, delta = intro_len, 0, intro_len + L
    elif where == "바꾸기":
        if not old:
            raise SystemExit("「바꾸기」에는 --바꿀 시작-끝(초) 이 필요하다")
        o0, o1 = _parse_span(old)
        T0, T_shift, delta = o0, o1, L - (o1 - o0)
        removed_video = [s for s in vsegs if o0 - 2000 <= s["target_timerange"]["start"] < o1 - 2000]
        for t in d["tracks"]:
            if t["type"] == "text" and t.get("name") in ("자막", 말자막.TRACK):
                removed_text += [(t, s) for s in t["segments"] if o0 - 2000 <= s["target_timerange"]["start"] < o1 - 2000]
    else:
        raise SystemExit("--자리 는 인트로뒤 · 맨앞 · 바꾸기 중 하나")

    for t in d["tracks"]:
        for s in t["segments"]:
            a = s["target_timerange"]["start"]
            b = a + s["target_timerange"]["duration"]
            if a < T_shift - 2000 < b - 4000 and s not in removed_video:
                raise SystemExit(f"경계 {T_shift / US:.3f}초에 걸친 조각이 있다: {t['type']} {a / US:.3f}~{b / US:.3f}. 먼저 캡컷에서 그 자리를 자른다")
    old_trans = []
    if removed_video:
        old_trans = [r for s in removed_video for r in s.get("extra_material_refs", []) if idx.get(r, ("",))[0] == "transitions"]
        vt["segments"] = [s for s in vt["segments"] if s not in removed_video]
    for t, s in removed_text:
        t["segments"].remove(s)
    if where == "바꾸기":
        left = [(t["type"], s["target_timerange"]["start"] / US) for t in d["tracks"] for s in t["segments"]
                if o0 + 2000 <= s["target_timerange"]["start"] < o1 - 2000]
        if left:
            raise SystemExit(f"옛 오프닝 구간에 남는 조각이 있다(새 오프닝과 겹친다): {left[:5]}")

    n_shift = 0
    for t in d["tracks"]:
        for s in t["segments"]:
            if s["target_timerange"]["start"] >= T_shift - 2000:
                s["target_timerange"]["start"] += delta
                n_shift += 1

    tmpl = next((s for s in vsegs if s not in removed_video and mat(s).get("path")
                 and s["target_timerange"]["start"] >= T_shift - 2000 + delta), None) or next(
        (s for s in vsegs if s not in removed_video and mat(s).get("path")), None)
    if tmpl is None:
        raise SystemExit("본으로 쓸 강의 영상 클립이 없다")
    tmat = mat(tmpl)

    def video_seg(path, a, b, at, dur_file):
        m = copy.deepcopy(tmat)
        m.update({"id": gid(), "path": path.replace("\\", "/"), "material_name": Path(path).name, "duration": dur_file,
                  "width": 1920, "height": 1080, "local_material_id": ""})
        d["materials"]["videos"].append(m)
        s = copy.deepcopy(tmpl)
        s.update({"id": gid(), "material_id": m["id"], "volume": 1.0, "last_nonzero_volume": 1.0,
                  "source_timerange": {"start": a, "duration": b - a}, "target_timerange": {"start": at, "duration": b - a}})
        s["extra_material_refs"] = [clone_material(d, idx[r][0], idx[r][1]) for r in tmpl.get("extra_material_refs", [])
                                    if r in idx and idx[r][0] != "transitions"]
        s["clip"] = {"scale": {"x": 1.0, "y": 1.0}, "rotation": 0.0, "transform": {"x": 0.0, "y": 0.0},
                     "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0}
        s["common_keyframes"] = []
        s["speed"] = 1.0
        return s

    bfade = template("전환_B페이드.json")["material"]
    diss = template("전환_디졸브.json")["material"]

    def add_trans(seg, m, dur=None):
        e = copy.deepcopy(m)
        if dur:
            e["duration"] = dur
        seg["extra_material_refs"].append(clone_material(d, "transitions", e))

    new_segs = []
    if where == "맨앞":
        s = video_seg(intro, 0, T0, 0, duration_us(intro))
        add_trans(s, bfade)
        new_segs.append(s)
    elif where == "인트로뒤":
        first = vsegs[0]
        if not any(idx.get(r, ("",))[0] == "transitions" for r in first.get("extra_material_refs", [])):
            add_trans(first, bfade)
    at = T0
    for k, (a, b) in enumerate(clips):
        s = video_seg(op, a, b, at, op_dur)
        if k + 1 < len(clips):
            add_trans(s, diss, 200000)               # 오프닝 안 컷 사이는 0.2초 디졸브
        new_segs.append(s)
        at += b - a
    if old_trans:
        new_segs[-1]["extra_material_refs"].append(old_trans[0])
    else:
        add_trans(new_segs[-1], bfade)               # 오프닝 → 본편
    vt["segments"] += new_segs
    vt["segments"].sort(key=lambda s: s["target_timerange"]["start"])

    # 말자막
    def to_edit(src):
        acc = T0
        for a, b in clips:
            if a / US - 0.3 <= src <= b / US:
                return acc + int(round(max(src, a / US) * US)) - a
            acc += b - a
        raise SystemExit(f"말자막 시각 {src}초가 컷 구간 밖이다")

    def clip_end(src):
        acc = T0
        for a, b in clips:
            if a / US - 0.3 <= src <= b / US:
                return acc + (b - a)
            acc += b - a

    track = next((t for t in d["tracks"] if t.get("name") == 말자막.TRACK), None)
    if track is None:
        track = 말자막.new_track(d)
        d["tracks"].append(track)
    bon = 말자막.load_bon()
    for i, it in enumerate(subs):
        st = to_edit(float(it["src"]))
        en = clip_end(float(it["src"]))
        if i + 1 < len(subs):
            en = min(en, to_edit(float(subs[i + 1]["src"])))
        m, s = 말자막.make(it["text"], st, en - st, bon)
        d["materials"]["texts"].append(m)
        track["segments"].append(s)

    print(f"{name}: 오프닝 클립 {len(clips)}개 {L / US:.2f}초 · 붙인 자리 {T0 / US:.3f}초 · 민 조각 {n_shift}개 {delta / US:+.2f}초 · "
          f"뺀 옛 클립 {len(removed_video)} · 뺀 옛 자막 {len(removed_text)} · 말자막 {len(subs)}줄")
    if dry:
        print("(시험 · 쓰지 않음)")
        return
    save(name, fs, d, "오프닝붙이기_전")


def _opt(a, k, default=None):
    return a[a.index(k) + 1] if k in a else default


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == "모델받기":
        cmd_모델받기()
    elif a[0] == "받아적기":
        cmd_받아적기(a[1], a[2], _opt(a, "--모델", "small"))
    elif a[0] == "컷":
        cmd_컷(a[1], a[2], a[3])
    elif a[0] == "합성":
        cmd_합성(a[1], a[2], a[3], int(_opt(a, "--머리", 400)), int(_opt(a, "--가운데", 960)), int(_opt(a, "--머리폭", 275)), _opt(a, "--모델"))
    elif a[0] == "붙이기":
        cmd_붙이기(a[1], _opt(a, "--합성본"), _opt(a, "--컷"), _opt(a, "--말자막"), _opt(a, "--자리"), _opt(a, "--인트로"),
                  _opt(a, "--바꿀"), "--dry" in a)
    else:
        raise SystemExit(__doc__)
