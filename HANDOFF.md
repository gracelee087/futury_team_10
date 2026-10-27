# 최신 업데이트 (2026-10-27) — 전체 루프 그림(한국어 입문용)
- 최신 커밋: `23808cb` (lisa-stories, 이번 세션, 미푸시). 그 전: `d2be005`.
- 사용자가 `loop-overview.txt` 내용(🤖 AI / ⚙️ 코드 / 👤 사람 역할 분담)으로 "한 화면, 초보자용" 전체 루프 그림을 요청 → 아티팩트로 만듦.
- 아티팩트(비공개): https://claude.ai/artifact/P7JA4zGJQ1yJrqMuQkJ9H4 — 4판, 흰 바탕(사용자 요청), 라이트 테마만 사용. 각 단계 왼쪽에 "결과물" 칸 추가: ① 검사 규칙 목록 + 근거 문장 / ② 테스트 상황 + 정답 / ③ 케이스별 결과표 + 쉬운 설명 + 서명.
- 원본 HTML: `C:\Users\honor\AppData\Local\Temp\claude\C--Users-honor-OneDrive-Desktop-futury\a2ea7ed2-6e99-4db0-bc19-03de9ee8e5cf\scratchpad\team10-loop.html` (스크래치패드, 저장소 밖에 있음).
- 그림 구성: 시작(ITSG 문서 → 1,219개 조각) / ① 규칙 / ② 테스트 / ③ 판정(케이스마다) / 옆에서 계속(하네스 300개, Langfuse). 파란 점선 = 다시 작성(최대 2번, LangGraph가 횟수 셈), 빨간 점선 = 거절·이의 → 되돌림, STOP 분기 = 파일 깨짐 → 사람.
- 그림 내용은 `loop-overview.txt`에 있는 것만 넣음. 박스 보조 문구 일부(예: "원문에 정말 있는지", "2단계 정답과 대조", "최종 결정")는 원문을 풀어 쓴 설명임.
- 하지 않은 것: git add/commit/push, 기존 `full-process.svg`·`figures/` 수정, 저장소 안 파일 생성.
- 사용자 질문 "규칙 단계는 뭘 하나" → `orchestrator/graph.py`·`agents.py` 원문 확인 후 답함. 그림과 코드의 차이 2가지:
  (1) 코드에서는 인용문 확인 실패 시에도 Rule writer로 되돌려 다시 씀(cite_rounds, 최대 2번, 이후 실패 인용은 삭제). 그림은 Checker 쪽 재작성만 표시.
  (2) 사람 거절은 MAX_REJECTS=2 → 세 번째 거절 시 실행 종료. 그림에는 횟수 표시 없음. 그림 수정 여부는 사용자 결정 대기.
- `C:\Users\honor\OneDrive\Desktop\itsg-workflow.svg` 확인(git hash-object 비교): 저장소 2번째 버전 45472d8(Amr, 2026-10-26 14:41 "docs: define ITSG workflow and agent governance")과 내용 동일 = 로컬 origin/main(942a05a, 마지막 fetch 기준)에 있는 최신본. 최초 업로드본 9780c87(Amr, 14:29 "Add files via upload")과는 다름. 2번째 버전에서 "Mandated forms / templates" 출처와 템플릿 렌더링·적합성 검사가 추가됨. 파일 크기 차이(13,351 vs 13,547B)는 줄바꿈(autocrlf) 차이. git fetch는 안 함.
- 최초 업로드본(9780c87)을 `C:\Users\honor\OneDrive\Desktop\itsg-workflow_original_9780c87.svg`로 꺼냄(git show, 해시 3354e086 일치). 기존 데스크톱 `itsg-workflow.svg`(수정본)는 그대로 둠.
- GitHub API로 직접 확인(10개 브랜치 전부): itsg-workflow.svg 커밋은 9780c87(최초, 2026-10-26 13:29:52Z UTC) → 45472d8 두 개뿐. GitHub의 9780c87 파일 해시 3354e086 = 데스크톱 `itsg-workflow_original_9780c87.svg` 해시. 즉 데스크톱에 꺼낸 파일이 GitHub 최초 업로드본.
- "에이전트 구성이 최초 SVG(9780c87)대로냐" 비교 결과(코드 graph.py/agents.py 원문 확인):
  - 같음: G1/G3/G5 사람 관문, AI는 출처 인용 필수, 비교는 코드, 깨진 출력 → BLOCKED → 사람.
  - 다름: 최초 SVG의 AI는 2개(requirement assistant, test-case assistant). 현재 코드는 6개(+requirement_critic, testcase_critic, findings_critic, explainer). 현재 구성은 CLAUDE.md "고정 규칙: 전체 루프"와 일치.
  - 최초 SVG에 있으나 orchestrator 코드에서 확인 못 한 것: 사람이 급여 프로그램 실행, 번역 분기, vendor 문서, 버전 출처 등록, 증거 그래프(Merge_graph_neo.py는 있으나 orchestrator에서 안 씀), G1 edit/escalate 선택지(코드는 approve/reject/stop).
  - 코드와 고정 루프 불일치: G5에서 이의 → 2)/1) 되돌림이 코드에 없음(G5 → END, graph.py build_verdict). 리포트 노드도 verdict graph에 없음(다른 곳 생성 여부 확인 못 함).
