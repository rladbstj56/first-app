"""규칙 기반 이슈 탐지 — 하드코딩 없이 어떤 성과 CSV에도 동작.

각 탐지기는 공통 스키마의 이슈 행(dict) 리스트를 반환하고, score_and_rank가
category별로 갈라 손실 이슈는 원(₩) 임팩트 누적으로 정렬한다.
설계 근거는 decisions.md Step 8~9 참조.
"""
import numpy as np
import pandas as pd

from calculate import load_and_clean, find_revenue_outliers, _week_key

METRICS = ['spend', 'revenue', 'conversions']

# industry-news.md 채널별 시장 벤치마크 (하위25%, 평균, 상위25%). 업계 통용 추정치 → 정성 평가용.
BENCHMARKS = {
    '네이버광고': {'CTR': (2.1, 4.5, 8.2), 'CVR': (1.2, 3.1, 6.8), 'ROAS': (1.8, 3.2, 6.5)},
    '메타광고':  {'CTR': (0.3, 1.1, 2.4), 'CVR': (0.8, 2.3, 5.0), 'ROAS': (1.2, 2.4, 4.8)},
    '카카오광고': {'CTR': (0.8, 1.9, 3.5), 'CVR': (0.5, 1.8, 4.2), 'ROAS': (1.5, 2.8, 5.1)},
    '오가닉':    {'CTR': (3.0, 6.5, 11.0), 'CVR': (1.5, 3.2, 6.5), 'ROAS': None},
    '이메일':    {'CTR': (1.5, 3.2, 7.8), 'CVR': (2.1, 5.4, 11.2), 'ROAS': (8.0, 18.5, 42.0)},
}


def _band(value, bench):
    """실측치가 벤치마크 (하위25%, 평균, 상위25%) 구간 중 어디인지 정성 등급으로 반환."""
    if bench is None or pd.isna(value):
        return '측정불가'
    lo, avg, hi = bench
    if value >= hi:
        return '상위25% 이상(우수)'
    if value >= avg:
        return '평균 이상'
    if value >= lo:
        return '평균 이하(개선여지)'
    return '하위25% 이하(미흡)'


def _loo_median(series_by_week, week):
    """해당 주차를 제외한 나머지 주차들의 중앙값(leave-one-out median).

    이상치 1건이 기준선 자체를 오염시키지 않도록(robust) 평균이 아닌 중앙값을 쓴다.
    """
    return series_by_week.drop(week).median()


def _lever(itype):
    """이슈 유형의 성격 → 조치 레버. 특정 지표명이 아니라 '문제의 종류'로 귀속.

    결측·이상치는 어느 지표(매출·노출·클릭 등)에서 나든 수집/기록 오류 → 데이터·트래킹.
    광고비 변동은 지출 의사결정 → 예산, 성과(매출·전환) 변동은 전환 최적화 → 운영·크리에이티브.
    예산 재배분(reallocate)은 lever=='예산'인 손실만 재원으로 써 데이터 오류를 재원에서 자동 배제한다.
    """
    if '결측' in itype or '이상치' in itype:
        return '데이터·트래킹'
    if '광고비' in itype:
        return '예산'
    if '성과' in itype:
        return '운영·크리에이티브'
    return '전략'  # 채널평가·오가닉 기회 등 진단·전략성 이슈


def _issue(channel, week, itype, category, metric, baseline, actual, impact, note, recoverable=np.nan,
           phenomenon=None, evidence=None):
    """공통 이슈 스키마 dict 생성 — 모든 탐지기가 이 형태로 반환한다.

    recoverable: 예산 재배분으로 회수 가능한 실지출액(원). 과집행만 초과지출액을 넣고
    나머지는 NaN. impact_won(놓친 매출·추정치)과 구분 — 옮기는 돈은 recoverable, 우선순위 크기는 impact.
    phenomenon/evidence: note를 마케팅팀 리포트용으로 두 문장으로 풀어 쓴 설명 — '무슨 일이 있었나(현상)'와
    '왜 그렇게 보나·다음에 뭘 확인해야 하나(근거)'를 분리해 각각 별도 줄로 렌더한다(합쳐서 한 문단으로 두면
    현상과 판단 근거가 섞여 읽기 어려움). 없으면 note를 현상으로, 근거는 빈 문자열로 채운다.
    문장은 명사형으로 종결(예: '급증', '추정') — '~습니다'체는 쓰지 않는다.
    """
    dev = (actual - baseline) / baseline if baseline not in (0, None) and not pd.isna(baseline) else np.nan
    return {
        'channel': channel, 'week': week, 'type': itype, 'category': category,
        'lever': _lever(itype),
        'metric': metric, 'baseline': baseline, 'actual': actual,
        'dev_pct': dev * 100 if not pd.isna(dev) else np.nan,
        'impact_won': impact, 'recoverable_won': recoverable, 'note': note,
        'phenomenon': phenomenon if phenomenon is not None else note,
        'evidence': evidence if evidence is not None else "",
    }


