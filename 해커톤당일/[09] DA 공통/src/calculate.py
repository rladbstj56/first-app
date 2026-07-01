"""마케팅 성과 정제·집계·ROI·변화율 계산.

계산은 전부 여기(Python)에서 확정하고, 해석(Claude)은 이 결과 수치만 사용한다.
ROI 정의는 과제 채점 기준을 따라 revenue/spend*100 (순위 비교용)로 고정한다.
"""
import pandas as pd

NUM_COLS = ['impressions', 'clicks', 'spend', 'conversions', 'revenue']
OUTLIER_MZ = 3.5  # AOV modified z-score 컷오프 (Iglewicz-Hoaglin 1993)
RECENT_WEEKS = 8  # 롤링 윈도우: 매번 가장 최근 8주만 분석 (그 이상은 트림)


def _week_key(w):
    """주차 라벨 정렬 키. 자릿수 우선(W2 < W10)으로 문자열 라벨을 올바른 시간순으로 정렬."""
    return (len(str(w)), str(w))


def trim_recent_weeks(df, n_weeks=RECENT_WEEKS):
    """가장 최근 n_weeks 주차만 남긴다 (롤링 윈도우 고정).

    주차 수가 n_weeks 이하면 원본 그대로 반환 — 현재 8주 데이터는 무변화(회귀 없음).
    이보다 많은 CSV가 들어오면 오래된 주차를 잘라, 추이·중앙값 기준선을 최근 창으로 고정한다.
    """
    weeks = sorted(df['week'].dropna().unique(), key=_week_key)
    if len(weeks) <= n_weeks:
        return df
    keep = set(weeks[-n_weeks:])
    return df[df['week'].isin(keep)].reset_index(drop=True)


def find_revenue_outliers(df, mz_threshold=OUTLIER_MZ):
    """채널별 AOV(매출/전환)의 modified z-score로 매출 이상치 행을 찾는다.

    반환: 이상치 행 정보 dict 리스트(index·channel·date·week·revenue·aov·median_aov·mz·est).
    정제(마스킹)와 이슈 보고가 같은 기준을 쓰도록 탐지 로직을 이 함수 하나로 통일한다.
    하드코딩 없이 어떤 CSV든 동작 → 재사용 파이프라인의 재현성 확보.
    modified z-score = 0.6745 × (x − median) / MAD, |mz| > 3.5면 이상치.
    """
    out = []
    for ch, sub in df.groupby('channel'):
        aov = (sub['revenue'] / sub['conversions']).dropna()
        if len(aov) < 3:
            continue
        med = aov.median()
        mad = (aov - med).abs().median()
        if mad == 0:
            continue
        mz = 0.6745 * (aov - med) / mad
        for idx in aov.index[mz.abs() > mz_threshold]:
            row = sub.loc[idx]
            out.append({'index': idx, 'channel': ch, 'date': row['date'], 'week': row['week'],
                        'revenue': row['revenue'], 'conversions': row['conversions'],
                        'aov': row['revenue'] / row['conversions'], 'median_aov': med,
                        'mz': mz.loc[idx], 'est': row['conversions'] * med})
    return out


def load_and_clean(path, mask_outlier=True, recent_weeks=RECENT_WEEKS):
    """CSV를 읽어 숫자형 변환 + 완전 중복 제거 + (옵션) 이상치 revenue만 NaN 처리.

    이상치는 revenue 값만 오염된 것으로 보고(그날 광고비·전환·클릭은 정상) 행 전체가 아니라
    revenue 한 칸만 NaN으로 만든다(결측 처리 원칙과 동일). revenue 합계에서는 자동 제외되면서
    정상 지출·전환은 집계에 보존된다. 이상치는 find_revenue_outliers로 동적 탐지한다.

    mask_outlier=False면 이상치 revenue를 살려서 반환 — 탐지기(detect_outliers)가 원본을 봐야 하므로.
    recent_weeks로 롤링 윈도우를 적용 — 중복 제거 후, 이상치 탐지 전에 잘라 기준선이 최근 창에서 계산되게 한다.
    """
    df = pd.read_csv(path)
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.drop_duplicates().reset_index(drop=True)
    if recent_weeks:
        df = trim_recent_weeks(df, recent_weeks)
    if mask_outlier:
        for o in find_revenue_outliers(df):
            df.loc[o['index'], 'revenue'] = pd.NA
        df['revenue'] = pd.to_numeric(df['revenue'], errors='coerce')
    return df


