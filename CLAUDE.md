# Claude Code Instructions — Team 10

Before every task, read the root `AGENTS.md`, `DELIVERY.md`, and `agent-governance.md`, then follow the checkpoint boot sequence in `.leapfrog/CLAUDE.md`. Treat `.leapfrog/board.md` and `.leapfrog/log.md` as the canonical asynchronous status for the team.

Begin every human-facing chat response to the team with `Team10-LetzGo! `. This marks instruction compliance only; it does not establish that the answer is correct. Never prepend it to structured payloads, official report files, or machine-readable output.

## Fixed rule: 전체 루프 (누가 하는지)

이 루프와 역할 분담은 고정 규칙이다. 바꾸려면 사용자 승인을 먼저 받는다.

🤖 = AI   ⚙️ = 코드   👤 = 사람

```
ITSG 규칙 문서
 -> 잘게 나눔 (1,219개 조각)                    ⚙️ 코드

0) 관련 조항 찾기
 -> 단어 검색으로 후보 추림 (+ 하위 조항)        ⚙️ 코드
 -> 관련 조항 고르기                             🤖 AI (Source finder, Haiku)
 -> 정답 조항 목록과 비교해 점수                 ⚙️ 코드

1) 규칙 단계
 -> 검사 규칙 작성 + 맞는 코드 검사 연결         🤖 AI (Rule writer, Sonnet)
 -> 인용문이 원문에 있는지 확인                  ⚙️ 코드
 -> 빠진 규칙 찾기                               🤖 AI (Checker, Haiku)
    ↺ 문제 있으면 다시 작성 (최대 2번)           ⚙️ 코드가 횟수 셈 (LangGraph)
 -> 규칙 확인                                    👤 사람
    ↺ 거절하면 처음으로

2) 테스트 단계
 -> 테스트 상황 작성                             🤖 AI (Test writer, Sonnet)
 -> 정답 계산 (R1–R6)                            ⚙️ 코드
 -> 빠진 테스트 찾기                             🤖 AI (Checker, Haiku)
    ↺ 문제 있으면 다시 작성 (최대 2번)           ⚙️ 코드가 횟수 셈 (LangGraph)
 -> 테스트 확인                                  👤 사람
    ↺ 거절하면 다시

3) 판정 단계 (케이스마다)
 -> 급여 프로그램 출력 파일 읽기                 ⚙️ 코드
 -> 정답과 비교 (1단계에서 연결된 검사만)          ⚙️ 코드
    (코드 검사 없는 규칙 -> 사람 확인으로 표시)   ⚙️ 코드
    (파일이 깨졌으면 -> STOP -> 사람에게)        ⚙️ 코드
 -> 의심되는 것 표시                             🤖 AI (Double-check, Haiku)
 -> 쉬운 설명                                    🤖 AI (Explainer, Haiku)
 -> 서명 (리포트 전체에 한 번)                   👤 사람
    ↺ 이의 있으면 2) 또는 1)로 되돌림 (최대 2번)
 -> 리포트                                       ⚙️ 코드

옆에서 계속:
 테스트 300개 실행 -> 정답과 비교해 점수         ⚙️ 코드 (하네스)
 -> 모든 단계 기록                               ⚙️ 코드 (Langfuse)
```

정리
- 🤖 AI = 글을 씀 (조항 고르기, 규칙 작성, 테스트 작성, 빠진 것 찾기, 의심 표시, 설명)
- ⚙️ 코드 = 숫자와 사실 (정답 계산, 비교, 인용문 확인, 횟수 세기, 기록)
- 👤 사람 = 결정 (승인, 거절, 서명)