def compute_adaptive_threshold(df, iqr_mult=1.5, floor=0.25):
    """급등/급락 임계값을 데이터에서 자동 산출한다 (고정 상수 대체). (decisions Step 22)

    왜: 고정 35%는 이 데이터셋 하나의 편차 분포에서 노이즈/이벤트 사이 빈 구간을 눈으로 보고 정한
    값이라 '한 데이터에 과적합' 공격에 취약했다. 대신 데이터와 무관한 통계 관례(Tukey 이상치 펜스)로
    임계값을 매번 자동 계산 → 새 CSV마다 재보정된다. 특정 숫자를 고르지 않으므로 그 공격이 소멸한다.

    로직: 모든 채널×주차×지표의 LOO 중앙값 대비 |편차율| 분포에서 Tukey 상단 펜스(Q3 + iqr_mult×IQR)를
    이상치 경계로 쓴다. IQR·펜스는 이상치에 강건하고 분포 대칭 가정이 없어(편차 절대값은 우측 왜곡)
    이 데이터에 맞다. iqr_mult=1.5는 이상치 탐지의 보편 관례라 '왜 이 값이냐'를 도메인이 아닌 통계로 답한다.
    단, 완전히 잠잠한 기간엔 펜스가 늘 존재해 사소한 변동까지 이슈로 뱉으므로, 회사 규칙 ±50%
    (company-info)의 절반인 floor로 하한을 둔다 → '통계적으로 튀고 AND 비즈니스적으로도 유의미한 크기'만 이슈.

    입력: 정제된 df. 출력: 임계값(fraction, 예 0.25).
    실측(현재 데이터): 펜스 22.95% < floor 25% → 25% 반환. 노이즈(≤20.50%)와 이벤트(≥36.49%) 사이
    빈 구간에 안착해, 지표 단위 9건(=메타 W5·카카오 W4·이메일 W6 3개 이벤트 × 각 3지표)만 탐지하고 노이즈는 배제.
    """
    devs = []
    for _, sub in df.groupby('channel'):
        wk = sub.groupby('week')[METRICS].sum()
        for week in wk.index:
            for m in METRICS:
                base = _loo_median(wk[m], week)
                if base > 0:
                    devs.append(abs((wk.loc[week, m] - base) / base))
    if not devs:
        return floor
    v = np.array(devs)
    q1, q3 = np.percentile(v, 25), np.percentile(v, 75)
    fence = q3 + iqr_mult * (q3 - q1)
    return max(fence, floor)


def compute_recency(df):
    """각 채널의 '가장 최근 주차' LOO 편차율(%)을 반환 — 과거 탐지된 이슈가 최근에도 지속되는지 판단용.

    왜: 이슈는 대개 과거 주차(예: 메타 W5 과집행)라, 독자가 '지금도 진행 중인가 이미 끝났나'를 알아야
    긴급 대응(지속)과 사후 학습(해소)을 가른다. 각 채널의 마지막 주차 지표를 LOO 중앙값 기준으로
    재계산해 편차를 제공한다. 주차 정렬은 compute_wow_change와 동일 키(W2<W10 보장).
    반환: {channel: {'week': 최근주차, 'spend'/'revenue'/'conversions': 편차율(%)}}
    """
    out = {}
    for ch, sub in df.groupby('channel'):
        wk = sub.groupby('week')[METRICS].sum()
        last = sorted(wk.index, key=lambda w: (len(w), w))[-1]
        rec = {'week': last}
        for m in METRICS:
            base = _loo_median(wk[m], last)
            rec[m] = (wk.loc[last, m] - base) / base * 100 if base > 0 else np.nan
        out[ch] = rec
    return out


