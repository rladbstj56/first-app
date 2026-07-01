"""예산 재배분 기획안 엔진 — 손실 이슈·채널 효율에서 재배분안을 산출한다.

진단(insight_report)이 '무슨 일이 있었나'라면, 여기는 '예산으로 무엇을 할까'(처방)다.
재원은 lever=='예산'인 손실(과집행 초과지출)만 사용 — 데이터 오류(이상치·결측)는 제외.
옮기는 금액은 recoverable_won(실지출 회수액), 우선순위 크기는 impact_won(놓친 매출·추정치)로 구분한다.
"""
import pandas as pd

from calculate import (load_and_clean, compute_summary, compute_channel_roi,
                       compute_wow_change, compute_weekly_channel_roas, compute_wow_by_channel,
                       find_revenue_outliers)
from detect_issues import (BENCHMARKS, _band, compute_adaptive_threshold, compute_recency,
                           detect_spike_drop, detect_outliers, detect_missing, evaluate_channels,
                           detect_opportunity, score_and_rank)

DATA = 'data/marketing_performance.csv'


def _won(x):
    return f"{x:,.0f}원"


def _meta(data_path):
    """리포트 개요용 데이터 메타정보(행수·중복·결측·이상치·기간·주차)를 원본에서 산출."""
    raw_all = pd.read_csv(data_path)
    n_dup = len(raw_all) - len(raw_all.drop_duplicates())
    n_weeks_file = raw_all['week'].dropna().nunique()   # 파일에 담긴 전체 주차 수 (트림 전)
    raw = load_and_clean(data_path, mask_outlier=False)  # 롤링 윈도우 적용된 분석 창
    n_missing = int(raw[['impressions', 'clicks', 'revenue']].isna().sum().sum())
    weeks = sorted(raw['week'].dropna().unique(), key=lambda w: (len(str(w)), str(w)))
    return {
        'path': data_path, 'n_raw': len(raw_all), 'n_dup': n_dup,
        'n_channels': raw['channel'].nunique(), 'n_missing': n_missing,
        'n_outlier': len(find_revenue_outliers(raw)),
        'date_min': raw['date'].min(), 'date_max': raw['date'].max(),
        'n_weeks': len(weeks), 'weeks': f"{weeks[0]}–{weeks[-1]}", 'n_weeks_file': n_weeks_file,
    }


def run_pipeline(data_path=DATA):
    """정제→집계→이슈→랭킹→재원→수혜→재배분을 한 번 실행해 모든 결과를 dict로 반환한다.

    md 생성기(build_report·build_exec_report)와 html 생성기가 이 하나의 결과를 공유 →
    표현이 달라도 수치는 절대 어긋나지 않는다('데이터 하나, 표현 둘'). 계산 로직은 전부 재사용.
    """
    df = load_and_clean(data_path)
    raw = load_and_clean(data_path, mask_outlier=False)
    s = compute_summary(df)
    ranked = score_and_rank(
        detect_spike_drop(df) + detect_outliers(raw) + detect_missing(raw)
        + evaluate_channels(s['by_channel'])
        + detect_opportunity(s['by_channel'], s['total']['total_revenue']))
    funding = compute_funding(ranked)
    targets = select_targets(s, ranked, exclude=list(funding['channel']))
    plans = build_plans(funding, targets, s)
    return {
        'df': df,  # 정제된 원본 — 경영진 요약본이 최근 2주만 재집계할 때 공유(재로드 없이 '데이터 하나')
        'meta': _meta(data_path), 'summary': s, 'roi': compute_channel_roi(df),
        'wow': compute_wow_change(df), 'wow_channel': compute_wow_by_channel(df),
        'weekly_roas': compute_weekly_channel_roas(df),
        'ranked': ranked, 'threshold': compute_adaptive_threshold(df),
        'recency': compute_recency(df),
        'funding': funding, 'targets': targets, 'plans': plans,
    }


