# Worklog · 마케팅 성과 리포트 자동화

주요 작업이 끝날 때마다 아래 형식으로 누적 기록한다. 최신 항목을 위에 추가한다.

## 기록 형식
```
### W-00N · 작업 제목
**요청** / **수행 작업** / **변경 파일** / **검증** / **결과**
```

---

### W-001 · 프로젝트 운영 체계 셋업
**요청**
- 기존 [09] DA 공통 폴더와 융합한 운영 체계 셋업

**수행 작업**
- 기존 CLAUDE.md, decisions.md, data/, context/, .claude/skills/, output/ 구조 확인
- 빠진 운영 파일(Worklog.md, Troubleshootinglog.md) 추가, src/ 폴더 생성

**변경 파일**
- Worklog.md (신규)
- Troubleshootinglog.md (신규)
- src/.gitkeep (신규)

**검증**
- 기존 파일 미수정, 셋업만 수행. 구현 미착수.

**결과**
- 완료: 운영 파일 추가
- 남은 작업: Basic 레벨 구현 시작 (/analyze → /insight → /generate → /review)

### W-002 · Basic 리포트 파이프라인 완성 (정제→계산→탐지→리포트)
**요청**
- 목표 Challenge로 설정, Basic부터 단계별 완성. 모든 설계·함수·임계값을 사용자 승인 후 진행.

**수행 작업**
- src/calculate.py: 정제(load_and_clean, 중복제거·결측NaN·이상치 revenue만 제외) + 집계(compute_summary: MER·유료ROI·오가닉 3종 분리) + ROI순위 + W7→W8 변화율
- src/detect_issues.py: 규칙 기반 이슈 탐지 6종(급등/급락·이상치·결측·벤치마크 평가·기회) + score_and_rank(카테고리별 분리, 손실은 원 임팩트 정렬)
- src/generate_report.py: calculate/detect_issues를 불러 output/insight_report.md 자동 생성(수치=Python, 해석=규칙기반 템플릿). 동적 섹션 번호.
- decisions.md: Step 1~16 의사결정 기록(판단 원칙 포함). 갱신 이력은 ⚠️ 표기로 보존.

**변경 파일**
- src/calculate.py, src/detect_issues.py, src/generate_report.py, src/analyze.py (신규)
- output/insight_report.md (신규 생성)
- decisions.md, Troubleshootinglog.md (T-001·T-002)

**검증**
- 각 스크립트 실행으로 수치·이슈 산출 확인. 손실 top3 = 이메일 이상치(2,884만)·메타 과집행(882만)·네이버 결측(139만).
- 기회 0건 시나리오에서 크래시 없음 확인. 물결표 취소선 재발 방지 확인.

**결과**
- 완료: Basic 산출물(insight_report.md) + 재현 파이프라인(generate_report.py) 완성. 채점 항목(핵심수치·ROI순위·이슈3·형식) 충족.
- 남은 작업: Standard(파이프라인 슬래시커맨드/스킬 패키징 + 리포트 양식 설계 근거) → Challenge(예산 재배분 기획안).

### W-003 · Standard 완성 (재현 파이프라인 + 설계 근거 문서)
**요청**: Basic 완료 후 Standard(재현성 + 리포트 설계 근거).
**수행 작업**
- 하드코딩 제거: OUTLIER_KEY→find_revenue_outliers 동적 탐지, 해석 문구 데이터 기반화, compute_wow_change 마지막 2주 자동.
- generate_report.py CLI 인자화([입력CSV] [출력MD]).
- .claude/skills/generate.md를 실제 파이프라인 실행으로 갱신.
- docs/REPORT_DESIGN.md 신규(섹션·지표·형식 설계 근거, 경영진/마케팅팀 관점).
**변경 파일**: src/calculate.py, src/detect_issues.py, src/generate_report.py, .claude/skills/generate.md, docs/REPORT_DESIGN.md(신규), decisions.md(Step 17), Troubleshootinglog.md(T-003)
**검증**: 변형 CSV(4주·3채널)로 크래시 없이 생성, 변화율 W3→W4 자동. 원본 회귀 없음.
**결과**: 완료 — Standard 산출물(재현 파이프라인 + 설계 근거). 남은 작업: Challenge(예산 재배분 기획안 + 양식·우선순위 기준).

### W-004 · 재현성 검증 자동화 (픽스처 영구 저장 + 검증 스크립트)
**요청**: W-003 검증에 쓴 변형 CSV가 일회성이라 폐기됨 → 재검증 재현성이 없음. 픽스처를 저장하고 재검증 자동화.
**수행 작업**
- tests/make_fixtures.py: 원본을 subset/relabel해 변형 3종 생성(가짜 숫자 없이 실제 분포 유지).
  - A variant_a_short(W1-4·3채널) / B variant_b_noorganic(오가닉 제거) / C variant_c_relabel(W1-8→W5-12).