def detect_spike_drop(df, threshold=None):
    """채널×주차 단위 급등/급락을 탐지한다.

    threshold를 안 주면 compute_adaptive_threshold(df)로 데이터에서 자동 산출한다(고정 상수 없음).

    유형(우선순위 순, 한 채널×주차당 1개):
    1) 광고비급등(과집행) — 광고비 편차 ≥+임계값 AND ROAS 하락(industry-news 유형A). 손실(₩=기회손실).
       ROAS 하락 조건이 있어 '광고비는 늘었지만 매출도 비례해 는 건강한 확장'(예: 이메일 W6)은 제외됨.
    2) 광고비급락(집행축소) — 광고비 편차 ≤-임계값. 매출 손실이 아니라 '운영 관찰'(₩ 랭킹 제외).
       company-info 손실 정의엔 없으나 과제가 이슈로 라벨(카카오 W4)했고 ±50% 양방향이라 보고는 함.
    3) 성과급락 — 광고비 정상인데 매출/전환 편차 ≤-임계값. 손실(₩=놓친매출).
    4) 성과호재 — 매출/전환 편차 ≥+임계값(과집행 아님). 긍정 신호(별도).

    기준선은 '판정 주차 제외 나머지 주차 중앙값(leave-one-out median)'. company-info 문구는
    '전주 대비(WoW)'이나 WoW는 직전 주가 이상하면 반동 가짜 이슈를 만든다(실측: 카카오 W4 딥 다음
    W5가 +52%로 오탐). 중앙값은 이에 강건. 임계값도 전주 대비용 고정 50%가 아니라 데이터 적응형으로 산출.
    """
    if threshold is None:
        threshold = compute_adaptive_threshold(df)
    issues = []
    for ch, sub in df.groupby('channel'):
        wk = sub.groupby('week')[METRICS].sum()
        for week in wk.index:
            b = {m: _loo_median(wk[m], week) for m in METRICS}
            a = {m: wk.loc[week, m] for m in METRICS}

            base_roas = b['revenue'] / b['spend'] if b['spend'] > 0 else np.nan
            this_roas = a['revenue'] / a['spend'] if a['spend'] > 0 else np.nan
            extra_spend = a['spend'] - b['spend']
            extra_rev = a['revenue'] - b['revenue']

            spend_dev = (a['spend'] - b['spend']) / b['spend'] if b['spend'] > 0 else np.nan
            rev_dev = (a['revenue'] - b['revenue']) / b['revenue'] if b['revenue'] > 0 else np.nan
            conv_dev = (a['conversions'] - b['conversions']) / b['conversions'] if b['conversions'] > 0 else np.nan

            roas_down = not pd.isna(this_roas) and not pd.isna(base_roas) and this_roas < base_roas

            if not pd.isna(spend_dev) and spend_dev >= threshold and roas_down:
                impact = max(0, extra_spend * base_roas - extra_rev)
                note = (f"광고비 {a['spend']:,.0f} vs 기준선 {b['spend']:,.0f}"
                        f"({spend_dev*100:+.2f}%), ROAS {this_roas:.2f} vs 평소 {base_roas:.2f}↓ "
                        f"(초과지출 {extra_spend:,.0f}, 선형확장 가정 상한)")
                phenomenon = (f"{ch} 광고비가 {week}에 {a['spend']:,.0f}원까지 올라 평소 수준"
                             f"({b['spend']:,.0f}원)보다 {spend_dev*100:.0f}% 급증. ROAS도 평소 {base_roas:.2f}에서 "
                             f"{this_roas:.2f}로 하락 — 늘어난 지출이 매출로 이어지지 못하는 상태.")
                evidence = f"평소보다 초과로 집행된 금액은 약 {extra_spend:,.0f}원으로 추정."
                issues.append(_issue(ch, week, '광고비급등(과집행)', 'loss', 'spend', b['spend'], a['spend'],
                                     impact, note, recoverable=extra_spend,
                                     phenomenon=phenomenon, evidence=evidence))

            elif not pd.isna(spend_dev) and spend_dev <= -threshold:
                note = (f"광고비 {a['spend']:,.0f} vs 기준선 {b['spend']:,.0f}({spend_dev*100:+.2f}%) — "
                        f"의도적 감축인지 집행 오류인지 확인 필요(매출 {a['revenue']:,.0f}, ROAS {this_roas:.2f})")
                phenomenon = (f"{ch} 광고비가 {week}에 {a['spend']:,.0f}원으로 평소 수준({b['spend']:,.0f}원)보다 "
                             f"{abs(spend_dev)*100:.0f}% 감소. 매출은 {a['revenue']:,.0f}원(ROAS {this_roas:.2f})으로 "
                             "집행 축소분 대비 큰 타격 없음.")
                evidence = "의도한 감축인지 집행 중단 사고인지 담당자 확인 필요."
                issues.append(_issue(ch, week, '광고비급락(집행축소)', 'operational', 'spend', b['spend'], a['spend'], 0,
                                     note, phenomenon=phenomenon, evidence=evidence))

            elif (not pd.isna(rev_dev) and rev_dev <= -threshold) or (not pd.isna(conv_dev) and conv_dev <= -threshold):
                impact = max(0, b['revenue'] - a['revenue'])
                rev_str = f"{rev_dev*100:+.2f}%" if not pd.isna(rev_dev) else "n/a"
                note = (f"매출 {a['revenue']:,.0f} vs 기준선 {b['revenue']:,.0f}({rev_str}), "
                        f"전환 {a['conversions']:.0f} vs {b['conversions']:.0f}, 광고비 {a['spend']:,.0f}(기준선 {b['spend']:,.0f})")
                phenomenon = (f"{ch}의 매출이 {week}에 {a['revenue']:,.0f}원으로 평소 수준"
                             f"({b['revenue']:,.0f}원)보다 {rev_str} 감소.")
                evidence = (f"광고비는 {a['spend']:,.0f}원으로 평소({b['spend']:,.0f}원)와 차이 없음 — "
                           "지출은 그대로인데 성과만 하락한 것으로 추정.")
                issues.append(_issue(ch, week, '성과급락', 'loss', 'revenue', b['revenue'], a['revenue'], impact, note,
                                     phenomenon=phenomenon, evidence=evidence))

            elif (not pd.isna(rev_dev) and rev_dev >= threshold) or (not pd.isna(conv_dev) and conv_dev >= threshold):
                impact = max(0, extra_rev)
                rev_str = f"{rev_dev*100:+.2f}%" if not pd.isna(rev_dev) else "n/a"
                note = (f"매출 {a['revenue']:,.0f} vs 기준선 {b['revenue']:,.0f}({rev_str}), "
                        f"광고비 {a['spend']:,.0f}(기준선 {b['spend']:,.0f}) — 호재")
                phenomenon = (f"{ch}의 매출이 {week}에 {a['revenue']:,.0f}원으로 평소 수준({b['revenue']:,.0f}원)보다 "
                             f"{rev_str} 증가.")
                evidence = (f"광고비는 {a['spend']:,.0f}원으로 평소({b['spend']:,.0f}원)와 비슷한 수준 — "
                           "지출 증가 없이 성과가 개선된 긍정 신호로 판단.")
                issues.append(_issue(ch, week, '성과호재', 'positive', 'revenue', b['revenue'], a['revenue'], impact,
                                     note, phenomenon=phenomenon, evidence=evidence))

    return issues


