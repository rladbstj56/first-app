"""insight_report.md 자동 생성 — 수치·표는 계산 엔진에서, 해석은 규칙 기반 템플릿으로.

calculate.py(집계)·detect_issues.py(이슈)를 불러 새 CSV에도 동일 품질의 리포트를 재현한다.
권장 조치는 임의 서술이 아니라 industry-news.md 4장 '성과 이슈 패턴(유형 A~D)'에 매핑한다.
"""
import re
import sys

import pandas as pd

from calculate import compute_summary
from detect_issues import BAND_SHORT
from reallocate import (run_pipeline, _plan_block,
                        PRIORITY_CRITERIA, PRIORITY_CAVEAT)

DATA = 'data/marketing_performance.csv'
OUT = 'output/insight_report.md'
EXEC_OUT = 'output/exec_report.md'

# 이슈 유형 → 권장 조치 (industry-news.md 4장 유형 A~D 대응)
REC = {
    '광고비급등(과집행)': "예산 한도 설정, 타겟 세분화, 소재 교체 (유형 A: 광고비 급증 후 ROAS 하락)",
    '매출이상치': "원본 데이터 재확인, 중복·테스트 주문 제거 후 재집계 (유형 D: 비현실적 급등)",
    'revenue결측': "즉시 담당자 확인, 수동 보정 또는 '데이터 없음' 명시 (유형 C: 데이터 결측)",
    'impressions결측': "트래킹 코드·플랫폼 API 점검 (유형 C: 데이터 결측)",
    'clicks결측': "트래킹 코드·플랫폼 API 점검 (유형 C: 데이터 결측)",
    '광고비급락(집행축소)': "의도적 감축인지 집행 중단 사고인지 담당자 확인",
    '성과급락': "랜딩페이지 A/B 테스트, UX·경쟁·소재 소진 점검 (유형 B)",
    '성과호재': "성공 요인 분석 후 예산 확대 검토",
}


def won(x):
    return f"{x:,.0f}원"


def won_compact(x):
    """요약 박스 전용 축약 표기 — 억/만원 단위로 줄여 숫자를 한눈에 잡히게 한다.

    상세 섹션(핵심 수치 요약·이슈·예산 재배분 등)은 won()으로 정확한 원 단위를 유지하고,
    md·html 요약 박스(핵심 요약)에서만 이 함수를 써서 표현만 다르게 한다.
    """
    sign = '-' if x < 0 else ''
    x = abs(x)
    if x >= 1e8:
        return f"{sign}{x / 1e8:.2f}억원"
    if x >= 1e4:
        return f"{sign}{x / 1e4:,.0f}만원"
    return f"{sign}{x:,.0f}원"


_WON_TEXT_RE = re.compile(r'-?[\d,]+원')


def compact_won_text(s):
    """이미 조립된 문장(build_summary_points 등) 안의 '1,234,567원' 패턴만 찾아 축약 표기로 치환."""
    return _WON_TEXT_RE.sub(lambda m: won_compact(float(m.group(0)[:-1].replace(',', ''))), s)


def _josa(word, with_batchim, without_batchim):
    """동적 채널명 뒤 한글 조사(이/가, 을/를)를 받침 유무로 선택 — '이메일가' 같은 오류 방지."""
    if not word:
        return without_batchim
    last = word[-1]
    if '가' <= last <= '힣':
        return with_batchim if (ord(last) - 0xAC00) % 28 else without_batchim
    return without_batchim


def _overview(meta):
    n_file, n_win = meta.get('n_weeks_file', meta['n_weeks']), meta['n_weeks']
    trim_line = (f"  - 롤링 윈도우: 파일 내 {n_file}주 중 가장 최근 {n_win}주만 분석 (이전 {n_file-n_win}주 제외)\n"
                 if n_file > n_win else "")
    return (f"- 분석 대상: {meta['path']} (원본 {meta['n_raw']}행, 채널 {meta['n_channels']}개)\n"
            f"- 분석 기간: {meta['date_min']} – {meta['date_max']} ({meta['n_weeks']}주: {meta['weeks']})\n"
            "- 데이터 정제:\n"
            f"  - 완전 중복 {meta['n_dup']}행 제거 ({meta['n_raw']}→{meta['n_raw']-meta['n_dup']}행)\n"
            + trim_line
            + f"  - 결측 {meta['n_missing']}건 NaN 유지 — 0으로 채우지 않고 집계에서 자동 제외\n"
            f"  - 매출 이상치 {meta['n_outlier']}건 revenue만 제외(AOV modified z-score>3.5 자동 탐지) — 정상 지출·전환은 보존\n"
            "  - 오가닉(광고비 0) ROI 측정 불가로 순위 제외\n")


def _summary(s):
    t = s['total']
    rows = ["| 지표 | 값 |", "|------|-----|",
            f"| 총 지출 (유료 광고비) | {won(t['total_spend'])} |",
            f"| 총 매출 (전 채널, 오가닉 포함) | {won(t['total_revenue'])} |",
            f"| ├ 오가닉(비유료) 매출 | {won(t['organic_revenue'])} ({t['organic_revenue']/t['total_revenue']*100:.2f}%) |",
            f"| └ 유료채널 매출 | {won(t['paid_revenue'])} |",
            f"| 전체 마케팅 효율 MER (오가닉 포함) | {t['mer']:.2f}% |",
            f"| 유료 광고 순효율 (오가닉 제외) | {t['paid_roi']:.2f}% |",
            f"| 총 전환수 | {t['total_conversions']:,.0f}건 |\n",
            "> **오가닉(organic)** = 광고비를 직접 쓰지 않고 들어온 매출(검색 결과·직접 방문·SEO·콘텐츠 등 자연 유입). "
            "이번 기간 광고 원장에 잡히는 지출이 0이라 ROI 계산 대상에선 빠지지만 매출 기여는 크므로 별도 표기한다"
            "(규모가 유의미하면 아래 '오가닉 성장 잠재력' 섹션에서 상세 분석).\n",
            "> MER은 경영진용(마케팅 조직 전체 성과), 유료 순효율은 마케팅팀용(광고 운영 효율).\n",
            "### 채널별 합계·파생지표\n",
            "| 채널 | 광고비(원) | 매출(원) | 전환 | ROI(%) | ROAS | CPA(원) | CTR(%) | CVR(%) |",
            "|------|-----------|---------|------|--------|------|---------|--------|--------|"]
    g = s['by_channel']
    for ch in g.sort_values('revenue', ascending=False).index:   # 채널 목록을 데이터에서 동적으로
        r = g.loc[ch]
        roi = "측정불가" if pd.isna(r['ROI']) else f"{r['ROI']:.2f}"
        roas = "-" if pd.isna(r['ROAS']) else f"{r['ROAS']:.2f}"
        cpa = "-" if pd.isna(r['CPA']) else f"{r['CPA']:,.0f}"
        rows.append(f"| {ch} | {r['spend']:,.0f} | {r['revenue']:,.0f} | {r['conversions']:,.0f} | "
                    f"{roi} | {roas} | {cpa} | {r['CTR']:.2f} | {r['CVR']:.2f} |")
    rows.append("\n> **ROAS(광고 지출 대비 매출)** = 매출 / 광고비. ROI와 계산식은 같지만 배수로 표현해 "
                "'광고비 1원당 매출 몇 원'인지 직관적으로 보여준다. 오가닉은 광고비 0이라 측정 제외(-).")
    rows.append("> **CTR(클릭률)** = 클릭 / 노출. 소재·타겟팅이 시선을 끄는 정도를 보는 퍼널 상단 지표.")
    rows.append("> **CVR(전환율)** = 전환 / 클릭. 클릭 이후 실제 구매·전환으로 이어지는 정도를 보는 퍼널 하단 지표.")
    rows.append("> **CPA(전환당 비용)** = 광고비 / 전환. 낮을수록 효율적(입찰·예산 조정의 직접 지표). "
                "오가닉은 광고비 0이라 측정 제외(-).")
    return "\n".join(rows) + "\n"


