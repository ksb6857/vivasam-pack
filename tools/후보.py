# -*- coding: utf-8 -*-
"""삭제 후보 표시: 내용 판단(청크 분석)이 「검토」로 남긴 말을 드래프트에 노란 글자로 띄운다. 자동으로 지우지 않는다.

  python tools/후보.py <드래프트> <analysis.json> <낱말.json> [--붙이기] [--출력 후보.json]

- <analysis.json> 은 lecture-cut merge_analysis 결과. `deletions_review`(confidence medium)를 쓴다
- <낱말.json> 은 청크 분석에 쓴 전사(원본 시각). 낱말 번호를 시각으로 바꾼다
- 청크 분석 지시문(lecture-cut docs/청크분석.md)의 「선생님이 최종 편집에서 지운 말」 유형을 medium 으로 받는다:
  같은 뜻 되풀이 · 진행 안내 · 화면 글 소리 내 읽기 · 오프닝과 겹치는 첫 인사 · 곁가지 · 사실과 다른 말
- --붙이기: lecture-cut apply_notes 로 「삭제 후보」 줄을 만든다. 선생님이 보고 지운 뒤 그 줄을 지운다

글자 패턴으로 찾는 판(2026-09-28 시험)은 네 차시에서 후보 75곳 중 11곳만 선생님이 실제로 지운 말이라 버렸다.
"""
import json
import subprocess
import sys
from pathlib import Path

from _팩 import LECTURE_CUT, load, win

import timemap  # noqa: E402


def _opt(a, k, default=None):
    return a[a.index(k) + 1] if k in a else default


def main(a):
    name, ap, wp = a[0], win(a[1]), win(a[2])
    _, d = load(name)
    tl = timemap.timeline(d)
    ana = json.loads(Path(ap).read_text(encoding="utf-8"))
    words = {w["i"]: w for w in json.loads(Path(wp).read_text(encoding="utf-8"))["words"] if "i" in w}
    items = []
    for r in ana.get("deletions_review", []):
        if "from_t" in r:
            s0, s1, said = float(r["from_t"]), float(r["to_t"]), r.get("text", "")
        else:
            ws = [words[i] for i in range(int(r["from_i"]), int(r["to_i"]) + 1) if i in words]
            if not ws:
                continue
            s0, s1 = ws[0]["start"], ws[-1]["end"]
            said = " ".join(w["text"].strip() for w in ws)
        e = timemap.span_to_edit(tl, s0, s1)
        if e is None:
            continue                                   # 이미 잘려 나갔다
        items.append({"src": [round(s0, 2), round(s1, 2)], "why": r.get("reason", ""), "said": said, "edit": e[0]})
    print(f"{name}: 삭제 후보 {len(items)}곳 (자동으로 지우지 않는다)")
    for it in items:
        print(f"  편집 {int(it['edit'] // 60)}:{it['edit'] % 60:04.1f} · {it['why'][:30]} · 「{it['said'][:40]}」")
    plan = {"track": "삭제 후보", "items": [{"src": it["src"], "text": f"삭제 후보 · {it['why'][:40]}\n「{it['said'][:30]}」"} for it in items]}
    out = _opt(a, "--출력", str(Path(ap).with_name(Path(ap).stem.replace("_analysis", "") + "_삭제후보.json")))
    Path(out).write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"계획: {out}")
    if "--붙이기" in a:
        subprocess.run([sys.executable, str(LECTURE_CUT / "src" / "apply_notes.py"), name, out], check=True)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
    else:
        main(sys.argv[1:])