- 사용자가 해커톤 목표 슬라이드 사진(`C:\Users\honor\OneDrive\Desktop\Cap 2026-10-27 00-16-30-674.jpg`, 6개 목표: Identify / Translate / Generate / Create traceable record / Test & compare / Deliver reports) 공유 → 루프 단계에 매핑. 약한 곳: "Test the payroll software"(루프는 출력 파일 읽기부터, 프로그램 실행은 루프 밖), "Deliver reports"(verdict graph에 리포트 노드 없음). 권고: 데모에서 6개 목표 ↔ 루프 단계 대응표 한 장 제시.
- "판정·리포트 FORM" 조사(1차 출처): 해커톤 발표자료 p.8–13에는 정해진 리포트 양식 없음(p.10 "generates a test report for the ITSG system review", p.11 "Deliver comprehensible test reports"뿐). chunks에서 Vordruck/Muster는 AU-Bescheinigung 등 의료 서식뿐(리포트 양식 아님). 참고 가능: (1) `futury_overview/해석/Hinweise_DTA-EEL-Bespiel_Vorerkrankung_Testkonstellation.docx`의 메시지별 표(Abgabegrund·Stornierung·DSID·DSID-UR·REF-ID·AZVU·Beginn 12-Monatsfrist·Ende EEL·Ende EEL Grund) (2) 기존 `reports/RPT-*.json`(report/test_case/execution/findings[id,rule,source,expected,actual,status]/robustness/review/trace_url) (3) architecture.md: 공식 양식 없으면 "synthetic template" 표시, 준수 주장 금지. 권고: 판정 = 검사 항목별 표, 리포트 = 1페이지(요약·표·쉬운 설명·서명).
- 판정 단계 예시 아티팩트(비공개, 별도): https://claude.ai/artifact/HxHs9HvCtPkPViMBxpdf7v — 원본 HTML `C:\Users\honor\AppData\Local\Temp\claude\C--Users-honor-OneDrive-Desktop-futury\a2ea7ed2-6e99-4db0-bc19-03de9ee8e5cf\scratchpad\team10-verdict-example.html`. 내용 출처: `reports/AGENTS-HARNESS-20261026-223252.json` 케이스 GOLD-13.3(이전 AU 2025-01-10~01-28, 현재 AU 08-31 시작, 간격 215일 > 6개월 → 41 불가; 코드: F2·F3·C10 틀림 → detected; AI double-check: C9·C11·C12 NEEDS_REVIEW; explainer 영어 원문 + 한국어 요약 번역; 사람 서명은 자동 테스트라 없음). 같은 실행에서 double-check로 정답 300→183 (d2be005 실험 2 계기).
- 판정·리포트 실제 모양 아티팩트(비공개): https://claude.ai/artifact/5jACB2sEqWgptBrbRLXM7m — `reports/RPT-20261026-221125.json`을 그대로 넣어 렌더링(빌드: scratchpad `report-view.tpl.html` + build로 `team10-report-view.html` 생성). 사실: 결과물은 케이스당 JSON 1개(report/test_case/execution/findings/robustness/review/trace_url) + 터미널 표(run_review.human). 이 파일은 PASS 10 · NOT EVALUATED 10 → 전체 NOT EVALUATED(가장 나쁜 상태가 전체 결과, run_review.py:271-273). C1–C8은 `checker/` 폴더 없음(지금도 없음), 공격 테스트도 미실행. 양식은 SYNTHETIC(공식 양식 없음). review는 pending. 이 RPT에는 AI 설명·의심 표시가 없음(그건 orchestrator AGENTS-HARNESS 결과에만 있음).
- "검사 항목 F/C는 ITSG가 정한 거냐" 확인: 번호(F1–F7, C1–C13)는 우리 팀이 붙인 것. 내용 출처는 다름.
  - C9–C12 = ITSG 제공 문서 `ITSG Files/test case/DTA-EEL-Beispiel_Vorerkrankung.docx`(원본: futury_overview/ITSG/ITSG/)의 "Ergänzende Kriterien zum DBVO" 4개 UUID 기준(f41c7278, 0cefe80e, aade0289 "Daumenkriterium", 9c8c9b58) 그대로. → ITSG가 정한 검사 기준.
  - C13(민간보험·미니잡이면 41 없음) = 우리가 VB 13.4 §3.12 p.136에서 추가. ITSG 기준 목록에는 없음.
  - F1–F7 = 우리가 VB 13.4(ITSG 공식 명세) 필드 규칙에서 골라 만든 메시지 칸 검사(예: ANZAHL-AU는 VB md 4034행에 있음).
  - C1–C8 = Fares의 comparator(origin/member2-comparator `checker/checks.py`), 출처 SRC-TK(테스트 예시 ID 표)·SRC-GG·SRC-VB. 현재 브랜치엔 checker 폴더 없음.