def _roi_rank(roi_df):
    rows = ["> ROI = 매출 / 광고비 × 100. 오가닉은 광고비 0이라 측정 불가로 제외.\n",
            "> **활용**: 효율 높은 채널을 키울 후보로 보되, 절대 ROI만으로 정하지 말고 아래 6번 시장 벤치마크 등급과 함께 판단하세요 — 절대 1위여도 자기 시장 대비 미달일 수 있습니다.\n",
            "| 순위 | 채널 | ROI(%) |", "|------|------|--------|"]
    for i, (ch, r) in enumerate(roi_df.iterrows(), 1):
        rows.append(f"| {i} | {ch} | {r['ROI']:.2f} |")
    rows.append("| - | 오가닉 | 측정 불가 (광고비 0) |")
    top = roi_df.index[0]
    rows.append(f"\n**해석**: 가장 효율적인 유료 채널은 {top}(ROI {roi_df.iloc[0]['ROI']:.2f}%). "
                "단 절대 효율(ROI)이 높다고 채널 벤치마크 대비 잘하는 것은 아니므로 6번 채널 평가와 함께 볼 것.\n")
    return "\n".join(rows)


def _status(itype, channel, recency, threshold):
    """이슈가 최근 주차에도 지속되는지 한 줄로 반환 (갭3: 진행 중 vs 해소 구분).

    급등/급락 이슈는 해당 지표의 최근 주차 LOO 편차를 임계값과 비교해 지속/해소를 판정한다.
    이상치·결측은 특정 일자 데이터 사안이라 '재발' 개념이 아니므로 그 성격만 명시한다.
    독자가 '지금 불이 났나(지속) 이미 끝난 일인가(해소)'를 알아 긴급도를 가르게 한다.
    """
    r = recency.get(channel)
    if r is None:
        return ""
    wk, thr = r['week'], threshold * 100
    if '과집행' in itype:
        v, hit = r['spend'], (not pd.isna(r['spend']) and r['spend'] >= thr)
    elif '집행축소' in itype:
        v, hit = r['spend'], (not pd.isna(r['spend']) and r['spend'] <= -thr)
    elif '성과급락' in itype:
        v = r['revenue']
        hit = any(not pd.isna(r[m]) and r[m] <= -thr for m in ('revenue', 'conversions'))
    elif '호재' in itype:
        v = r['revenue']
        hit = any(not pd.isna(r[m]) and r[m] >= thr for m in ('revenue', 'conversions'))
    else:
        return "- 최근성: 특정 일자 데이터 사안(재발 개념 아님) — 정정 후 재탐지로 확인"
    if pd.isna(v):
        return ""
    tag = "지속(최근 주차도 임계값 초과 — 긴급)" if hit else "해소(최근 주차 정상 범위 — 사후 점검)"
    return f"- 최근 {wk} 상태: {tag}, 해당 지표 편차 {v:+.1f}%"


_SHOW_STATUS_TYPES = ('광고비급등(과집행)', '광고비급락(집행축소)', '성과급락', '성과호재')


def _issue_block_md(i, r, recency, threshold, label='이슈'):
    """이슈 1건을 md 블록으로 — 임팩트(₩)가 있으면 금액을 표기하고, 없으면(집행축소·결측 등) 생략한다.

    발생 표기는 loss행(weeks·frequency 보유)과 관찰·품질행(week 단수)의 컬럼 구조가 달라 분기한다 —
    pd.concat으로 합친 뒤라 없는 컬럼은 NaN으로 채워지므로 'in r.index'가 아니라 notna로 판별해야 한다.
    최근 지속 여부(_status)는 '재발 가능한 패턴' 유형(과집행·집행축소·성과급락·호재)에만 의미가 있어
    이상치·결측(1회성 데이터 사안)에는 표시하지 않는다.
    """
    has_amt = not pd.isna(r['impact_won']) and r['impact_won'] > 0
    head = f"**{label} {i}: {r['channel']} — {r['type']}"
    if has_amt:
        if r['type'] == '성과호재':
            amt_label = '매출 증가분'
        elif r['lever'] == '데이터·트래킹':
            amt_label = '왜곡·추정 금액'
        else:
            amt_label = '기회손실'
        head += f" ({amt_label} {won(r['impact_won'])})"
    head += f" `[{r['lever']}]`**"
    lines = [head, f"- 현상: {r['phenomenon']}", f"- 근거: {r['evidence']}"]
    lines.append(f"- 발생: {r['weeks']} (빈도 {r['frequency']:.0f}주)" if pd.notna(r.get('weeks')) else f"- 발생: {r['week']}")
    if r['type'] in _SHOW_STATUS_TYPES:
        st = _status(r['type'], r['channel'], recency, threshold)
        if st:
            lines.append(st)
    lines.append(f"- 권장 조치: {REC.get(r['type'], '원인 분석 후 대응')}\n")
    return "\n".join(lines)


def _issues(ranked, recency, threshold):
    """이슈를 **담당·조치처(레버) 하나의 기준**으로 3그룹(예산·운영·크리에이티브·데이터·트래킹)으로 나눈다.

    예전엔 '매출 영향 유무'와 '레버'를 섞어 5개 그룹(실행가능한 손실·데이터 정정·운영 관찰·데이터 품질·긍정 신호)으로
    나눴는데, 독자 입장에서 두 기준이 겹쳐 보여 분류가 산만하다는 피드백을 반영해 레버 하나로 통일했다.
    같은 레버라도 임팩트(₩)가 있으면 금액을 표기하고 없으면(집행축소·결측처럼 성격상 0) 생략만 다르게 한다 —
    그룹 자체를 나누지 않는다. 문제가 아닌 '긍정 신호'는 애초에 조치 레버 개념이 안 맞아 맨 아래 참고로 분리.
    정렬: 각 그룹 안에서 임팩트(₩) 큰 순 — 임팩트 없는 항목은 자연히 하단에 위치.
    """
    loss = ranked.get('loss')
    operational = ranked.get('operational')
    quality = ranked.get('quality')
    positive = ranked.get('positive')

    def _collect(lever):
        parts = [df[df['lever'] == lever] for df in (loss, operational, quality)
                 if df is not None and not df.empty]
        parts = [p for p in parts if not p.empty]
        if not parts:
            return []
        combined = pd.concat(parts, ignore_index=False, sort=False)
        return list(combined.sort_values('impact_won', ascending=False, na_position='last').iterrows())

    rows = ["> **분류**: 담당·조치처(레버) 하나의 기준으로 3그룹 — **예산**(재배분 대상)·"
            "**운영·크리에이티브**(채널 담당 확인)·**데이터·트래킹**(원본·수집 확인, 예산 조치 아님). "
            "문제가 아닌 **긍정 신호**는 맨 아래 참고로 별도 표시한다.\n",
            "> **정렬**: 각 그룹 안에서 임팩트(₩) 큰 순 — 임팩트가 없는 항목(집행축소·결측 등 성격상 0)은 "
            "자연히 하단에 위치한다.\n"]

    for lever, title, empty_msg, footnote in [
        ('예산', '예산 (재배분 대상 — 마케팅 리드 확인)', '예산 레버로 확인할 이슈 없음.',
         "> 이 중 회수 가능한 초과 지출은 예산 재배분 재원이 된다 — 상세 기획은 아래 '예산 재배분 기획안' 섹션 참조.\n"),
        ('운영·크리에이티브', '운영·크리에이티브 (채널 담당 확인)', '운영·크리에이티브 레버로 확인할 이슈 없음.', None),
        ('데이터·트래킹', '데이터·트래킹 (원본·수집 확인 — 예산 조치 아님)', '데이터·트래킹 레버로 확인할 이슈 없음.',
         "> 위 '금액'은 잃은 돈이 아니라 **데이터가 왜곡·누락된 규모**다. 예산 재배분 대상이 아니다.\n"),
    ]:
        rows.append(f"### {title}\n")
        items = _collect(lever)
        if not items:
            rows.append(empty_msg + "\n")
            continue
        for i, (_, r) in enumerate(items, 1):
            rows.append(_issue_block_md(i, r, recency, threshold))
        if footnote:
            rows.append(footnote)

    if positive is not None and not positive.empty:
        rows.append("### 참고: 주목할 긍정 신호 (문제 아님)\n")
        for i, (_, r) in enumerate(positive.iterrows(), 1):
            rows.append(_issue_block_md(i, r, recency, threshold, label='긍정'))
    return "\n".join(rows)


