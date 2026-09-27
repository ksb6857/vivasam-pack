# -*- coding: utf-8 -*-
"""비바샘 말자막 서식.

    글꼴 고딕체 · 크기 6 · 흰색 · 위치 Y −810 · 배경 검정 불투명도 70 · 높이 0

- 「고딕체」는 캡컷 글꼴 목록의 이름이다. 드래프트에는 리소스 6808056385679397389, 파일 DoHyeon-Regular.ttf 로 적힌다
- 위치 Y −810 은 드래프트 값 transform.y −0.75 다(−0.75 × 1080)
- 캡컷 값은 짓지 않는다. 사람이 캡컷에서 만든 말자막 한 줄을 templates/말자막_본.json 으로 떠 두고,
  새 말자막은 그 소재와 조각을 복제해 글과 시각만 바꾼다
- 말자막 줄 이름은 「인트로 말자막」. 강의 자막(편집용, 굽기 전에 숨김)과 다른 줄이다

사용
  python tools/말자막.py 검사 <드래프트> ...          「인트로 말자막」 줄마다 서식이 맞는지 본다(읽기만)
  python tools/말자막.py 맞추기 <드래프트> [--dry]    글과 시각은 두고 서식만 본으로 바꾼다(캡컷을 끈 뒤)
  python tools/말자막.py 뜨기 <드래프트>              (팩 관리용) 서식이 맞는 줄 하나를 본으로 뜬다
"""
import copy
import json
import os
import sys
import time

from _팩 import TEMPLATES, gid, load, mindex, save, template

TRACK = "인트로 말자막"
STYLE = {"font_resource_id": "6808056385679397389", "size": 6.0, "color": [1.0, 1.0, 1.0],
         "background_style": 1, "background_color": "#000000", "background_alpha": 0.70, "background_height": 0.0, "y": -0.75}
STYLE_TEXT = "고딕체 · 크기 6 · 흰색 · 위치 Y −810 · 배경 검정 불투명도 70 · 높이 0"


def mismatch(m, s):
    """본 서식과 다른 점. 비었으면 맞다."""
    out = []
    c = json.loads(m.get("content") or "{}")
    if str(m.get("font_resource_id")) != STYLE["font_resource_id"]:
        out.append(f"글꼴 {m.get('font_title') or os.path.basename(m.get('font_path', ''))}")
    sizes = {float(st.get("size", -1)) for st in c.get("styles", [])} | {float(m.get("font_size", -1))}
    if sizes != {STYLE["size"]}:
        out.append(f"크기 {sorted(sizes)}")
    for st in c.get("styles", []):
        col = ((st.get("fill") or {}).get("content") or {}).get("solid", {}).get("color")
        if col is not None and [round(float(x), 3) for x in col] != STYLE["color"]:
            out.append(f"글자색 {col}")
            break
    if m.get("background_style") != STYLE["background_style"] or str(m.get("background_color")).lower() != STYLE["background_color"]:
        out.append(f"배경 {m.get('background_style')} {m.get('background_color')}")
    if abs(float(m.get("background_alpha", -1)) - STYLE["background_alpha"]) > 0.005:
        out.append(f"불투명도 {float(m.get('background_alpha', -1)) * 100:.1f}")
    if abs(float(m.get("background_height", -1)) - STYLE["background_height"]) > 1e-6:
        out.append(f"배경 높이 {m.get('background_height')}")
    tr = (s.get("clip") or {}).get("transform") or {}
    if abs(float(tr.get("y", 9)) - STYLE["y"]) > 0.001 or abs(float(tr.get("x", 9))) > 0.001:
        out.append(f"위치 X {float(tr.get('x', 0)) * 1920:.0f} Y {float(tr.get('y', 0)) * 1080:.0f}")
    return out


def load_bon():
    b = template("말자막_본.json")
    font = b["material"].get("font_path", "")
    if font and not os.path.exists(font):
        print("  알림: 이 PC 캡컷에 「고딕체」 글꼴 파일이 아직 없다. 캡컷에서 글자를 하나 넣고 글꼴을 「고딕체」로 한 번 고르면 받아진다")
    return b


