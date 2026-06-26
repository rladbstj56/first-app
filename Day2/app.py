import streamlit as st
import pandas as pd

st.set_page_config(page_title="대출 심사 대시보드", layout="wide")

st.markdown("""
<style>
    html, body, [class*="css"] {
        font-family: 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
    }
    h1 { color: #2E3250; font-weight: 800; font-size: 2.2rem; padding-bottom: 0.2rem; }
    h3 { color: #2E3250; font-weight: 700; margin-top: 0.5rem; }
    [data-testid="metric-container"] {
        background-color: #ffffff;
        border: 1px solid #DDE1F0;
        border-radius: 16px;
        padding: 20px 28px;
        box-shadow: 0 2px 8px rgba(92, 107, 192, 0.08);
    }
    [data-testid="metric-container"] label { font-size: 0.9rem; color: #7B83B0; font-weight: 600; }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        font-size: 2rem; font-weight: 800; color: #5C6BC0;
    }
    [data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; border: 1px solid #DDE1F0; }
    hr { border: none; border-top: 1.5px solid #DDE1F0; margin: 1rem 0; }
    .upload-box {
        background: #F4F5FB;
        border: 1.5px dashed #B0B8E0;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("# 대출 심사 대시보드")
st.markdown("<p style='color:#7B83B0; margin-top:-12px; font-size:0.95rem;'>대출 신청 데이터와 심사 결과 데이터를 업로드하면 통합 현황을 확인할 수 있습니다.</p>", unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

# ── 파일 업로드 ─────────────────────────────────────────────────────────────────
col_up1, col_up2 = st.columns(2)
with col_up1:
    st.markdown("**📄 대출 신청 파일** (`loan_applications.xlsx`)")
    app_file = st.file_uploader("대출 신청 파일 업로드", type=["xlsx"], key="app", label_visibility="collapsed")
with col_up2:
    st.markdown("**📋 심사 결과 파일** (`loan_screening_results.xlsx`)")
    screen_file = st.file_uploader("심사 결과 파일 업로드", type=["xlsx"], key="screen", label_visibility="collapsed")

if not app_file or not screen_file:
    st.info("두 파일을 모두 업로드하면 대시보드가 표시됩니다.")
    st.stop()

# ── 데이터 로드 & 머지 ───────────────────────────────────────────────────────────
df_app = pd.read_excel(app_file)
df_screen = pd.read_excel(screen_file)

df = pd.merge(df_app, df_screen, on="customer_id", how="left")
df["apply_date"] = pd.to_datetime(df["apply_date"])
df["approval_yn"] = df["approval_yn"].fillna(0).astype(int)

# ── 필터 ────────────────────────────────────────────────────────────────────────
with st.expander("🔍 필터", expanded=True):
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        all_purposes = sorted(df["loan_purpose"].dropna().unique().tolist())
        sel_purpose = st.multiselect("대출 목적", options=all_purposes, default=all_purposes)
    with fc2:
        all_channels = sorted(df["channel"].dropna().unique().tolist())
        sel_channel = st.multiselect("채널", options=all_channels, default=all_channels)
    with fc3:
        all_reviewers = sorted(df["reviewer_type"].dropna().unique().tolist())
        sel_reviewer = st.multiselect("심사자 유형", options=all_reviewers, default=all_reviewers)

mask = df["loan_purpose"].isin(sel_purpose) & df["channel"].isin(sel_channel)
if sel_reviewer:
    mask &= df["reviewer_type"].isin(sel_reviewer)
filtered = df[mask]

st.markdown("<hr>", unsafe_allow_html=True)

# ── KPI 카드 ─────────────────────────────────────────────────────────────────────
total_count = len(filtered)
approved = filtered["approval_yn"].sum()
approval_rate = approved / total_count * 100 if total_count > 0 else 0
avg_requested = filtered["requested_amount"].mean() if total_count > 0 else 0
avg_rate = filtered["interest_rate"].dropna().mean() if total_count > 0 else 0
avg_approved = filtered.loc[filtered["approval_yn"] == 1, "approved_amount"].mean()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("총 신청 건수", f"{total_count:,} 건")
k2.metric("승인 건수", f"{int(approved):,} 건")
k3.metric("승인율", f"{approval_rate:.1f}%")
k4.metric("평균 신청 금액", f"₩ {avg_requested:,.0f}")
k5.metric("평균 이자율", f"{avg_rate:.2f}%")

st.markdown("<hr>", unsafe_allow_html=True)

# ── 차트 1행: 승인/거절 + 대출 목적별 ────────────────────────────────────────────
row1_c1, row1_c2 = st.columns(2, gap="large")

with row1_c1:
    st.markdown("### 승인 / 거절 현황")
    approval_df = filtered["approval_yn"].value_counts().reset_index()
    approval_df.columns = ["승인여부", "건수"]
    approval_df["승인여부"] = approval_df["승인여부"].map({1: "승인", 0: "거절"})
    st.bar_chart(approval_df.set_index("승인여부")["건수"], color="#5C6BC0")

with row1_c2:
    st.markdown("### 대출 목적별 신청 건수")
    purpose_df = (
        filtered.groupby("loan_purpose", as_index=False)
        .size()
        .rename(columns={"loan_purpose": "대출목적", "size": "건수"})
        .sort_values("건수", ascending=False)
    )
    st.bar_chart(purpose_df.set_index("대출목적")["건수"], color="#7986CB")

# ── 차트 2행: 채널별 + 심사자 유형별 ─────────────────────────────────────────────
row2_c1, row2_c2 = st.columns(2, gap="large")

with row2_c1:
    st.markdown("### 채널별 신청 현황")
    channel_df = (
        filtered.groupby("channel", as_index=False)
        .size()
        .rename(columns={"channel": "채널", "size": "건수"})
        .sort_values("건수", ascending=False)
    )
    st.bar_chart(channel_df.set_index("채널")["건수"], color="#9575CD")

with row2_c2:
    st.markdown("### 심사자 유형별 승인율")
    reviewer_stats = (
        filtered.groupby("reviewer_type")
        .agg(total=("approval_yn", "count"), approved=("approval_yn", "sum"))
        .reset_index()
    )
    reviewer_stats["승인율(%)"] = (reviewer_stats["approved"] / reviewer_stats["total"] * 100).round(1)
    reviewer_stats = reviewer_stats.rename(columns={"reviewer_type": "심사자유형"})
    st.bar_chart(reviewer_stats.set_index("심사자유형")["승인율(%)"], color="#4DB6AC")

st.markdown("<hr>", unsafe_allow_html=True)

# ── 신용점수 분포 + DTI 분포 ──────────────────────────────────────────────────────
row3_c1, row3_c2 = st.columns(2, gap="large")

with row3_c1:
    st.markdown("### NICE 신용점수 분포")
    score_data = filtered["nice_credit_score"].dropna()
    if not score_data.empty:
        bins = list(range(300, 1001, 50))
        score_hist = pd.cut(score_data, bins=bins).value_counts().sort_index()
        score_hist.index = [str(i) for i in score_hist.index]
        st.bar_chart(score_hist, color="#FF8A65")
    else:
        st.info("신용점수 데이터가 없습니다.")

with row3_c2:
    st.markdown("### DTI 비율 분포")
    dti_data = filtered["dti_ratio"].dropna()
    if not dti_data.empty:
        dti_bins = list(range(0, 101, 10))
        dti_hist = pd.cut(dti_data, bins=dti_bins).value_counts().sort_index()
        dti_hist.index = [str(i) for i in dti_hist.index]
        st.bar_chart(dti_hist, color="#F06292")
    else:
        st.info("DTI 데이터가 없습니다.")

st.markdown("<hr>", unsafe_allow_html=True)

# ── 거절 사유 테이블 ──────────────────────────────────────────────────────────────
st.markdown("### 거절 사유 분석")
rejected = filtered[filtered["approval_yn"] == 0]["reject_reason"].dropna()
if not rejected.empty:
    reject_df = (
        rejected.value_counts()
        .reset_index()
        .rename(columns={"reject_reason": "거절 사유", "count": "건수"})
    )
    reject_df["비율"] = (reject_df["건수"] / reject_df["건수"].sum() * 100).round(1).astype(str) + "%"
    st.dataframe(reject_df, use_container_width=True, hide_index=True)
else:
    st.info("거절 건수가 없거나 거절 사유 데이터가 없습니다.")

st.markdown("<hr>", unsafe_allow_html=True)

# ── 머지된 전체 데이터 테이블 ─────────────────────────────────────────────────────
with st.expander("📊 머지된 전체 데이터 보기", expanded=False):
    display_df = filtered.copy()
    display_df["approval_yn"] = display_df["approval_yn"].map({1: "승인", 0: "거절"})
    display_df["requested_amount"] = display_df["requested_amount"].apply(lambda x: f"₩ {x:,.0f}")
    display_df["approved_amount"] = display_df["approved_amount"].apply(
        lambda x: f"₩ {x:,.0f}" if pd.notna(x) else "-"
    )
    st.dataframe(display_df.reset_index(drop=True), use_container_width=True)