def detect_outliers(raw_df):
    """매출 이상치를 이슈로 만든다 (탐지는 calculate.find_revenue_outliers가 담당).

    입력은 이상치가 살아있는 원본(load_and_clean(mask_outlier=False)).
    임팩트 = |원본 revenue − 정상추정(전환 × 채널 중앙 AOV)| = 왜곡 금액.
    """
    issues = []
    for o in find_revenue_outliers(raw_df):
        impact = abs(o['revenue'] - o['est'])
        note = (f"{o['date']} AOV {o['aov']:,.0f} vs 채널 중앙 {o['median_aov']:,.0f}(mz={o['mz']:.2f}), "
                f"원본매출 {o['revenue']:,.0f} vs 정상추정 {o['est']:,.0f}")
        phenomenon = (f"{o['channel']} {o['date']}의 건당 평균 결제액(AOV)이 {o['aov']:,.0f}원으로 이 채널 평소 수준"
                     f"({o['median_aov']:,.0f}원) 대비 비정상적 급등. 이날 매출 {o['revenue']:,.0f}원 기록, "
                     f"평소 패턴 기준 추정치 {o['est']:,.0f}원 대비 부풀려졌을 가능성.")
        evidence = "중복 주문 또는 테스트 결제 혼입 여부 원본 데이터 재확인 필요."
        issues.append(_issue(o['channel'], o['week'], '매출이상치', 'loss', 'aov', o['est'], o['revenue'], impact,
                             note, phenomenon=phenomenon, evidence=evidence))
    return issues


