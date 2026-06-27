import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, date, timedelta
from supabase import create_client, Client
import os

# ── 설정 ──────────────────────────────────────────────
st.set_page_config(page_title="운동 대시보드", page_icon="💪", layout="wide")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://kdsoofhefenuxkratcbf.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imtkc29vZmhlZmVudXhrcmF0Y2JmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIyODg4NTQsImV4cCI6MjA5Nzg2NDg1NH0.ibc6qTCArbY4z4w757O2hTogKYNhdGw1__zN80tsXpU")

@st.cache_resource
def get_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_client()

# 운동 유형 정의
WORKOUT_TYPES = {
    "폼롤러":      {"category": "회복",   "emoji": "🧘",    "kcal_per_min": 2.5},
    "요가":        {"category": "유연성", "emoji": "🧘‍♀️", "kcal_per_min": 3.5},
    "헬스장":      {"category": "근력",   "emoji": "🏋️",   "kcal_per_min": 6.0},
    "천국의계단":  {"category": "유산소", "emoji": "🪜",    "kcal_per_min": 9.5},
    "러닝":        {"category": "유산소", "emoji": "🏃",    "kcal_per_min": 9.0},
    "사이클":      {"category": "유산소", "emoji": "🚴",    "kcal_per_min": 7.5},
    "수영":        {"category": "유산소", "emoji": "🏊",    "kcal_per_min": 8.0},
    "필라테스":    {"category": "근력",   "emoji": "🤸",    "kcal_per_min": 4.5},
    "홈트":        {"category": "근력",   "emoji": "🏠",    "kcal_per_min": 5.5},
    "기타":        {"category": "기타",   "emoji": "⚡",    "kcal_per_min": 5.0},
}

CATEGORY_COLORS = {
    "유산소": "#FF6B6B",
    "근력":   "#4ECDC4",
    "유연성": "#45B7D1",
    "회복":   "#96CEB4",
    "기타":   "#FFEAA7",
}

WEEK_GOAL = 5


# ── DB 헬퍼 ──────────────────────────────────────────
def load_workouts() -> pd.DataFrame:
    res = supabase.table("workouts").select("*").order("date", desc=True).execute()
    if res.data:
        df = pd.DataFrame(res.data)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df
    return pd.DataFrame(columns=["id","date","workout","category","duration_min","intensity","memo","kcal"])


def load_inbody() -> pd.DataFrame:
    res = supabase.table("inbody").select("*").order("date").execute()
    if res.data:
        df = pd.DataFrame(res.data)
        df["date"] = pd.to_datetime(df["date"])
        return df
    return pd.DataFrame(columns=["id","date","weight","body_fat_pct","muscle_kg","fat_kg","bmi","memo"])


def insert_workout(record: dict):
    supabase.table("workouts").insert(record).execute()


def delete_workout(workout_id: str):
    supabase.table("workouts").delete().eq("id", workout_id).execute()


def insert_inbody(record: dict):
    supabase.table("inbody").upsert(record, on_conflict="date").execute()


# ── 유틸 ──────────────────────────────────────────────
def get_week_range(target: date):
    monday = target - timedelta(days=target.weekday())
    return monday, monday + timedelta(days=6)


def week_label(d: date):
    m, s = get_week_range(d)
    return f"{m.strftime('%m/%d')} ~ {s.strftime('%m/%d')}"


def metric_card(label, value, delta=None, delta_color="normal"):
    delta_html = ""
    if delta is not None:
        color = "#2ecc71" if delta_color == "good" else ("#e74c3c" if delta_color == "bad" else "#aaa")
        if isinstance(delta, str):
            arrow = "▲" if delta.startswith('+') else "▼" if delta.startswith('-') else "─"
            delta_html = f'<p style="margin:0;font-size:.85rem;color:{color}">{arrow} {delta}</p>'
        else:
            arrow = "▲" if delta > 0 else "▼" if delta < 0 else "─"
            delta_html = f'<p style="margin:0;font-size:.85rem;color:{color}">{arrow} {abs(delta)}</p>'
    return f"""
    <div style="background:#1e1e2e;border-radius:12px;padding:18px 20px;border:1px solid #2a2a3e">
      <p style="margin:0;font-size:.8rem;color:#aaa;letter-spacing:.05em">{label}</p>
      <p style="margin:4px 0 2px;font-size:1.8rem;font-weight:700;color:#fff">{value}</p>
      {delta_html}
    </div>"""


