# -*- coding: utf-8 -*-
"""설치 점검. 처음 한 번, 그리고 막힐 때 돌린다. 아무것도 고치지 않는다.

  python tools/점검.py
"""
import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PACK = Path(__file__).resolve().parent.parent
rows = []


def row(ok, what, note=""):
    rows.append(("○" if ok is True else "✗" if ok is False else "△", what, note))


row(sys.version_info >= (3, 10), f"파이썬 {sys.version.split()[0]}", "3.10 이상")
for mod, need in (("numpy", True), ("PIL", True), ("onnxruntime", True), ("pycapcut", True), ("soundfile", False), ("faster_whisper", False)):
    try:
        importlib.import_module(mod)
        row(True, f"{mod}")
    except Exception:
        row(False if need else None, f"{mod} 없음", "pip install -r requirements.txt" if need else "받아 적기에 쓴다(없어도 된다)")
for exe in ("ffmpeg", "ffprobe"):
    p = shutil.which(exe)
    if p:
        v = subprocess.run([exe, "-version"], capture_output=True, text=True).stdout.split("\n")[0][:60]
        row(True, v)
    else:
        row(False, f"{exe} 없음", "윈도우: winget install --id Gyan.FFmpeg -e")

lc = None
for c in (os.environ.get("LECTURE_CUT"), Path.home() / ".claude" / "skills" / "lecture-cut", PACK.parent / "lecture-cut", Path("C:/projects/lecture-cut")):
    if c and (Path(c) / "src" / "draft_doctor.py").exists():
        lc = Path(c)
        break
if lc:
    rev = subprocess.run(["git", "-C", str(lc), "log", "-1", "--format=%h %cs"], capture_output=True, text=True).stdout.strip()
    row(True, f"lecture-cut {lc}", rev)
else:
    row(False, "lecture-cut 없음", "https://github.com/ksb6857/lecture-cut 를 받고 LECTURE_CUT 환경변수로 알려 준다")

la = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
apps = la / "CapCut" / "Apps"
vers = sorted((p.name for p in apps.glob("*.*.*.*") if p.is_dir()), key=lambda s: [int(x) for x in s.split(".")]) if apps.exists() else []
if vers:
    major = int(vers[-1].split(".")[0])
    row(True if major <= 9 else None, f"캡컷 {vers[-1]}", "9.5 에서 확인했다" if major <= 9 else
        "10 이상은 밖에서 만든 드래프트를 거부한다는 보고가 있다. 시험 드래프트가 열리는지 먼저 본다")
else:
    row(None, "캡컷 설치 폴더를 못 찾았다", "국제판 CapCut(PC) 을 쓴다")
if lc:
    sys.path.insert(0, str(lc / "src"))
    try:
        from draft_root import find_draft_root
        row(True, f"캡컷 드래프트 폴더 {find_draft_root()}")
    except SystemExit as e:
        row(False, "캡컷 드래프트 폴더를 못 찾았다", str(e)[:80])
row((PACK / "models" / "rvm_mobilenetv3_fp32.onnx").exists() or None, "오프닝 매팅 모델", "python tools/오프닝.py 모델받기 (15MB)")
font = la / "CapCut" / "User Data" / "Cache" / "effect" / "6808056385679397389"
row(font.exists() or None, "캡컷 글꼴 「고딕체」", "캡컷에서 글자를 하나 넣고 글꼴을 고딕체로 한 번 고르면 받아진다")
key = os.environ.get("ELEVENLABS_API_KEY") or (Path.home() / ".elevenlabs.key").exists()
row(True if key else None, "ElevenLabs 키" + (" 있음" if key else " 없음"), "없으면 위스퍼(무료)로 받아 적는다")

for mark, what, note in rows:
    print(f"  {mark} {what}" + (f"  · {note}" if note else ""))
print("\n✗ 는 고쳐야 하고, △ 는 그 기능을 쓸 때만 필요하다")