- **코드 변경(사용자 승인, 커밋 23808cb on lisa-stories, 푸시 안 함)**: `run_review.py`에서 메시지 흐름 검사 C1–C8 삭제 — `flow_findings()` 제거, 리포트 scope·터미널 머리말에서 "message flow" 문구 제거, `observed_sources.messages_2_to_7` 제거. `--checker-dir`는 robustness(checker/attacks.py)용으로 유지(sys.path 삽입을 main으로 옮김). diff: 5+ / 17-.
  - 검증(Langfuse 키 비우고 실행, 업로드 없음): `python run_review.py` → 12개 항목(F1–F7, C9–C13), PASS 10 · NOT EVALUATED 2, 저장 `reports/RPT-20261027-005658.json`. `python harness/run_harness.py` → 300/300 correct, false_alarms 0(변경 전 221438과 동일), 저장 `reports/harness-HARNESS-20261027-005700.json`.
  - 판정·리포트 아티팩트(5jACB2s…) 2판으로 갱신: 새 파일 `reports/RPT-20261027-005658.json` 기준, 12개 항목(C1–C8 없음).
- 질문 "규칙 단계 결과를 판정에 어떻게 연결?" → 계획만 제시(승인 전, 코드 안 건드림). 사실: run_review.py 검사(F1–F7, C9–C13)는 하드코딩, 규칙 단계 결과(criteria: id/text/chunk/quote/uncertain)를 읽지 않음.
  - 추천 A "연결표": 승인된 규칙 R-xx ↔ 기존 코드 검사 ID 연결표(JSON)를 G1 직후 사람이 확정 → 판정은 연결된 검사만 실행, 결과에 규칙 ID·인용문 첨부, 검사 없는 규칙은 "검사 코드 없음"으로 리포트에 표시, 규칙 없는 검사는 "근거 규칙 미승인" 표시. 비추천 B(AI가 검사 코드 작성), 보류 C(구조화 조건 + 범용 엔진).
  - 실제 설계 실행(AGENTS-design-20261026-222512.json) 15개 규칙을 내가 읽고 대응 추정(사람 확인 필요): R-01/R-02→C9, R-03→C12, R-06/R-09→C10·C11, R-08→F7, R-11→C13, R-13→F5, R-14→F6, R-15→F4, R-05→F2(부분), R-04는 C12 계산에 쓰임, R-07·R-10·R-12는 대응 검사 없음.
  - 미정: 연결표를 누가 만드나(사람 / AI 제안+사람 확인), 데모(10/27 13:00) 전에 할지.
- "현재 규칙→판정 연결 상태" 확인(graph.py, run_review.py 원문):
  - 규칙 단계 → 테스트 단계: 연결됨. testcase_agent(criteria) 입력으로 승인 규칙 받음.
  - 테스트 단계 정답: expected_calc = 고정 코드 decide()(R1–R6, generate_cases). 규칙 목록 안 읽음.
  - 판정: `graph.py verdict`는 `data/testcases.json`의 고정 케이스(기본 GOLD-13.1~13.5)를 씀 — design 단계에서 만든 케이스를 안 받음. 검사는 run_review/harness의 하드코딩 F1–F7, C9–C13.
  - 연결 고리는 C9–C12의 ITSG UUID(criterion_id)뿐(사람이 코드에 직접 적음). 규칙 단계의 R-xx와는 연결 없음.
  - 청크: 헤더 단위, path 예 "VB/3.12.7.md". 지난 실행 15개 규칙 중 10개가 VB/3.12.md(5,948자) 한 조각에서 나옴 → 조각 번호만으론 짝 구분 불가, 조각+인용문 필요.