# ── 사이드바 ──────────────────────────────────────────
st.sidebar.title("💪 운동 대시보드")
page = st.sidebar.radio(
    "메뉴",
    ["🏠 홈 / 이번 주", "📅 이번 달", "➕ 운동 기록", "📊 분석", "⚖️ 인바디", "🗂️ 전체 기록"],
    label_visibility="collapsed",
)
st.sidebar.markdown("---")
st.sidebar.markdown(f"**주 목표:** {WEEK_GOAL}일 이상")
today = date.today()
st.sidebar.markdown(f"**오늘:** {today.strftime('%Y년 %m월 %d일')}")


# ══════════════════════════════════════════════════════
# 1. 홈 / 이번 주
# ══════════════════════════════════════════════════════
if page == "🏠 홈 / 이번 주":
    st.title("🏠 이번 주 운동 현황")

    df = load_workouts()
    mon, sun = get_week_range(today)

    week_df = df[(df["date"] >= mon) & (df["date"] <= sun)] if not df.empty else pd.DataFrame()

    workout_days = week_df["date"].nunique() if not week_df.empty else 0
    total_min    = int(week_df["duration_min"].sum()) if not week_df.empty else 0
    total_kcal   = int(week_df["kcal"].sum()) if not week_df.empty else 0
    sessions     = len(week_df)

    col1, col2, col3, col4 = st.columns(4)
    col1.markdown(metric_card("이번 주 운동 일수", f"{workout_days} / {WEEK_GOAL}일"), unsafe_allow_html=True)
    col2.markdown(metric_card("총 운동 시간", f"{total_min//60}h {total_min%60}m"), unsafe_allow_html=True)
    col3.markdown(metric_card("소모 칼로리", f"{total_kcal:,} kcal"), unsafe_allow_html=True)
    col4.markdown(metric_card("총 세션 수", f"{sessions}회"), unsafe_allow_html=True)

    progress = min(workout_days / WEEK_GOAL, 1.0)
    bar_color = "#2ecc71" if progress >= 1.0 else "#f39c12" if progress >= 0.6 else "#e74c3c"
    st.markdown(f"""
    <br>
    <div style="background:#2a2a3e;border-radius:10px;height:20px;overflow:hidden;margin-bottom:6px">
      <div style="width:{progress*100:.0f}%;height:100%;background:{bar_color};border-radius:10px;
                  display:flex;align-items:center;justify-content:center">
        <span style="font-size:.75rem;font-weight:700;color:#fff">{progress*100:.0f}%</span>
      </div>
    </div>
    <p style="text-align:center;color:#aaa;font-size:.85rem">
      목표까지 <b style="color:#fff">{max(WEEK_GOAL-workout_days,0)}일</b> 남음 ({week_label(today)})
    </p>""", unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("📆 이번 주 캘린더")
    days_kr = ["월","화","수","목","금","토","일"]
    worked_days = set(week_df["date"].tolist()) if not week_df.empty else set()
    cols = st.columns(7)
    for i, col in enumerate(cols):
        d = mon + timedelta(days=i)
        is_today = (d == today)
        worked = d in worked_days
        border = "2px solid #f39c12" if is_today else "1px solid #2a2a3e"
        bg = "#2ecc71" if worked else "#1e1e2e"
        emoji = "✅" if worked else ("📍" if is_today else "○")
        col.markdown(f"""
        <div style="border:{border};background:{bg};border-radius:10px;padding:14px 8px;text-align:center">
          <p style="margin:0;font-size:.9rem;color:#ddd">{days_kr[i]}</p>
          <p style="margin:4px 0;font-size:1.2rem">{emoji}</p>
          <p style="margin:0;font-size:.75rem;color:#aaa">{d.strftime('%m/%d')}</p>
        </div>""", unsafe_allow_html=True)

    if not week_df.empty:
        st.markdown("---")
        st.subheader(f"이번 주 운동 목록")
        for _, row in week_df.sort_values("date", ascending=False).iterrows():
            emoji = WORKOUT_TYPES.get(row["workout"], {}).get("emoji", "⚡")
            color = CATEGORY_COLORS.get(row.get("category",""), "#888")
            col_a, col_b = st.columns([6, 1])
            with col_a:
                st.markdown(f"""
                <div style="background:#1e1e2e;border-left:4px solid {color};
                            border-radius:8px;padding:12px 16px;margin-bottom:8px">
                  {emoji} <b>{row['workout']}</b>
                  <span style="color:{color};font-size:.8rem;margin-left:8px">{row['category']}</span>
                  <span style="color:#aaa;float:right;font-size:.85rem">
                    {row['date']} | {int(row['duration_min'])}분 | {int(row['kcal'])} kcal
                  </span>
                  {"<br><span style='color:#aaa;font-size:.82rem'>" + str(row['memo']) + "</span>" if row.get('memo') else ""}
                </div>""", unsafe_allow_html=True)
            with col_b:
                if st.button("🗑️", key=f"del_{row['id']}"):
                    delete_workout(str(row["id"]))
                    st.rerun()
    else:
        st.info("이번 주 기록된 운동이 없습니다. '운동 기록' 메뉴에서 추가해보세요! 💪")


# ══════════════════════════════════════════════════════
# 2. 이번 달
# ══════════════════════════════════════════════════════
elif page == "📅 이번 달":
    st.title(f"📅 {today.strftime('%Y년 %m월')} 통계")

    df = load_workouts()
    if df.empty:
        st.info("기록된 운동이 없습니다.")
        st.stop()

    month_df = df[
        (df["date"].apply(lambda x: x.year) == today.year) &
        (df["date"].apply(lambda x: x.month) == today.month)
    ]
    if month_df.empty:
        st.info("이번 달 기록된 운동이 없습니다.")
        st.stop()

    total_days = month_df["date"].nunique()
    total_min  = int(month_df["duration_min"].sum())
    total_kcal = int(month_df["kcal"].sum())
    month_df = month_df.copy()
    month_df["week"] = month_df["date"].apply(lambda x: x.isocalendar()[1])
    avg_days_per_week = round(month_df.groupby("week")["date"].nunique().mean(), 1)

    col1, col2, col3, col4 = st.columns(4)
    col1.markdown(metric_card("운동 일수", f"{total_days}일"), unsafe_allow_html=True)
    col2.markdown(metric_card("총 운동 시간", f"{total_min//60}h {total_min%60}m"), unsafe_allow_html=True)
    col3.markdown(metric_card("총 소모 칼로리", f"{total_kcal:,} kcal"), unsafe_allow_html=True)
    goal_color = "good" if avg_days_per_week >= WEEK_GOAL else "bad"
    col4.markdown(metric_card("주 평균 운동일", f"{avg_days_per_week}일",
                               delta=avg_days_per_week-WEEK_GOAL, delta_color=goal_color), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("날짜별 운동 시간")
        daily = month_df.groupby(["date","category"])["duration_min"].sum().reset_index()
        daily["date"] = daily["date"].astype(str)
        fig = px.bar(daily, x="date", y="duration_min", color="category",
                     color_discrete_map=CATEGORY_COLORS,
                     labels={"duration_min":"시간(분)","date":"날짜","category":"분류"})
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
                          font_color="#ddd",height=300,legend_title_text="",
                          xaxis=dict(gridcolor="#2a2a3e"),yaxis=dict(gridcolor="#2a2a3e"))
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader("카테고리별 비율 (시간)")
        cat_sum = month_df.groupby("category")["duration_min"].sum().reset_index()
        fig2 = px.pie(cat_sum, names="category", values="duration_min",
                      color="category", color_discrete_map=CATEGORY_COLORS, hole=0.45)
        fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
                           font_color="#ddd",height=300)
        fig2.update_traces(textinfo="label+percent")
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("주별 운동 일수")
    weekly = month_df.groupby("week")["date"].nunique().reset_index()
    weekly.columns = ["week","days"]
    fig3 = go.Figure()
    fig3.add_trace(go.Bar(x=weekly["week"].astype(str), y=weekly["days"],
                          name="실제 일수", marker_color="#4ECDC4"))
    fig3.add_trace(go.Scatter(x=weekly["week"].astype(str), y=[WEEK_GOAL]*len(weekly),
                               name="목표", mode="lines+markers",
                               line=dict(color="#FF6B6B",dash="dash",width=2)))
    fig3.update_layout(plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
                       font_color="#ddd",height=280,
                       xaxis=dict(title="주차",gridcolor="#2a2a3e"),
                       yaxis=dict(title="운동 일수",gridcolor="#2a2a3e"),
                       legend=dict(orientation="h",yanchor="bottom",y=1.02))
    st.plotly_chart(fig3, use_container_width=True)