def make(text, start, dur, bon=None):
    """본을 복제해 말자막 한 줄(소재, 조각)을 만든다. 시각은 µs."""
    b = bon or load_bon()
    m = copy.deepcopy(b["material"])
    m["id"] = gid()
    c = json.loads(m["content"])
    c["text"] = text
    for st in c["styles"]:
        st["range"] = [0, len(text)]
    m["content"] = json.dumps(c, ensure_ascii=False, separators=(",", ":"))
    s = copy.deepcopy(b["segment"])
    s.update({"id": gid(), "material_id": m["id"], "target_timerange": {"start": int(start), "duration": int(dur)},
              "extra_material_refs": [], "track_attribute": 0, "visible": True})
    bad = mismatch(m, s)
    if bad:
        raise SystemExit(f"본이 정한 서식과 다르다: {bad} · {TEMPLATES / '말자막_본.json'}")
    return m, s


def new_track(d):
    """「인트로 말자막」 줄을 만든다(강의 자막 줄의 속성을 본뜬다)."""
    src = next((t for t in d["tracks"] if t["type"] == "text"), None)
    t = {k: copy.deepcopy(v) for k, v in (src or {"type": "text", "flag": 0}).items() if k != "segments"}
    t.update({"id": gid(), "type": "text", "name": TRACK, "attribute": 0, "segments": [], "is_default_name": False})
    return t


def cmd_검사(names):
    for name in names:
        _, d = load(name)
        idx = mindex(d)
        tr = next((t for t in d["tracks"] if t.get("name") == TRACK), None)
        if not tr:
            print(f"{name}: 「{TRACK}」 줄 없음")
            continue
        bad = {}
        for s in tr["segments"]:
            for x in mismatch(idx[s["material_id"]][1], s):
                bad[x] = bad.get(x, 0) + 1
        print(f"{name}: 말자막 {len(tr['segments'])}줄 · " + ("서식 맞음" if not bad else
              "다른 곳 " + " · ".join(f"{k}({v}줄)" for k, v in bad.items())))


def cmd_맞추기(name, dry):
    fs, d = load(name)
    idx = mindex(d)
    tr = next((t for t in d["tracks"] if t.get("name") == TRACK), None)
    if not tr:
        raise SystemExit(f"{name}: 「{TRACK}」 줄이 없다")
    bon = load_bon()
    n = 0
    for s in tr["segments"]:
        m = idx[s["material_id"]][1]
        if not mismatch(m, s):
            continue
        text = json.loads(m["content"])["text"]
        m2, s2 = make(text, s["target_timerange"]["start"], s["target_timerange"]["duration"], bon)
        m2["id"] = m["id"]
        m.clear()
        m.update(m2)
        s["clip"] = copy.deepcopy(s2["clip"])
        n += 1
    print(f"{name}: 서식을 바꿀 말자막 {n}줄 / {len(tr['segments'])}줄")
    if dry or not n:
        print("(쓰지 않음)")
        return
    save(name, fs, d, "말자막서식_전")
    cmd_검사([name])


def cmd_뜨기(name):
    _, d = load(name)
    idx = mindex(d)
    tr = next((t for t in d["tracks"] if t.get("name") == TRACK), None)
    if not tr:
        raise SystemExit(f"{name}: 「{TRACK}」 줄이 없다")
    for s in sorted(tr["segments"], key=lambda s: s["target_timerange"]["start"]):
        m = idx[s["material_id"]][1]
        if mismatch(m, s) or s.get("extra_material_refs"):
            continue
        m2 = copy.deepcopy(m)
        c = json.loads(m2["content"])
        c["text"] = "말자막"
        for st in c["styles"]:
            st["range"] = [0, 3]
        m2["content"] = json.dumps(c, ensure_ascii=False, separators=(",", ":"))
        s2 = copy.deepcopy(s)
        s2["target_timerange"] = {"start": 0, "duration": 1_000_000}
        text = json.dumps({"_출처": f"사람이 캡컷에서 만든 말자막 한 줄 ({time.strftime('%Y-%m-%d')})", "_서식": STYLE_TEXT,
                           "material": m2, "segment": s2}, ensure_ascii=False, indent=1)
        la = os.environ.get("LOCALAPPDATA", "").replace("\\", "/")
        if la:
            text = text.replace(la, "{LOCALAPPDATA}")
        (TEMPLATES / "말자막_본.json").write_text(text, encoding="utf-8")
        print(f"본을 떴다 ← {name} 「{json.loads(m['content'])['text']}」")
        return
    raise SystemExit(f"{name}: 서식({STYLE_TEXT})이 맞는 줄이 없다")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == "검사":
        cmd_검사(a[1:])
    elif a[0] == "맞추기":
        cmd_맞추기(a[1], "--dry" in a)
    elif a[0] == "뜨기":
        cmd_뜨기(a[1])
    else:
        raise SystemExit(__doc__)