def detect_missing(raw_df):
    """결측 셀을 탐지한다. 원본(이상치 살아있는 df)에서 찾아 진짜 결측만 잡는다.

    revenue 결측 → 손실(임팩트 = 채널 revenue 중앙값으로 추정한 결측 매출).
    impressions/clicks 결측 → 데이터품질(매출 직접 연결 약함, 수집 오류 의심. 임팩트 0).
    """
    metric_label = {'impressions': '노출수', 'clicks': '클릭수'}
    issues = []
    for m in ['revenue', 'impressions', 'clicks']:
        for idx in raw_df[raw_df[m].isna()].index:
            row = raw_df.loc[idx]
            if m == 'revenue':
                est = raw_df[raw_df['channel'] == row['channel']]['revenue'].median()
                phenomenon = (f"{row['date']} {row['channel']}의 매출 데이터 결측(0원이 아니라 기록 누락).")
                evidence = (f"채널 평소 매출 수준({est:,.0f}원)으로 임시 추정해 집계 반영 — "
                           "트래킹 오류 여부 확인 후 실제 값 교체 필요.")
                issues.append(_issue(row['channel'], row['week'], 'revenue결측', 'loss', 'revenue',
                                     est, np.nan, est,
                                     f"{row['date']} {row['channel']} 매출 결측 → 채널 중앙값 {est:,.0f}으로 추정",
                                     phenomenon=phenomenon, evidence=evidence))
            else:
                phenomenon = f"{row['date']} {row['channel']}의 {metric_label[m]} 데이터 결측."
                evidence = ("매출과 직접 연결되는 지표는 아니나 광고 집행 중단 또는 트래킹 코드 오류 가능성 — "
                           "확인 필요.")
                issues.append(_issue(row['channel'], row['week'], f'{m}결측', 'quality', m,
                                     np.nan, np.nan, 0,
                                     f"{row['date']} {row['channel']} {m} 결측 — 집행 중단·트래킹 오류 의심",
                                     phenomenon=phenomenon, evidence=evidence))
    return issues


# 등급 → 표 셀용 축약 라벨 (범례에서 전체 의미를 설명하므로 표는 짧게).
BAND_SHORT = {
    '상위25% 이상(우수)': '우수', '평균 이상': '평균이상',
    '평균 이하(개선여지)': '개선여지', '하위25% 이하(미흡)': '미흡', '측정불가': '측정불가',
}
WEAK_BANDS = ('평균 이하(개선여지)', '하위25% 이하(미흡)')  # 퍼널 약점으로 볼 등급

# 종합 등급(ROAS band) → 예산 방향. 최종 성과 지표인 ROAS로 증액/유지/개선을 가른다.
_DIRECTION = {'상위25% 이상(우수)': '증액 후보', '평균 이상': '유지',
              '평균 이하(개선여지)': '개선 우선', '하위25% 이하(미흡)': '개선 우선',
              '측정불가': '측정불가'}