- 루프 그림 5판: 코드와 끊긴 곳 표시(빨간 점점선 "끊김" 범례 추가). ②→③ 화살표 = 끊김("지금 판정은 ②에서 만든 테스트를 받지 않음"), ③ 위에 "지금 입력: 고정 케이스 data/testcases.json · 검사 12개 고정", 정답 계산 박스 보조문구 "고정 코드 R1–R6", 서명 이의 → ②/① 되돌림 = 끊김("코드에 아직 없음", graph.py G5 → END).
- "self-evolving / self-reflection 있나" 확인(grep 전체 .py/.md): 이름 붙은 기능 없음.
  - 비슷한 것 1: 작성 AI ↔ 별도 Checker AI 되돌림(최대 2번) = 다른 AI가 비판하는 구조(자기 반성 아님). 지난 실행에서 지적 수 6→10→8로 줄지 않음.
  - 비슷한 것 2: `experiments.md` 실험 1~5 = 사람이 프롬프트(agents-v1→v2→v3) 바꾸고 하네스로 측정. 자동 진화 아님.
  - 일부러 막은 근거: agent-governance.md:167 "Never hot-edit a production prompt without a traceable release", architecture.md:104 "Infer rules from prompt text at runtime"를 하지 말 것.
- 다음 할 일(미정): PPT용 PNG나 SVG 파일이 필요하면 내보내기 / 공유하려면 아티팩트 Share 메뉴에서 공유 설정.

---

# Session Handoff — Team 10 EEL review: story cases, Langfuse fixes, multi-agent orchestrator, PPT figures

## Where it started
Sohee Lee (Team 10, ITSG challenge, Abgabegrund 41 / DBVO; demo 2026-10-27 13:00, pitch 15:00) asked for test cases from stories 1/3/4/6, then simpler/brighter PPT figures, a Langfuse status check against the logging checklist, and finally a real multi-agent build (LangGraph + Claude, human in the loop). Answer in Korean, prefix "Team10-LetzGo! "; plan first, no hard jargon in figures; futury_overview must never be committed.

## Decisions locked + what shipped
- 200 story cases (story 1: 40, 3: 40, 4: 60, 6: 60) — `harness/generate_story_cases.py` → `data/story_cases.json`, `testCase-stories.md`. Stories 1/3: 80/80 correct; stories 4/6 (insurer reply 61, cancel flow 88): NOT EVALUATED, no checker exists. Story-6 defects "88 points to the wrong message" and "88 cancels the 41" are the same mutation.
- `harness/run_harness.py`: report_id + rules_version ("VB EEL 13.4 + GG EEL 13.1") metadata, BLOCKED check spans at level ERROR, `not_evaluated` score, `--stories` flag (dataset `team10-stories-v1`), story 4/6 → NOT EVALUATED via `evaluate()`.
- Langfuse uploaded: HARNESS-20261026-221438 (300/300, 0 false alarms), HARNESS-20261026-221845 (stories: 80/80 evaluated, 120 not evaluated). Earlier: -210148 (3), -210300 (143/300 before fixes), -211026 (300/300).
- Langfuse legacy read APIs return 410 for this org (dataset runs, traces list, v2 scores); use `/api/public/experiments` (fromStartTime required), `/api/public/v2/observations`, `/api/public/v2/metrics`, `/api/public/v3/scores`. Legacy endpoints end 2026-11-16.
- Multi-agent built (user approved: Sonnet 5.5 writers, Haiku 5.5 checkers; double-check on sample = all code-flagged + 10% clean, seed 7): `orchestrator/llm.py` (one call = Langfuse generation, streaming, max_tokens 32000, non-JSON/refusal/max_tokens → AgentError → BLOCKED; `TEAM10_MOCK=1|broken`), `orchestrator/agents.py` (6 agents), `orchestrator/graph.py` (design graph 02→G1→03→G3, verdict graph compare→double-check→explainer→G5; interrupt gates; `--auto` = "auto-approved (harness)", BLOCKED never auto-approved), `orchestrator/harness_agents.py`.
- Real design run `reports/AGENTS-design-20261026-222512.json` (7m23s): 15 criteria (3 uncertain), 15/15 quotes verified, critic issues 6→10→8 (did not decrease), 20 test cases, expected values by code, 10 open issues. Critic doubted 3 code values: T-13 critic wrong (counted periods outside 12 months); T-11 is a reading question (open end = today+6 → 29 days vs agent "one week" → 30); T-12 not checked.
- Figures (light, poster style, plain words, 3200×1800): `figures/architecture.png`, `figures/multi-agent-loop.png`; also dark `figures/system-overview.png`, `figures/multi-agent.png`. Gates renamed in figures only: "Person checks rules / tests", "Person signs report"; code still uses G1/G3/G5.
- Git: `lisa-stories` = 08f0392 (story cases) + 733e5e2 (orchestrator, run_harness changes, 4 PNGs), pushed. `main` = 942a05a (old dark PNGs only). `lisa-agents` branch exists locally, no commits beyond main; stash@{0} "carry-run_harness" holds the same run_harness.py change (redundant). Nothing merged to main from lisa-stories.
- Hypotheses set by user: H1 test success 100% (assumption), H2 role-injected agents lower failure rate, H3 fewer hand-offs to people. Measurement not defined. Note: double-check AI can only add NEEDS_REVIEW, so H3 can only get worse in the current design; H2 had no support in the design run.