- tests/verify_reproducibility.py: 원본+픽스처 4종에 build_report 실행 → 크래시·필수섹션·변화율라벨·기회섹션·물결표 자동 점검, 실패 시 exit 1.
- 픽스처를 tests/fixtures/에 영구 저장(W-003의 일회성 테스트를 재사용 가능 자산으로 전환).
**변경 파일**: tests/make_fixtures.py(신규), tests/verify_reproducibility.py(신규), tests/fixtures/*.csv(신규 3개)
**검증**: 4종 전체 통과. A→변화율 W3→W4·기회 있음, B→기회 섹션 자동 생략, C→변화율 W11→W12 자동, 전 케이스 물결표 없음(T-001 재발방지 확인).
**결과**: 완료 — `python3 tests/verify_reproducibility.py` 한 줄로 회귀 검증 가능. 남은 작업: Challenge(예산 재배분 기획안 + 양식·우선순위 기준).

### W-005 · Challenge 예산 재배분 엔진(reallocate.py) + 레버 분류 도입
**요청**: 채널 ROI·이슈 근거로 예산 이동 제안(문제정의·근거·재배분안·우선순위) + 양식·우선순위 기준 설계. 진행 중 사용자 지적으로 (a)이상치·결측을 재원에서 배제할 판별 로직, (b)수혜처의 재현성 검증 필요성 반영.
**수행 작업**
- detect_issues.py: `_lever(itype)` 추가 — 이슈를 '문제 종류'로 4레버 분류(예산/운영·크리에이티브/데이터·트래킹/전략). 지표명이 아닌 성격 키워드로 귀속(매출결측·revenue이상치 등 조합 변화에 강건). `_issue`에 lever·recoverable_won 필드 추가, 과집행에 초과지출액 기록, score_and_rank 손실 집계에 두 필드 보존.
- generate_report.py: insight_report 손실 섹션에 `[레버]` 라벨 병기 + 범례(예산=재배분 대상, 데이터·트래킹=예산 무관). → 최대 손실인 이메일 이상치(2,884만)가 [데이터·트래킹]으로 표기돼 예산 재배분 재원이 아님이 명시됨.
- src/reallocate.py(신규): compute_funding(재원=lever '예산'만) / select_targets(수혜=벤치마크 우수+오가닉, 재원채널 제외) / build_plans(재원×수혜 매칭, 우선순위 2단 정렬) / build_reallocation(md 생성기) + CLI.
- output/budget_reallocation.md(신규): 개요·재원요약·재배분안(4항목 양식)·우선순위 설계 근거·방법론. 재원/수혜처 없으면 섹션 조건부 생략(A 과집행없음→"유지 권고", 수혜처 없음→"유보").
- tests/verify_reproducibility.py: 진단(build_report)에 더해 재배분(build_reallocation)까지 4케이스 점검하도록 확장.
**변경 파일**: src/detect_issues.py, src/generate_report.py, src/reallocate.py(신규), output/insight_report.md·budget_reallocation.md, tests/verify_reproducibility.py, decisions.md(Step 18·20)
**검증**: 원본 재배분안 2건(rank1 메타→네이버 회수 3,194,281원·순증상한 1,277만, rank2 메타→오가닉 정성), 회수가능액≠임팩트 구분(회수 319만 vs 임팩트 882만). **재현성 4종 전체 통과** — 원본/C 2건, B(오가닉없음) 1건, A(과집행없음) 재원없음→유지권고. 검증 과정에서 테스트 과단정(재원 없을 때도 '우선순위 판단 기준' 요구) 발견·수정 — 재배분안 있을 때만 조건부 요구로 변경.
**결과**: Challenge(예산 재배분 기획안 + 양식·우선순위 설계) 완료. Basic 100 + Standard 30 + Challenge 30 = 목표 160점 산출물 완비.

### W-006 · HTML 대시보드 생성 + run_pipeline 리팩터('데이터 하나, 표현 둘')
**요청**: md 산출물을 HTML로도 생성(진단·재배분 2개). 샘플 HTML은 옛 로직이라 디자인만 참고하고 내용은 현재 파이프라인 값 사용.
**수행 작업**
- reallocate.py: `run_pipeline(data_path)` 신설 — 정제·집계·이슈·랭킹·재원·수혜·재배분을 한 번 실행해 결과 dict 반환. `_meta`도 이리로 이동(순환 임포트 방지 위해 reallocate에 배치, 상류 모듈들이 단방향 import).
- generate_report.build_report·reallocate.build_reallocation: data 인자로 run_pipeline 결과 주입 허용(중복 계산 제거, 수치 단일 출처). generate_report 임포트 정리(run_pipeline·BAND_SHORT만).
- src/generate_html.py(신규): 같은 결과 dict를 카드·CSS막대·색상태그·이슈/재배분 카드로 렌더링. 이미지 차트 없이 CSS만(과제 제약 준수). insight_report.html·budget_reallocation.html 생성 + CLI.
- tests/verify_reproducibility.py: run_pipeline 1회 실행해 md·html 4산출물 모두 점검(HTML 생성 크래시·물결표까지).
- .claude/skills/generate.md: 3개 실행 명령·파이프라인 구조(run_pipeline·generate_html) 갱신.
**변경 파일**: src/reallocate.py, src/generate_report.py, src/generate_html.py(신규), output/insight_report.html·budget_reallocation.html(신규), tests/verify_reproducibility.py, .claude/skills/generate.md
**검증**: 스탯카드 4개 값 md와 정확 일치(총지출 50,992,739·총매출 439,553,059·MER 862.0%·전환 22,858). 재현성 4종 전체 통과(md+html), HTML도 데이터 적응(A 과집행없음→재배분 축약, B 오가닉없음→진단 축약). 리팩터 회귀 없음.
**결과**: 완료 — md 2종 + html 2종 산출물. 계산 단일화(run_pipeline)로 표현 계층 추가에도 수치 정합 보장.

### W-007 · 제출 패키지 정리 (hackathon_과제.md 요건 대조 + SUBMISSION.md)
**요청**: 과제 제출 요건 검토 후 제출 방식 결정. 결정 — 제출 채널은 output/*.md 파일, HTML도 정식 제출물로 포함.
**수행 작업**
- hackathon_과제.md ⑤·⑥·⑦ 대조: 제출형식(노션/독스/md), 제외범위(이미지차트·대시보드), 채점표 확인. 필수 산출물 전부 충족 확인.
- SUBMISSION.md(신규): 채점자 길잡이 — 실행 명령, 산출물↔채점항목 매핑(Basic/Standard/Challenge), 계산·해석 분리 원칙, 재현성 검증, 의사결정 기록 위치.
- HTML 제약 방어 문구 명시: 이미지차트 아님(CSS만)·인터랙티브 웹앱 아님(정적)·계산은 Python(md와 동일 수치) → ⑥ 제외범위와 비충돌 근거.
- 전체 산출물(md 2·html 2) 최신 재생성.
**변경 파일**: SUBMISSION.md(신규)
**검증**: verify_reproducibility 4종 전체 통과 유지. 산출물 목록 확인(output/insight_report·budget_reallocation의 .md·.html).
**결과**: 제출 준비 완료. 정본 md + 파이프라인(src·skills·tests) + 기획안 + HTML 보조, SUBMISSION.md가 진입점.

### W-008 · 목표 재정의 → 독자별 2종 리포트 + 주차별 ROAS 추이 + 롤링 8주 (decisions Step 27)
**요청**: 프로젝트 목표 재작성(이커머스/서비스 마케팅 DA, 최근 8주 일별 CSV, 경영진·마케팅팀 주간 보고)을 REPORT_DESIGN에 기록하고 리포트를 재설계.
**수행 작업**
- 최근 8주 롤링 윈도우: calculate.trim_recent_weeks — 8주 초과 CSV는 최근 8주만 분석(중복 제거 후·이상치 탐지 전 적용). 현재 8주 데이터는 무동작(회귀 없음).
- 주차별 채널 효율 추이(ROAS): compute_weekly_channel_roas + build_weekly_channel_trend — 주차×채널 매트릭스 + 자동 인사이트(리더 유지/역전·상승 추세). insight_report에만 배치.
- 전주 대비 최근 2주 심층: compute_wow_by_channel + build_wow_channel_insight — 채널별 지출·ROAS 변화를 예산 방향으로 문장화. 이상치 판정은 중앙값 기준 유지(WoW로 판정 안 함).
- 독자별 2종 리포트(계산 1벌, 렌더 2벌): exec_report(경영진 요약본 — 승인용 1장, 데이터 정정 제외) 신규. insight_report는 마케팅팀 상세본으로 재규정 + 예산 재배분 기획안 흡수.
- standalone budget_reallocation.md/.html 생성·함수 제거(build_reallocation·build_reallocation_html 등). reallocate.py는 엔진 모듈로 유지. 조사 오류 방지 _josa 헬퍼 추가. SUBMISSION·portfolio 2종 구조로 갱신.
**변경 파일**: docs/REPORT_DESIGN.md, src/calculate.py·reallocate.py·generate_report.py·generate_html.py, tests/make_fixtures.py(12주 변형 D)·verify_reproducibility.py, output/(insight_report·exec_report .md·.html, budget_reallocation 삭제), decisions.md(Step 27), SUBMISSION.md, portfolio.md
**검증**: verify_reproducibility 5케이스 전체 통과. D(12주)→분석 창 8주(W5-W12) 트림 증명. 산출물 2종(insight_report·exec_report)만 생성 확인.
**결과**: 독자별 2종 리포트 체계 완성 — 경영진 요약본 1장 + 마케팅팀 상세본(예산 흡수), 최근 8주 고정 동향.