def _wow(wow_df):
    prev, curr = wow_df.columns[0], wow_df.columns[1]   # 실제 마지막 두 주차 (하드코딩 제거)
    rows = [f"| 지표 | {prev} | {curr} | 변화율(%) | 상태 |", "|------|----|----|----------|------|"]
    label = {'spend': '지출', 'revenue': '매출', 'conversions': '전환수', 'CTR': 'CTR'}
    max_abs = 0
    for m in ['spend', 'revenue', 'conversions', 'CTR']:
        r = wow_df.loc[m]
        chg = r['change_pct']
        max_abs = max(max_abs, abs(chg))
        state = "↑↑" if chg >= 50 else "↑" if chg > 5 else "→" if chg >= -5 else "↓↓" if chg <= -50 else "↓"
        v0 = f"{r[prev]:,.0f}" if m != 'CTR' else f"{r[prev]:.2f}%"
        v1 = f"{r[curr]:,.0f}" if m != 'CTR' else f"{r[curr]:.2f}%"
        rows.append(f"| {label[m]} | {v0} | {v1} | {chg:+.2f} | {state} |")
    verdict = (f"모든 지표가 ±50% 이내(최대 변동 {max_abs:.2f}%)로 {prev}→{curr}는 안정적. 급변 없음."
               if max_abs < 50 else f"일부 지표가 ±50%를 초과({prev}→{curr} 최대 {max_abs:.2f}%) — 급변 발생, 원인 확인 필요.")
    rows.append(f"\n> {verdict}\n")
    return "\n".join(rows)


def build_wow_channel_insight(d):
    """채널별 최근 2주 변화에서 예산 인사이트 문장을 규칙으로 뽑는다 — md·html 공유.

    입력: run_pipeline 결과(wow_channel). 출력: 문장 리스트.
    규칙: ①지출을 가장 크게 늘린 채널(±10%↑)을 ROAS 유지 여부로 '효과적 증액/증액 효과 미흡'으로 판정,
          ②ROAS가 10%↑ 하락한 채널은 점검 대상으로 표시. 최근 2주를 예산 방향으로 직접 잇는다.
    문장은 판정(무엇)에 그치지 않고 '왜 그렇게 판단하는지·다음에 뭘 해야 하는지'까지 풀어 쓴다
    — 명사형 종결은 유지하되(Step 31), 함의를 압축된 태그가 아니라 문장으로 전달한다.
    """
    wc = d['wow_channel']
    paid = wc[wc['spend_curr'] > 0]
    out = []
    sp = paid.dropna(subset=['spend_chg'])
    if not sp.empty:
        top = sp.loc[sp['spend_chg'].abs().idxmax()]
        if top['spend_chg'] >= 10:
            ch = top['channel']
            if pd.isna(top['roas_chg']) or top['roas_chg'] >= -5:
                out.append(f"{ch} 지출을 최근 2주간 {top['spend_chg']:+.0f}% 늘렸는데도 ROAS는 이전 수준을 그대로 유지 — "
                           f"늘어난 예산이 효율 저하 없이 흡수되고 있다는 신호로, 추가로 투입해도 비슷한 효율을 낼 가능성이 높은 "
                           f"채널. 다음 예산 배정 시 우선 증액 후보로 검토 필요.")
            else:
                out.append(f"{ch} 지출을 {top['spend_chg']:+.0f}% 늘렸지만 ROAS는 {top['roas_chg']:+.0f}% 하락 — "
                           f"늘린 예산만큼 효율이 따라오지 못하고 있다는 신호로, 무분별한 추가 증액보다 소재·타겟팅 점검이 "
                           f"먼저 필요한 채널.")
    for _, r in paid.dropna(subset=['roas_chg']).iterrows():
        if r['roas_chg'] <= -10:
            out.append(f"{r['channel']}의 ROAS가 최근 2주간 {r['roas_chg']:+.0f}% 하락 — 지출 변화와 무관하게 "
                       f"효율 자체가 떨어지고 있어, 오퍼·랜딩페이지 등 전환 단계 점검이 필요한 채널.")
    if not out:
        out.append("최근 2주간 채널별 지출·효율에 예산 조정이 필요할 만큼 큰 변화는 감지되지 않음 — "
                   "현재 배분을 유지해도 무방한 안정적인 구간.")
    return out


def _wow_channel_md(d):
    wc = d['wow_channel']
    prev, curr = d['wow'].columns[0], d['wow'].columns[1]
    paid = wc[wc['spend_curr'] > 0]
    lines = [f"\n### 채널별 최근 2주 변화 ({prev} → {curr})\n",
             "> 전체 변화가 '조직이 어떻게 변했나'라면, 아래는 '어느 채널이 움직였나' — 최근 예산 인사이트의 근거다.\n",
             "| 채널 | 지출 변화 | ROAS 변화 | ROAS(최근) |",
             "|------|-----------|-----------|-----------|"]
    for _, r in paid.iterrows():
        sc = "–" if pd.isna(r['spend_chg']) else f"{r['spend_chg']:+.1f}%"
        rc = "–" if pd.isna(r['roas_chg']) else f"{r['roas_chg']:+.1f}%"
        rn = "–" if pd.isna(r['roas_curr']) else f"{r['roas_curr']:.2f}"
        lines.append(f"| {r['channel']} | {sc} | {rc} | {rn} |")
    lines.append("\n**최근 2주 예산 인사이트**\n")
    for s in build_wow_channel_insight(d):
        lines.append(f"- {s}")
    return "\n".join(lines) + "\n"


_DIR_ORDER = ['증액 후보', '유지', '개선 우선', '측정불가']
_DIR_LABEL = {'증액 후보': '증액 후보', '유지': '유지', '개선 우선': '개선 우선',
              '측정불가': '측정불가(별도 판단)'}


