"""HTML 대시보드 생성 — md와 같은 run_pipeline 결과를 카드·막대·표로 렌더링한다.

md 생성기(generate_report·reallocate)와 동일한 계산 결과 dict를 소비하므로 수치가 어긋나지 않는다.
이미지 차트(Matplotlib/Plotly)는 쓰지 않고 CSS 요소로만 시각화 → 과제 제약(이미지 차트 제외) 준수.
사용법: python3 src/generate_html.py [입력CSV]  → output/insight_report.html·exec_report.html
"""
import sys
from html import escape

import pandas as pd

from detect_issues import BAND_SHORT, BENCHMARKS, _band
from generate_report import (build_summary_points, build_playbook,
                             build_weekly_channel_trend, build_wow_channel_insight, won, _status,
                             exec_perf_2w, _perf_body, PERF_DEFS, ROAS_DEF, won_compact, compact_won_text,
                             _SHOW_STATUS_TYPES)
from reallocate import (run_pipeline, plan_lead_sentence,
                        PRIORITY_CRITERIA, PRIORITY_CAVEAT)

INSIGHT_OUT = 'output/insight_report.html'
EXEC_OUT = 'output/exec_report.html'

# 조치 레버 → 태그 색상 클래스. 예산=회수·이동 대상(강조), 데이터=예산 무관(중립), 운영=최적화.
_LEVER_CLASS = {'예산': 't-budget', '데이터·트래킹': 't-data',
                '운영·크리에이티브': 't-ops', '전략': 't-strat'}
