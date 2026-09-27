# -*- coding: utf-8 -*-
"""비바샘 소리: 오포닉 보정 목소리를 넣고, 영상 소리를 끄고, 배경음악을 깐다.

편집이 다 끝난 뒤에 한다. 순서
  1. 캡컷에서 인트로(0~8초) 소리를 끄고 **오디오만 내보낸다**(처음부터 끝까지 한 파일)
  2. 오포닉(Auphonic)에 올려 Voice Cleaner → Remove Breath 로 보정한다
  3. 받은 파일의 앞뒤 워터마크 음성을 잘라 낸다(못 잘랐으면 4번이 찾아 알린다)
  4. python tools/소리.py 목소리넣기 <드래프트> <보정본.wav>
     보정본을 「보정 목소리」 줄에 깔고, 원래 녹음과 파형을 맞대어 시각을 1ms 단위로 맞춘다.
     그다음 영상 클립 소리를 끈다(인트로 클립은 그대로). 보정본에만 있는 소리(워터마크 의심)를 찾아 알린다

사용
  python tools/소리.py 목소리넣기 <드래프트> <보정본.wav> [--찾기 10] [--dry]   --찾기: 보정본이 앞뒤로 밀렸을 수 있는 초
  python tools/소리.py 맞춤검사 <드래프트>                          보정 목소리가 원래 녹음과 몇 ms 어긋나는지(읽기만)
  python tools/소리.py 음소거 <드래프트> [--dry]                    영상 클립 소리만 끈다(인트로 클립은 그대로)
  python tools/소리.py 배경음악 <드래프트> <bgm.wav> --구간 30.6-70.6,308.4-315.2 [--음량 0.37] [--dry]
                                                                    표지·학습 목표·학습 내용·간지 구간에 배경음악
  python tools/소리.py 음악맞춤 <비바샘 제공 BGM> <출력.wav>          배경음악 크기를 −21.4 LUFS 로 맞춘다(003·배경음악용)
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from _팩 import US, clone_material, duration_us, gid, load, main_track, mindex, save, template, win

SR = 16000
VOICE_TRACK = "보정 목소리"
BGM_TRACK = "배경음악"
INTRO_WORDS = ("인트로", "intro", "Intro", "INTRO")


def _is_intro(seg, m):
    """맨 앞(1초 안에서 시작) 제공 인트로 클립. 오프닝 파일 이름에 「인트로」가 들어 있어도 8초 뒤에 있으면 인트로가 아니다."""
    name = (m.get("material_name") or m.get("path") or "")
    t = seg["target_timerange"]
    return t["start"] < US and (any(w in name for w in INTRO_WORDS) or abs(t["duration"] - 8 * US) < 0.6 * US)


def _audio(path, t, d):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.4f}", "-t", f"{d:.4f}", "-i", win(path), "-vn", "-ac", "1",
                        "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout
    return np.frombuffer(r, np.float32).astype(np.float64)


def _lecture_clips(d, idx):
    out = []
    for s in main_track(d)["segments"]:
        m = idx.get(s["material_id"], (None, {}))[1]
        if not m.get("path") or _is_intro(s, m):
            continue
        tt, st = s["target_timerange"], s.get("source_timerange") or {}
        out.append((tt["start"] / US, (tt["start"] + tt["duration"]) / US, st.get("start", 0) / US, m["path"], s))
    return out


def _points(clips, k=9):
    long = [c for c in clips if c[1] - c[0] >= 4.0]
    if not long:
        return []
    pick = [long[int(i)] for i in np.linspace(0, len(long) - 1, min(k, len(long)))]
    return [((a + b) / 2, a, b, s0, p) for a, b, s0, p, _ in pick]


def _lag(ref, sig, search=None):
    """sig 안에서 ref 가 가장 잘 맞는 자리(표본)와 정규화 상관. FFT 로 한 번에 잰다."""
    m = len(ref)
    if m < 100 or len(sig) < m or ref.std() < 1e-5:
        return None, 0.0
    r = ref - ref.mean()
    r = r / (np.linalg.norm(r) + 1e-12)
    n = 1 << int(np.ceil(np.log2(len(sig) + m)))
    cc = np.fft.irfft(np.fft.rfft(sig, n) * np.fft.rfft(r[::-1], n), n)[m - 1:len(sig)]
    cs = np.concatenate([[0.0], np.cumsum(sig)])
    cs2 = np.concatenate([[0.0], np.cumsum(sig * sig)])
    ws, wq = cs[m:] - cs[:-m], cs2[m:] - cs2[:-m]
    den = np.sqrt(np.maximum(wq - ws * ws / m, 1e-12))
    ncc = cc / den
    ncc[den < 1e-4] = -1
    pos = int(np.argmax(ncc))
    return pos, float(ncc[pos])


def _offset(d, idx, wav, search=10.0):
    """보정본 시각 − 편집 시각(초). 여러 곳에서 재어 가운데 값."""
    res = []
    for t, a, b, s0, path in _points(_lecture_clips(d, idx)):
        raw = _audio(path, s0 + (t - a) - 1.0, 2.0)
        sig = _audio(wav, t - search - 1.0, 2 * search + 2.0)
        pos, c = _lag(raw, sig, search)
        if pos is None or c < 0.5:
            continue
        res.append((t, (t - search - 1.0) + pos / SR - (t - 1.0), c))
    if len(res) < 3:
        raise SystemExit(f"보정본과 원래 녹음을 맞댈 곳을 {len(res)}곳밖에 못 찾았다. 캡컷에서 내보낸 오디오가 지금 편집과 같은지 본다")
    offs = np.array([o for _, o, _ in res])
    med = float(np.median(offs))
    spread = float(offs.max() - offs.min())
    return med, spread, res


def cmd_맞춤검사(name):
    _, d = load(name)
    idx = mindex(d)
    tr = next((t for t in d["tracks"] if t.get("name") == VOICE_TRACK), None)
    if tr is None:
        cand = [t for t in d["tracks"] if t["type"] == "audio" and t["segments"]]
        tr = max(cand, key=lambda t: sum(s["target_timerange"]["duration"] for s in t["segments"]), default=None)
    if tr is None:
        raise SystemExit("목소리 줄이 없다")
    print(f"{name}: 「{tr.get('name') or '이름 없는 소리 줄'}」 대 원래 녹음 (+ 면 목소리가 늦다)")
    for t, a, b, s0, path in _points(_lecture_clips(d, idx)):
        seg = next((s for s in tr["segments"] if s["target_timerange"]["start"] / US <= t - 1.5
                    and (s["target_timerange"]["start"] + s["target_timerange"]["duration"]) / US >= t + 1.5), None)
        if seg is None:
            continue
        vpath = idx[seg["material_id"]][1]["path"]
        vt = seg["source_timerange"]["start"] / US + (t - seg["target_timerange"]["start"] / US)
        raw = _audio(path, s0 + (t - a) - 1.0, 2.0)
        sig = _audio(vpath, vt - 1.2, 2.4)
        pos, c = _lag(raw, sig, 0.2)
        if pos is not None:
            print(f"  편집 {int(t // 60)}:{t % 60:05.2f} · 어긋남 {((pos / SR) - 0.2) * 1000:+6.1f}ms · 상관 {c:.2f}")


def _mute(d, idx):
    n = 0
    for t in d["tracks"]:
        if t["type"] != "video":
            continue
        for s in t["segments"]:
            m = idx.get(s["material_id"], (None, {}))[1]
            if _is_intro(s, m) or not (s.get("volume") or 0) > 0:
                continue
            s["last_nonzero_volume"] = s.get("volume") or 1.0
            s["volume"] = 0.0
            n += 1
    return n


def cmd_음소거(name, dry):
    fs, d = load(name)
    n = _mute(d, mindex(d))
    print(f"{name}: 소리를 끌 영상 클립 {n}개 (인트로 클립 제외)")
    if not dry and n:
        save(name, fs, d, "영상소리끄기_전")


def _audio_seg(d, path, src_start, tgt_start, dur, volume, fades=True):
    t = template("소리조각_BGM.json")
    m = copy.deepcopy(t["material"])
    m.update({"id": gid(), "path": win(path).replace("\\", "/"), "name": Path(path).name, "duration": duration_us(path),
              "local_material_id": "", "music_id": gid().lower()})
    d["materials"].setdefault("audios", []).append(m)
    s = copy.deepcopy(t["segment"])
    s.update({"id": gid(), "material_id": m["id"], "volume": volume, "last_nonzero_volume": volume,
              "source_timerange": {"start": int(src_start), "duration": int(dur)},
              "target_timerange": {"start": int(tgt_start), "duration": int(dur)}})
    s["extra_material_refs"] = [clone_material(d, e["kind"], e["material"]) for e in t["extras"]
                                if fades or e["kind"] != "audio_fades"]
    return s


def _audio_track(d, name):
    tr = next((t for t in d["tracks"] if t.get("name") == name), None)
    if tr is None:
        tr = {"id": gid(), "type": "audio", "flag": 0, "attribute": 0, "name": name, "is_default_name": False, "segments": []}
        d["tracks"].append(tr)
    return tr


def _only_in_wav(d, idx, wav, off, lo, hi):
    """lo~hi(편집 시각)에서 보정본에는 소리가 있는데 원래 녹음은 조용한 구간. 워터마크 의심."""
    if hi - lo < 1.0:
        return []
    step = int(0.05 * SR)
    w = _audio(wav, lo + off, hi - lo)
    raw = np.zeros(len(w))
    for a, b, s0, path, _ in _lecture_clips(d, idx):
        x0, x1 = max(a, lo), min(b, hi)
        if x1 <= x0:
            continue
        r = _audio(path, s0 + (x0 - a), x1 - x0)
        i = int((x0 - lo) * SR)
        raw[i:i + len(r)] = r[:max(0, len(raw) - i)]
    out, run = [], 0
    for i in range(0, len(w) - step, step):
        wdb = 20 * np.log10(np.sqrt(np.mean(w[i:i + step] ** 2)) + 1e-9)
        rdb = 20 * np.log10(np.sqrt(np.mean(raw[i:i + step] ** 2)) + 1e-9)
        if wdb > -40 and rdb < -55:
            run += 1
            continue
        if run * 0.05 >= 0.8:
            out.append((lo + (i / SR) - run * 0.05, lo + i / SR))
        run = 0
    if run * 0.05 >= 0.8:
        out.append((hi - run * 0.05, hi))
    return out


def cmd_목소리넣기(name, wav, dry, search=10.0):
    wav = win(wav)
    fs, d = load(name)
    idx = mindex(d)
    if any(t.get("name") == VOICE_TRACK for t in d["tracks"]):
        raise SystemExit(f"「{VOICE_TRACK}」 줄이 이미 있다. 다시 넣으려면 캡컷에서 그 줄을 지우고 한다")
    off, spread, res = _offset(d, idx, wav, search)
    for t, o, c in res:
        print(f"  편집 {int(t // 60)}:{t % 60:05.2f} · 보정본이 {o * 1000:+8.1f}ms · 상관 {c:.2f}")
    print(f"보정본 시각 = 편집 시각 {off * 1000:+.1f}ms (재는 곳끼리 차 {spread * 1000:.1f}ms)")
    if spread > 0.02:
        raise SystemExit("재는 곳마다 차이가 20ms 넘게 다르다. 오디오를 내보낸 뒤 편집을 바꿨는지 보고, 다시 내보내 보정한다")
    total = max(s["target_timerange"]["start"] + s["target_timerange"]["duration"] for s in main_track(d)["segments"])
    wlen = duration_us(wav)
    src0, tgt0 = (int(round(off * US)), 0) if off >= 0 else (0, int(round(-off * US)))
    dur = min(wlen - src0, total - tgt0)
    tr = _audio_track(d, VOICE_TRACK)
    tr["segments"].append(_audio_seg(d, wav, src0, tgt0, dur, 1.0, fades=False))
    n = _mute(d, idx)
    print(f"「{VOICE_TRACK}」 줄: 보정본 {src0 / US:.3f}초부터 편집 {tgt0 / US:.3f}초에 {dur / US:.1f}초 · 영상 클립 소리 끔 {n}개")
    sus = _only_in_wav(d, idx, wav, off, max(0.0, tgt0 / US), min(20.0, total / US)) + \
        _only_in_wav(d, idx, wav, off, max(0.0, total / US - 20.0), total / US)
    for a, b in sus:
        print(f"  ⚠ 보정본에만 있는 소리 {a:.1f}~{b:.1f}초(편집 시각). 오포닉 워터마크이거나, 인트로를 끄지 않고 내보내 인트로 음악이 섞였을 수 있다. 들어 본다")
    if dry:
        print("(시험 · 쓰지 않음)")
        return
    save(name, fs, d, "보정목소리넣기_전")


def cmd_배경음악(name, bgm, spans, vol, dry):
    bgm = win(bgm)
    fs, d = load(name)
    tr = _audio_track(d, BGM_TRACK)
    blen = duration_us(bgm)
    n = 0
    for sp in spans.split(","):
        a, b = (int(round(float(x) * US)) for x in sp.split("-"))
        dur = min(b - a, blen)
        tr["segments"].append(_audio_seg(d, bgm, 0, a, dur, vol))
        n += 1
    print(f"{name}: 배경음악 {n}곳 · 음량 {vol} · 앞 1초 페이드인 · 끝 2초 페이드아웃")
    if not dry:
        save(name, fs, d, "배경음악_전")


def cmd_음악맞춤(src, out, target=-21.4):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", win(src), "-af", f"loudnorm=I={target}:TP=-2:LRA=11", "-ar", "48000", "-ac", "2",
                    win(out)], check=True)
    print(f"{out}: {target} LUFS 로 맞췄다")


def _opt(a, k, default=None):
    return a[a.index(k) + 1] if k in a else default


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == "목소리넣기":
        cmd_목소리넣기(a[1], a[2], "--dry" in a, float(_opt(a, "--찾기", 10)))
    elif a[0] == "맞춤검사":
        cmd_맞춤검사(a[1])
    elif a[0] == "음소거":
        cmd_음소거(a[1], "--dry" in a)
    elif a[0] == "배경음악":
        cmd_배경음악(a[1], a[2], _opt(a, "--구간"), float(_opt(a, "--음량", 0.37)), "--dry" in a)
    elif a[0] == "음악맞춤":
        cmd_음악맞춤(a[1], a[2])
    else:
        raise SystemExit(__doc__)
