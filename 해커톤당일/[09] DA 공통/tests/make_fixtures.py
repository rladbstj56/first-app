"""재현성 검증용 변형 CSV(픽스처) 생성.

원본(data/marketing_performance.csv)을 subset/relabel해 현실적 변형 3종을 만든다.
가짜 숫자를 지어내지 않고 실제 분포를 유지 → 파이프라인이 "다른 데이터"에서도
크래시 없이 동일 구조 리포트를 내는지 정직하게 검증하기 위함.

- variant_a_short.csv    : W1-W4 · 3채널(네이버·메타·오가닉)  → 주차·채널 축소, 손실 0건 엣지(T-003)
- variant_b_noorganic.csv: 오가닉 제거                         → 기회 섹션 생략 경로(T-002)
- variant_c_relabel.csv  : 주차 W1-W8 → W5-W12 재라벨          → 변화율 마지막 2주 자동 조정(하드코딩 없음)
"""
import os
import pandas as pd

HERE = os.path.dirname(__file__)
SRC = os.path.join(HERE, '..', 'data', 'marketing_performance.csv')
OUT = os.path.join(HERE, 'fixtures')


def main():
    os.makedirs(OUT, exist_ok=True)
    df = pd.read_csv(SRC)

    a = df[df['week'].isin(['W1', 'W2', 'W3', 'W4'])
           & df['channel'].isin(['네이버광고', '메타광고', '오가닉'])].copy()
    a.to_csv(os.path.join(OUT, 'variant_a_short.csv'), index=False)

    b = df[df['channel'] != '오가닉'].copy()
    b.to_csv(os.path.join(OUT, 'variant_b_noorganic.csv'), index=False)

    remap = {f'W{i}': f'W{i + 4}' for i in range(1, 9)}  # W1..W8 -> W5..W12
    c = df.copy()
    c['week'] = c['week'].map(remap)
    c.to_csv(os.path.join(OUT, 'variant_c_relabel.csv'), index=False)

    # 12주 변형: 원본 W1-W8 + 원본 W1-W4를 W9-W12로 재라벨해 이어붙임(실제 분포 재사용, 숫자 조작 없음).
    # 롤링 윈도우가 최근 8주(W5-W12)만 분석하는지 검증하기 위한 픽스처.
    ext = df[df['week'].isin(['W1', 'W2', 'W3', 'W4'])].copy()
    ext['week'] = ext['week'].map({'W1': 'W9', 'W2': 'W10', 'W3': 'W11', 'W4': 'W12'})
    d12 = pd.concat([df, ext], ignore_index=True)
    d12.to_csv(os.path.join(OUT, 'variant_d_twelveweeks.csv'), index=False)

    for name in ('variant_a_short', 'variant_b_noorganic', 'variant_c_relabel', 'variant_d_twelveweeks'):
        f = os.path.join(OUT, name + '.csv')
        n = len(pd.read_csv(f))
        print(f'생성: {name}.csv  ({n}행)')


if __name__ == '__main__':
    main()