# 벤치마크 등급 → 태그 색상. 우수>평균이상>개선여지>미흡.
_BAND_CLASS = {'상위25% 이상(우수)': 't-best', '평균 이상': 't-mid',
               '평균 이하(개선여지)': 't-low', '하위25% 이하(미흡)': 't-low', '측정불가': 't-na'}

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans KR', sans-serif; background: #f4f5f7; color: #1a1a2e; line-height: 1.6; }
.container { max-width: 1080px; margin: 0 auto; padding: 40px 24px; }
.header { background: #fff; border-radius: 12px; padding: 32px 36px; margin-bottom: 24px; border-left: 5px solid #2d6a4f; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.header.rx { border-left-color: #7048e8; }
.badge { display: inline-block; background: #2d6a4f; color: #fff; font-size: 12px; font-weight: 600; padding: 4px 12px; border-radius: 20px; margin-bottom: 14px; letter-spacing: .5px; }
.badge.rx { background: #7048e8; }
.header h1 { font-size: 22px; font-weight: 700; margin-bottom: 10px; }
.header-meta { font-size: 13px; color: #6c757d; display: flex; flex-wrap: wrap; gap: 16px; }
.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.stat { background: #f8f9fb; border-radius: 10px; padding: 20px; text-align: center; border-top: 4px solid; }
.stat-n { font-size: 28px; font-weight: 800; letter-spacing: -.3px; }
.stat-label { font-size: 13px; color: #666; margin-top: 2px; }
.stat-sub { font-size: 12px; color: #999; margin-top: 4px; }
.c-red { border-color: #e63946; color: #e63946; } .c-blue { border-color: #4361ee; color: #4361ee; }
.c-green { border-color: #2d6a4f; color: #2d6a4f; } .c-purple { border-color: #7048e8; color: #7048e8; }
.section { background: #fff; border-radius: 12px; padding: 28px 32px; margin-bottom: 24px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.section-title { font-size: 19px; font-weight: 700; padding-bottom: 14px; margin-bottom: 20px; border-bottom: 1px solid #eee; }
.section-sub { font-size: 16px; font-weight: 700; color: #2d6a4f; margin: 26px 0 14px; padding-top: 18px; border-top: 1px dashed #e3e6ea; } .section-sub:first-of-type { margin-top: 4px; padding-top: 0; border-top: none; }
.note { font-size: 12px; color: #888; margin-bottom: 14px; }
.bar-row { margin-bottom: 12px; }
.bar-meta { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 5px; font-weight: 600; }
.bar-track { background: #f0f2f5; border-radius: 6px; height: 30px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 6px; display: flex; align-items: center; padding-left: 12px; color: #fff; font-size: 12px; font-weight: 700; }
.bar-na { height: 30px; background: repeating-linear-gradient(45deg,#eef0f3,#eef0f3 8px,#e3e6ea 8px,#e3e6ea 16px); border-radius: 6px; display: flex; align-items: center; padding-left: 12px; color: #888; font-size: 12px; font-weight: 700; }
.tbl-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
thead th { background: #f8f9fa; font-size: 12px; font-weight: 700; color: #6c757d; padding: 10px 12px; text-align: left; border-bottom: 2px solid #e9ecef; white-space: nowrap; }
tbody td { padding: 9px 12px; border-bottom: 1px solid #f0f2f5; vertical-align: middle; }
tbody tr:hover { background: #f8f9fb; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
td.lnum { text-align: left; font-variant-numeric: tabular-nums; }
.rank { font-weight: 800; color: #4361ee; }
td.led { font-weight: 800; color: #1f5c3d; background: #eaf6f0; }
.tag { display:inline-block; font-size:11px; font-weight:700; padding:2px 8px; border-radius:5px; }
.t-best { background:#d0ebe0; color:#1f5c3d; } .t-mid { background:#dde3ff; color:#3452cc; }
.t-low { background:#fff3cd; color:#856404; } .t-na { background:#e9ecef; color:#495057; }
.t-budget { background:#ffe0d6; color:#b5341a; } .t-data { background:#e9ecef; color:#495057; }
.t-ops { background:#dde3ff; color:#3452cc; } .t-strat { background:#e7dcff; color:#5b34b5; }
.chg-up { color:#2d6a4f; font-weight:700; } .chg-down { color:#e63946; font-weight:700; }
.issue { border:1px solid #eee; border-left:4px solid #e63946; border-radius:8px; padding:16px 18px; margin-bottom:14px; }
.issue.budget { border-left-color:#e8590c; } .issue.data { border-left-color:#868e96; }
.issue.positive { border-left-color:#2d6a4f; }
.issue-h { font-size:14px; font-weight:700; margin-bottom:8px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
.issue-row { font-size:13px; margin-top:4px; } .issue-row b { color:#555; }
.plan { border:1px solid #e7dcff; border-left:4px solid #7048e8; border-radius:8px; padding:18px 20px; margin-bottom:16px; }
.plan-h { font-size:14px; font-weight:700; margin-bottom:10px; }
.plan-h .pr { background:#7048e8; color:#fff; border-radius:6px; padding:2px 9px; font-size:12px; margin-right:8px; }
.callout { background:#f8f6ff; border-radius:8px; padding:16px 20px; font-size:16px; color:#3d2f66; margin-top:8px; line-height:1.7; } .callout li { margin-bottom:6px; }
.mom-lead { font-size:15px; color:#333; font-weight:600; margin-bottom:12px; line-height:1.6; }
.budget-h { font-size:17px; font-weight:800; color:#3d2f66; margin-bottom:10px; line-height:1.5; }
.budget-line { font-size:15px; color:#4a3a7a; margin-top:9px; line-height:1.7; }
.budget-line b { color:#3d2f66; }
.summary { background:#fff; border-radius:12px; padding:24px 28px; margin-bottom:24px; border-left:5px solid #2d6a4f; box-shadow:0 1px 4px rgba(0,0,0,.06); }
.summary h2 { font-size:19px; margin-bottom:6px; } .summary .note { margin-bottom:12px; }
.summary ul { list-style:none; } .summary li { font-size:16px; padding:11px 0; border-bottom:1px solid #f0f2f5; line-height:1.55; }
.summary li:last-child { border-bottom:none; } .summary li b { color:#2d6a4f; }
.win-tag { display:inline-block; font-size:10px; font-weight:700; padding:1px 8px; border-radius:8px; margin-left:6px; vertical-align:1px; }
.win-2w { background:#e7f5ee; color:#2d6a4f; } .win-8w { background:#fff4e6; color:#e8590c; }
.li-note { font-size:11.5px; color:#999; margin-top:4px; line-height:1.5; }
.issue-detail { font-size:14px; color:#444; margin-top:8px; line-height:1.7; }
.issue-detail b { color:#333; }
.def-note { font-size:12px; color:#888; margin:2px 0 14px; line-height:1.6; } .def-note b { color:#555; }
.foot { font-size:12px; color:#999; text-align:center; padding:8px 0 4px; }
ol.crit { margin:6px 0 0 18px; } ol.crit li { font-size:13px; margin-bottom:8px; }
.playbook { border-left:5px solid #e8590c; }
.pb-rank { font-weight:800; color:#e8590c; text-align:center; }
.when-now { color:#e63946; font-weight:700; } .when-wk { color:#e8590c; font-weight:700; } .when-mo { color:#6c757d; font-weight:600; }
td.owner { color:#495057; white-space:nowrap; }
.plan-lead { background:#f8f6ff; border-radius:8px; padding:13px 16px; font-size:14px; line-height:1.7; margin:2px 0 14px; }
.plan-lead b { color:#5b34b5; }
.flow { display:flex; align-items:center; justify-content:center; gap:14px; flex-wrap:wrap; margin:6px 0 16px; }
.flow-node { border-radius:10px; padding:12px 18px; text-align:center; min-width:132px; }
.flow-node.from { border:2px solid #f1b0b7; background:#fff5f4; }
.flow-node.to { border:2px solid #9dc9b4; background:#f2f9f5; }
.flow-node .fn-name { font-weight:700; font-size:15px; }
.flow-node .fn-roas { font-size:11px; color:#777; margin-top:3px; }
.flow-node .fn-amt { font-size:14px; font-weight:800; margin-top:7px; }
.fn-amt.neg { color:#e63946; } .fn-amt.pos { color:#2d6a4f; }
.flow-arrow { text-align:center; color:#7048e8; line-height:1.35; }
.flow-arrow .fa-amt { font-size:13px; font-weight:700; } .flow-arrow .fa-line { font-size:24px; }
.ratio { display:inline-block; background:#7048e8; color:#fff; font-size:11px; font-weight:700; padding:2px 9px; border-radius:11px; margin-top:3px; }
.plan .subhead { font-size:12px; color:#999; margin:12px 0 6px; font-weight:700; }
.aud { background:#2d6a4f; color:#fff !important; padding:3px 10px; border-radius:12px; font-weight:600; }
/* 마케팅팀 상세본(insight_report)만 본문 글씨를 키운다 — 경영진 요약본(container.rx)은 제외.
   제목(.section-title 등)은 그대로 두고, 표·이슈·체크리스트 같은 '읽고 판단하는' 본문 텍스트만 대상. */
.container:not(.rx) .note { font-size: 14px; }
.container:not(.rx) table { font-size: 15px; }
.container:not(.rx) thead th { font-size: 13px; }
.container:not(.rx) .issue-row { font-size: 15px; }
.container:not(.rx) .issue-h { font-size: 16px; }
.container:not(.rx) .plan-lead { font-size: 16px; }
.container:not(.rx) ol.crit li { font-size: 15px; }
.container:not(.rx) .callout { font-size: 17px; }
"""


def _won(x):
    return f"{x:,.0f}원"


def _page(title, badge_cls, body):
    """badge_cls('rx'=경영진, ''=마케팅팀)를 컨테이너 클래스로도 써 CSS가 리포트별로 다르게 스코프되게 한다."""
    container_cls = f"container {badge_cls}".strip()
    return (f"<!DOCTYPE html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"UTF-8\">\n"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
            f"<title>{escape(title)}</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
            f"<div class=\"{container_cls}\">\n{body}\n</div>\n</body>\n</html>\n")


def _stat(n, label, sub, color):
    sub_html = f'<div class="stat-sub">{escape(sub)}</div>' if sub else ''
    return f'<div class="stat {color}"><div class="stat-n">{escape(n)}</div><div class="stat-label">{escape(label)}</div>{sub_html}</div>'


def _roi_bars(summary, roi):
    """채널 ROI를 막대로. 최상위 ROI를 100% 폭 기준으로 정규화. 오가닉은 측정불가 빗금 막대.

    우리 채널 간 순위(1위~n위)만 보면 '가장 잘하는 채널'로 오해하기 쉽지만, 업계 평균과 비교하면
    순위와 무관하게 시장 대비로는 평범하거나 미흡할 수 있다(예: 이메일이 1위여도 업계에선 평균 이하일 수 있음).
    그래서 채널별 업계 벤치마크(ROAS 평균)와 등급 배지를 함께 보여준다 — BENCHMARKS·_band는 detect_issues의
    '채널 평가' 섹션과 같은 기준을 그대로 재사용해 두 섹션의 판정이 어긋나지 않게 한다.
    """
    colors = ['#2d6a4f', '#4361ee', '#4895ef', '#4cc9f0']
    top = roi['ROI'].max()
    bars = []
    for i, (ch, r) in enumerate(roi.iterrows()):
        w = max(6, r['ROI'] / top * 100)
        c = colors[i] if i < len(colors) else '#8390fa'
        roas = r['revenue'] / r['spend']
        bench = BENCHMARKS.get(ch, {}).get('ROAS')
        bench_txt = f" · 업계 평균 ROAS {bench[1]:.1f}" if bench else ""
        band = _band(roas, bench)
        band_tag = (f"<span class='tag {_BAND_CLASS.get(band, 't-na')}'>{BAND_SHORT[band]}</span>"
                    if bench else "")
        bars.append(f'<div class="bar-row"><div class="bar-meta"><span>{i+1}. {escape(ch)}</span>'
                    f'<span>{r["ROI"]:.2f}% · ROAS {roas:.2f}{bench_txt} {band_tag}</span></div>'
                    f'<div class="bar-track"><div class="bar-fill" style="width:{w:.1f}%;background:{c}">{r["ROI"]:.0f}%</div></div></div>')
    g = summary['by_channel']
    for ch in g.index:
        if g.loc[ch, 'spend'] == 0:
            bars.append(f'<div class="bar-row"><div class="bar-meta"><span>– {escape(ch)}</span>'
                        f'<span>측정 불가</span></div><div class="bar-na">광고비 0원 (오가닉)</div></div>')
    return "".join(bars)


def _channel_table(summary):
    g = summary['by_channel'].sort_values('revenue', ascending=False)
    rows = []
    for ch in g.index:
        r = g.loc[ch]
        roi = "측정불가" if pd.isna(r['ROI']) else f"{r['ROI']:.2f}%"
        roas = "–" if pd.isna(r['ROAS']) else f"{r['ROAS']:.2f}"
        cpa = "–" if pd.isna(r['CPA']) else f"{r['CPA']:,.0f}"
        bench = BENCHMARKS.get(ch, {}).get('ROAS')
        band = _band(r['ROAS'], bench)
        rb = f"<span class='tag {_BAND_CLASS.get(band, 't-na')}'>{BAND_SHORT[band]}</span>"
        rows.append(f"<tr><td>{escape(ch)}</td><td class='num'>{r['spend']:,.0f}</td>"
                    f"<td class='num'>{r['revenue']:,.0f}</td><td class='num'>{r['conversions']:,.0f}</td>"
                    f"<td class='num'>{roi}</td><td class='num'>{roas} {rb}</td><td class='num'>{cpa}</td>"
                    f"<td class='num'>{r['CTR']:.2f}%</td><td class='num'>{r['CVR']:.2f}%</td></tr>")
    return ("<p class='note'>CTR(클릭률) = 클릭 / 노출 — 소재·타겟팅이 시선을 끄는 정도를 보여줍니다.</p>"
            "<p class='note'>CVR(전환율) = 전환 / 클릭 — 클릭 이후 실제 전환으로 이어지는 정도를 보여줍니다.</p>"
            "<p class='note'>CPA(전환당 비용) = 광고비 / 전환 — 낮을수록 효율적입니다. 오가닉은 광고비 0이라 측정 제외(–)입니다.</p>"
            "<p class='note'>ROAS 옆 배지는 같은 채널의 업계 벤치마크 대비 등급이며, 우리 채널 간 순위와는 별개입니다.</p>"
            "<div class='tbl-wrap'><table><thead><tr><th>채널</th><th>광고비</th><th>매출</th>"
            "<th>전환</th><th>ROI</th><th>ROAS</th><th>CPA</th><th>CTR</th><th>CVR</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")




_WHEN_CLASS = {'즉시': 'when-now', '이번 주': 'when-wk', '이번 달': 'when-mo'}


def _playbook_html(data):
    """'이번 주 업무 우선순위' 표 html — md와 동일한 build_playbook을 렌더만 다르게.

    표의 할 일·근거 컬럼이 이미 각 항목의 실행 맥락을 담고 있어, 별도 실행 단계 하위 목록은
    두지 않는다(같은 내용을 두 형태로 중복 표기하지 않음).
    """
    items = build_playbook(data)
    note = ("<p class='note'>아래 '핵심 이슈' 섹션의 근거를 우선순위·담당·시점으로 재구성 — 이 표만으로 이번 주 팀 업무 분배가 됩니다. "
            "(담당은 역할 예시로, 조직의 실제 담당자로 대체 · 각 근거의 상세는 '핵심 이슈' 섹션 참조)</p>")
    if not items:
        return ('<div class="section playbook"><div class="section-title">이번 주 업무 우선순위</div>'
                f'{note}<p>이번 주 특별히 실행할 조치가 없습니다 — 현 운영을 유지하세요.</p></div>')
    rows = "".join(
        f"<tr><td class='pb-rank'>{it['rank']}</td><td>{escape(it['action'])}</td>"
        f"<td>{escape(it['basis'])}</td><td class='owner'>{escape(it['owner'])}</td>"
        f"<td class='{_WHEN_CLASS.get(it['when'], '')}'>{escape(it['when'])}</td></tr>" for it in items)
    return ('<div class="section playbook"><div class="section-title">이번 주 업무 우선순위</div>'
            f"{note}<div class='tbl-wrap'><table><thead><tr><th>순위</th><th>할 일</th>"
            "<th>근거</th><th>담당</th><th>시점</th></tr></thead><tbody>"
            f"{rows}</tbody></table></div></div>")


# 경영진 요약본은 성과(2주)·이슈·예산(8주)이 서로 다른 창을 쓰므로, 항목 라벨에 창 배지를 붙여
# '왜 이 항목의 근거 주차가 최근 2주 밖에 있는지'를 페이지 안에서 바로 알 수 있게 한다.
_WINDOW_TAG_2W = ('최근 2주 성과', '최근 추세')
_WINDOW_TAG_8W = ('가장 시급한 예산 리스크', '예산 재배분 승인 요청', '예산 조정 필요 없음')


def _window_tag(label):
    if any(label.startswith(p) for p in _WINDOW_TAG_2W):
        return '<span class="win-tag win-2w">최근 2주</span>'
    if any(label.startswith(p) for p in _WINDOW_TAG_8W):
        return '<span class="win-tag win-8w">8주 누적</span>'
    return ''


def _perf_def_note_html():
    """핵심 요약 제목 바로 아래 붙는 지표 정의 html(용어만 볼드) — md는 generate_report.perf_def_note_md가 같은 PERF_DEFS를 렌더."""
    return " · ".join(f"<b>{escape(term)}</b> = {escape(desc)}" for term, desc in PERF_DEFS)


def _roas_def_note_html():
    """모멘텀 섹션 제목 바로 아래 붙는 ROAS 정의 html — md는 generate_report.roas_def_note_md가 같은 ROAS_DEF를 렌더."""
    term, desc = ROAS_DEF
    return f"<b>{escape(term)}</b> = {escape(desc)}"


def _exec_summary_html(data, exclude_prefixes=(), perf=None, title="핵심 요약",
                        show_note=False, compact=True, dual_window=False, top_note=None):
    """리포트 최상단 요약 박스 html (갭1) — md와 동일한 build_summary_points를 렌더링만 다르게.

    마케팅팀 상세본·경영진 요약본 모두 이 함수 하나로 렌더해 두 리포트의 요약 박스 제목·구조를 통일한다
    (제목·부연 문구 생략·금액 축약이 기본값 — exec_report 호출부는 이 기본값을 그대로 씀).
    exclude_prefixes: 라벨이 이 접두사로 시작하는 항목은 제외(경영진 요약본에서 데이터 정정 노이즈 제거용).
    perf: (라벨, 본문) 튜플 — 경영진 요약본이 성과 헤드라인을 최근 2주로 교체할 때만 전달.
    compact: 문장 속 '1,234,567원'을 억/만 단위로 축약 — 요약 박스 전용, 아래 상세 섹션은 정확 원 단위 유지.
    dual_window: 항목별로 성과(2주)·이슈·예산(8주) 기준 창이 다름을 배지로 표시(경영진 요약본 전용).
    top_note: 제목 바로 아래(항목보다 먼저) 붙는 지표 정의 — 리포트에서 그 지표가 처음 나오는 자리라 여기 배치.
    """
    items = []
    for label, body, note in build_summary_points(data, perf=perf):
        if any(label.startswith(p) for p in exclude_prefixes):
            continue
        b = compact_won_text(body) if compact else body
        tag = _window_tag(label) if dual_window else ''
        note_li = f"<div class='li-note'>{escape(note)}</div>" if note else ''
        items.append(f"<li><b>{escape(label)}</b>{tag} · {escape(b)}{note_li}</li>")
    note_html = ("<p class='note'>이 박스만으로 '전체 성과 · 지금 할 일 · 위험'을 먼저 판단하도록 요약.</p>"
                 if show_note else "")
    top_note_html = f"<div class='def-note'>{top_note}</div>" if top_note else ""
    return (f"<div class='summary'><h2>{escape(title)}</h2>{note_html}{top_note_html}"
            f"<ul>{''.join(items)}</ul></div>")


def _issue_card(r, i, recency, threshold, label='이슈'):
    """이슈 1개 카드 — 임팩트(₩)가 있으면 금액 배지를 표시하고 없으면(집행축소·결측 등) 생략한다.

    담당·조치처(레버) 하나의 기준으로 그룹을 나누므로(_issue_cards), 같은 그룹 안에 임팩트 있는 행과
    없는 행이 섞일 수 있어 배지 표시 여부를 행 단위로 판단한다. 발생 표기는 loss행(weeks·frequency)과
    관찰·품질행(week 단수)의 컬럼 구조가 달라 notna로 분기(pd.concat 후엔 없는 컬럼이 NaN으로 채워짐).
    """
    lever = r['lever']
    cls = 'positive' if label == '긍정' else ('data' if lever == '데이터·트래킹' else 'budget')
    tag = f"<span class='tag {_LEVER_CLASS.get(lever, 't-na')}'>{escape(lever)}</span>"
    amt_html = ""
    if pd.notna(r['impact_won']) and r['impact_won'] > 0:
        if r['type'] == '성과호재':
            amt_label = '매출 증가분'
        elif lever == '데이터·트래킹':
            amt_label = '왜곡·추정 금액'
        else:
            amt_label = '기회손실'
        amt_html = f"<span style='margin-left:auto;color:#e63946'>{amt_label} {_won(r['impact_won'])}</span>"
    occ = f"{r['weeks']} (빈도 {r['frequency']:.0f}주)" if pd.notna(r.get('weeks')) else str(r['week'])
    rows = [f"<div class='issue-row'><b>현상</b> {escape(str(r['phenomenon']))}</div>",
            f"<div class='issue-row'><b>근거</b> {escape(str(r['evidence']))}</div>",
            f"<div class='issue-row'><b>발생</b> {escape(occ)}</div>"]
    if r['type'] in _SHOW_STATUS_TYPES:
        st = _status(r['type'], r['channel'], recency, threshold)
        if st:
            rows.append(f"<div class='issue-row'>{escape(st.lstrip('- '))}</div>")
    return (f"<div class='issue {cls}'>"
            f"<div class='issue-h'>{label} {i}: {escape(r['channel'])} — {escape(r['type'])} {tag}{amt_html}</div>"
            + "".join(rows) + "</div>")


def _issue_cards(ranked, recency, threshold):
    """이슈를 담당·조치처(레버) 하나의 기준으로 3그룹(예산·운영·크리에이티브·데이터·트래킹)으로 나눈다.

    md _issues()와 같은 원칙(단일 기준 재조정) — 매출 영향 유무와 레버를 섞어 5개 그룹으로 나누던 이전
    구조가 독자에게 산만하게 보인다는 피드백을 반영해 레버 하나로 통일했다.
    """
    loss = ranked.get('loss')
    operational = ranked.get('operational')
    quality = ranked.get('quality')
    positive = ranked.get('positive')

    def _h4(text, mt='16px'):
        return f"<h4 style='font-size:16px;margin:{mt} 0 8px'>{text}</h4>"

    def _collect(lever):
        parts = [df[df['lever'] == lever] for df in (loss, operational, quality)
                 if df is not None and not df.empty]
        parts = [p for p in parts if not p.empty]
        if not parts:
            return []
        combined = pd.concat(parts, ignore_index=False, sort=False)
        return list(combined.sort_values('impact_won', ascending=False, na_position='last').iterrows())

    out = ["<p class='note'><b>분류</b> · 담당·조치처(레버) 하나의 기준으로 3그룹 — <b>예산</b>(재배분 대상)·"
           "<b>운영·크리에이티브</b>(채널 담당 확인)·<b>데이터·트래킹</b>(원본·수집 확인, 예산 조치 아님). "
           "문제가 아닌 <b>긍정 신호</b>는 맨 아래 참고로 별도 표시합니다.</p>",
           "<p class='note'><b>정렬</b> · 각 그룹 안에서 임팩트(₩) 큰 순 — 임팩트 없는 항목(집행축소·결측 등)은 자연히 하단.</p>"]

    for lever, title, empty_msg, footnote in [
        ('예산', '예산 (재배분 대상 — 마케팅 리드 확인)', '예산 레버로 확인할 이슈 없음.',
         "<p class='note'>이 중 회수 가능한 초과 지출은 예산 재배분 재원이 된다 — 상세 기획은 아래 '예산 재배분 기획안' 섹션 참조.</p>"),
        ('운영·크리에이티브', '운영·크리에이티브 (채널 담당 확인)', '운영·크리에이티브 레버로 확인할 이슈 없음.', None),
        ('데이터·트래킹', '데이터·트래킹 (원본·수집 확인 — 예산 조치 아님)', '데이터·트래킹 레버로 확인할 이슈 없음.',
         "<p class='note'>위 '금액'은 잃은 돈이 아니라 <b>데이터가 왜곡·누락된 규모</b>다. 예산 재배분 대상이 아니다.</p>"),
    ]:
        out.append(_h4(title, '6px' if lever == '예산' else '16px'))
        items = _collect(lever)
        if not items:
            out.append(f"<p class='note'>{empty_msg}</p>")
            continue
        out += [_issue_card(r, i, recency, threshold) for i, (_, r) in enumerate(items, 1)]
        if footnote:
            out.append(footnote)

    if positive is not None and not positive.empty:
        out.append(_h4('참고: 주목할 긍정 신호 (문제 아님)'))
        out += [_issue_card(r, i, recency, threshold, label='긍정') for i, (_, r) in enumerate(positive.iterrows(), 1)]
    return "".join(out)


def _wow_table(wow):
    prev, curr = wow.columns[0], wow.columns[1]
    label = {'spend': '지출', 'revenue': '매출', 'conversions': '전환수', 'CTR': 'CTR'}
    rows = []
    for m in ['spend', 'revenue', 'conversions', 'CTR']:
        r = wow.loc[m]
        chg = r['change_pct']
        cls = 'chg-up' if chg > 5 else 'chg-down' if chg < -5 else ''
        v0 = f"{r[prev]:,.0f}" if m != 'CTR' else f"{r[prev]:.2f}%"
        v1 = f"{r[curr]:,.0f}" if m != 'CTR' else f"{r[curr]:.2f}%"
        rows.append(f"<tr><td>{label[m]}</td><td class='lnum'>{v0}</td><td class='lnum'>{v1}</td>"
                    f"<td class='lnum {cls}'>{chg:+.2f}%</td></tr>")
    return (f"<div class='tbl-wrap'><table><thead><tr><th>지표</th><th>{prev}</th><th>{curr}</th>"
            "<th>변화율</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")


def _weekly_trend_html(d):
    """주차별 채널 ROAS 추이 표 + 인사이트 html — md _weekly_trend_md와 같은 내용.

    리더 교체·뚜렷한 추세(has_signal)가 없으면 표 없이 한 줄 인사이트만 보여준다 — '변화 없음' 판정에
    큰 표를 펼쳐 스캔할 정보만 늘리고 판단에 쓸 신호는 주지 않는 걸 방지(md와 동일 원칙).
    """
    t = build_weekly_channel_trend(d)
    mat, weeks, paid, leaders = t['matrix'], t['weeks'], t['paid'], t['leaders']
    if not t['has_signal']:
        return ("<p class='note'>합산 순위가 못 보는 <b>주차별 ROAS</b>로 효율 역전·상승 추세를 봐 예산 이동 "
                "<b>타이밍</b>을 잡습니다. 오가닉은 ROAS 측정불가라 제외.</p>"
                f"<div class='callout'><b>추이 인사이트</b> · {escape(t['insights'][0])} "
                "<span style='color:#999;font-size:12px'>(주차별 표는 리더 교체·뚜렷한 추세가 있을 때만 표시)</span></div>")
    head = "".join(f"<th>{escape(c)}</th>" for c in paid)
    rows = []
    for w in weeks:
        cells = []
        for c in paid:
            v = mat.loc[w, c]
            if pd.isna(v):
                cells.append("<td class='num'>–</td>")
            elif leaders[w] == c:
                cells.append(f"<td class='num led'>{v:.2f}</td>")
            else:
                cells.append(f"<td class='num'>{v:.2f}</td>")
        rows.append(f"<tr><td>{escape(str(w))}</td>{''.join(cells)}"
                    f"<td><span class='tag t-best'>{escape(leaders[w] or '–')}</span></td></tr>")
    ins = "".join(f"<li>{escape(s)}</li>" for s in t['insights'])
    return ("<p class='note'>합산 순위가 못 보는 <b>주차별 ROAS</b>로 효율 역전·상승 추세를 봐 예산 이동 "
            "<b>타이밍</b>을 잡습니다. 각 주 1위 셀은 강조. 오가닉은 ROAS 측정불가라 제외.</p>"
            "<div class='tbl-wrap'><table><thead><tr><th>주차</th>" + head +
            "<th>1위</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
            f"<div class='callout'><b>추이 인사이트</b><ul style='margin:6px 0 0 18px'>{ins}</ul></div>")


def _wow_channel_html(d):
    """채널별 최근 2주 변화 표 + 예산 인사이트 html — md _wow_channel_md와 같은 내용."""
    wc = d['wow_channel']
    paid = wc[wc['spend_curr'] > 0]
    rows = []
    for _, r in paid.iterrows():
        sc = "–" if pd.isna(r['spend_chg']) else f"{r['spend_chg']:+.1f}%"
        rc = "–" if pd.isna(r['roas_chg']) else f"{r['roas_chg']:+.1f}%"
        rn = "–" if pd.isna(r['roas_curr']) else f"{r['roas_curr']:.2f}"
        rc_cls = '' if pd.isna(r['roas_chg']) else ('chg-up' if r['roas_chg'] > 5 else 'chg-down' if r['roas_chg'] < -5 else '')
        rows.append(f"<tr><td>{escape(str(r['channel']))}</td><td class='lnum'>{sc}</td>"
                    f"<td class='lnum {rc_cls}'>{rc}</td><td class='lnum'>{rn}</td></tr>")
    ins = "".join(f"<li>{escape(s)}</li>" for s in build_wow_channel_insight(d))
    return ("<h4 style='font-size:13px;margin:18px 0 8px'>채널별 최근 2주 변화</h4>"
            "<p class='note'>전체 변화가 '조직이 어떻게 변했나'라면, 아래는 '어느 채널이 움직였나' — 최근 예산 인사이트의 근거.</p>"
            "<div class='tbl-wrap'><table><thead><tr><th>채널</th><th>지출 변화</th><th>ROAS 변화</th>"
            "<th>ROAS(최근)</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
            f"<div class='callout'><b>최근 2주 예산 인사이트</b><ul style='margin:6px 0 0 18px'>{ins}</ul></div>")


def _benchmark_table(ranked):
    b = ranked['benchmark']
    rows = []
    for _, r in b.iterrows():
        roas = "측정불가" if pd.isna(r['ROAS']) else f"{r['ROAS']:.2f}"
        rb = f"<span class='tag {_BAND_CLASS.get(r['roas_band'], 't-na')}'>{BAND_SHORT[r['roas_band']]}</span>"
        rows.append(f"<tr><td>{escape(r['channel'])}</td>"
                    f"<td class='num'>{r['CTR']:.2f}% <span class='tag {_BAND_CLASS.get(r['ctr_band'],'t-na')}'>{BAND_SHORT[r['ctr_band']]}</span></td>"
                    f"<td class='num'>{r['CVR']:.2f}% <span class='tag {_BAND_CLASS.get(r['cvr_band'],'t-na')}'>{BAND_SHORT[r['cvr_band']]}</span></td>"
                    f"<td class='num'>{roas} {rb}</td><td>{escape(str(r['action']))}</td></tr>")
    return ("<p class='note'>등급은 우리 주차 비교가 아니라 <b>같은 채널 업계 분포(2026 한국 시장 벤치마크)</b> 대비 위치. "
            "종합 등급은 최종 성과 ROAS 기준.</p>"
            "<div class='tbl-wrap'><table><thead><tr><th>채널</th><th>CTR</th><th>CVR</th>"
            "<th>ROAS(종합)</th><th>제안 방향</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")


def _reallocation_section_html(data):
    """예산 재배분 기획안을 insight_report(마케팅팀) 안에 흡수 — _plan_card 재사용.

    실행 체크리스트('지금 당장 할 일')는 '이번 주 업무 우선순위'(_playbook_html)의 1순위 상세로
    통합했다 — 같은 실행 단계를 두 군데(플레이북·여기)에 중복 표시하던 것을 한 곳으로 모음.
    """
    funding, plans = data['funding'], data['plans']
    title = '<div class="section-title">예산 재배분 기획안 (처방)</div>'
    intro = ("<p class='note'>위 진단의 <b>처방</b> — 예산으로 무엇을 할지. 재원은 과집행 회수분만, 데이터 오류는 제외. "
            "실행 체크리스트는 '이번 주 업무 우선순위'(1순위 상세)로 통합했습니다.</p>")
    out = []
    if funding.empty:
        out.append(f'<div class="section">{title}{intro}'
                   '<p>재원(광고비 과집행)이 없어 예산 이동 없이 현 배분을 유지합니다.</p></div>')
        return "".join(out)
    frows = "".join(f"<tr><td>{escape(f['channel'])}</td><td class='lnum'>{_won(f['recoverable_won'])}</td>"
                    f"<td class='lnum'>{_won(f['impact_won'])}</td><td class='lnum'>{f['frequency']}주</td>"
                    f"<td>{escape(str(f['weeks']))}</td></tr>" for _, f in funding.iterrows())
    fund_tbl = ("<h4 class='section-sub' style='margin-top:4px;padding-top:0;border-top:none'>재원 요약 (어디서 얼마를 회수하나)</h4>"
                "<p class='note'>회수가능액(옮길 돈)은 실지출이라 확실, 기회손실(임팩트)은 추정치.</p>"
                "<div class='tbl-wrap'><table><thead><tr><th>재원 채널</th><th>회수가능액</th>"
                "<th>기회손실(임팩트)</th><th>빈도</th><th>발생</th></tr></thead><tbody>"
                + frows + "</tbody></table></div>")
    if plans.empty:
        out.append(f'<div class="section">{title}{intro}{fund_tbl}'
                   '<p>재원은 있으나 증액 여력이 검증된 수혜처가 없어 재원을 유보합니다.</p></div>')
        return "".join(out)
    cards = "".join(_plan_card(r) for _, r in plans.iterrows())
    crit = "".join(f"<li><b>{escape(t)}</b><br>{escape(b)}</li>" for t, b in PRIORITY_CRITERIA)
    out.append(f'<div class="section">{title}{intro}{fund_tbl}'
               "<h4 class='section-sub'>재배분안 (우선순위 순)</h4>" + cards +
               "<h4 class='section-sub'>우선순위, 이렇게 정했습니다 (판단 기준)</h4>"
               f"<ol class='crit'>{crit}</ol>"
               f"<div class='callout'><b>정직한 고지</b> · {escape(PRIORITY_CAVEAT)}</div></div>")
    return "".join(out)


def build_insight_html(data):
    t = data['summary']['total']
    m = data['meta']
    stats = "".join([
        _stat(won_compact(t['total_spend']), "지출 (유료 광고비)", "", "c-blue"),
        _stat(won_compact(t['total_revenue']), "매출 (오가닉 포함)", f"MER {t['mer']:.0f}%", "c-green"),
        _stat(f"{t['paid_roi']:.0f}%", "유료 광고 순효율 (오가닉 비포함)", "", "c-purple"),
        _stat(f"{t['total_conversions']:,.0f}", "전환수(건)", "", "c-red"),
    ])
    # 성격이 비슷한 옛 섹션들을 묶어 목차 항목 수를 줄인다(md와 같은 그룹핑 원칙 공유) —
    # ROI 순위·시장 벤치마크·오가닉은 모두 '채널을 어떻게 평가하나', 전주 대비·주차별 ROAS는
    # 모두 '시간에 따른 변화'라는 같은 질문이라 하위 섹션(section-sub)으로 통합한다.
    roi_notes = ('<p class="note">ROI = 매출 / 광고비 × 100 — 광고비 대비 매출이 몇 %인지 보여주는 지표로, 이 순위의 기준입니다.</p>'
        '<p class="note">ROAS(광고 지출 대비 매출) = 매출 / 광고비(배수 표현) — 광고비 1원당 매출이 몇 원인지 보여주는 '
        '지표로, 표에서는 ROI와 나란히 참고용으로 표기합니다.</p>'
        '<p class="note">단, 이 순위는 <b>우리 채널끼리의 비교</b>일 뿐이라 1위라도 시장 전체로 보면 평범하거나 미흡할 '
        '수 있습니다. 그래서 각 채널의 ROAS 옆에 <b>같은 채널의 업계 평균</b> 대비 등급 배지를 함께 표기했습니다 '
        '— 예를 들어 이메일이 우리 채널 중 ROAS 1위여도, 업계 평균이 훨씬 높다면 배지는 평균 이하로 뜰 수 있습니다. '
        '오가닉은 광고비 0이라 ROI·ROAS 둘 다 측정 불가입니다.</p>')
    channel_eval = (f'<h4 class="section-sub">ROI 순위 (내부 비교)</h4>{roi_notes}'
                    f'{_roi_bars(data["summary"], data["roi"])}{_channel_table(data["summary"])}'
                    f'<h4 class="section-sub">시장 벤치마크 등급 (외부 비교)</h4>{_benchmark_table(data["ranked"])}')
    if 'opportunity' in data['ranked']:
        opp = data['ranked']['opportunity'].iloc[0]
        channel_eval += (f'<h4 class="section-sub">오가닉 성장 잠재력</h4>'
                    f"<div class='callout'><div class='budget-h'>{escape(str(opp['channel']))} — "
                    f"매출 {won(opp['impact_won'])}, 광고비 0원</div>"
                    f"<div class='issue-detail'><b>무슨 일인가</b> · {escape(str(opp['phenomenon']))}</div>"
                    f"<div class='issue-detail'><b>왜 중요한가</b> · {escape(str(opp['evidence']))}</div>"
                    "<div class='issue-detail'><b>어떻게 하나</b> · 광고비를 늘리는 방식이 아니라 SEO·콘텐츠 투자로 "
                    "키우는 채널입니다. 이 투자는 예산 재배분 기획안의 전략 투자처로 연결됩니다.</div></div>")
    trend = (f'<h4 class="section-sub">전주 대비 변화율 ({data["wow"].columns[0]} → {data["wow"].columns[1]})</h4>'
            f'{_wow_table(data["wow"])}{_wow_channel_html(data)}'
            f'<h4 class="section-sub">주차별 채널 효율 추이 (ROAS)</h4>{_weekly_trend_html(data)}')
    body = [
        '<div class="header"><span class="badge">마케팅팀 상세본</span>'
        '<h1>마케팅 성과 인사이트 리포트</h1><div class="header-meta">'
        '<span class="aud">대상: 마케팅팀 (경영진 요약본 별도 제공)</span>'
        f'<span>{escape(str(m["date_min"]))} – {escape(str(m["date_max"]))} ({m["n_weeks"]}주 · 주간)</span>'
        f'<span>원본 {m["n_raw"]}행 · 중복 {m["n_dup"]}·이상치 {m["n_outlier"]}·결측 {m["n_missing"]} 처리</span>'
        '<span>계산: Python pandas</span></div></div>',
        _exec_summary_html(data, top_note=_perf_def_note_html()),
        _playbook_html(data),
        (f'<div class="section"><div class="section-title">데이터 개요 및 핵심 성과 지표</div>'
         f'<div class="stats-row">{stats}</div></div>'),
        f'<div class="section"><div class="section-title">채널 효율 평가 (ROI · 시장 벤치마크 · 오가닉)</div>{channel_eval}</div>',
        f'<div class="section"><div class="section-title">추세 (전주 대비 · 주차별 ROAS)</div>{trend}</div>',
        (f'<div class="section"><div class="section-title">이슈 (비즈니스 임팩트 순)</div>'
         f'{_issue_cards(data["ranked"], data["recency"], data["threshold"])}</div>'),
        _reallocation_section_html(data),
    ]
    body.append('<div class="foot">계산: Python · 표현: HTML 대시보드 · md 리포트와 동일한 run_pipeline 결과</div>')
    return _page("마케팅 성과 인사이트 리포트", "", "\n".join(body))


def _plan_card(r):
    """재배분안 카드 — 돈의 흐름(source −금액 ➜ target +금액)을 시각화하고 '쉽게 말하면' 한 줄을 앞세운다.

    핵심 액션을 1초에 잡게 하고(플로우+효율 배수), 분석가 양식 4항목은 '자세한 근거'로 강등한다.
    """
    amt = _won(r['amount_won'])
    from_sub = f"ROAS {r['source_roas']:.2f}" if not pd.isna(r['source_roas']) else "저효율 지출"
    if r['kind'] == '광고 증액' and not pd.isna(r['target_roas']):
        to_sub = f"ROAS {r['target_roas']:.2f}"
        ratio_badge = ""
        if not pd.isna(r['source_roas']) and r['source_roas'] > 0:
            ratio_badge = f"<div class='ratio'>{r['target_roas']/r['source_roas']:.1f}배 효율 ↑</div>"
        move = f"{escape(r['source'])} → {escape(r['target'])}, {amt}(테스트 상한)으로 시작해 점진 증액 후 재측정"
        effect = (f"순증 매출 상한 약 <b>{_won(r['expected_won'])}</b> (선형확장 가정). "
                  "실제는 한계수익 체감으로 하회 가능 — 소액 테스트로 검증 후 확대하세요.")
    else:
        to_sub = "장기 자산 · 즉시 ROAS 없음"
        ratio_badge = ""
        move = f"{escape(r['source'])} → {escape(r['target'])}, {amt} 범위 내 SEO·콘텐츠 투자(광고비 직접 배정 아님)"
        effect = "오가닉은 ROAS 측정불가라 원 단위 추정 없이 정성 기대(중장기 유입 성장). 효과 발현에 시차 존재."
    flow = (f"<div class='flow'>"
            f"<div class='flow-node from'><div class='fn-name'>{escape(r['source'])}</div>"
            f"<div class='fn-roas'>{from_sub}</div><div class='fn-amt neg'>−{amt}</div></div>"
            f"<div class='flow-arrow'><div class='fa-amt'>{amt}</div><div class='fa-line'>➜</div>{ratio_badge}</div>"
            f"<div class='flow-node to'><div class='fn-name'>{escape(r['target'])}</div>"
            f"<div class='fn-roas'>{to_sub}</div><div class='fn-amt pos'>+{amt}</div></div></div>")
    lead = f"<div class='plan-lead'><b>핵심 실행</b> · {escape(plan_lead_sentence(r))}</div>"
    return (f"<div class='plan'><div class='plan-h'><span class='pr'>{r['rank']}순위</span>"
            f"예산 재배분<span style='color:#888;font-weight:400;font-size:12px;margin-left:8px'>"
            f"우선순위 점수 {r['priority_score']:,.0f} = 놓친 매출 {_won(r['impact_won'])} × 반복 {r['frequency']}주 (클수록 먼저)</span></div>"
            f"{flow}{lead}"
            "<div class='subhead'>자세한 근거</div>"
            f"<div class='issue-row'><b>무엇이 문제</b> · {escape(r['source'])} 과집행으로 회수 가능한 저효율 지출이 발생했습니다.</div>"
            f"<div class='issue-row'><b>근거 숫자</b> · 회수가능액 {amt} / {escape(r['source'])} 평소 ROAS {r['source_roas']:.2f} / 수혜 근거: {escape(str(r['basis']))}</div>"
            f"<div class='issue-row'><b>실행 방법</b> · {move}</div>"
            f"<div class='issue-row'><b>기대와 주의</b> · {effect}</div></div>")


def build_exec_html(data):
    """경영진 요약본 html — 마케팅팀 상세본과 같은 run_pipeline 결과 공유. 요약 고도만 렌더."""
    m = data['meta']
    wow = data['wow']
    # 성과 헤드라인은 최근 2주 합계로 재집계(이슈·예산은 8주 기준선 유지) — md 경영진 요약본과 동일 규칙.
    prev, curr, t = exec_perf_2w(data)
    # MER·유료 순효율·오가닉 정의는 리포트에서 처음 등장하는 '핵심 요약' 항목에 작은 글씨 부연으로 붙인다 —
    # 여기 지표 카드는 숫자만 크게 보여주고 별도 범례를 중복하지 않는다.
    perf = (f"최근 2주 성과 ({prev}→{curr})", _perf_body(t))
    stats = "".join([
        _stat(won_compact(t['total_spend']), "지출 (유료 광고비)", "", "c-blue"),
        _stat(won_compact(t['total_revenue']), "매출 (오가닉 포함)", f"MER {t['mer']:.0f}%", "c-green"),
        _stat(f"{t['paid_roi']:.0f}%", "유료 광고 순효율 (오가닉 비포함)", "", "c-purple"),
        _stat(f"{t['total_conversions']:,.0f}", "전환수(건)", "", "c-red"),
    ])
    # 최근 2주 모멘텀
    max_abs = wow['change_pct'].abs().max()
    verdict = "안정적, 급변 없음" if max_abs < 50 else "급변 발생 — 원인 확인 필요"
    mom_ins = "".join(f"<li>{escape(s)}</li>" for s in build_wow_channel_insight(data))
    momentum = (f"<p class='mom-lead'>매출 {wow.loc['revenue','change_pct']:+.1f}%, 지출 {wow.loc['spend','change_pct']:+.1f}% "
                f"({escape(str(prev))}→{escape(str(curr))}) — {verdict}.</p>"
                f"<div class='callout'><b>채널 인사이트</b><ul style='margin:6px 0 0 18px'>{mom_ins}</ul></div>")
    # 핵심 이슈 (예산·매출 직결)
    loss = data['ranked'].get('loss')
    act = None if loss is None or loss.empty else loss[loss['lever'] != '데이터·트래킹']
    if act is None or act.empty:
        issues = "<p>현재 예산·매출 직결 손실 이슈 없음.</p>"
    else:
        li = "".join(
            f"<li><b>{escape(r['channel'])} {escape(r['type'])}</b> — 기회손실 {escape(won_compact(r['impact_won']))} "
            f"({escape(str(r['weeks']))}, 최근 8주 중 {r['frequency']}주 반복 발생)"
            f"<div class='issue-detail'><b>무슨 일인가</b> · {escape(str(r['phenomenon']))} {escape(str(r['evidence']))}</div>"
            f"<div class='issue-detail'><b>어떻게 대응하나</b> · 이 채널에서 평소보다 더 쓴 광고비를 회수해, "
            "시장 평균보다 효율이 좋은 다른 채널로 옮기는 예산 재배분을 진행할 예정입니다. "
            "옮길 금액과 수혜 채널은 아래 '예산 재배분 결정' 섹션에서 확인할 수 있습니다.</div></li>"
            for _, r in act.iterrows())
        issues = (f"<p class='note'>예산·매출 직결 이슈만. 데이터 정정(이상치·결측)은 마케팅팀 리포트에서 처리·수집팀 요청. "
                  f"이 이슈·재배분은 이상 탐지에 기준선이 필요해 <b>최근 8주 누적</b>으로 판단합니다(성과 헤드라인만 최근 2주).</p>"
                  f"<ul style='margin:2px 0 0 18px'>{li}</ul>")
    # 예산 재배분 결정 (승인 요청)
    plans = data['plans']
    if plans.empty:
        budget = "<p>재배분 재원(과집행 회수분)이 탐지되지 않아 현 예산 배분을 유지할 것을 권고합니다.</p>"
    else:
        p = plans.iloc[0]
        src, tgt = escape(p['source']), escape(p['target'])
        exp_line = (f"<div class='budget-line'><b>기대 효과</b> · 선형확장을 가정하면, 이번 재배분으로 기대되는 "
                    f"순증 매출 상한은 약 <b>{won_compact(p['expected_won'])}</b>입니다.</div>"
                    if not pd.isna(p['expected_won']) else "")
        # 한 문단 서술형(4문장 연속)은 승인권자가 핵심을 놓치기 쉬워, 핵심이슈 섹션과 같은
        # '헤드라인 + 짧은 문장 단위 라벨' 구조로 통일 — 문장은 유지하되 항목별로 끊어 가독성 확보.
        budget = ("<div class='callout'>"
                  f"<div class='budget-h'>{src} → {tgt}로 {won_compact(p['amount_won'])} 재배분 (1순위)</div>"
                  f"<div class='budget-line'><b>무엇을 하나</b> · {src}에서 예산을 과집행해 회수 가능한 지출 "
                  f"{won_compact(p['amount_won'])}을, 시장 벤치마크 대비 효율이 검증된 {tgt}로 옮기는 안입니다.</div>"
                  f"{exp_line}"
                  "<div class='budget-line'><b>실행 방식</b> · 전액을 바로 옮기지 않고 소액 테스트로 먼저 시작해, "
                  "2주 후 ROAS를 재측정한 뒤 개선이 확인되면 점차 확대합니다(상세 실행안·우선순위 로직은 "
                  "마케팅팀 리포트 참조).</div>"
                  "<div class='budget-line'><b>승인 요청</b> · 위 재배분안의 집행 승인을 요청합니다.</div>"
                  "</div>")
    # 관련 채널 효율 비교 (참고) — 전체 채널 순위표 대신 재배분에 관련된 재원·수혜 두 채널만 노출.
    compare_section = ""
    if not plans.empty:
        p = plans.iloc[0]
        g = data['summary']['by_channel']
        rows = []
        for ch, role in [(p['source'], '재원 (과집행 회수처)'), (p['target'], '수혜 (재배분 투입처)')]:
            r = g.loc[ch]
            roas = "측정불가" if pd.isna(r['ROAS']) else f"{r['ROAS']:.2f}"
            rows.append(f"<tr><td>{escape(ch)}</td><td>{escape(role)}</td><td class='lnum'>{won(r['spend'])}</td>"
                        f"<td class='lnum'>{won(r['revenue'])}</td><td class='lnum'>{roas}</td></tr>")
        compare_table = ("<p class='note'>이번 재배분 결정에 관련된 두 채널만 비교합니다. 전체 채널 효율은 마케팅팀 리포트를 참조하세요.</p>"
                         "<div class='tbl-wrap'><table><thead><tr><th>채널</th><th>역할</th><th>광고비</th>"
                         "<th>매출</th><th>ROAS</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")
        compare_section = (f'<div class="section rx"><div class="section-title">관련 채널 효율 비교 (참고)</div>'
                           f'{compare_table}</div>')
    body = [
        '<div class="header rx"><span class="badge rx">경영진 요약</span>'
        f'<span class="badge rx" style="background:#b91c1c">최근 2주({escape(str(prev))}→{escape(str(curr))}) 전주 대비 기준</span>'
        '<h1>마케팅 성과 경영진 요약 리포트</h1><div class="header-meta">'
        '<span class="aud">대상: 경영진</span>'
        f'<span>분석 기준: 최근 2주 ({escape(str(prev))}→{escape(str(curr))}) 전주 대비 · 성과 수치는 최근 2주 합계</span>'
        '<span>이 한 장으로 성과·위험·예산 결정 판단 · 8주 전체 상세는 마케팅팀 리포트</span></div></div>',
        _exec_summary_html(data, exclude_prefixes=('데이터 정정',), perf=perf,
                           title="핵심 요약", show_note=False, compact=True, dual_window=True,
                           top_note=_perf_def_note_html()),
        f'<div class="section rx"><div class="section-title">핵심 성과 지표 · 최근 2주</div>'
        f'<div class="stats-row">{stats}</div></div>',
        f'<div class="section rx"><div class="section-title">최근 2주 모멘텀</div>'
        f'<div class="def-note">{_roas_def_note_html()}</div>{momentum}</div>',
        f'<div class="section rx"><div class="section-title">핵심 이슈 (예산·매출 직결)</div>{issues}</div>',
        f'<div class="section rx"><div class="section-title">예산 재배분 결정 (승인 요청)</div>{budget}</div>',
        compare_section,
        '<div class="foot">계산: Python · 마케팅팀 상세 리포트와 동일한 run_pipeline 결과</div>',
    ]
    return _page("마케팅 성과 경영진 요약 리포트", "rx", "\n".join(body))


if __name__ == '__main__':
    data_path = sys.argv[1] if len(sys.argv) > 1 else 'data/marketing_performance.csv'
    d = run_pipeline(data_path)   # 한 번 실행해 두 HTML(마케팅팀·경영진)이 같은 결과를 공유
    for out, builder in [(INSIGHT_OUT, build_insight_html), (EXEC_OUT, build_exec_html)]:
        html = builder(d)
        with open(out, 'w') as f:
            f.write(html)
        print(f"생성 완료: {out} ({len(html):,}자)")
