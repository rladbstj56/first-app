# Skill: /generate — 리포트 자동 생성

새 성과 CSV를 넣으면 **정제 → 계산 → 이슈 탐지 → 리포트**까지 한 번에 자동 생성한다.
수치·표·이슈는 Python이 계산하고(오류 없는 정확성), 해석·권장 조치는 규칙 기반 템플릿 + Claude 서술로 채운다.

---

## 실행 (한 줄)

```bash
python3 src/generate_report.py [입력CSV] [출력MD]   # 마케팅팀 상세본 + 경영진 요약본 (md 2종)
python3 src/generate_html.py [입력CSV]             # 위 둘의 HTML 대시보드 2종
```

- 인자 생략 시: `data/marketing_performance.csv` → `output/insight_report.md`
- 새 데이터: `python3 src/generate_report.py data/2026-06_perf.csv output/2026-06_report.md`
- md와 html은 같은 `run_pipeline` 결과를 소비 → 수치가 절대 어긋나지 않음('데이터 하나, 표현 둘').

입력 CSV는 원본과 같은 컬럼(date, channel, impressions, clicks, spend, conversions, revenue, week)이면 된다.
주차 라벨·채널 구성·기간이 달라도 자동 적응한다(하드코딩 없음).

---

## 파이프라인 구조 (src/)

1. **calculate.py** — 정제·집계
   - `load_and_clean`: 숫자형 변환, 완전 중복 제거, 매출 이상치 revenue만 NaN(동적 탐지)
   - `find_revenue_outliers`: 채널별 AOV modified z-score>3.5 이상치 탐지(정제·보고 공용)
   - `compute_summary`: 총지출·총매출·MER·유료ROI·오가닉 분리 + 채널별 파생지표(ROI/ROAS/CTR/CVR)
   - `compute_channel_roi`, `compute_wow_change`(마지막 2주 자동)
2. **detect_issues.py** — 규칙 기반 이슈 탐지
   - 급등/급락(LOO 중앙값 기준선, 데이터 적응형 임계값=Tukey IQR 펜스+하한 25%, 과집행은 ROAS↓ 조건), 이상치, 결측
   - 벤치마크 채널 평가(industry-news.md), 오가닉 기회(매출 비중 10%↑)
   - `score_and_rank`: 손실은 원(₩) 임팩트 정렬, 나머지는 카테고리별 분리
   - `compute_weekly_channel_roas`(주차별 채널 ROAS 추이) / `compute_wow_by_channel`(채널별 최근 2주 변화) / `trim_recent_weeks`(롤링 8주)
3. **reallocate.py** — 예산 재배분 엔진 + 오케스트레이션
   - `run_pipeline`: 정제(롤링 8주 트림)→집계→이슈→랭킹→재원→수혜→재배분을 한 번 실행해 결과 dict 반환(md·html 공용)
   - `compute_funding`(재원=예산 레버만) / `select_targets`(벤치마크 우수+오가닉) / `build_plans`(우선순위 2단 정렬)
   - `build_action_checklist`·`_plan_block`·`PRIORITY_CRITERIA`: 예산 재배분 기획안 빌딩블록(generate_report가 흡수해 재사용)
4. **generate_report.py** — `run_pipeline` 결과로 insight_report.md(마케팅팀 상세본, 예산 재배분 흡수) + exec_report.md(경영진 요약본) 조립
5. **generate_html.py** — 같은 결과로 insight_report.html·exec_report.html 조립(CSS 대시보드, 이미지 차트 없음)

---

## 재현성 검증됨 (자동 회귀 테스트)

```bash
python3 tests/make_fixtures.py          # 변형 픽스처 4종 생성(원본 subset/relabel)
python3 tests/verify_reproducibility.py  # 원본+픽스처 5케이스 자동 점검(실패 시 exit 1)
```

- 주차/채널이 다른 변형 CSV로도 크래시 없이 생성(변화율 섹션이 실제 마지막 2주로 자동 조정).
- 손실 이슈가 0건이어도, 오가닉이 없어도 섹션이 안전하게 생략/대체됨.
- 픽스처(tests/fixtures/): A 4주·3채널 / B 오가닉 없음 / C 주차 재라벨(W5-12) / D 12주(롤링 8주 트림 검증). 각 케이스가 서로 다른 엣지 경로를 검증.

## 완료 기준
- [ ] `python3 src/generate_report.py` 실행 오류 없음
- [ ] output/insight_report.md 생성 (핵심수치·ROI순위·이슈·변화율·채널평가 포함)
- [ ] 새 CSV로도 동일 품질 생성 확인
- [ ] 중요한 판단은 decisions.md에 기록

→ 설계 근거·지표 선택 이유는 docs/REPORT_DESIGN.md 참조