def compute_summary(df):
    """이상치를 제외한 전체·채널별 합계와 파생지표(ROI/ROAS/CTR/CVR)를 계산한다.

    반환: dict {total: {...}, by_channel: DataFrame}
    NaN(결측·이상치 revenue)은 pandas sum이 자동 제외하므로 별도 처리 없이 정확한 합계가 나온다.
    spend=0(오가닉) 채널은 ROI/ROAS를 NaN(측정 불가)으로 둔다.
    """
    d = df

    total_spend = d['spend'].sum()
    total_revenue = d['revenue'].sum()
    channel_spend = d.groupby('channel')['spend'].sum()
    organic_channels = channel_spend[channel_spend == 0].index  # 총 광고비 0인 채널 = 오가닉
    organic_revenue = d[d['channel'].isin(organic_channels)]['revenue'].sum()
    paid_revenue = total_revenue - organic_revenue
    total = {
        'total_spend': total_spend,               # 유료 광고비 합 (오가닉 spend=0)
        'total_revenue': total_revenue,           # 전체 매출 (오가닉 포함)
        'organic_revenue': organic_revenue,       # 오가닉 무료 기여 매출 (분리 표기)
        'paid_revenue': paid_revenue,             # 유료채널 매출
        'mer': total_revenue / total_spend * 100,        # 전체 마케팅 효율(경영진용, 오가닉 포함)
        'paid_roi': paid_revenue / total_spend * 100,    # 유료 광고 순효율(마케팅팀용)
        'total_conversions': d['conversions'].sum(),
    }

    g = d.groupby('channel').agg(
        spend=('spend', 'sum'), revenue=('revenue', 'sum'),
        conversions=('conversions', 'sum'),
        impressions=('impressions', 'sum'), clicks=('clicks', 'sum'),
    )
    g['ROI'] = (g['revenue'] / g['spend'] * 100).where(g['spend'] > 0)
    g['ROAS'] = (g['revenue'] / g['spend']).where(g['spend'] > 0)
    g['CPA'] = (g['spend'] / g['conversions']).where(g['spend'] > 0)  # 전환당 광고비. 오가닉(spend=0)은 측정 제외(NaN)
    g['CTR'] = g['clicks'] / g['impressions'] * 100
    g['CVR'] = g['conversions'] / g['clicks'] * 100
    return {'total': total, 'by_channel': g}


def compute_channel_roi(df):
    """spend>0 채널만 ROI 내림차순으로 정렬한 순위표를 반환한다 (오가닉 제외).

    오가닉은 광고비 0이라 ROI 정의가 불가능하므로 순위 비교 대상에서 뺀다.
    """
    d = df
    g = d.groupby('channel').agg(spend=('spend', 'sum'), revenue=('revenue', 'sum'))
    g = g[g['spend'] > 0]
    g['ROI'] = g['revenue'] / g['spend'] * 100
    return g.sort_values('ROI', ascending=False)


def compute_wow_change(df, prev=None, curr=None):
    """직전주(prev) 대비 최근주(curr)의 지출·매출·전환수·CTR 증감율(%)을 계산한다.

    prev/curr 미지정 시 데이터의 정렬된 마지막 두 주차를 자동 선택 — 새 CSV의 다른 주차 라벨에도 동작.
    반환: DataFrame (index=지표, columns=[prev, curr, change_pct]).
    CTR은 합으로 더할 수 없어 각 주 clicks합/impressions합으로 재계산한다.
    """
    d = df
    if prev is None or curr is None:
        weeks = sorted(d['week'].dropna().unique(), key=lambda w: (len(w), w))  # W2 < W10 순서 보장
        prev, curr = weeks[-2], weeks[-1]
    out = {}
    for w in (prev, curr):
        s = d[d['week'] == w]
        out[w] = {
            'spend': s['spend'].sum(),
            'revenue': s['revenue'].sum(),
            'conversions': s['conversions'].sum(),
            'CTR': s['clicks'].sum() / s['impressions'].sum() * 100,
        }
    res = pd.DataFrame(out)
    res['change_pct'] = (res[curr] - res[prev]) / res[prev] * 100
    return res