# ══════════════════════════════════════════════════════
# 3. 운동 기록 추가
# ══════════════════════════════════════════════════════
elif page == "➕ 운동 기록":
    st.title("➕ 운동 기록 추가")

    with st.form("workout_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            workout_date = st.date_input("날짜", value=today)
            workout_type = st.selectbox("운동 종류", list(WORKOUT_TYPES.keys()),
                                         format_func=lambda x: f"{WORKOUT_TYPES[x]['emoji']} {x}")
        with col2:
            duration = st.number_input("운동 시간 (분)", min_value=5, max_value=300, value=60, step=5)
            intensity = st.select_slider("강도",
                                          options=["매우 낮음","낮음","보통","높음","매우 높음"],
                                          value="보통")

        memo = st.text_area("메모 (선택)", placeholder="오늘의 운동 메모를 남겨보세요...")

        intensity_mult = {"매우 낮음":0.7,"낮음":0.85,"보통":1.0,"높음":1.15,"매우 높음":1.3}
        est_kcal = int(duration * WORKOUT_TYPES[workout_type]["kcal_per_min"] * intensity_mult[intensity])

        st.info(f"💡 예상 소모 칼로리: **{est_kcal} kcal** ({workout_type}, {duration}분, 강도: {intensity})")

        if st.form_submit_button("✅ 기록 저장", use_container_width=True, type="primary"):
            record = {
                "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                "date": str(workout_date),
                "workout": workout_type,
                "category": WORKOUT_TYPES[workout_type]["category"],
                "duration_min": duration,
                "intensity": intensity,
                "memo": memo,
                "kcal": est_kcal,
            }
            insert_workout(record)
            st.success(f"🎉 {workout_type} {duration}분 기록 완료! ({est_kcal} kcal 소모 예상)")
            st.balloons()

    df = load_workouts()
    if not df.empty:
        today_df = df[df["date"] == today]
        if not today_df.empty:
            st.markdown("---")
            st.subheader(f"오늘({today.strftime('%m/%d')}) 기록")
            for _, row in today_df.iterrows():
                emoji = WORKOUT_TYPES.get(row["workout"],{}).get("emoji","⚡")
                color = CATEGORY_COLORS.get(row.get("category",""),"#888")
                col_a, col_b = st.columns([5,1])
                with col_a:
                    st.markdown(f"""
                    <div style="background:#1e1e2e;border-left:4px solid {color};
                                border-radius:8px;padding:10px 14px">
                      {emoji} <b>{row['workout']}</b> | {int(row['duration_min'])}분 |
                      강도: {row['intensity']} | {int(row['kcal'])} kcal
                      {"<br><span style='color:#aaa;font-size:.82rem'>" + str(row['memo']) + "</span>" if row.get('memo') else ""}
                    </div>""", unsafe_allow_html=True)
                with col_b:
                    if st.button("🗑️ 삭제", key=f"del_{row['id']}"):
                        delete_workout(str(row["id"]))
                        st.rerun()


# ══════════════════════════════════════════════════════
# 4. 분석
# ══════════════════════════════════════════════════════
elif page == "📊 분석":
    st.title("📊 운동 분석")

    df = load_workouts()
    if df.empty:
        st.info("분석할 데이터가 없습니다.")
        st.stop()

    df2 = df.copy()
    df2["date_dt"] = pd.to_datetime(df2["date"])
    df2["week"]    = df2["date_dt"].dt.to_period("W").astype(str)

    period = st.selectbox("기간 선택", ["최근 4주","최근 3개월","전체"])
    cutoff = (datetime.now() - timedelta(weeks=4) if period == "최근 4주"
              else datetime.now() - timedelta(days=90) if period == "최근 3개월"
              else df2["date_dt"].min())
    filtered = df2[df2["date_dt"] >= cutoff]

    st.markdown("---")
    st.subheader("📈 유산소 vs 근력 주간 트렌드")
    trend = filtered.groupby(["week","category"])["duration_min"].sum().reset_index()
    trend_pivot = trend.pivot(index="week",columns="category",values="duration_min").fillna(0).reset_index()
    fig = go.Figure()
    for cat, color in CATEGORY_COLORS.items():
        if cat in trend_pivot.columns:
            fig.add_trace(go.Scatter(x=trend_pivot["week"], y=trend_pivot[cat],
                                     name=cat, mode="lines+markers",
                                     line=dict(color=color,width=2), marker=dict(size=6)))
    fig.update_layout(plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
                      font_color="#ddd",height=320,
                      xaxis=dict(title="주차",gridcolor="#2a2a3e"),
                      yaxis=dict(title="운동 시간(분)",gridcolor="#2a2a3e"),
                      legend=dict(orientation="h",yanchor="bottom",y=1.02))
    st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🏅 운동 종류별 누적 시간")
        by_type = filtered.groupby("workout")["duration_min"].sum().sort_values(ascending=True).reset_index()
        by_type["label"] = by_type["workout"].apply(
            lambda x: f"{WORKOUT_TYPES.get(x,{}).get('emoji','⚡')} {x}")
        fig2 = px.bar(by_type, x="duration_min", y="label", orientation="h",
                      color="duration_min", color_continuous_scale="teal",
                      labels={"duration_min":"시간(분)","label":""})
        fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
                           font_color="#ddd",height=300,coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)

    with col2:
        st.subheader("🔥 주간 칼로리 소모")
        kcal_week = filtered.groupby("week")["kcal"].sum().reset_index()
        fig3 = px.bar(kcal_week, x="week", y="kcal", color="kcal",
                      color_continuous_scale="Reds",
                      labels={"kcal":"소모 칼로리","week":"주차"})
        fig3.update_layout(plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
                           font_color="#ddd",height=300,coloraxis_showscale=False)
        st.plotly_chart(fig3, use_container_width=True)

    st.subheader("⚡ 운동 강도 분포")
    intensity_order = ["매우 낮음","낮음","보통","높음","매우 높음"]
    cnt = filtered["intensity"].value_counts().reindex(intensity_order,fill_value=0).reset_index()
    cnt.columns = ["intensity","count"]
    fig4 = px.bar(cnt, x="intensity", y="count", color="intensity",
                  color_discrete_sequence=["#96CEB4","#45B7D1","#4ECDC4","#f39c12","#FF6B6B"],
                  labels={"count":"세션 수","intensity":"강도"})
    fig4.update_layout(plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
                       font_color="#ddd",height=280,showlegend=False)
    st.plotly_chart(fig4, use_container_width=True)

    st.subheader("📅 요일별 운동 패턴")
    days_kr_map = {0:"월",1:"화",2:"수",3:"목",4:"금",5:"토",6:"일"}
    filtered = filtered.copy()
    filtered["요일"] = filtered["date_dt"].dt.dayofweek.map(days_kr_map)
    dow = filtered.groupby("요일")["duration_min"].mean().reindex(
        ["월","화","수","목","금","토","일"], fill_value=0).reset_index()
    fig5 = px.bar(dow, x="요일", y="duration_min", color="duration_min",
                  color_continuous_scale="Blues",
                  labels={"duration_min":"평균 운동 시간(분)","요일":""})
    fig5.update_layout(plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
                       font_color="#ddd",height=260,coloraxis_showscale=False)
    st.plotly_chart(fig5, use_container_width=True)