def compute_funding(ranked):
    """재배분 재원(어디서 얼마를 뺄 수 있나)을 채널별로 집계한다.

    입력: score_and_rank 결과 dict (ranked['loss'] = 손실 이슈 DataFrame).
    처리: 손실 중 lever=='예산' 행만 필터 → 과집행 초과지출만 재원으로 인정.
          이상치·결측(데이터·트래킹 레버)은 여기서 자동 배제된다.
    출력: DataFrame [channel, recoverable_won, impact_won, frequency, weeks], 회수액 내림차순.
          재원이 없으면 빈 DataFrame(같은 컬럼) 반환 — 새 CSV에서 과집행이 없어도 안전.
    """
    cols = ['channel', 'recoverable_won', 'impact_won', 'frequency', 'weeks']
    loss = ranked.get('loss')
    if loss is None or loss.empty:
        return pd.DataFrame(columns=cols)
    src = loss[(loss['lever'] == '예산') & (loss['recoverable_won'] > 0)]
    if src.empty:
        return pd.DataFrame(columns=cols)
    funding = src.groupby('channel').agg(
        recoverable_won=('recoverable_won', 'sum'),
        impact_won=('impact_won', 'sum'),
        frequency=('frequency', 'sum'),
        weeks=('weeks', lambda s: ','.join(s)),
    ).reset_index().sort_values('recoverable_won', ascending=False)
    return funding[cols]


def select_targets(summary, ranked, exclude=()):
    """재원을 넣을 수혜처 후보를 선정한다 (어디에 넣나).

    입력: compute_summary 결과(채널별 ROAS), score_and_rank 결과(오가닉 기회), 제외 채널(재원 채널).
    두 유형의 후보를 낸다:
      1) 광고 증액 — 벤치마크 ROAS 등급이 '우수'(시장 상위25% 이상)인 유료 채널. 절대 ROI가 아니라
         자기 시장 대비 우수 = '아직 더 태울 여지 검증'. 재원 채널 자신은 제외(과집행처에 재투입 모순).
      2) 전략 투자 — 오가닉(detect_opportunity). 광고비 배정이 아니라 SEO·콘텐츠 투자처로 제시.
    출력: DataFrame [channel, kind, roas, grade, evidence]. 후보 없으면 빈 DataFrame(같은 컬럼).
    """
    cols = ['channel', 'kind', 'roas', 'grade', 'evidence']
    g = summary['by_channel']
    rows = []
    for ch in g.index:
        if ch in exclude:
            continue
        bench = BENCHMARKS.get(ch, {})
        roas = g.loc[ch, 'ROAS']
        if pd.isna(roas) or not bench.get('ROAS'):
            continue  # 오가닉·벤치마크 없는 채널은 광고 증액 후보에서 제외
        band = _band(roas, bench['ROAS'])
        if '우수' in band:
            rows.append({'channel': ch, 'kind': '광고 증액', 'roas': roas, 'grade': band,
                         'evidence': f'ROAS {roas:.2f} — 시장 벤치마크 상위25% 이상(증액 여력 검증)'})
    opp = ranked.get('opportunity')
    if opp is not None and not opp.empty:
        for _, o in opp.iterrows():
            if o['channel'] in exclude:
                continue
            rows.append({'channel': o['channel'], 'kind': '전략 투자(SEO·콘텐츠)', 'roas': float('nan'),
                         'grade': '측정불가(오가닉)', 'evidence': o['note']})
    return pd.DataFrame(rows, columns=cols)


# 수혜처 유형별 즉효성 순위 (우선순위 2차 정렬용). 낮을수록 우선 — 광고 증액은 즉시 ROAS 실현, 전략 투자는 지연.
_KIND_RANK = {'광고 증액': 0, '전략 투자(SEO·콘텐츠)': 1}


