# -*- coding: utf-8 -*-
"""비바샘 팩 도구가 같이 쓰는 것. lecture-cut 을 찾고, 드래프트를 읽고 쓰고, 본(템플릿)을 연다."""
import copy
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

PACK = Path(__file__).resolve().parent.parent
TEMPLATES = PACK / "templates"
US = 1_000_000


def _find_lecture_cut():
    cands = [os.environ.get("LECTURE_CUT"), Path.home() / ".claude" / "skills" / "lecture-cut",
             PACK.parent / "lecture-cut", Path("C:/projects/lecture-cut")]
    for c in cands:
        if c and (Path(c) / "src" / "draft_doctor.py").exists():
            return Path(c)
    raise SystemExit("lecture-cut 을 못 찾았다. 환경변수 LECTURE_CUT 에 lecture-cut 폴더를 지정하세요 "
                     "(https://github.com/ksb6857/lecture-cut)")


LECTURE_CUT = _find_lecture_cut()
sys.path.insert(0, str(LECTURE_CUT / "src"))

from draft_doctor import contents, resolve  # noqa: E402,F401
from port_effects import capcut_running  # noqa: E402,F401


def gid():
    u = str(uuid.uuid4()).upper().split("-")
    u[2] = u[2].lower()
    return "-".join(u)


def mindex(d):
    """소재 id -> (종류, 소재)"""
    return {m["id"]: (k, m) for k, l in d["materials"].items() if isinstance(l, list)
            for m in l if isinstance(m, dict) and "id" in m}


def load(name):
    """드래프트 본문 사본들(뿌리·Timelines, 하위 프로젝트 제외)과 그 내용."""
    fs = contents(resolve(name))
    if not fs:
        raise SystemExit(f"{name}: draft_content.json 이 없다")
    return fs, json.loads(fs[0].read_text(encoding="utf-8"))


def same_copies(fs):
    return len({f.read_bytes() for f in fs}) == 1


def save(name, fs, d, memo):
    """캡컷이 꺼져 있을 때만. 판을 떠 두고 사본 모두에 같은 내용을 쓴다. 길이도 맞춘다."""
    if capcut_running():
        raise SystemExit("캡컷이 실행 중입니다. 완전히 종료한 뒤 다시 실행하세요.")
    for t in d["tracks"]:
        t["segments"].sort(key=lambda s: s["target_timerange"]["start"])
    order = main_track_gaps(d)
    if order:
        raise SystemExit(f"주 트랙에 틈이나 겹침이 있다(첫 곳 {order[0][0]:.3f} → {order[0][1]:.3f}초). 쓰지 않는다")
    end = max((s["target_timerange"]["start"] + s["target_timerange"]["duration"]
               for t in d["tracks"] for s in t["segments"]), default=0)
    d["duration"] = end
    import draft_snapshot
    draft_snapshot.save(name, memo)
    text = json.dumps(d, ensure_ascii=False)
    for f in fs:
        f.write_text(text, encoding="utf-8")
    mp = resolve(name) / "draft_meta_info.json"
    if mp.exists():
        meta = json.loads(mp.read_text(encoding="utf-8"))
        meta["tm_duration"] = end
        mp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    print(f"썼다: {name} (사본 {len(fs)}벌, 길이 {end / US:.2f}초, 판 「{memo}」)")


def main_track(d):
    return next(t for t in d["tracks"] if t["type"] == "video")


def main_track_gaps(d):
    """주 트랙 목록 순서대로 이어 볼 때 틈·겹침(2ms 넘는) 목록. 캡컷은 목록 순서로 늘어놓는다."""
    out, prev = [], None
    for s in main_track(d)["segments"]:
        a = s["target_timerange"]["start"]
        if prev is not None and abs(a - prev) > 2000:
            out.append((prev / US, a / US))
        prev = a + s["target_timerange"]["duration"]
    return out


def template(name):
    """templates/<name>.json 을 읽는다. {LOCALAPPDATA} 는 이 PC 경로로 바꾼다."""
    s = (TEMPLATES / name).read_text(encoding="utf-8")
    la = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")).replace("\\", "/")
    return json.loads(s.replace("{LOCALAPPDATA}", la))


def clone_material(d, kind, m):
    """소재 하나를 새 id 로 복제해 드래프트에 넣고 id 를 돌려준다."""
    e = copy.deepcopy(m)
    e["id"] = gid()
    d["materials"].setdefault(kind, []).append(e)
    return e["id"]


def duration_us(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return int(round(float(r.stdout.strip()) * US))
    except ValueError:
        raise SystemExit(f"길이를 못 읽었다: {path}")


def win(path):
    """Git Bash 경로(/c/...)를 C:/... 로. 파이썬이 부른 ffmpeg 는 /c/ 경로를 못 연다."""
    p = str(path)
    if len(p) > 2 and p[0] == "/" and p[2] == "/" and p[1].isalpha():
        p = p[1].upper() + ":" + p[2:]
    return p