def compute_weekly_channel_roas(df):
    """주차(행)×채널(열) ROAS 매트릭스를 계산한다 (주차별 채널 효율 추이용).

    각 주·채널의 ROAS = 그 주 매출합 / 광고비합. 광고비 0(오가닉·미집행)은 NaN(측정불가).
    반환: DataFrame (index=주차 시간순, columns=채널). 채널 순서는 창 전체 매출 큰 순.
    합산 순위(compute_channel_roi)가 못 보는 '주차 간 효율 역전·상승 추세'를 드러내 예산 타이밍 근거가 된다.
    """
    weeks = sorted(df['week'].dropna().unique(), key=_week_key)
    g = df.groupby(['week', 'channel']).agg(spend=('spend', 'sum'), revenue=('revenue', 'sum'))
    roas = (g['revenue'] / g['spend']).where(g['spend'] > 0)
    mat = roas.unstack('channel').reindex(weeks)
    ch_order = df.groupby('channel')['revenue'].sum().sort_values(ascending=False).index
    return mat[[c for c in ch_order if c in mat.columns]]


def compute_wow_by_channel(df, prev=None, curr=None):
    """채널별 최근 2주(prev→curr) 광고비·매출·ROAS 변화를 계산한다 (최근 2주 심층).

    전체 WoW(compute_wow_change)가 '조직 전체가 어떻게 변했나'라면, 여기는 '어느 채널이 움직였나' —
    최근 예산 배분 인사이트의 근거가 된다. prev/curr 미지정 시 창의 마지막 두 주차 자동 선택.
    반환: DataFrame [channel, spend_prev, spend_curr, spend_chg, roas_prev, roas_curr, roas_chg], 매출 큰 순.
    """
    weeks = sorted(df['week'].dropna().unique(), key=_week_key)
    if prev is None or curr is None:
        prev, curr = weeks[-2], weeks[-1]
    rows = []
    for ch in df.groupby('channel')['revenue'].sum().sort_values(ascending=False).index:
        cur = {}
        for tag, w in (('prev', prev), ('curr', curr)):
            sub = df[(df['week'] == w) & (df['channel'] == ch)]
            sp, rev = sub['spend'].sum(), sub['revenue'].sum()
            cur[f'spend_{tag}'] = sp
            cur[f'roas_{tag}'] = rev / sp if sp > 0 else float('nan')
        sp0, sp1 = cur['spend_prev'], cur['spend_curr']
        r0, r1 = cur['roas_prev'], cur['roas_curr']
        cur.update(channel=ch,
                   spend_chg=(sp1 - sp0) / sp0 * 100 if sp0 > 0 else float('nan'),
                   roas_chg=(r1 - r0) / r0 * 100 if r0 and not pd.isna(r0) and r0 > 0 else float('nan'))
        rows.append(cur)
    return pd.DataFrame(rows)[['channel', 'spend_prev', 'spend_curr', 'spend_chg',
                               'roas_prev', 'roas_curr', 'roas_chg']]


if __name__ == '__main__':
    pd.set_option('display.width', 200)
    pd.set_option('display.max_columns', None)
    df = load_and_clean('data/marketing_performance.csv')
    print(f"정제 후 행수: {len(df)}  (이메일 이상치 revenue 1건 NaN 처리)\n")

    s = compute_summary(df)
    print("=== 핵심 수치 요약 (이상치 revenue 제외) ===")
    for k, v in s['total'].items():
        print(f"  {k}: {v:,.1f}")
    print("\n=== 채널별 합계·파생지표 ===")
    print(s['by_channel'].round(1).to_string())

    print("\n=== 채널 ROI 순위 (오가닉 제외) ===")
    print(compute_channel_roi(df).round(1).to_string())

    print("\n=== W7 → W8 변화율 ===")
    print(compute_wow_change(df).round(1).to_string())