def _channel_action(direction, ctr_weak, cvr_weak):
    """종합 방향 + 퍼널 약점(CTR/CVR)을 조합해 채널별 제안 문구를 만든다.

    CTR 약함 → 소재·타겟팅, CVR 약함 → 랜딩·오퍼(industry-news 유형 B). 약점이 없는데도
    '개선 우선'이면 원인은 퍼널이 아니라 매출효율(ROAS) 자체이므로 오퍼·객단가 고도화로 안내.
    반환: (약점 요약, 제안 문구).
    """
    weak = []
    if ctr_weak:
        weak.append('CTR(소재·타겟팅)')
    if cvr_weak:
        weak.append('CVR(랜딩·오퍼)')
    weak_str = ', '.join(weak) if weak else '없음'
    if direction == '증액 후보':
        return weak_str, ('증액 1순위' if not weak else f'증액 1순위 + {weak_str} 개선 시 추가 상승')
    if direction == '유지':
        return weak_str, ('현상 유지' if not weak else f'현상 유지 + {weak_str} 보강')
    if direction == '개선 우선':
        fix = weak_str if weak else '매출효율(ROAS): 오퍼·객단가·세그먼트 고도화'
        return weak_str, f'시장 대비 미달 → {fix} 개선 우선, 증액 보류'
    return weak_str, '증액 대상 아님(오가닉 성장 잠재력 섹션 참조)'


def evaluate_channels(by_channel):
    """각 채널의 CTR/CVR/ROAS를 industry-news.md 시장 벤치마크와 비교해 등급·방향·제안을 만든다.

    입력: compute_summary(df)['by_channel'] DataFrame.
    반환: category='benchmark' 행들. 지표별 실측치·등급(band)·예산 방향(direction)·제안(action)을
    구조화 필드로 담아 리포트가 표·인사이트를 조립하게 한다. 반사실 금액 추정 없음(정성).
    등급은 '우리 회사 주차 비교'가 아니라 '같은 채널 업계 분포' 대비 위치임(원 임팩트 랭킹엔 미사용).
    """
    issues = []
    for ch, b in BENCHMARKS.items():
        if ch not in by_channel.index:
            continue
        r = by_channel.loc[ch]
        roas = r['ROAS'] if 'ROAS' in r else np.nan
        ctr_band, cvr_band = _band(r['CTR'], b['CTR']), _band(r['CVR'], b['CVR'])
        roas_band = _band(roas, b['ROAS'])
        direction = _DIRECTION[roas_band]
        weak_str, action = _channel_action(direction, ctr_band in WEAK_BANDS, cvr_band in WEAK_BANDS)
        note = (f"CTR {r['CTR']:.2f}%→{ctr_band}, CVR {r['CVR']:.2f}%→{cvr_band}, "
                + (f"ROAS {roas:.2f}→{roas_band}" if pd.notna(roas) else "ROAS 측정불가"))
        d = _issue(ch, '전체', '채널평가', 'benchmark', 'ROAS', np.nan,
                   roas if pd.notna(roas) else np.nan, np.nan, note)
        d.update({'CTR': r['CTR'], 'CVR': r['CVR'], 'ROAS': roas,
                  'ctr_band': ctr_band, 'cvr_band': cvr_band, 'roas_band': roas_band,
                  'direction': direction, 'weak': weak_str, 'action': action})
        issues.append(d)
    return issues


def detect_opportunity(by_channel, total_revenue, min_share=0.10):
    """광고비 0인데 매출 비중이 유의미한 채널(오가닉)을 성장 잠재력으로 잡는다.

    손실이 아니라 미활용 자산이므로 원 임팩트 랭킹과 분리(category='opportunity').
    매출 비중이 min_share(기본 10%) 미만이면 '기회'로 볼 규모가 아니라 제외 —
    새 CSV에서 미미한 오가닉이 매번 기회로 뜨는 노이즈를 막는다.
    """
    issues = []
    for ch in by_channel.index:
        r = by_channel.loc[ch]
        share = r['revenue'] / total_revenue if total_revenue > 0 else 0
        if r['spend'] == 0 and r['revenue'] > 0 and share >= min_share:
            note = f"광고비 직접지출 0(무료 아님 — 과거 유료광고 낙수효과·SEO 누적 결과), 매출 {r['revenue']:,.0f}(전체 {share*100:.2f}%), CVR {r['CVR']:.2f}%"
            phenomenon = (f"{ch}은 광고비를 한 푼도 쓰지 않았는데도 매출 {r['revenue']:,.0f}원을 만들어내며, "
                          f"전체 매출의 {share*100:.1f}%를 차지. 전환율(CVR)도 {r['CVR']:.2f}%로 측정되어 "
                          "유입된 방문이 실제 구매로 잘 이어지고 있음.")
            evidence = ("작지 않은 비중은 과거 유료광고의 낙수효과와 SEO·콘텐츠 누적이 이미 큰 자산으로 작동하고 "
                        "있다는 뜻 — 이 채널은 광고비 배정이 아니라 SEO·콘텐츠 투자로 키우는 채널이라, 투자를 "
                        "강화하면 광고비를 늘리지 않고도 매출을 더 키울 여력이 있음.")
            issues.append(_issue(ch, '전체', '오가닉 성장 잠재력', 'opportunity', 'revenue',
                                 np.nan, r['revenue'], r['revenue'], note,
                                 phenomenon=phenomenon, evidence=evidence))
    return issues


