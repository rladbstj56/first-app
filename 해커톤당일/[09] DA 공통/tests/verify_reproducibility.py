"""재현성 검증: 원본 + 변형 픽스처 전부에 파이프라인을 돌려 크래시 없이
동일 구조 리포트가 나오는지 자동 점검한다.

각 CSV마다: (1) 마케팅팀 상세본(진단+주차별 추이+흡수된 예산 재배분 기획안), (2) 경영진 요약본,
(3) 롤링 8주 트림을 점검한다. 재배분은 재원(과집행)·수혜처(오가닉) 유무가 데이터마다 달라
(B 오가닉없음·A 과집행없음 등) 크래시 없이 조건부로 대응하는지가 핵심. 하나라도 실패하면 exit 1.
"""
import os
import re
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, '..', 'src'))
from reallocate import run_pipeline  # noqa: E402
from generate_report import build_report, build_exec_report  # noqa: E402
from generate_html import build_insight_html, build_exec_html  # noqa: E402

FIX = os.path.join(HERE, 'fixtures')
CASES = [
    ('원본(8주·5채널)', os.path.join(HERE, '..', 'data', 'marketing_performance.csv')),
    ('A 짧은·소채널(4주·3채널)', os.path.join(FIX, 'variant_a_short.csv')),
    ('B 오가닉 없음', os.path.join(FIX, 'variant_b_noorganic.csv')),
    ('C 주차 재라벨(W5-W12)', os.path.join(FIX, 'variant_c_relabel.csv')),
    ('D 12주(롤링 트림 검증)', os.path.join(FIX, 'variant_d_twelveweeks.csv')),
]
# 마케팅팀 상세본 필수 섹션 — 신규 '주차별 채널 효율 추이'·흡수된 '예산 재배분 기획안' 포함.
REQUIRED = ['데이터 개요', '핵심 수치', 'ROI', '이슈', '변화율', '주차별 채널 효율 추이', '예산 재배분 기획안']


def check(label, path):
    d = run_pipeline(path)          # 한 번 실행해 md·html이 같은 결과 공유(예외 시 크래시=실패)
    report = build_report(data=d)   # 마케팅팀 상세본 (예산 재배분 기획안 흡수)
    missing = [s for s in REQUIRED if s not in report]
    wow = re.search(r'(W\d+)\s*→\s*(W\d+)', report)
    wow_txt = f'{wow.group(1)} → {wow.group(2)}' if wow else '없음'
    has_opp = '오가닉 성장' in report
    tilde = '~' in report  # 취소선 유발 물결표가 남아있으면 안 됨(T-001)

    # 흡수된 예산 재배분 기획안 상태 — 재원·수혜처 유무에 따라 조건부로 성립하는지 확인.
    n_plans = report.count('[재배분안 #')
    if '재원(광고비 과집행)이 탐지되지 않아' in report:
        r_state = '재원 없음(유지 권고)'
    elif n_plans == 0:
        r_state = '재원 있으나 수혜처 없음'
    else:
        r_state = f'재배분안 {n_plans}건'
        if '우선순위, 이렇게 정했습니다' not in report:  # 재배분안이 있으면 우선순위 설계 근거 필수
            missing.append('우선순위 판단 기준')

    insight_html = build_insight_html(d)      # HTML 생성 크래시 체크
    exec_md = build_exec_report(data=d)       # 경영진 요약본 생성 크래시·물결표 체크
    exec_html = build_exec_html(d)
    html_ok = len(insight_html) > 500 and '~' not in insight_html
    exec_ok = '경영진' in exec_md and len(exec_html) > 300 and '~' not in exec_md

    # 롤링 윈도우: 분석 창은 항상 최근 8주 이하. D(12주)는 8주로 트림돼야 함.
    n_win, n_file = d['meta']['n_weeks'], d['meta']['n_weeks_file']
    trim_ok = n_win <= 8 and (n_win == 8 and n_file == 12 if label.startswith('D') else True)

    ok = not missing and not tilde and html_ok and exec_ok and trim_ok
    print(f'[{"OK " if ok else "FAIL"}] {label}')
    print(f'       마케팅팀 상세본: {len(report):,}자 | 변화율 {wow_txt} | 기회섹션 {"있음" if has_opp else "없음"} | 재배분 {r_state} | 물결표 {"있음(문제)" if tilde else "없음"}')
    print(f'       분석 창: {n_win}주 (파일 {n_file}주) | 트림 {"OK" if trim_ok else "문제"}')
    print(f'       경영진 요약본: {len(exec_md):,}자·HTML {len(exec_html):,}자 | {"OK" if exec_ok else "문제"}')
    print(f'       HTML: 상세본 {len(insight_html):,}자 | {"OK" if html_ok else "문제"}')
    if missing:
        print(f'       누락 섹션: {missing}')
    return ok


def main():
    results = [check(label, path) for label, path in CASES]
    print('\n' + ('전체 통과' if all(results) else '실패 케이스 있음'))
    sys.exit(0 if all(results) else 1)


if __name__ == '__main__':
    main()