def build_plans(funding, targets, summary):
    """재원 × 수혜처를 매칭해 우선순위가 매겨진 재배분안 목록을 만든다.

    입력: compute_funding·select_targets 결과, compute_summary(재원 채널의 평소 ROAS 조회용).
    처리:
      - 각 재원(과집행 채널)의 회수액을 각 수혜처로 보내는 안을 생성. 옮기는 금액 = recoverable(회수 실지출·테스트 상한).
      - 광고 증액: 기대효과를 원(₩)으로 추정 — 순증분 = 회수액 × (수혜 ROAS − 재원채널 평소 ROAS)(선형확장 상한).
      - 전략 투자(오가닉): ROAS 측정불가라 원 추정 없이 정성 기대효과.
      - 우선순위: 1차 impact_won×frequency(재원의 심각도·반복성) 내림차순, 동점은 수혜처 즉효성(_KIND_RANK) 오름차순.
    출력: DataFrame(우선순위 rank 부여). 재원·수혜처 중 하나라도 없으면 빈 DataFrame(같은 컬럼).
    복수 안이 같은 재원을 공유하므로(돈은 한 번만 씀) rank 1을 우선 집행, 성과 확인 후 후속 안으로 순차 배분한다.
    """
    cols = ['rank', 'source', 'target', 'kind', 'amount_won', 'source_roas', 'target_roas',
            'expected_won', 'expected_note', 'priority_score', 'impact_won', 'frequency', 'basis']
    g = summary['by_channel']
    if funding.empty or targets.empty:
        return pd.DataFrame(columns=cols)

    rows = []
    for _, f in funding.iterrows():
        src = f['channel']
        src_roas = g.loc[src, 'ROAS'] if src in g.index else float('nan')
        amount = f['recoverable_won']
        score = f['impact_won'] * f['frequency']
        for _, t in targets.iterrows():
            tgt_roas = t['roas']
            if t['kind'] == '광고 증액' and not pd.isna(tgt_roas) and not pd.isna(src_roas):
                expected = amount * (tgt_roas - src_roas)   # 재원채널 대신 수혜채널에 썼을 때 순증 매출(상한)
                note = (f"회수액을 평소 ROAS {src_roas:.2f}인 {src} 대신 {tgt_roas:.2f}인 {t['channel']}에 재투입 시 "
                        f"매출 순증 상한 (선형확장 가정)")
            else:
                expected = float('nan')                     # 오가닉은 원 추정 안 함(정성)
                note = f"{t['channel']} {t['evidence']} — SEO·콘텐츠 투자로 중장기 유입 성장(즉시 ROAS 미정)"
            rows.append({'source': src, 'target': t['channel'], 'kind': t['kind'], 'amount_won': amount,
                         'source_roas': src_roas, 'target_roas': tgt_roas, 'expected_won': expected,
                         'expected_note': note, 'priority_score': score,
                         'impact_won': f['impact_won'], 'frequency': f['frequency'], 'basis': t['evidence']})

    out = pd.DataFrame(rows)
    out['_kind_rank'] = out['kind'].map(_KIND_RANK).fillna(9)
    out = out.sort_values(['priority_score', '_kind_rank'], ascending=[False, True]).reset_index(drop=True)
    out['rank'] = out.index + 1
    return out[cols]


def plan_lead_sentence(r):
    """재배분안 1건을 '쉽게 말하면' 한 문장으로 — md·html 공유. 분석가 양식 대신 실무자 언어.

    ROAS를 '광고비 1원당 X원 회수'로 풀고, 효율 배수·기대 매출을 넣어 '무엇을·왜' 즉시 이해되게 한다.
    광고 증액이면 효율 비교 문장, 전략 투자(오가닉)면 '오래 남는 자산' 문장으로 분기한다.
    """
    if r['kind'] == '광고 증액' and not pd.isna(r['source_roas']) and r['source_roas'] > 0 and not pd.isna(r['target_roas']):
        ratio = r['target_roas'] / r['source_roas']
        exp = f" 같은 예산으로 매출 최대 {_won(r['expected_won'])}을 추가로 기대할 수 있습니다." if not pd.isna(r['expected_won']) else ""
        return (f"저효율 채널 {r['source']}(ROAS {r['source_roas']:.1f})에서 회수한 {_won(r['amount_won'])}을, "
                f"효율이 {ratio:.1f}배 높은 {r['target']}(ROAS {r['target_roas']:.1f})로 이동합니다.{exp}")
    return (f"{r['source']}에서 회수한 {_won(r['amount_won'])}을 {r['target']} SEO·콘텐츠에 투자합니다. "
            f"즉시 매출로는 잡히지 않지만, 광고 중단 시 사라지는 유료 유입과 달리 지속적으로 남는 자산이 됩니다.")


