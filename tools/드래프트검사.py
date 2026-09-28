# -*- coding: utf-8 -*-
"""굽기 전에 드래프트를 검사한다. 읽기만 한다(캡컷이 켜져 있어도 된다).

  python tools/드래프트검사.py <드래프트> ...

보는 것: 소재 끊김 · 주 트랙 순서 · 인트로 · 말자막 서식과 자리 · 강의 자막 숨김 · 영상 소리(보정 목소리와 겹침) · 배경음악
"""
import os
import subprocess
import sys

from _팩 import LECTURE_CUT, US, load, main_track, main_track_gaps, mindex, resolve
import 말자막


def check(name):
    fs, d = load(name)
    idx = mindex(d)
    bad, warn, ok = [], [], []

    from draft_doctor import contents, scan
    broken = 0
    for q in contents(resolve(name), sub=True):
        broken += scan(q)[1]
    (bad if broken else ok).append(f"끊긴 소재 {broken}개")
    if len({f.read_bytes() for f in fs}) != 1:
        bad.append("뿌리와 Timelines 사본이 서로 다르다(캡컷에서 한 번 열었다 닫으면 맞춰진다)")

    gaps = main_track_gaps(d)
    (bad if gaps else ok).append(f"주 트랙 틈·겹침 {len(gaps)}곳" + (f" (첫 곳 {gaps[0][0]:.2f}→{gaps[0][1]:.2f}초)" if gaps else ""))

    v = main_track(d)["segments"]
    m0 = idx.get(v[0]["material_id"], (None, {}))[1]
    intro_like = "인트로" in (m0.get("material_name") or m0.get("path") or "") or abs(v[0]["target_timerange"]["duration"] - 8 * US) < 0.6 * US
    (ok if intro_like else warn).append("맨 앞 인트로(8초)" + ("" if intro_like else " 없음"))

    tr = next((t for t in d["tracks"] if t.get("name") == 말자막.TRACK), None)
    if not tr or not tr["segments"]:
        warn.append("「인트로 말자막」 줄이 없다")
    else:
        mis = {}
        for s in tr["segments"]:
            for x in 말자막.mismatch(idx[s["material_id"]][1], s):
                mis[x] = mis.get(x, 0) + 1
        (bad if mis else ok).append(f"말자막 {len(tr['segments'])}줄 서식 " + ("맞음" if not mis else "다름: " + " · ".join(f"{k}({n}줄)" for k, n in mis.items())))
        import json
        long_lines = [json.loads(idx[s["material_id"]][1]["content"])["text"] for s in tr["segments"] if s["target_timerange"]["start"] < 150 * US]
        long_lines = [x for x in long_lines if len(x.splitlines()) > 1 or len(x.replace(" ", "")) > 25 or len(x) > 28]
        if long_lines:
            warn.append(f"말자막 {len(long_lines)}줄이 두 줄이거나 25자를 넘는다(가급적 한 줄 25자 안, 길면 두 번에 나눈다): "
                        + " / ".join("「" + " ".join(x.split())[:30] + "」" for x in long_lines[:3]))
        late = [(s["target_timerange"]["start"] / US, " ".join(json.loads(idx[s["material_id"]][1]["content"])["text"].split()))
                for s in tr["segments"] if s["target_timerange"]["start"] > 150 * US]
        if late:
            warn.append(f"「{말자막.TRACK}」 줄에 오프닝 밖(150초 뒤) 글이 {len(late)}줄 있다. 지도 Tip 자막이면 그대로 둔다. "
                        "말을 받아 적은 자막이면 뺀다(본연수 말자막 금지): " + " / ".join(f"{t // 60:.0f}:{t % 60:04.1f} 「{x[:24]}」" for t, x in late[:4]))

    lec = [t for t in d["tracks"] if t["type"] == "text" and t.get("name") != 말자막.TRACK and t["segments"]]
    shown = [t for t in lec if not (t.get("attribute") or 0) & 2]
    if shown:
        warn.append(f"강의 자막 줄 {len(shown)}개가 보이는 상태다. 굽기 직전에 숨긴다(줄 왼쪽 눈 아이콘)")

    audio = [t for t in d["tracks"] if t["type"] == "audio"]
    bgm = [t for t in audio if t.get("name") == "배경음악" or any(0 < (s.get("volume") or 0) < 0.6 for s in t["segments"])]
    (ok if bgm else warn).append("배경음악 줄" + ("" if bgm else " 없음. 표지·학습 목표·학습 내용·간지에 깐다"))

    r = subprocess.run([sys.executable, str(LECTURE_CUT / "src" / "verify_draft_audio.py"), name], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    for line in r.stdout.splitlines():
        if "같은 말이 두 번" in line or "소리를 낸다" in line:
            bad.append("보정 목소리 밑에서 영상 클립 소리가 난다. python tools/소리.py 음소거 " + name)
        if "소리 관련 검사 통과" in line:
            ok.append("소리 검사 통과")
    print(f"== {name}")
    for x in bad:
        print(f"  ✗ {x}")
    for x in warn:
        print(f"  △ {x}")
    for x in ok:
        print(f"  ○ {x}")
    return not bad


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
    else:
        good = [check(n) for n in sys.argv[1:]]
        sys.exit(0 if all(good) else 1)