def _benchmark(ranked):
    b = ranked['benchmark']
    rows = [
        "> **여기서 '등급'은 우리 회사 주차 비교가 아니라, 같은 채널을 운영하는 업계 분포(2026 한국 시장 벤치마크, "
        "industry-news.md) 대비 위치다.** 출처가 업계 통용 추정치라 정성 판단용으로만 쓰고 원(₩) 랭킹엔 넣지 않는다.\n",
        "> 등급의 뜻과 그에 따른 조치:",
        "> - **우수(상위25%↑)**: 그 채널을 쓰는 회사들 상위 25%보다 잘함 → 검증된 효율, 증액해도 효율 유지 기대(증액 후보)",
        "> - **평균이상**: 시장 중간보다 나음 → 현상 유지·소폭 최적화",
        "> - **개선여지(평균 이하)**: 시장 중간에 못 미침 → 증액 보류, 원인부터 개선",
        "> - 종합 등급은 최종 성과인 **ROAS** 기준. CTR·CVR은 퍼널 어디가 약한지 진단용(CTR 약함=소재·타겟, CVR 약함=랜딩·오퍼).\n",
        "> **활용**: 맨 오른쪽 '제안 방향' 열이 곧 예산 액션입니다 — 증액 후보부터 늘리고, 개선 우선 채널은 원인 교정 후 재검토, 유지 채널은 현상 유지하세요.\n",
        "| 채널 | CTR | CVR | ROAS(종합) | 제안 방향 |",
        "|------|-----|-----|-----------|-----------|",
    ]
    for _, r in b.iterrows():
        roas_cell = "측정불가" if pd.isna(r['ROAS']) else f"{r['ROAS']:.2f}({BAND_SHORT[r['roas_band']]})"
        rows.append(f"| {r['channel']} | {r['CTR']:.2f}%({BAND_SHORT[r['ctr_band']]}) | "
                    f"{r['CVR']:.2f}%({BAND_SHORT[r['cvr_band']]}) | {roas_cell} | {r['action']} |")

    groups = {}
    for _, r in b.iterrows():
        groups.setdefault(r['direction'], []).append(r['channel'])
    parts = [f"{_DIR_LABEL[d]} = {', '.join(groups[d])}" for d in _DIR_ORDER if d in groups]
    rows.append(f"\n**핵심 인사이트 (예산 방향)**: {' / '.join(parts)}. "
                "종합 등급은 ROAS(시장 대비 매출효율) 기준이라, 절대 ROI 순위가 높아도 자기 채널 시장 벤치마크로는 "
                "미달일 수 있다(예: 이메일 — 절대 ROI 1위지만 CRM 벤치마크 대비 개선여지). "
                "증액은 '증액 후보'부터, '개선 우선' 채널은 원인 교정 후 재검토한다.\n")
    return "\n".join(rows)


def _opportunity(ranked):
    rows = []
    for _, r in ranked['opportunity'].iterrows():
        rows.append(f"- **{r['channel']}**: {r['note']}")
    rows.append("\n> **오가닉은 '무료'가 아니다.** 과거 유료 광고의 낙수효과(브랜딩→검색·직접 유입)와 "
                "SEO·콘텐츠 투자가 누적된 결과이며, 단지 현재 기간 광고비 원장에 직접 귀속되는 클릭당 비용이 0일 뿐이다. "
                "광고비를 직접 배정하는 채널이 아니므로 'SEO·콘텐츠 투자 확대' 또는 '브랜딩 광고의 낙수효과 활용'으로 키운다 "
                "(industry-news 채널 믹스 전략).\n>\n"
                "> ⚠️ 오가닉 매출의 일부는 유료 채널(특히 브랜딩)의 기여이므로, 채널 ROI를 독립적으로 비교하면 "
                "이 교차 기여를 놓친다. 정밀 예산 배분은 MTA/MMM 등 교차 채널 기여 분석이 필요하다(industry-news 트렌드 2).\n")
    return "\n".join(rows)


def exec_perf_2w(d):
    """경영진 성과 헤드라인용 최근 2주(전주+금주) 합계 — 이슈·예산은 8주 기준선을 유지하되 성과만 '지금'을 본다.

    입력: run_pipeline 결과(공유 df·wow). 출력: (전주 라벨, 금주 라벨, 최근 2주 total dict).
    경영진 요약본은 매주 '이번에 얼마 썼고 벌었나'가 핵심이라 8주 누적 대신 최근 2주만 재집계해 신선도를 높인다.
    이상 탐지(핵심 이슈)·재배분 재원은 기준선이 필요해 8주 그대로 두므로, 성과 수치에만 이 값을 쓴다.
    """
    prev, curr = d['wow'].columns[0], d['wow'].columns[1]
    df2 = d['df'][d['df']['week'].isin([prev, curr])]
    return prev, curr, compute_summary(df2)['total']


def _perf_body(t):
    """성과 total dict → 요약 한 줄 문자열 (8주·2주 공용, 표기 일관)."""
    return (f"총매출 {won(t['total_revenue'])} · 유료 광고비 {won(t['total_spend'])} "
            f"(MER {t['mer']:.0f}%, 유료 순효율 {t['paid_roi']:.0f}%, 전환 {t['total_conversions']:,.0f}건)")


# 핵심 요약 제목 바로 아래(항목보다 먼저) 붙는 지표 정의 — 리포트에서 MER·유료 순효율·오가닉이
# 처음 등장하는 자리라 여기서 설명한다. 용어(term)만 굵게 표시하고 본문 문장에는 섞지 않는다.
PERF_DEFS = [
    ("MER", "총매출÷광고비(오가닉 포함 전체 마케팅 효율)"),
    ("유료 순효율", "유료매출÷광고비(광고 자체만의 효율)"),
    ("오가닉", "광고비 없이 자연 유입된 매출(검색·직접방문·SEO 등)"),
]


def perf_def_note_md():
    """핵심 요약 제목 아래 붙는 지표 정의 md(용어만 볼드) — html은 generate_html._perf_def_note_html이 같은 PERF_DEFS를 렌더."""
    return " · ".join(f"**{term}** = {desc}" for term, desc in PERF_DEFS)


# ROAS는 경영진 요약본에서 '최근 2주 모멘텀'(채널 인사이트)에 처음 등장한다 — 그 섹션 제목 바로 아래에
# 작은 글씨로 설명을 붙인다. (MER·유료 순효율·오가닉과 달리 성과 항목이 아니라 모멘텀 섹션에서 처음 등장하므로
# PERF_DEFS와는 별도로 관리)
ROAS_DEF = ("ROAS", "매출÷광고비 — 광고비 1원당 매출이 얼마인지 보여주는 채널 효율 지표"
            "(배수로 표현, 1보다 크면 광고비보다 매출이 큼)")


def roas_def_note_md():
    """모멘텀 섹션 제목 아래 붙는 ROAS 정의 md(용어만 볼드) — html은 generate_html._roas_def_note_html이 같은 ROAS_DEF를 렌더."""
    term, desc = ROAS_DEF
    return f"**{term}** = {desc}"