## Key files for next session
- `C:\Users\honor\OneDrive\Desktop\futury\futury_team_10\orchestrator\graph.py` — the multi-agent graph, gates, CLI.
- `C:\Users\honor\OneDrive\Desktop\futury\futury_team_10\orchestrator\harness_agents.py` — 300-case agent run (result pending).
- `C:\Users\honor\OneDrive\Desktop\futury\futury_team_10\harness\run_harness.py` — scoring + Langfuse upload.
- `C:\Users\honor\OneDrive\Desktop\futury\futury_team_10\reports\AGENTS-design-20261026-222512.json` — real agent output.
- `C:\Users\honor\OneDrive\Desktop\futury\futury_team_10\figures\` — PPT images.
- Plan file: `C:\Users\honor\.claude\plans\cryptic-juggling-axolotl.md` (plan v2; agents now implemented as MVP).
- Memory files touched: none.
- Figure sources: scratchpad `C:\Users\honor\AppData\Local\Temp\claude\C--Users-honor-OneDrive-Desktop-futury\7eeab864-645c-4750-bc2f-d8bca9dd3b4a\scratchpad\arch_light.svg`, `...\agents_light.svg`; artifacts https://claude.ai/artifact/N7wDCSQgrrE3SFnudWJyA5 and https://claude.ai/artifact/4L7Dvw5mPjxuVWXoivrcmw (dark versions, private).

## Running state
- Background processes: shell `b3xx3q9a0` — `python orchestrator/harness_agents.py` (300 cases, real Claude Haiku), output at end to `reports/agents-harness.log` and `reports/AGENTS-HARNESS-<ts>.json`, Langfuse session AGENTS-HARNESS-<ts>. Started ~22:32. Stop: TaskStop b3xx3q9a0.
- Dev servers / ports: none.
- Open worktrees / branches: current branch `lisa-stories` (pushed); local `lisa-agents` (no own commits); `main`.

## Verification — how to confirm things still work
- `python harness/run_harness.py` — 300 cases, correct 300, false_alarms 0.
- `python harness/run_harness.py --stories` — evaluated 80, correct 80, not_evaluated 120.
- `TEAM10_MOCK=1 python orchestrator/graph.py design --auto` — each critic loop runs exactly 2 revisions, G1/G3 "auto-approved (harness)".
- `TEAM10_MOCK=broken python orchestrator/graph.py design --auto` — BLOCKED → "G1 stop".
- `TEAM10_MOCK=1 python orchestrator/graph.py verdict --auto` — GOLD-13.1..13.5: clean, clean, detected ×3.
- `python orchestrator/graph.py design` — interactive gates (approve / reject <note> / stop, then name).

## Deferred + open questions
- Deferred: checkers for story 4 (61 reply, VB §3.12.2–3.12.14) and story 6 (88 flow, GG EEL §2.5; Fares C1–C8 maybe reusable) — not requested yet.
- Deferred: merge lisa-stories → main and push (user said yes earlier for lisa-agents → main after harness; code now lives on lisa-stories) — confirm which branch to merge right before doing it.
- Deferred: written description of full architecture and multi-agent architecture (user asked for it after the harness finishes).
- Open: how to measure H2 and H3 (user agreed to decide after harness results).
- Open: G3 human decision on open-end counting (today+6 vs one week) — T-11.
- Open: rotate the Claude API key pasted in chat (after demo).
- Open: Notion session log not yet written this session.

## Pick up here
Wait for background `b3xx3q9a0` to finish, report before/after accuracy and double-check changes, then write the two architecture descriptions and confirm the merge of `lisa-stories` into `main`.

## 2026-10-26 에이전트 300건 하네스 결과 (AGENTS-HARNESS-20261026-223252)
- 300건 실제 Claude(Haiku)로 판정 단계 실행. Double-check AI 실행 188건(코드가 걸러낸 건 전부 + 깨끗한 건 10%), 설명 175건.
- 정답 일치: 코드만 300/300 → Double-check 후 183/300.
- Double-check가 147건에서 검사를 "사람 확인"으로 보냄. 판정이 바뀐 것: 오류를 잡은 108건이 "사람 확인만"으로 바뀜, 깨끗한 9건에 불필요한 사람 확인.
- 놓친 오류(PASS로 바뀐 것) 0건 — 설계상 AI는 PASS로 바꿀 수 없음.
- 가장 많이 보낸 검사: C12(30일 합계) 101, F1 32, C11 30, F3 26.
- Langfuse 전송 일부 실패(cloud.langfuse.com 타임아웃/DNS 오류) → 이 실행 기록이 완전한지 확인 못 함.
- 해석: H3(사람 확인 감소)과 반대 결과. Double-check AI가 너무 보수적.
- 루프 고정 규칙을 futury_team_10/CLAUDE.md에 추가(커밋 안 함). loop-overview.txt 생성(커밋 안 함).

## 2026-10-26 실험 기록 시작
- experiments.md 새로 만듦 (커밋 안 함): 실험1 = AGENTS-HARNESS-20261026-223252 (prompt agents-v1), 결과 표 포함.
- 실험2 시작: Double-check AI 프롬프트 v2 (증거 3개 field/seen/expected 없으면 코드가 표시를 버림). TEAM10_PROMPT=v1로 실험1 재현 가능, 기본 v2.
- 실행 중: background bkjfic0yh, 로그 reports/agents-harness-exp2.log.

## 2026-10-27 00:15 제거 실험(ablation) 계획안 — 승인 대기, 아직 아무것도 안 함
- 목표(사용자): 에이전트를 늘리는 게 아니라, 하나씩 빼고 프롬프트를 바꿔서 어떤 목적의 에이전트가 결과를 좋게 하는지 측정.
- 판정 단계(300건, Haiku): V0 AI 없음 / V1 실험1 / V2 실험2(진행 중) / V3 "코드가 놓친 오류 찾기" 목적 / V4 V2를 Sonnet으로 / 설명 AI 유무. 지표: 정답 수, 사람 확인 건수, 놓친 오류, 설명이 실패 항목을 다 언급하는지(코드).
- 설계 단계(Sonnet, 1회 약 7분): 전부 / 규칙 Checker 뺌 / 테스트 Checker 뺌 / Checker 둘 다 뺌 / 작성 프롬프트 변형. 반복 3회. 지표(코드): 인용 일치율, R1–R6·AMBIGUOUS 결과 종류 커버, 경계값(6개월 정확, 30일·29일) 커버, 깨진 시나리오 수. 기준 12개(F1–F7, C9–C13) 커버율은 AI 채점이 필요 → 결정 필요.
- 병렬: 백그라운드 프로세스 여러 개 동시 실행. 비용 추정 약 5~15달러(2차 출처 가격), 시간 약 1시간.

## 2026-10-27 실험2 결과 (AGENTS-HARNESS-20261026-235609, prompt agents-v2)
- 코드만 300/300 → Double-check 후 295/300 (실험1 183). AI가 사람에게 보낸 케이스 40 (실험1 147). 잡은 오류를 "사람 확인만"으로 바꾼 것 5 (실험1 108), 깨끗한 건 불필요 확인 0 (실험1 9), 놓친 오류 0.
- experiments.md에 실험2와 H1–H3 해석 추가 (커밋 안 함). H2 공정한 측정에는 코드가 못 잡는 케이스(스토리 4/6 등)가 필요.
- 제거 실험(ablation) 계획은 사용자 답 대기.

## 2026-10-27 실험2 분석 (API 호출 없음, 코드로 재계산)
- 실험2에서 AI가 표시한 검사 48개 중 26개는 코드가 이미 MISMATCH라고 한 항목(AI가 동의한 것), 22개는 PASS였던 항목. 표시된 40건 모두 결함 케이스, 깨끗한 케이스 0.
- 실패 5건(DEC-093, DEC-095 C12 / OUT-086, 088, 090 F5)은 모두 AI가 코드와 같은 오류를 짚었는데 우리 코드가 MISMATCH를 NEEDS_REVIEW로 바꿔서 생김 → 설계 버그.
- 가정 계산: "MISMATCH에 대한 AI 표시 = 동의, 그대로 둠, PASS에 대한 표시만 사람에게" 규칙이면 300/300, AI가 사람에게 넘기는 케이스 21개 (실험2 40). 스크립트 scratchpad exp2_status.py.

## 2026-10-27 실험3 시작
- 규칙 변경(graph.f_critic): MISMATCH에 대한 AI 표시는 그대로 오류 유지(critic_on_mismatch로 기록), PASS에 대한 표시만 사람에게.
- 프롬프트 v3(agents.py FINDINGS_CRITIC_V3): 코드 상태 + 규칙 원문(chunks VB §3.12.x, 2500자까지) 제공, 코드와 다를 때만 말함, field/seen/expected/rule_quote 없으면 버림.
- 실행 중: background, TEAM10_PROMPT=v3, 로그 reports/agents-harness-exp3.log. experiments.md에 규칙 변경과 실험3 설정 기록(커밋 안 함).

## 2026-10-27 Langfuse 기록 확인 (v2 metrics API, 읽기 전용)
- 실험2 AGENTS-HARNESS-20261026-235609: agent-review-case 관측 600 (= 300건 × trace+span 2), findings_critic 179, explainer 179 (표본 188 중 깨진 파일 9건은 AI 안 거침 → 179 정상) → 전부 기록됨.
- 실험1 AGENTS-HARNESS-20261026-223252: 592 / 175 / 175 → 4건 누락 (로그의 export 실패 4회와 일치).
- 설계 실행 AGENTS-design-20261026-222512: requirement_agent 3, testcase_agent 3 기록됨.
- 스크립트: scratchpad lf_sessions.py.

## 2026-10-27 실험3 결과 (AGENTS-HARNESS-20261027-002646, v3 + 새 규칙)
- 299/300, AI가 사람에게 보낸 케이스 33, 깨끗한 케이스 오표시 1 (DEC-139, F2/F3), 놓친 오류 0, 코드 오류에 단 코멘트 27(영향 없음).
- 비교: 실험2 표시 + 새 규칙(계산) = 300/300, 사람에게 21 → v3가 v2보다 나아지지 않음. 각 1회 실행이라 우연 가능.
- Langfuse: 실험3은 조회 시점에 agent-review-case 511/600, findings_critic 134 — 수집 지연(몇 분) 또는 누락(export 실패 1회). 다시 확인 필요.
- experiments.md 갱신 (커밋 안 함).

## 2026-10-27 실험4 시작: v2 + 새 규칙 실제 실행 (계산값 300/300, 21건 확인용). 로그 reports/agents-harness-exp4.log.

## 2026-10-27 01:01 병렬 실험 시작 (실험4와 동시)
- 5a: v2 + 새 규칙 반복 2회 (labels v2rep2, v2rep3). 5b: v2 + 새 규칙, Explainer 없이 (v2noexpl). 로그 reports/agents-harness-<label>.log.
- 코드: graph.py TEAM10_NO_EXPLAINER 옵션, harness_agents.py TEAM10_RUN_LABEL (병렬 run_id 충돌 방지). 커밋 안 함.

## 2026-10-27 실험4·5 결과 (v2 + 새 규칙)
- 3회 반복(005809, v2rep2, v2rep3): 정답 299/300/299, 사람에게 16/14/18 (평균 16), 놓친 오류 0. 계산값(300, 21)과 근접, 실행 간 ±2 정도.
- Explainer 없이(v2noexpl): 300/300, 사람에게 18, 시간 16분 vs 24–25분, AI 호출 179회 절약, 설명 없음.
- Langfuse: 실험3은 이제 600/600 완전. 실험4 530, rep2·rep3 483 — 조회 직후라 수집 지연 가능, 재확인 필요. v2noexpl 600 완전.
- experiments.md 갱신 (커밋 안 함).

## 2026-10-27 01:30 ②→③ 연결 (끊김 1곳 해결)
- graph.py verdict --from-design: 2단계 AI 테스트 + 코드 기대값을 판정에 사용, 급여 출력은 시뮬레이션(정상 41 + AU-AB-AG 하루 늦은 복사본 / 허용 안 되는 경우 잘못 보낸 41).
- 실제 실행 AGENTS-verdict-20261027-012918: 30/30, 사람에게 0. Explainer 문장 정확성은 측정 안 함(T-06-bad 설명에 의심 문장).
- 기존 실험 영향 없음 확인: run_harness 300/300, harness_agents mock 동작 동일. 실험1–5 결과 파일 그대로.
- 남은 끊김: 판정 검사 항목이 고정 12개(1단계 AI 규칙 미사용), 서명 이의 시 되돌림 없음 → 로드맵.
- 커밋 안 함, 푸시 안 함.

## Update 2026-10-27 ~01:56 — gaps connected, stage 0, workflow figure
- Gap A (rules → checks): `orchestrator/agents.py` `CHECKS` + `check` field in REQ_SYSTEM; `graph.py`
  `citation_check` drops unknown links, `compare`/`apply_criteria` runs only linked checks, unlinked criteria → NOT EVALUATED.
- Gap B (dispute → back): `graph.py full` with `sign_report` / `run_full`; `dispute g3|g1 <note>`, max 2. Mock-tested both.
- Real run `reports/AGENTS-full-20261027-014300.json`: 15 criteria (12 linked, R-12/R-13/R-15 without check),
  29 / 29 correct, 0 to a person. Gates auto (not human approval).
- Stage 0 `orchestrator/find_sources.py`, run `reports/SOURCES-20261027-015353.json`: 66 candidates, AI picked 39;
  answer list A 9/9, B 22/22; 17 extra (12 = Beispiel 16.x insurer answers, unjudged). `--sources` flag on design/full (mock only).
- Workflow artifact https://claude.ai/artifact/P7JA4zGJQ1yJrqMuQkJ9H4 republished (version 6): cut marks removed, stage 0
  added, dispute routes drawn as real loops. Source: scratchpad `workflow/team10-loop.html`.
- Not changed: fixed-rule loop text in `futury_team_10/CLAUDE.md` (needs user approval to add stage 0); experiments 1–5.
- Not committed, not pushed.
- Colleague question (does the code meet the ITSG brief): answered in chat; main gap = no real payroll software
  (output simulated), scope only Abgabegrund 41, report not the official ITSG form.

- CLAUDE.md fixed loop updated (user approved 2026-10-27): stage 0 source finder, check links, NOT EVALUATED -> person, one report signature, dispute max 2. loop-overview.txt not updated.

## Update 2026-10-27 ~02:25
- Experiment a done (see `experiments.md`): 3 × 200 new cases (`harness/generate_expa.py`, `data/expa_*.json`), code 200/200 each, with AI 200/200 each, AI sent 12 / 13 / 3 cases to a person, 0 clean. `--cases` option added to `harness/run_harness.py` and `orchestrator/harness_agents.py`; `story1/story3(k)` multiplier in `generate_story_cases.py` (k=1 output unchanged, checked with git diff).
- Langfuse: `find_sources.py` now has its own trace/session + recall scores; `graph.py compare` logs one span per check when criteria drive the run. Arrival in Langfuse NOT yet confirmed (queries after 02:14 show none of the new names; harness traces do arrive).
- New `error-log.md` (E-01..E-17), approval column for a person only.
- Artifacts: report 5jACB2sEqWgptBrbRLXM7m redesigned (v3, same data); new English full-loop report https://claude.ai/artifact/8XfKJcM6RosQR7kfBAoYfR + Desktop/Team10-test-report.pdf; orchestration one-screen https://claude.ai/artifact/9J2UScCY9DcdqACS7xtHBZ + Desktop/Team10-orchestration.pdf; workflow P7JA4… in English + Desktop/Team10-full-loop.pdf.
- Open: T-12/T-13 expected-value doubts from the test checker (E-14); not committed, not pushed.

- 02:30 Langfuse arrival confirmed: SOURCES-20261027-021434 own session (find-sources + source_finder); AGENTS-verdict-20261027-021514 has checks + check F1..C13 x29. Cause of "missing": ~10-15 min Langfuse delay + empty result of v2 observations fromStartTime query (error-log E-18). The 2 source_finder rows without session are the 01:53 run before the fix; 1 requirement_agent + 1 requirement_critic without session still unexplained.

- 02:40 Annotated report for the team (Korean notes per heading: meaning, ITSG objective, importance): Desktop/Team10-test-report-annotated.pdf (script scratchpad fullreport/annotate.py). Judge version Team10-test-report.pdf unchanged. Commit 8b4d54f on lisa-stories (not pushed).

- 02:55 Artifact 5jACB2sEqWgptBrbRLXM7m: v4 = restored original Korean single-case page; v5 = same layout, English, data from AGENTS-full-20261027-014300 (29 cases, case picker). Builder: scratchpad report/build_latest.py + template-en.html. Note: F1 not run in this run (no criterion linked to F1). experiment-log.md added (not committed).

- 02:45 E-19 fixed: F1/F4/F6 always run (graph.py ALWAYS). Rerun AGENTS-verdict-20261027-024151: F1 29/29, 29/29 correct; wrong Abgabegrund test detected. Not committed.

- 03:00 Experiment log artifact https://claude.ai/artifact/X2ajV1r8sgUU8osCAFXiZN + Desktop/Team10-experiment-log.pdf (A4 landscape, 4 pages). Langfuse per-run cost/latency (metrics API): v3 critic 2.61M tokens/$0.36 vs v2 0.42M/$0.11; no-explainer -34% cost; full loop $0.52 (92% Sonnet writers); expa 600 cases $0.30. Langfuse arrival of check F1 spans for AGENTS-verdict-20261027-024151 not yet confirmed. Report restyle (white, 5jACB2) running in a subagent.

- 03:10 Report 5jACB2sEqWgptBrbRLXM7m v6: white printed-style report (latest.json data, All cases table, F1 note) + Desktop/Team10-review-report.pdf (5 pages). Build: scratchpad build_white.py, report/template-white.html.

- 03:15 Pushed HEAD (lisa-stories, 2e130f0) to new remote branch origin/lisa-update (user request). Contains d2be005, 23808cb, 8b4d54f, 2e130f0 on top of origin/lisa-stories 733e5e2. PR link: https://github.com/gracelee087/futury_team_10/pull/new/lisa-update

- 03:25 Added deliverables/ (4 PDFs: experiment log, review report, full loop, orchestration) and pushed to origin/lisa-update.

- 03:30 Final English answer to the colleague question (does our code solve the ITSG challenge) given in chat: objectives 1-4, 6 covered with caveats; 5 = comparison real, payroll output simulated; scope only Abgabegrund 41.
