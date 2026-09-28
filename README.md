# 비바샘 팩 (vivasam-pack)

비바샘 원격연수 강의 영상(001 본연수 + 003 정리)을 납품 규격대로 만드는 도구와 규칙 모음이다.
범용 컷 편집 스킬 [lecture-cut](https://github.com/ksb6857/lecture-cut) 위에서 돈다.
lecture-cut 이 쉼 정리·다시 말한 곳 지우기·자막 같은 컷 편집을 하고, 이 팩은 비바샘에만 있는 것을 맡는다.

클로드 코드(Claude Code)나 코덱스(Codex)에게 「비바샘 영상 만들어 줘」라고 말하면 에이전트가 이 팩의 절차([SKILL.md](SKILL.md))대로 진행한다.
결과물은 **캡컷 프로젝트**다. 선생님이 캡컷에서 확인하고 내보낸다.

## 무엇을 해 주나

| 단계 | 팩이 하는 일 | 선생님이 하는 일 |
|---|---|---|
| 러프컷 | 쉼 정리, 다시 말한 곳 지우기, 편집용 자막 (lecture-cut) | 원본 녹화를 준다 |
| 효과 | 오래 멈춘 화면 찾기, 강조 상자, 작은 글씨 확대, 이메일·키 가림 | 계획과 확인 그림을 본다 |
| 오프닝 | 촬영본에서 좋은 테이크 고르기, 사람만 오려 팀 배경에 합성(파란 천 없어도 됨), 말자막, 인트로 뒤에 붙이기 | 오프닝을 찍는다 |
| 편집 | 드래프트 검사 | 캡컷에서 다듬는다 |
| 배경음악 | 표지·학습 목표·학습 내용·간지에 BGM | 구간을 확인한다 |
| 목소리 | 보정본을 1ms 단위로 맞춰 넣고 영상 소리 끄기, 워터마크 찾기 | 오디오를 내보내 오포닉으로 보정한다 |
| 003 | 그림 5장 + BGM 으로 40초 정리 영상 | 캔바에서 그림을 받는다 |
| 최종본 | 규격·음량·본편 말자막·싱크·워터마크·장면 모음 검사 보고서 | 캡컷에서 내보낸다, 보고서를 본다 |

검수서에서 반복된 지적(본연수 말자막 금지, 학습 목표·내용·간지 BGM, 003 은 차시 예고로 끝, 참고문헌 형식, 보정 목소리 밑 날소리 겹침 등)은
[docs/검수-공통지적.md](docs/검수-공통지적.md) 에 모았고, 기계로 잴 수 있는 것은 도구가 검사한다.

## 준비물

- 윈도우 PC, 파이썬 3.10 이상, ffmpeg
- 캡컷(CapCut, 국제판 PC). **9.5 에서 확인했다. 자동 업데이트를 꺼 둔다**(10 이상은 밖에서 만든 프로젝트를 거부한다는 보고가 있다)
- 클로드 코드 또는 코덱스
- 오포닉(Auphonic) 계정 (목소리 보정)
- 비상교육이 준 인트로(8초)·BGM 파일, 팀 오프닝 배경 그림 — **이 저장소에는 없다.** 받은 파일을 쓴다

## 설치

클로드 코드나 코덱스를 열고 아래를 그대로 붙여 넣는다.

> https://github.com/ksb6857/lecture-cut 과 https://github.com/ksb6857/vivasam-pack 을 받아 줘.
> 둘 다 README 대로 설치하고(클로드 코드면 둘 다 스킬로 등록), 필요한 파이썬 패키지와 ffmpeg 도 설치해 줘.
> 끝나면 vivasam-pack 의 `python tools/점검.py` 를 돌려 결과를 보여 줘.

직접 할 때:

```bash
git clone https://github.com/ksb6857/lecture-cut.git C:/projects/lecture-cut
git clone https://github.com/ksb6857/vivasam-pack.git C:/projects/vivasam-pack
pip install -r C:/projects/lecture-cut/requirements.txt -r C:/projects/vivasam-pack/requirements.txt
python C:/projects/vivasam-pack/tools/점검.py
```

클로드 코드 스킬 등록(윈도우, 관리자 권한 필요 없음):

```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\skills\lecture-cut" -Target "C:\projects\lecture-cut"
New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\skills\vivasam-pack" -Target "C:\projects\vivasam-pack"
```

코덱스는 `vivasam-pack` 폴더에서 열면 `AGENTS.md` 를 읽는다. lecture-cut 을 다른 곳에 두었으면 환경변수 `LECTURE_CUT` 에 그 폴더를 적는다.

## 쓰는 법

에이전트에게 이렇게 말하면 된다.

> 비바샘 3권 13차시 영상 만들어 줘. 녹화 원본은 C:\projects\video\13차시 폴더, 오프닝 촬영본은 ○○.MOV,
> 팀 배경은 ○○.png, 인트로·BGM 은 ○○ 폴더에 있어.

에이전트가 필요한 것을 묻고 단계마다 보고한다. 단계별 명령은 [SKILL.md](SKILL.md), 각 도구의 도움말은 `python tools/<도구>.py` 로 본다.

| 도구 | 하는 일 |
|---|---|
| `tools/점검.py` | 설치 점검 |
| `tools/오프닝.py` | 받아적기 · 컷 · 합성 · 붙이기 · 모델받기 |
| `tools/말자막.py` | 말자막 서식 검사·맞추기 |
| `tools/소리.py` | 목소리넣기 · 맞춤검사 · 음소거 · 배경음악(음량 자동) · 오포닉 API(선택) |
| `tools/효과.py` | 오래 멈춘 화면 · 개인정보 찾기 · 강조 상자 · 확대 · 가림 |
| `tools/후보.py` | 삭제 후보 표시(자동으로 지우지 않음) |
| `tools/만들기_003.py` | 003 드래프트 |
| `tools/드래프트검사.py` | 굽기 전 검사 |
| `tools/최종본검사.py` | 내보낸 mp4 검사 보고서 |

## 알아 둘 것

- 결과물은 캡컷 프로젝트다. 캡컷에는 명령으로 내보내는 기능이 없어서 **확인과 내보내기는 사람이 한다**
- 설명이 맞는지(내용 오류), 차시명·참고문헌 글자가 공식 목록과 같은지는 도구가 판단하지 못한다. 확인할 화면을 그림으로 뽑아 준다
- 캡컷이 켜져 있으면 프로젝트를 고치지 않는다. 에이전트에게 시키기 전에 캡컷을 닫는다
- 한 강의(3권 12·13차시, 2권 11·14차시)를 만들며 굳힌 값이다. 다른 차시에서 어긋나는 것이 있으면 알려 주면 팩에 반영한다

## 라이선스

MIT. 오프닝 매팅 모델은 [Robust Video Matting](https://github.com/PeterL1n/RobustVideoMatting)(GPL-3.0) 공식 배포에서 받아 쓴다(저장소에 넣지 않는다).