def build_summary_points(d, perf=None):
    """요약 박스 항목 (라벨, 본문, 부연설명) 리스트 — md·html이 공유(표현만 다르고 수치·판단은 동일).

    한 곳에서만 요약 로직을 만들어 md↔html 불일치를 원천 차단한다(decisions Step 21 원칙).
    순서: ① 전체 성과 ② 가장 시급한 리스크(원인·손실) ③ 그 리스크에 대응하는 예산 승인 요청
    ④ 데이터 정정 규모(분리) ⑤ 최근 안정성 — 문제(②)를 먼저 보여준 뒤 해법(③)이 이어지게 배치.
    재원 없음·이슈 없음 등 조건부에도 문장이 성립하도록 분기한다.
    문장은 대시보드 관행에 맞춰 명사형으로 종결(예: '기회손실 발생', '대응 예정') — '~습니다'체는 쓰지 않는다.
    perf: (라벨, 본문[, 부연설명]) 튜플을 주면 첫 성과 항목을 그대로 교체(경영진 요약본이 최근 2주 성과로 덮어쓸 때만 사용).
    """
    s, ranked, plans, wow = d['summary'], d['ranked'], d['plans'], d['wow']
    t = s['total']
    if perf:
        pts = [perf if len(perf) == 3 else (perf[0], perf[1], None)]
    else:
        pts = [("이번 기간 성과", _perf_body(t), None)]

    loss = ranked.get('loss')
    top = None
    if loss is not None and not loss.empty:
        act = loss[loss['lever'] == '예산']
        if not act.empty:
            top = act.iloc[0]
            pts.append(("가장 시급한 예산 리스크",
                        f"{top['channel']} 예산 과집행으로 {won(top['impact_won'])} 기회손실 발생"
                        f"({top['weeks']}). 초과 지출분 회수 후 예산 재배분으로 대응 예정.", None))

    if not plans.empty:
        p = plans.iloc[0]
        exp = f" 최대 {won(p['expected_won'])} 순증 매출 기대(선형확장 가정)." if not pd.isna(p['expected_won']) else ""
        pts.append(("예산 재배분 승인 요청",
                    f"{p['source']} 과집행 회수분 {won(p['amount_won'])}을(를) 시장 벤치마크 우수 채널 "
                    f"{p['target']}로 재배분(1순위).{exp} (상세: 예산 재배분 기획안 섹션)", None))
    else:
        pts.append(("예산 조정 필요 없음", "과집행 등 재배분 재원 없음 — 현 배분 유지 권장.", None))

    if loss is not None and not loss.empty:
        data_loss = loss[loss['lever'] == '데이터·트래킹']
        if not data_loss.empty:
            pts.append(("데이터 정정 필요(예산 조치 아님)",
                        f"{len(data_loss)}건, 왜곡·추정 금액 합 {won(data_loss['impact_won'].sum())} "
                        f"— 원본 재확인·트래킹 점검 대상(손실 아님)", None))

    prev, curr = wow.columns[0], wow.columns[1]
    max_abs = wow['change_pct'].abs().max()
    stat = "안정적, 급변 없음" if max_abs < 50 else "급변 발생 — 원인 확인 필요"
    pts.append((f"최근 추세({prev}→{curr})",
               f"매출·지출의 전주 대비 안정성 지표(변동폭 50% 초과 시 급변 판정) — "
               f"{stat} (최대 변동 {max_abs:.1f}%)", None))
    return pts


def build_playbook(d):
    """리포트 곳곳에 흩어진 조치를 '이번 주 업무 우선순위' 한 리스트로 취합 — md·html 공유.

    입력: run_pipeline 결과(ranked·plans). 출력: dict 리스트 [{rank, action, basis, owner, when}].
    이미 계산된 판단(재배분·손실·벤치마크·관찰·긍정)을 실무 액션으로 '번역'만 한다 — 새 계산 없음.
    담당·시점을 붙여 리포트를 '읽을거리'에서 '업무 분배 도구'로 바꾼다. tier(1급함~3)로 정렬.
    """
    ranked, plans = d['ranked'], d['plans']
    items = []   # 각 항목에 trank(유형 우선), amt(동유형 내 금액 정렬용) 부여. 최종 정렬은 시점→유형→금액.

    if not plans.empty:   # 예산 재배분 — 실제 회수 가능한 손실·즉시. 시점 최상단.
        p = plans.iloc[0]
        exp = f", 순증 상한 {won(p['expected_won'])}" if not pd.isna(p['expected_won']) else ""
        items.append({'trank': 0, 'amt': p['priority_score'],
                      'action': f"{p['source']} 과집행 차단 후 회수분을 {p['target']}에 재배분",
                      'basis': f"초과지출 {won(p['amount_won'])}{exp} · 상세: 예산 재배분 기획안",
                      'owner': '마케팅 리드', 'when': '즉시'})

    loss = ranked.get('loss')
    if loss is not None and not loss.empty:   # 데이터 정정 — 수치 신뢰도, 왜곡 금액 큰 순
        for _, r in loss[loss['lever'] == '데이터·트래킹'].iterrows():
            items.append({'trank': 1, 'amt': r['impact_won'],
                          'action': f"{r['channel']} {r['type']} 원본 재확인·보정",
                          'basis': f"왜곡·추정 {won(r['impact_won'])} (예산 손실 아님)",
                          'owner': '트래킹팀', 'when': '이번 주'})

    b = ranked.get('benchmark')
    covered = set(plans['target']) if not plans.empty else set()
    if b is not None and not b.empty:   # 벤치마크 방향 — 증액 후보(미커버)·개선 우선만 (유지는 제외)
        for _, r in b.iterrows():
            if r['direction'] == '증액 후보' and r['channel'] not in covered:
                items.append({'trank': 2, 'amt': 0,
                              'action': f"{r['channel']} 증액 검토",
                              'basis': str(r['action']), 'owner': '마케팅 리드', 'when': '이번 주'})
            elif r['direction'] == '개선 우선':
                items.append({'trank': 4, 'amt': 0,
                              'action': f"{r['channel']} 효율 개선 (증액 보류)",
                              'basis': str(r['action']), 'owner': '채널 담당', 'when': '이번 달'})

    op = ranked.get('operational')
    if op is not None and not op.empty:   # 운영 관찰 — 의도 여부 확인
        for _, r in op.iterrows():
            items.append({'trank': 3, 'amt': 0,
                          'action': f"{r['channel']} {r['type']} 의도 여부 담당자 확인",
                          'basis': f"{r['week']} 발생 · 의도적 조정인지 불명",
                          'owner': '채널 담당', 'when': '이번 주'})

    pos = ranked.get('positive')
    if pos is not None and not pos.empty:   # 긍정 신호 — 성공요인 분석·확대
        for _, r in pos.iterrows():
            items.append({'trank': 5, 'amt': 0,
                          'action': f"{r['channel']} 성공요인 분석 후 확대 검토",
                          'basis': f"{r['week']} 성과 호재", 'owner': '마케팅 리드', 'when': '이번 달'})

    when_rank = {'즉시': 0, '이번 주': 1, '이번 달': 2}
    items.sort(key=lambda x: (when_rank[x['when']], x['trank'], -x['amt']))
    for i, it in enumerate(items, 1):
        it['rank'] = i
    return items