# ══════════════════════════════════════════════════════
# 5. 인바디
# ══════════════════════════════════════════════════════
elif page == "⚖️ 인바디":
    st.title("⚖️ 인바디 기록")

    tab1, tab2 = st.tabs(["📝 기록 추가", "📈 변화 추이"])

    with tab1:
        with st.form("inbody_form", clear_on_submit=True):
            st.subheader("인바디 측정 결과 입력")
            col1, col2 = st.columns(2)
            with col1:
                ib_date      = st.date_input("측정일", value=today)
                weight       = st.number_input("체중 (kg)", min_value=30.0, max_value=200.0, value=65.0, step=0.1, format="%.1f")
                body_fat_pct = st.number_input("체지방률 (%)", min_value=3.0, max_value=60.0, value=20.0, step=0.1, format="%.1f")
            with col2:
                muscle_kg = st.number_input("골격근량 (kg)", min_value=10.0, max_value=80.0, value=28.0, step=0.1, format="%.1f")
                fat_kg    = round(weight * body_fat_pct / 100, 1)
                bmi       = round(weight / (1.70 ** 2), 1)
                st.metric("체지방량 (kg)", fat_kg)
                st.metric("BMI", bmi)

            ib_memo = st.text_area("메모", placeholder="측정 당시 상태, 식사 여부 등...")
            if st.form_submit_button("✅ 저장", use_container_width=True, type="primary"):
                insert_inbody({
                    "date": str(ib_date), "weight": weight,
                    "body_fat_pct": body_fat_pct, "muscle_kg": muscle_kg,
                    "fat_kg": fat_kg, "bmi": bmi, "memo": ib_memo,
                })
                st.success("✅ 인바디 기록 저장 완료!")

    with tab2:
        ib_df = load_inbody()
        if ib_df.empty:
            st.info("인바디 기록이 없습니다.")
        else:
            ib_df = ib_df.sort_values("date")
            latest = ib_df.iloc[-1]
            prev   = ib_df.iloc[-2] if len(ib_df) > 1 else None

            def delta_metric(col, label, val, prev_val, unit="", good_dir="down"):
                delta = round(val - prev_val, 1) if prev_val is not None else None
                if delta is not None:
                    color = "good" if (delta <= 0) == (good_dir == "down") else "bad"
                    d_str = f"{'+' if delta>0 else ''}{delta}{unit}"
                else:
                    color, d_str = "normal", None
                col.markdown(metric_card(label, f"{val}{unit}", d_str, color), unsafe_allow_html=True)

            col1, col2, col3, col4 = st.columns(4)
            delta_metric(col1, "체중",     round(float(latest["weight"]),1),
                         round(float(prev["weight"]),1) if prev is not None else None, "kg")
            delta_metric(col2, "체지방률", round(float(latest["body_fat_pct"]),1),
                         round(float(prev["body_fat_pct"]),1) if prev is not None else None, "%")
            delta_metric(col3, "골격근량", round(float(latest["muscle_kg"]),1),
                         round(float(prev["muscle_kg"]),1) if prev is not None else None, "kg", "up")
            delta_metric(col4, "BMI",      round(float(latest["bmi"]),1),
                         round(float(prev["bmi"]),1) if prev is not None else None, "")

            st.markdown("<br>", unsafe_allow_html=True)

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scatter(x=ib_df["date"], y=ib_df["weight"],
                                     name="체중(kg)", mode="lines+markers",
                                     line=dict(color="#4ECDC4",width=2)), secondary_y=False)
            fig.add_trace(go.Scatter(x=ib_df["date"], y=ib_df["muscle_kg"],
                                     name="골격근량(kg)", mode="lines+markers",
                                     line=dict(color="#2ecc71",width=2)), secondary_y=False)
            fig.add_trace(go.Scatter(x=ib_df["date"], y=ib_df["fat_kg"],
                                     name="체지방량(kg)", mode="lines+markers",
                                     line=dict(color="#FF6B6B",width=2)), secondary_y=False)
            fig.add_trace(go.Bar(x=ib_df["date"], y=ib_df["body_fat_pct"],
                                 name="체지방률(%)", marker_color="rgba(255,107,107,0.2)"),
                          secondary_y=True)
            fig.update_layout(title="인바디 변화 추이",
                              plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
                              font_color="#ddd",height=380,
                              xaxis=dict(gridcolor="#2a2a3e"),
                              yaxis=dict(title="kg",gridcolor="#2a2a3e"),
                              yaxis2=dict(title="체지방률(%)"),
                              legend=dict(orientation="h",yanchor="bottom",y=1.02))
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("측정 이력")
            disp = ib_df[["date","weight","body_fat_pct","muscle_kg","fat_kg","bmi","memo"]].copy()
            disp.columns = ["날짜","체중(kg)","체지방률(%)","골격근량(kg)","체지방량(kg)","BMI","메모"]
            disp["날짜"] = disp["날짜"].dt.strftime("%Y-%m-%d")
            st.dataframe(disp.sort_values("날짜",ascending=False), use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("🎯 맞춤 운동 계획 제안")
            fat = float(latest["body_fat_pct"])
            if fat > 25:
                plan = "체지방률이 높습니다. **유산소(러닝/천국의계단)** 비중을 높이고 주 4회 이상 유산소 운동을 권장합니다."
                reco = [("러닝",4),("천국의계단",2),("헬스장",2),("요가",1)]
            elif fat < 15:
                plan = "체지방률이 낮습니다. **근력 운동(헬스장)** 비중을 늘려 골격근량을 키우는 것을 추천합니다."
                reco = [("헬스장",4),("러닝",2),("폼롤러",2),("요가",1)]
            else:
                plan = "체지방률이 적절합니다. **유산소와 근력 균형**을 맞춘 복합 트레이닝을 추천합니다."
                reco = [("헬스장",3),("러닝",2),("천국의계단",1),("요가",1),("폼롤러",1)]

            st.info(plan)
            rcols = st.columns(len(reco))
            for col, (workout, freq) in zip(rcols, reco):
                emoji = WORKOUT_TYPES.get(workout,{}).get("emoji","⚡")
                cat   = WORKOUT_TYPES.get(workout,{}).get("category","")
                color = CATEGORY_COLORS.get(cat,"#888")
                col.markdown(f"""
                <div style="background:#1e1e2e;border:1px solid {color};border-radius:10px;
                            padding:14px;text-align:center">
                  <p style="font-size:1.6rem;margin:0">{emoji}</p>
                  <p style="margin:4px 0;font-weight:700;color:#fff">{workout}</p>
                  <p style="margin:0;color:{color};font-size:.85rem">주 {freq}회</p>
                </div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════
# 6. 전체 기록
# ══════════════════════════════════════════════════════
elif page == "🗂️ 전체 기록":
    st.title("🗂️ 전체 운동 기록")

    df = load_workouts()
    if df.empty:
        st.info("기록된 운동이 없습니다.")
        st.stop()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        workout_filter = st.multiselect("운동 종류", list(WORKOUT_TYPES.keys()))
    with col2:
        category_filter = st.multiselect("카테고리", list(CATEGORY_COLORS.keys()))
    with col3:
        date_from = st.date_input("시작일", value=df["date"].min())
    with col4:
        date_to = st.date_input("종료일", value=today)

    filtered = df[(df["date"] >= date_from) & (df["date"] <= date_to)]
    if workout_filter:
        filtered = filtered[filtered["workout"].isin(workout_filter)]
    if category_filter:
        filtered = filtered[filtered["category"].isin(category_filter)]

    st.markdown(f"**{len(filtered)}개** 기록 표시 중")

    if not filtered.empty:
        disp = filtered[["date","workout","category","duration_min","intensity","kcal","memo"]].copy()
        disp.columns = ["날짜","운동","카테고리","시간(분)","강도","칼로리(kcal)","메모"]
        st.dataframe(disp.sort_values("날짜",ascending=False), use_container_width=True, hide_index=True)
        csv = disp.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 CSV 다운로드", csv, "workout_records.csv", "text/csv")
    else:
        st.info("해당 조건의 기록이 없습니다.")


# ── 푸터 ──────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.markdown("<p style='color:#666;font-size:.8rem;text-align:center'>💪 Keep going!</p>",
                    unsafe_allow_html=True)
