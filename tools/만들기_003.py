# -*- coding: utf-8 -*-
"""003(정리 영상, 40초 안팎) 캡컷 드래프트를 만든다.

003 은 목소리 없이 슬라이드 그림을 넘기며 배경음악만 깐다.
  돌아보기 1 · 돌아보기 2 · 돌아보기 3 · 참고 문헌 · 차시 예고   ← 차시 예고로 끝낸다(엔딩 표지 없음)

그림은 **캔바(교안 원본)에서 PNG 로 내려받는다.** 파워포인트로 뽑으면 교안 글꼴이 다른 글꼴로 바뀐다(검수 지적).
그림 이름 순서대로 놓는다(1.png, 2.png …).

  python tools/만들기_003.py <그림폴더> <배경음악.wav> <드래프트이름> [--길이 10,10,10,5,5] [--전환 0.5] [--페이드 2.5]

배경음악은 먼저 크기를 맞춘다: python tools/소리.py 음악맞춤 <비바샘 제공 BGM> <맞춘.wav>
"""
import sys
from pathlib import Path

from _팩 import capcut_running, win

import pycapcut as cc  # noqa: E402
from draft_root import find_draft_root  # noqa: E402


def _opt(a, k, default=None):
    return a[a.index(k) + 1] if k in a else default


def run(slide_dir, bgm, name, durs, trans, fade):
    slide_dir, bgm = Path(win(slide_dir)), win(bgm)
    imgs = sorted(list(slide_dir.glob("*.png")) + list(slide_dir.glob("*.PNG")), key=lambda p: p.name)
    imgs = list(dict.fromkeys(imgs))
    if len(imgs) != len(durs):
        raise SystemExit(f"그림이 {len(imgs)}장이고 길이는 {len(durs)}개다. --길이 로 장마다 초를 준다")
    if capcut_running():
        raise SystemExit("캡컷이 실행 중입니다. 완전히 종료한 뒤 다시 실행하세요.")
    root = find_draft_root()
    if (root / name).exists():
        raise SystemExit(f"같은 이름의 드래프트가 있다: {name}. 다른 이름을 쓴다")
    total = sum(durs)
    script = cc.DraftFolder(str(root)).create_draft(name, 1920, 1080, fps=30, allow_replace=False)
    script.add_track(cc.TrackType.video)
    t = 0.0
    for k, (img, d) in enumerate(zip(imgs, durs)):
        seg = cc.VideoSegment(cc.VideoMaterial(str(img.resolve())), cc.trange(f"{t}s", f"{d}s"))
        if k < len(durs) - 1:
            seg.add_transition(cc.TransitionType.叠化, duration=f"{trans}s")
        script.add_segment(seg)
        t += d
    script.add_track(cc.TrackType.audio)
    a = cc.AudioSegment(cc.AudioMaterial(str(Path(bgm).resolve())), cc.trange("0s", f"{total}s"),
                        source_timerange=cc.trange("0s", f"{total}s"))
    a.add_fade("0s", f"{fade}s")
    script.add_segment(a)
    script.save()
    print(f"만들었다: {name} · 그림 {len(imgs)}장 · {total:.1f}초 · 디졸브 {trans}초 · 끝 {fade}초 페이드아웃")
    for img, d in zip(imgs, durs):
        print(f"   {img.name}  {d}초")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 3:
        print(__doc__)
    else:
        run(a[0], a[1], a[2], [float(x) for x in _opt(a, "--길이", "10,10,10,5,5").split(",")],
            float(_opt(a, "--전환", 0.5)), float(_opt(a, "--페이드", 2.5)))