def build_weekly_channel_trend(d):
    """주차별 채널 ROAS 추이 + 자동 인사이트 — md·html 공유.

    입력: run_pipeline 결과(weekly_roas 매트릭스). 출력: dict{matrix, weeks, paid, leaders, insights}.
    합산 순위(3번 섹션)가 못 보는 '주차 간 효율 역전·최근 상승/하락'을 규칙으로 문장화해 예산 타이밍 근거를 만든다.
    임계값: 창 후반 평균이 전반 대비 ±15% 이상이면 상승/하락 추세로 판정(노이즈 한 주에 흔들리지 않게 절반 평균 비교).
    """
    mat = d['weekly_roas']
    weeks = list(mat.index)
    paid = [c for c in mat.columns if mat[c].notna().any()]   # ROAS 측정가능(유료) 채널만
    leaders = {w: (mat.loc[w, paid].dropna().idxmax() if mat.loc[w, paid].notna().any() else None)
               for w in weeks}
    insights = []
    has_signal = False   # 리더 교체·뚜렷한 상승/하락 추세가 하나라도 있어야 표를 펼쳐 보일 값이 있다고 판단.
    lead_seq = [leaders[w] for w in weeks if leaders[w]]
    if lead_seq and len(set(lead_seq)) == 1:
        lead = lead_seq[0]
        insights.append(f"{lead}{_josa(lead, '이', '가')} 최근 {len(weeks)}주 내내 ROAS 1위를 유지했습니다 — 검증된 최상위 효율 채널.")
    elif lead_seq:
        for i in range(len(weeks) - 1, 0, -1):   # 가장 최근 리더 교체 지점부터
            a, b = leaders[weeks[i - 1]], leaders[weeks[i]]
            if a and b and a != b:
                insights.append(f"{weeks[i]}에 {b}{_josa(b, '이', '가')} {a}{_josa(a, '을', '를')} 제치고 "
                                "ROAS 1위로 올라섰습니다 — 최근 효율 역전.")
                has_signal = True
                break
    if len(weeks) >= 4:   # 창 전반/후반 평균 비교로 추세 판정
        half = len(weeks) // 2
        early, recent = weeks[:half], weeks[half:]
        for c in paid:
            e, r = mat.loc[early, c].mean(), mat.loc[recent, c].mean()
            if pd.isna(e) or pd.isna(r) or e == 0:
                continue
            chg = (r - e) / e * 100
            if chg >= 15:
                insights.append(f"{c} ROAS가 창 후반 평균 {chg:+.0f}% 상승 추세 — 증액 여력 점검 대상.")
                has_signal = True
            elif chg <= -15:
                insights.append(f"{c} ROAS가 창 후반 평균 {chg:+.0f}% 하락 — 소재·타겟 점검 필요.")
                has_signal = True
    if not insights:
        insights.append("최근 창에서 채널 간 효율 순위·추세에 뚜렷한 변화가 없습니다 — 현 배분 유지.")
    return {'matrix': mat, 'weeks': weeks, 'paid': paid, 'leaders': leaders, 'insights': insights,
            'has_signal': has_signal}


def _weekly_trend_md(d):
    """주차별 채널 ROAS 추이 렌더 — 리더 교체·상승/하락 추세가 있을 때만 표를 펼치고, 없으면 한 줄 요약만.

    표(주×채널 매트릭스)는 '변화 없음' 판정일 땐 정보량이 한 줄 인사이트에 못 미치는데도 자리를 크게 차지해,
    독자가 스캔할 정보가 늘어나기만 하고 판단에 쓸 신호는 없다 — 신호가 있을 때만 상세를 보여준다.
    """
    t = build_weekly_channel_trend(d)
    mat, weeks, paid, leaders = t['matrix'], t['weeks'], t['paid'], t['leaders']
    lines = ["> 합산 ROI 순위(3번)는 '누가 8주 통틀어 효율적'까지만 답한다. 여기서는 **주차별 ROAS**로 "
             "'어느 주에 누가 1위였고 순위가 언제 뒤바뀌었나'를 봐 예산 이동 **타이밍** 근거를 잡는다. "
             "오가닉은 ROAS 측정불가라 제외.\n"]
    if not t['has_signal']:
        lines.append(f"**추이 인사이트**: {t['insights'][0]} (주차별 표는 리더 교체·뚜렷한 추세가 있을 때만 표시)\n")
        return "\n".join(lines) + "\n"
    lines += ["각 주 1위는 **굵게**.\n",
              "| 주차 | " + " | ".join(paid) + " | 1위 |",
              "|------|" + "|".join(["------"] * (len(paid) + 1)) + "|"]
    for w in weeks:
        cells = []
        for c in paid:
            v = mat.loc[w, c]
            cell = "–" if pd.isna(v) else (f"**{v:.2f}**" if leaders[w] == c else f"{v:.2f}")
            cells.append(cell)
        lines.append(f"| {w} | " + " | ".join(cells) + f" | {leaders[w] or '–'} |")
    lines.append("\n**추이 인사이트**\n")
    for s in t['insights']:
        lines.append(f"- {s}")
    return "\n".join(lines) + "\n"


def _playbook_md(d):
    """'이번 주 업무 우선순위' 표 — 표의 할 일·근거 컬럼이 이미 각 항목의 실행 맥락을 담고 있어,
    별도 실행 단계 하위 목록은 두지 않는다(같은 내용을 두 형태로 중복 표기하지 않음).
    """
    items = build_playbook(d)
    head = ["> 아래 '핵심 이슈' 섹션의 근거를 **우선순위·담당·시점**으로 재구성했습니다. 이 표만으로 이번 주 팀 업무 분배가 됩니다. "
            "(담당은 역할 예시 — 조직의 실제 담당자로 대체, 각 근거의 상세는 '핵심 이슈' 섹션 참조)\n"]
    if not items:
        return "\n".join(head) + "\n이번 주 특별히 실행할 조치가 탐지되지 않았습니다 — 현 운영을 유지하세요.\n"
    rows = ["| 순위 | 할 일 | 근거 | 담당 | 시점 |", "|------|------|------|------|------|"]
    for it in items:
        rows.append(f"| {it['rank']} | {it['action']} | {it['basis']} | {it['owner']} | {it['when']} |")
    out = "\n".join(head + rows) + "\n"
    return out


def _executive_summary(d):
    """리포트 최상단 요약 박스 md (갭1) — 경영진 요약본(핵심 요약)과 같은 구조로 성과·위험·예산 결정을 압축 전달.

    부연 설명 문구는 빼고 지표 정의(perf_def_note_md)만 항목 위에 둔다 — exec_report의 '핵심 요약'과 동일 구성.
    금액은 이 박스에서만 억/만원으로 축약(won_compact)하고, 아래 상세 섹션(핵심 수치 요약·이슈 등)은
    정확한 원 단위(won)를 그대로 써 '한눈에 파악'과 '정확한 근거'를 구역별로 분리한다.
    """
    lines = ["## 핵심 요약\n", perf_def_note_md() + "\n"]
    for label, body, note in build_summary_points(d):
        lines.append(f"- **{label}**: {compact_won_text(body)}")
        if note:
            lines.append(f"  > *{note}*")
    lines.append("")
    return "\n".join(lines)


def _decisions(threshold):
    # 방법론(데이터와 무관하게 고정)만 기술 — 특정 수치·날짜는 데이터마다 달라지므로 넣지 않음.
    # 임계값은 데이터 적응형이라 이번 기간 산출값을 표기(고정 상수 아님).
    return ("상세 근거·이력은 decisions.md 참조. 적용한 방법론:\n"
            "- 결측: NaN 유지(0으로 채우지 않음), 집계 자동 제외\n"
            "- 매출 이상치: 채널별 AOV modified z-score>3.5로 동적 탐지 → revenue만 제외(정상 지출·전환 보존)\n"
            "- 완전 중복 행: drop_duplicates로 제거(집계 부풀림 방지)\n"
            "- 전체 ROI: MER(오가닉 포함)·유료 순효율·오가닉 매출 3종 분리 표기\n"
            f"- 이슈 탐지: LOO 중앙값 기준선 + 데이터 적응형 임계값(Tukey IQR 펜스, 하한 25%) "
            f"— 이번 기간 {threshold*100:.0f}% + 원(₩) 임팩트 정렬. 과집행은 'ROAS 하락' 조건\n"
            "- 채널 평가: 내부 순위가 아닌 industry-news 벤치마크 대비 정성 판정\n")