def score_and_rank(all_issues):
    """모든 이슈를 category별로 나누고, 손실(loss)은 (채널,유형) 누적 임팩트로 정렬한다.

    빈도(발생 주차 수)는 곱하지 않고 병기(1회성 vs 구조적 구분용).
    반환: dict {loss: DataFrame(정렬), positive/quality/benchmark/opportunity: DataFrame}
    """
    df = pd.DataFrame(all_issues)
    out = {}
    if df.empty:
        return out
    loss = df[df['category'] == 'loss']
    if not loss.empty:
        agg = loss.groupby(['channel', 'type']).agg(
            lever=('lever', 'first'),
            impact_won=('impact_won', 'sum'),
            recoverable_won=('recoverable_won', 'sum'),
            frequency=('week', 'nunique'),
            # 같은 주에 여러 날 잡히는 이상치는 주차가 중복되므로 dedup + W2<W10 정렬(표시용).
            weeks=('week', lambda s: ','.join(sorted(set(s), key=lambda w: (len(str(w)), str(w))))),
            note=('note', 'first'),
            phenomenon=('phenomenon', 'first'),
            evidence=('evidence', 'first'),
        ).reset_index().sort_values('impact_won', ascending=False)
        out['loss'] = agg
    for cat in ['operational', 'positive', 'quality', 'opportunity']:
        sub = df[df['category'] == cat]
        if not sub.empty:
            sub = sub[['channel', 'week', 'type', 'lever', 'impact_won', 'note', 'phenomenon', 'evidence']]
            if cat != 'opportunity':   # 오가닉 기회는 주차 개념이 없는 '전체' 단위라 정렬 대상 아님
                # impact_won이 없거나 0인 카테고리라 임팩트 정렬이 무의미 — 대신 가장 최근에 발생한
                # 것이 지금 더 관련성 높다고 보고 주차 내림차순(최신 먼저)으로 긴급도를 대체한다.
                sub = sub.iloc[sub['week'].map(_week_key).argsort()[::-1]]
            out[cat] = sub.reset_index(drop=True)
    bench = df[df['category'] == 'benchmark']   # 채널평가는 표·인사이트용 구조화 필드를 통째로 보존
    if not bench.empty:
        out['benchmark'] = bench.reset_index(drop=True)
    return out


if __name__ == '__main__':
    pd.set_option('display.width', 240)
    pd.set_option('display.max_columns', None)
    from calculate import compute_summary
    df = load_and_clean('data/marketing_performance.csv')
    raw = load_and_clean('data/marketing_performance.csv', mask_outlier=False)
    summary = compute_summary(df)

    all_issues = (detect_spike_drop(df) + detect_outliers(raw) + detect_missing(raw)
                  + evaluate_channels(summary['by_channel'])
                  + detect_opportunity(summary['by_channel'], summary['total']['total_revenue']))
    ranked = score_and_rank(all_issues)

    print("=== [손실 랭킹] 누적 임팩트(원) 내림차순 ===")
    print(ranked['loss'][['channel', 'type', 'impact_won', 'frequency', 'weeks']].to_string(index=False))
    for cat, title in [('operational', '운영 관찰(광고비 급락 등)'), ('benchmark', '채널 평가(벤치마크 대비)'),
                       ('opportunity', '기회'), ('quality', '데이터품질'), ('positive', '긍정 신호')]:
        if cat in ranked:
            print(f"\n=== [{title}] ===")
            print(ranked[cat][['channel', 'type', 'note']].to_string(index=False))