def _plan_block(r):
    """재배분안 1건을 '쉽게 말하면' 요약 + 4항목 근거(문제·근거·실행·기대) 양식으로 서술한다."""
    if r['kind'] == '광고 증액':
        move = f"**{r['source']} → {r['target']}**, {_won(r['amount_won'])}(테스트 상한), 점진 증액 후 재측정"
        effect = (f"순증 매출 상한 약 {_won(r['expected_won'])} — {r['expected_note']}.\n"
                  f"  - 한계: 선형확장 가정 상한이라 한계수익 체감으로 실제는 하회 가능. 소액 테스트로 검증 후 확대.")
    else:
        move = f"**{r['source']} → {r['target']}**, {_won(r['amount_won'])} 범위 내 SEO·콘텐츠 투자(광고비 직접 배정 아님)"
        effect = (f"{r['expected_note']}.\n"
                  f"  - 한계: 오가닉은 ROAS 측정불가라 원 단위 기대효과를 추정하지 않음(정성). 효과 발현에 시차 존재.")
    return "\n".join([
        f"### [재배분안 #{r['rank']}] 우선순위 {r['rank']}순위  "
        f"(임팩트 {_won(r['impact_won'])} × 빈도 {r['frequency']}주 = 점수 {r['priority_score']:,.0f})\n",
        f"> **핵심 실행**: {plan_lead_sentence(r)}\n",
        f"1. **문제 정의** — {r['source']} 과집행: 회수 가능한 저효율 지출 발생(insight_report 손실 이슈 참조).",
        f"2. **근거 데이터** — 회수가능액 {_won(r['amount_won'])} / 재원채널 평소 ROAS "
        f"{r['source_roas']:.2f} / 수혜채널 근거: {r['basis']}",
        f"3. **재배분안** — {move}",
        f"4. **기대효과·한계** — {effect}\n",
    ])


# 우선순위 판단 기준 — 마케팅 실무자 눈높이의 (제목, 설명) 쌍. md·html이 공유해 문구가 어긋나지 않는다.
PRIORITY_CRITERIA = [
    ("손실 규모 × 발생 빈도로 우선순위를 매깁니다",
     "놓친 매출(손실 규모)만으로 줄을 세우면 일회성 대형 이슈와 매주 반복되는 소액 누수가 뒤섞입니다. "
     "발생 빈도를 곱해, 구조적으로 반복되는 예산 누수를 상위로 끌어올립니다 — 재배분으로 가장 크게 회수할 수 있는 지점입니다."),
    ("점수가 같으면 전환이 즉시 발생하는 채널을 우선합니다",
     "같은 재원을 나눠 쓰는 안들은 손실 규모·빈도가 같아 우선순위 점수가 동일해집니다. "
     "이때는 집행 즉시 전환·매출로 이어지는 광고 증액을, 효과가 수개월 뒤 나타나는 SEO·콘텐츠 투자보다 먼저 집행합니다."),
    ("재배분액은 추정 손실이 아니라 실제 회수 가능한 예산으로 산정합니다",
     "'놓친 매출'은 추정치이고, '과집행된 광고비'는 실제로 회수 가능한 확정 금액입니다. "
     "추정치를 재배분액으로 잡으면 실제로 집행할 수 없는 규모의 계획이 되므로, 옮기는 금액은 회수 가능액만 사용합니다."),
    ("증액처는 절대 ROI 1위가 아니라 시장 대비 증액 여력이 검증된 채널로 선정합니다",
     "절대 ROI가 가장 높은 채널은 이미 예산이 포화 상태일 수 있어, 추가 투입 시 한계 효율이 빠르게 떨어질 수 있습니다. "
     "그래서 동종 업계 벤치마크 상위권(우수 등급)이면서 아직 증액 여력이 남은 채널을 우선 증액 대상으로 삼습니다."),
]

PRIORITY_CAVEAT = ("위 기대 매출은 현재 효율이 선형으로 유지된다는 가정 하의 상한값으로, 실제 성과는 이보다 낮을 수 있습니다. "
                   "오가닉 기여는 ROAS 측정이 불가해 정성적 방향으로만 제시합니다. "
                   "모든 안은 소액 테스트 → 성과 재측정 → 확대의 단계적 검증을 전제로 합니다.")


# NOTE: 예산 재배분 기획안은 별도 파일(build_reallocation)로 내보내지 않고 insight_report(마케팅팀)에
# 흡수한다(Step 27, 독자별 2종 리포트). 이 모듈은 재배분 '엔진'으로만 쓰이며, 위의
# _plan_block·PRIORITY_CRITERIA 등을 generate_report/_reallocation_section이 재사용한다.