def _reallocation_section_md(d):
    """예산 재배분 기획안을 insight_report(마케팅팀) 안에 흡수 — reallocate.py 빌딩블록 재사용.

    별도 파일이 아니라 진단과 한 문서에 두어, 마케팅팀이 '무슨 일이 있었나 → 무엇을 할까'를 이어서 본다.
    재원(과집행 회수분)·수혜처가 없으면 그 사실을 명시하고 안전하게 종료(빈 데이터에도 문장 성립).
    """
    funding, plans = d['funding'], d['plans']
    lines = ["> 위 진단의 **처방** — 예산으로 무엇을 할지. 재원은 광고비 과집행 회수분만 쓰고, "
             "데이터 오류(이상치·결측)는 예산으로 못 고치므로 제외한다. "
             "실행 체크리스트는 '이번 주 업무 우선순위'(1순위 상세)로 통합했다.\n"]
    if funding.empty:
        lines.append("재원(광고비 과집행)이 탐지되지 않아 예산 이동 없이 현 배분을 유지합니다.\n")
        return "\n".join(lines)
    lines += ["**재원 요약 (어디서 얼마를 회수하나)**\n",
              "| 재원 채널 | 회수가능액 | 기회손실(임팩트) | 빈도 | 발생 |",
              "|-----------|-----------|-----------------|------|------|"]
    for _, f in funding.iterrows():
        lines.append(f"| {f['channel']} | {won(f['recoverable_won'])} | {won(f['impact_won'])} | "
                     f"{f['frequency']}주 | {f['weeks']} |")
    lines.append("\n> 회수가능액(옮길 돈)은 실지출이라 확실하고, 기회손실(임팩트)은 '평소 효율이었다면' 추정치다.\n")
    if plans.empty:
        lines.append("재원은 있으나 증액 여력이 검증된 수혜처가 없어 재원을 유보하고 채널 효율 개선을 우선합니다.\n")
        return "\n".join(lines)
    lines.append("**재배분안 (우선순위 순)**\n")
    for _, r in plans.iterrows():
        lines.append(_plan_block(r))
    lines.append("**우선순위, 이렇게 정했습니다 (판단 기준)**\n")
    for i, (title, body) in enumerate(PRIORITY_CRITERIA, 1):
        lines.append(f"{i}. **{title}** — {body}")
    lines.append(f"\n**한계(정직한 고지)**: {PRIORITY_CAVEAT}\n")
    return "\n".join(lines)


def _exec_momentum_md(d):
    """경영진용 최근 2주 모멘텀 — 전체 매출·지출 변화 한 줄 + 채널 인사이트(예산 방향)."""
    wow = d['wow']
    prev, curr = wow.columns[0], wow.columns[1]
    max_abs = wow['change_pct'].abs().max()
    verdict = "안정적, 급변 없음" if max_abs < 50 else "급변 발생 — 원인 확인 필요"
    lines = [f"- 매출 {wow.loc['revenue', 'change_pct']:+.1f}%, 지출 {wow.loc['spend', 'change_pct']:+.1f}% "
             f"({prev}→{curr}) — {verdict}."]
    for s in build_wow_channel_insight(d):
        lines.append(f"- {s}")
    return "\n".join(lines) + "\n"


def _exec_issues_md(d):
    """경영진용 핵심 이슈 — 예산·매출 직결(데이터·트래킹 레버 제외)만. 데이터 정정은 마케팅팀 리포트로 위임."""
    loss = d['ranked'].get('loss')
    head = ("> 예산·매출에 직결되는 이슈만 싣습니다. 데이터 정정 사안(이상치·결측)은 마케팅팀 상세 리포트에서 처리·수집팀 요청합니다.\n"
            "> 이 이슈·재배분은 이상 탐지에 기준선이 필요해 **최근 8주 누적**으로 판단합니다(성과 헤드라인만 최근 2주).\n")
    act = None if loss is None or loss.empty else loss[loss['lever'] != '데이터·트래킹']
    if act is None or act.empty:
        return head + "\n현재 예산·매출 직결 손실 이슈 없음.\n"
    lines = [head]
    for i, (_, r) in enumerate(act.iterrows(), 1):
        lines.append(f"{i}. **{r['channel']} {r['type']}** — 기회손실 {won(r['impact_won'])} ({r['weeks']}), 예산 재배분으로 대응.")
    return "\n".join(lines) + "\n"


def _exec_budget_md(d):
    """경영진용 예산 재배분 '결정 요약' — 승인 대상만. 실행 상세는 마케팅팀 리포트로.

    항목별 나열(결정/근거/실행방식/승인) 대신 승인권자가 읽는 한 문단의 서술형으로 잇는다 —
    경영진 요약본은 '읽고 판단'하는 문서라 표(라벨-값) 형식보다 문장으로 흐르는 게 자연스럽다.
    """
    plans = d['plans']
    if plans.empty:
        return "재배분 재원(광고비 과집행 회수분)이 탐지되지 않아 현 예산 배분을 유지할 것을 권고합니다.\n"
    p = plans.iloc[0]
    exp = (f" 선형확장을 가정하면 이번 재배분으로 기대되는 순증 매출 상한은 약 {won(p['expected_won'])}입니다."
           if not pd.isna(p['expected_won']) else "")
    return (
        f"{p['source']} 예산 과집행으로 발생한 회수 가능분 {won(p['amount_won'])}을(를) 시장 벤치마크 우수 채널 "
        f"{p['target']}로 재배분(1순위)하는 안을 승인 요청합니다. {p['source']} 과집행 회수분을 효율이 검증된 "
        f"{p['target']}에 재투입한다는 것이 근거입니다.{exp} 실행은 소액 테스트로 시작해 2주 후 ROAS를 재측정하고, "
        "개선이 확인되면 확대하는 방식으로 진행하며(상세 실행안·우선순위 로직은 마케팅팀 리포트 참조), "
        "위 재배분안의 집행 승인을 요청합니다.\n"
    )


def _exec_channel_compare_md(d):
    """예산 재배분에 관련된 2개 채널(재원·수혜처)만 효율을 비교 — 전체 채널 순위표 대신 최소 근거만 노출.

    경영진 요약본은 전체 채널 상세 진단을 마케팅팀 리포트로 위임하는 설계(Step 27)를 유지한다.
    다만 "왜 이 두 채널 사이의 재배분인지"를 경영진이 직접 검증할 수 있어야 하므로, 이번 결정에
    관련된 재원 채널(회수처)·수혜 채널(투입처) 딱 둘만 광고비·매출·ROAS로 비교해 보여준다.
    plans가 없으면(재원 없음) 비교할 결정 자체가 없으므로 None을 반환해 섹션을 생략한다.
    """
    plans = d['plans']
    if plans.empty:
        return None
    p = plans.iloc[0]
    g = d['summary']['by_channel']
    rows = ["| 채널 | 역할 | 광고비 | 매출 | ROAS |", "|------|------|--------|------|------|"]
    for ch, role in [(p['source'], '재원 (과집행 회수처)'), (p['target'], '수혜 (재배분 투입처)')]:
        r = g.loc[ch]
        roas = "측정불가" if pd.isna(r['ROAS']) else f"{r['ROAS']:.2f}"
        rows.append(f"| {ch} | {role} | {won(r['spend'])} | {won(r['revenue'])} | {roas} |")
    return ("> 이번 재배분 결정에 관련된 두 채널만 비교합니다. 전체 채널 효율은 마케팅팀 리포트를 참조하세요.\n\n"
            + "\n".join(rows) + "\n")


def build_exec_report(data_path=DATA, data=None):
    """경영진 요약본(exec_report.md) — 계산은 마케팅팀 리포트와 동일한 run_pipeline 결과를 공유.

    경영진이 승인권자임을 전제로 '성과·위험·예산 결정'만 요약 고도로 싣는다.
    채널 진단·데이터 정정 등 실행 상세는 insight_report(마케팅팀)로 위임한다.
    """
    d = data or run_pipeline(data_path)
    prev, curr, t2 = exec_perf_2w(d)
    # 경영진 요약에서는 데이터 정정(예산 조치 아님)은 노이즈라 제외 — 마케팅팀 리포트가 전담.
    # 성과 헤드라인만 최근 2주로 교체하고, 이슈·예산 항목은 8주 기준선 판단을 그대로 싣는다.
    perf = (f"최근 2주 성과 ({prev}→{curr})", _perf_body(t2))
    summary_lines = []
    for label, body, note in build_summary_points(d, perf=perf):
        if label.startswith('데이터 정정'):
            continue
        summary_lines.append(f"- **{label}**: {body}")
        if note:
            summary_lines.append(f"  > *{note}*")
    summary = "\n".join(summary_lines)
    parts = [
        "# 마케팅 성과 경영진 요약 리포트\n",
        f"> ## 📌 최근 2주({prev}→{curr}) 전주 대비 기준\n"
        f"> 성과 수치는 **최근 2주 합계**입니다. 경영진 판단에 필요한 '지금'만 담았고, "
        f"8주 전체 상세는 마케팅팀 리포트(insight_report)를 참조하세요.\n",
        f"> **대상: 경영진** · 주간 · **분석 기준: 최근 2주 ({prev}→{curr}) 전주 대비**\n>\n"
        "> 이 한 장으로 '얼마 써서 얼마 벌었나 · 지금 위험 · 다음 예산 결정'을 판단합니다. "
        "채널 진단·데이터 정정 등 실행 상세는 마케팅팀 리포트(insight_report)에 있습니다.\n",
        "## 한눈에 보기\n\n" + perf_def_note_md() + "\n\n" + summary + "\n",
        "## 최근 2주 모멘텀\n\n" + roas_def_note_md() + "\n\n" + _exec_momentum_md(d),
        "## 핵심 이슈 (예산·매출 직결)\n\n" + _exec_issues_md(d),
        "## 예산 재배분 결정 (승인 요청)\n\n" + _exec_budget_md(d),
    ]
    compare = _exec_channel_compare_md(d)
    if compare:
        parts.append("## 관련 채널 효율 비교 (참고)\n\n" + compare)
    return "\n---\n\n".join(parts).replace('~', '–')


def build_report(data_path=DATA, data=None):
    """insight_report.md를 생성한다. data(run_pipeline 결과)를 받으면 재사용, 없으면 직접 실행.

    html 생성기와 같은 결과를 공유하도록 data 주입을 허용 — 수치가 md·html 간 어긋나지 않게.
    """
    d = data or run_pipeline(data_path)
    s, ranked, wow = d['summary'], d['ranked'], d['wow']
    prev, curr = wow.columns[0], wow.columns[1]
    # 섹션은 (제목, 본문) 리스트로 모아 순서대로 렌더한다. 목차·번호는 두지 않는다(단순한 순차 읽기 문서로 유지).
    # 성격이 비슷한 옛 섹션들은 하나로 묶어둔다 — ①데이터 개요+핵심 수치 요약(모두 '분석 대상·전체 숫자' 배경 정보)
    # ②ROI 순위+시장 벤치마크+오가닉(모두 '채널을 어떻게 평가하나')을 하위 소제목(###)으로 통합.
    # 전주 대비 변화율+주차별 ROAS추이도 '시간에 따른 변화'라는 같은 질문이라 '추세'로 묶는다.
    # 이슈·예산 재배분·의사결정 로그는 각자 고유한 목적(문제·처방·방법론)이라 병합하지 않는다.
    # 순서: 개요(무엇) → 채널평가(누가 잘·못하나, 전체 그림) → 추세(평소 패턴이 어떻게 흘러왔나)
    # → 이슈(그 패턴에서 벗어난 구체적 문제) → 예산 재배분(문제에 대한 처방, 이슈 바로 다음 유지)
    # → 의사결정 로그(방법론, 부록 성격이라 항상 마지막). 채널평가·추세를 이슈보다 앞에 둬
    # 독자가 배경 지식 없이 구체적 사건부터 마주치지 않게 한다.
    overview_summary = ("### 데이터 개요\n\n" + _overview(d['meta']) +
                        "\n\n### 핵심 수치 요약\n\n" + _summary(s))
    channel_eval = ("### ROI 순위 (내부 비교 — 채널 간 상대 효율)\n\n" + _roi_rank(d['roi']) +
                    "\n\n### 시장 벤치마크 등급 (외부 비교 — 업계 대비 위치)\n\n" + _benchmark(ranked))
    if 'opportunity' in ranked:   # 유의미한 오가닉이 있을 때만 하위 소제목으로 포함 (없으면 생략)
        channel_eval += "\n\n### 오가닉 성장 잠재력\n\n" + _opportunity(ranked)
    trend = (f"### 전주 대비 변화율 ({prev} → {curr})\n\n" + _wow(wow) + _wow_channel_md(d) +
             "\n\n### 주차별 채널 효율 추이 (ROAS)\n\n" + _weekly_trend_md(d))
    sections = [
        ("데이터 개요 및 핵심 수치 요약", overview_summary),
        ("채널 효율 평가 (ROI · 시장 벤치마크 · 오가닉)", channel_eval),
        ("추세 (전주 대비 · 주차별 ROAS)", trend),
        ("이슈 (비즈니스 임팩트 순)", _issues(ranked, d['recency'], d['threshold'])),
        ("예산 재배분 기획안 (처방)", _reallocation_section_md(d)),
        ("의사결정 로그 요약", _decisions(d['threshold'])),
    ]

    parts = ["# 마케팅 성과 인사이트 리포트 (마케팅팀 상세본)\n",
             "> **대상 독자: 마케팅팀** · 주기: 주간 · 경영진 요약본은 exec_report 참조\n>\n"
             "> 계산: Python (calculate.py) · 이슈 탐지: detect_issues.py · 해석: 규칙 기반 + Claude\n",
             _executive_summary(d),
             "## 🎯 이번 주 업무 우선순위\n\n" + _playbook_md(d)]
    for title, body in sections:
        parts.append(f'## {title}\n\n{body}')
    report = "\n---\n\n".join(parts)
    # 물결표(~)는 마크다운에서 쌍으로 만나면 취소선(~~)이 되어 글자가 지워져 보인다.
    # 본 리포트의 ~는 모두 범위 표기(W1~W8, 날짜)이므로 엔대시로 치환해 취소선 오작동을 원천 차단.
    return report.replace('~', '–')


if __name__ == '__main__':
    # 사용법: python3 src/generate_report.py [입력CSV] [출력MD]  (인자 생략 시 기본 샘플·경로)
    # 한 번의 계산(run_pipeline)으로 마케팅팀 상세본·경영진 요약본 두 md를 함께 생성 — 수치 공유.
    data_path = sys.argv[1] if len(sys.argv) > 1 else DATA
    out_path = sys.argv[2] if len(sys.argv) > 2 else OUT
    d = run_pipeline(data_path)
    report = build_report(data=d)
    with open(out_path, 'w') as f:
        f.write(report)
    print(f"생성 완료: {out_path} ({len(report):,}자) ← 입력: {data_path}")
    exec_report = build_exec_report(data=d)
    with open(EXEC_OUT, 'w') as f:
        f.write(exec_report)
    print(f"생성 완료: {EXEC_OUT} ({len(exec_report):,}자) ← 경영진 요약본")
