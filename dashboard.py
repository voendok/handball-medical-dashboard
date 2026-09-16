import streamlit as st
import pandas as pd
import hashlib
from datetime import date, timedelta
from supabase import create_client

# ============ НАСТРОЙКА СТРАНИЦЫ ============
st.set_page_config(
    page_title="Медицинский дашборд — Гандбол",
    page_icon="🏐",
    layout="wide"
)

# ============ ПОДКЛЮЧЕНИЕ К SUPABASE ============
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# ============ АВТОРИЗАЦИЯ ============
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def check_login(username: str, password: str):
    try:
        response = (
            supabase.table("app_users")
            .select("*")
            .eq("username", username)
            .eq("is_active", True)
            .execute()
        )
        if response.data and len(response.data) > 0:
            user = response.data[0]
            if user["password_hash"] == hash_password(password):
                return user
        return None
    except Exception as e:
        st.error(f"Ошибка авторизации: {e}")
        return None


def login_screen():
    st.title("🏐 Медицинский дашборд")
    st.subheader("Вход в систему")
    
    with st.form("login_form"):
        username = st.text_input("Логин")
        password = st.text_input("Пароль", type="password")
        submitted = st.form_submit_button("Войти", type="primary")
        
        if submitted:
            user = check_login(username, password)
            if user:
                st.session_state["authenticated"] = True
                st.session_state["user"] = user
                st.rerun()
            else:
                st.error("❌ Неверный логин или пароль")


if not st.session_state.get("authenticated", False):
    login_screen()
    st.stop()

user = st.session_state.get("user", {})
user_role = user.get("role", "guest")
user_athlete_id = user.get("athlete_id")

# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============
def format_dates(df, date_columns):
    if df.empty:
        return df
    df = df.copy()
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%d.%m.%Y')
            df[col] = df[col].fillna('')
    return df


# ============ ФУНКЦИИ ЗАГРУЗКИ ДАННЫХ ============
@st.cache_data(ttl=60)
def load_today_dashboard():
    response = supabase.table("v_today_dashboard").select("*").execute()
    return pd.DataFrame(response.data)

@st.cache_data(ttl=60)
def load_missing_reports():
    response = supabase.table("v_missing_reports").select("*").execute()
    return pd.DataFrame(response.data)

@st.cache_data(ttl=60)
def load_overdue_exams():
    response = supabase.table("v_overdue_exams").select("*").execute()
    return pd.DataFrame(response.data)

@st.cache_data(ttl=60)
def load_athletes():
    response = (
        supabase.table("athletes")
        .select("id, full_name, jersey_number")
        .eq("is_active", True)
        .order("jersey_number")
        .execute()
    )
    return pd.DataFrame(response.data)

@st.cache_data(ttl=60)
def load_health_logs(days=30):
    since_date = (date.today() - timedelta(days=days)).isoformat()
    response = (
        supabase.table("daily_health_logs")
        .select("*, athletes(full_name, jersey_number)")
        .gte("log_date", since_date)
        .order("log_date", desc=False)
        .execute()
    )
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df = df.drop(columns=["athletes"])
    return df

@st.cache_data(ttl=60)
def load_injuries(days=90):
    since_date = (date.today() - timedelta(days=days)).isoformat()
    response = (
        supabase.table("injuries_and_illnesses")
        .select("*, athletes(full_name, jersey_number), dict_body_parts(name)")
        .gte("incident_date", since_date)
        .order("incident_date", desc=True)
        .execute()
    )
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df["body_part"] = df["dict_body_parts"].apply(lambda x: x["name"] if x else None)
        df = df.drop(columns=["athletes", "dict_body_parts"])
    return df

@st.cache_data(ttl=60)
def load_medications():
    today = date.today().isoformat()
    response = (
        supabase.table("medication_intake")
        .select("*, athletes(full_name, jersey_number), dict_medicines(name, wada_status, tue_required)")
        .lte("course_start", today)
        .gte("course_end", today)
        .execute()
    )
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df["medicine_name"] = df["dict_medicines"].apply(lambda x: x["name"] if x else None)
        df["wada_status"] = df["dict_medicines"].apply(lambda x: x["wada_status"] if x else None)
        df["tue_required"] = df["dict_medicines"].apply(lambda x: x["tue_required"] if x else None)
        df = df.drop(columns=["athletes", "dict_medicines"])
    return df

@st.cache_data(ttl=300)
def load_exam_templates():
    response = (
        supabase.table("dict_exam_templates")
        .select("id, name, specialist_type, validity_days, is_mandatory")
        .order("name")
        .execute()
    )
    return pd.DataFrame(response.data)

@st.cache_data(ttl=60)
def load_all_examinations():
    response = (
        supabase.table("examinations")
        .select("*, athletes(full_name, jersey_number), dict_exam_templates(name, specialist_type)")
        .order("examination_date", desc=True)
        .execute()
    )
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df["exam_name"] = df["dict_exam_templates"].apply(lambda x: x["name"] if x else None)
        df = df.drop(columns=["athletes", "dict_exam_templates"])
    return df

# ============ ЗАГРУЗКА ДАННЫХ ============
df_dashboard = load_today_dashboard()
df_missing = load_missing_reports()
df_overdue = load_overdue_exams()
df_athletes = load_athletes()
df_logs = load_health_logs(30)
df_exam_templates = load_exam_templates()
df_all_exams = load_all_examinations()

# ============ ЗАГОЛОВОК ============
st.title("🏐 Медицинский дашборд команды")
if user_role == "athlete":
    st.caption(f"Личный кабинет спортсменки · {user.get('full_name', '')}")
else:
    st.caption(
        f"Мониторинг состояния спортсменок в реальном времени · "
        f"Пользователь: {user.get('full_name', 'Гость')} "
        f"({user_role})"
    )

# ============ ЛИЧНЫЙ КАБИНЕТ СПОРТСМЕНКИ ============
if user_role == "athlete" and user_athlete_id:
    tab_status, tab_dynamics, tab_exams_self = st.tabs([
        "📊 Мой статус",
        "📈 Моя динамика",
        "🏥 Мои осмотры"
    ])
    
    # --- Личные данные спортсменки ---
    df_my_dashboard = df_dashboard[df_dashboard["№"] == int(df_athletes[df_athletes["id"] == user_athlete_id]["jersey_number"].iloc[0])] if not df_athletes[df_athletes["id"] == user_athlete_id].empty else pd.DataFrame()
    df_my_logs = df_logs[df_logs["athlete_id"] == user_athlete_id]
    df_my_exams = df_all_exams[df_all_exams["athlete_id"] == user_athlete_id]
    
    with tab_status:
        st.header("📊 Мой статус на сегодня")
        
        # Находим свою строку в дашборде
        my_jersey = None
        my_athlete_row = df_athletes[df_athletes["id"] == user_athlete_id]
        if not my_athlete_row.empty:
            my_jersey = my_athlete_row["jersey_number"].iloc[0]
        
        if my_jersey is not None:
            my_row = df_dashboard[df_dashboard["№"] == int(my_jersey)]
        else:
            my_row = pd.DataFrame()
        
        if not my_row.empty:
            status = my_row["status"].iloc[0] if "status" in my_row.columns else "grey"
            icon = my_row["icon"].iloc[0] if "icon" in my_row.columns else "⚪"
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Статус", f"{icon} {status}")
            col2.metric("Пульс", my_row["Пульс"].iloc[0] if pd.notna(my_row["Пульс"].iloc[0]) else "—")
            col3.metric("Разница", my_row["Разница"].iloc[0] if pd.notna(my_row["Разница"].iloc[0]) else "—")
            col4.metric("Сон", my_row["Сон"].iloc[0] if pd.notna(my_row["Сон"].iloc[0]) else "—")
            
            st.divider()
            if "Причина" in my_row.columns:
                st.info(f"**Причина:** {my_row['Причина'].iloc[0]}")
        else:
            st.info("📭 Сегодня вы ещё не отправляли утренний отчёт. Напишите боту в Telegram!")
    
    with tab_dynamics:
        st.header("📈 Моя динамика за 30 дней")
        
        if df_my_logs.empty:
            st.info("📭 Нет данных за последние 30 дней. Отправляйте отчёты боту каждое утро!")
        else:
            df_chart = df_my_logs[["log_date", "morning_hr", "ortho_hr_after", "sleep_hours", "borg_rating"]].copy()
            df_chart = df_chart.sort_values("log_date").set_index("log_date")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("❤️ Мой пульс")
                if df_chart["morning_hr"].notna().any():
                    pulse_data = df_chart[["morning_hr"]].dropna()
                    pulse_data.columns = ["Пульс утром"]
                    st.line_chart(pulse_data, use_container_width=True)
                else:
                    st.info("Нет данных")
            
            with col2:
                st.subheader("😴 Мой сон")
                if df_chart["sleep_hours"].notna().any():
                    sleep_data = df_chart[["sleep_hours"]].dropna()
                    sleep_data.columns = ["Часы сна"]
                    st.line_chart(sleep_data, use_container_width=True)
                else:
                    st.info("Нет данных")
            
            st.subheader("📊 Моя ортостатическая разница")
            ortho_df = df_chart[["morning_hr", "ortho_hr_after"]].dropna()
            if not ortho_df.empty:
                ortho_df["Разница"] = ortho_df["ortho_hr_after"] - ortho_df["morning_hr"]
                ortho_df = ortho_df[["Разница"]]
                st.line_chart(ortho_df, use_container_width=True)
                st.caption("🔴 > 25 — критическая зона. 🟡 15-25 — внимание.")
            
            col3, col4 = st.columns(2)
            
            with col3:
                st.subheader("💪 Моя шкала Борга")
                if df_chart["borg_rating"].notna().any():
                    borg_data = df_chart[["borg_rating"]].dropna()
                    borg_data.columns = ["Борг"]
                    st.line_chart(borg_data, use_container_width=True)
            
            with col4:
                st.subheader("📉 Мои средние значения")
                avg_data = pd.DataFrame({
                    "Показатель": ["Средний пульс", "Средний сон", "Средний Борг"],
                    "Значение": [
                        round(df_chart["morning_hr"].mean(), 1) if df_chart["morning_hr"].notna().any() else "—",
                        round(df_chart["sleep_hours"].mean(), 1) if df_chart["sleep_hours"].notna().any() else "—",
                        round(df_chart["borg_rating"].mean(), 1) if df_chart["borg_rating"].notna().any() else "—"
                    ]
                })
                st.dataframe(avg_data, use_container_width=True, hide_index=True)
    
    with tab_exams_self:
        st.header("🏥 Мои медицинские осмотры")
        
        if df_my_exams.empty:
            st.info("Осмотры пока не внесены.")
        else:
            display_cols = ["examination_date", "exam_name", "is_approved", "next_exam_date", "restrictions"]
            available_cols = [c for c in display_cols if c in df_my_exams.columns]
            
            df_show = df_my_exams[available_cols].copy()
            df_show = format_dates(df_show, ["examination_date", "next_exam_date"])
            df_show = df_show.rename(columns={
                "examination_date": "Дата",
                "exam_name": "Осмотр",
                "is_approved": "Допуск",
                "next_exam_date": "Следующий",
                "restrictions": "Ограничения"
            })
            st.dataframe(df_show, use_container_width=True, hide_index=True)

# ============ ДАШБОРД ДЛЯ ВРАЧА/ТРЕНЕРА/АДМИНА ============
else:
    # ============ ВКЛАДКИ С УЧЁТОМ РОЛИ ============
    if user_role == "coach":
        tab_today, tab_dynamics = st.tabs(["📊 Сегодня", "📈 Динамика"])
        tab_exams = None
        tab_injuries = None
        tab_meds = None
    elif user_role == "masseur":
        tab_today, tab_dynamics, tab_exams, tab_injuries = st.tabs([
            "📊 Сегодня", "📈 Динамика", "🏥 Осмотры", "🩹 Травмы"
        ])
        tab_meds = None
    else:
        tab_today, tab_dynamics, tab_exams, tab_injuries, tab_meds = st.tabs([
            "📊 Сегодня", "📈 Динамика", "🏥 Осмотры", "🩹 Травмы", "💊 Лекарства"
        ])
    
    # ============ ВКЛАДКА 1: СЕГОДНЯ ============
    with tab_today:
        st.header("📊 Сводка за сегодня")
        
        red_count = len(df_dashboard[df_dashboard["status"] == "red"]) if not df_dashboard.empty else 0
        yellow_count = len(df_dashboard[df_dashboard["status"] == "yellow"]) if not df_dashboard.empty else 0
        green_count = len(df_dashboard[df_dashboard["status"] == "green"]) if not df_dashboard.empty else 0
        grey_count = len(df_dashboard[df_dashboard["status"] == "grey"]) if not df_dashboard.empty else 0
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🔴 Проблемы", red_count)
        col2.metric("🟡 Внимание", yellow_count)
        col3.metric("🟢 Норма", green_count)
        col4.metric("⚪ Нет данных", grey_count)
        
        st.divider()
        st.subheader("🚦 Статус спортсменок")
        
        if not df_dashboard.empty:
            status_filter = st.selectbox(
                "Фильтр по статусу",
                ["Все", "🔴 Только красные", "🟡 Только жёлтые", "🟢 Только зелёные", "⚪ Только без данных"]
            )
            
            if status_filter == "🔴 Только красные":
                df_filtered = df_dashboard[df_dashboard["status"] == "red"]
            elif status_filter == "🟡 Только жёлтые":
                df_filtered = df_dashboard[df_dashboard["status"] == "yellow"]
            elif status_filter == "🟢 Только зелёные":
                df_filtered = df_dashboard[df_dashboard["status"] == "green"]
            elif status_filter == "⚪ Только без данных":
                df_filtered = df_dashboard[df_dashboard["status"] == "grey"]
            else:
                df_filtered = df_dashboard
            
            display_cols = ["icon", "№", "ФИО", "Пульс", "Разница", "Борг", "Сон", "Причина"]
            available_cols = [c for c in display_cols if c in df_filtered.columns]
            st.dataframe(df_filtered[available_cols], use_container_width=True, hide_index=True)
        else:
            st.info("Пока нет данных за сегодня. Спортсменки ещё не отправили отчёты.")
        
        st.divider()
        st.subheader("📵 Не сдали утренний отчёт")
        if not df_missing.empty:
            st.warning(f"Не сдали: {len(df_missing)} спортсменок")
            st.dataframe(df_missing, use_container_width=True, hide_index=True)
        else:
            st.success("✅ Все спортсменки сдали отчёт!")
    
    # ============ ВКЛАДКА 2: ДИНАМИКА ============
    with tab_dynamics:
        st.header("📈 Динамика за последние 30 дней")
        
        athlete_options = ["👥 Вся команда"]
        athlete_map = {}
        
        if not df_athletes.empty:
            for _, row in df_athletes.iterrows():
                if pd.notna(row['jersey_number']):
                    jersey = int(row['jersey_number'])
                    label = f"№{jersey} — {row['full_name']}"
                else:
                    label = f"(без номера) {row['full_name']}"
                athlete_options.append(label)
                athlete_map[label] = row['id']
        
        st.caption(f"👥 Всего спортсменок в списке: {len(athlete_options) - 1}")
        selected_athlete = st.selectbox("Выберите спортсменку или всю команду", athlete_options)
        
        if selected_athlete == "👥 Вся команда":
            df_filtered_logs = df_logs
            chart_title_suffix = "всей команды"
        else:
            athlete_id = athlete_map[selected_athlete]
            df_filtered_logs = df_logs[df_logs["athlete_id"] == athlete_id]
            chart_title_suffix = f"спортсменки {selected_athlete}"
        
        if df_filtered_logs.empty:
            st.info(f"📭 Пока нет данных для {chart_title_suffix}.")
        else:
            if selected_athlete == "👥 Вся команда":
                df_chart = df_filtered_logs.groupby("log_date").agg({
                    "morning_hr": "mean", "ortho_hr_after": "mean",
                    "sleep_hours": "mean", "borg_rating": "mean"
                }).reset_index()
            else:
                df_chart = df_filtered_logs[["log_date", "morning_hr", "ortho_hr_after", "sleep_hours", "borg_rating"]].copy()
            
            df_chart = df_chart.sort_values("log_date").set_index("log_date")
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader(f"❤️ Пульс — {chart_title_suffix}")
                if "morning_hr" in df_chart.columns and df_chart["morning_hr"].notna().any():
                    pulse_data = df_chart[["morning_hr"]].dropna()
                    pulse_data.columns = ["Пульс утром"]
                    st.line_chart(pulse_data, use_container_width=True)
            with col2:
                st.subheader(f"😴 Сон — {chart_title_suffix}")
                if "sleep_hours" in df_chart.columns and df_chart["sleep_hours"].notna().any():
                    sleep_data = df_chart[["sleep_hours"]].dropna()
                    sleep_data.columns = ["Часы сна"]
                    st.line_chart(sleep_data, use_container_width=True)
            
            st.subheader(f"📊 Ортостатическая разница — {chart_title_suffix}")
            if "morning_hr" in df_chart.columns and "ortho_hr_after" in df_chart.columns:
                ortho_df = df_chart[["morning_hr", "ortho_hr_after"]].dropna()
                if not ortho_df.empty:
                    ortho_df["Разница"] = ortho_df["ortho_hr_after"] - ortho_df["morning_hr"]
                    ortho_df = ortho_df[["Разница"]]
                    st.line_chart(ortho_df, use_container_width=True)
                    st.caption("🔴 > 25 — критическая зона. 🟡 15-25 — внимание.")
            
            col3, col4 = st.columns(2)
            with col3:
                st.subheader(f"💪 Шкала Борга — {chart_title_suffix}")
                if "borg_rating" in df_chart.columns and df_chart["borg_rating"].notna().any():
                    borg_data = df_chart[["borg_rating"]].dropna()
                    borg_data.columns = ["Борг"]
                    st.line_chart(borg_data, use_container_width=True)
            with col4:
                st.subheader("📉 Средние значения за период")
                avg_data = pd.DataFrame({
                    "Показатель": ["Средний пульс", "Средний сон", "Средний Борг"],
                    "Значение": [
                        round(df_chart["morning_hr"].mean(), 1) if "morning_hr" in df_chart and df_chart["morning_hr"].notna().any() else "—",
                        round(df_chart["sleep_hours"].mean(), 1) if "sleep_hours" in df_chart and df_chart["sleep_hours"].notna().any() else "—",
                        round(df_chart["borg_rating"].mean(), 1) if "borg_rating" in df_chart and df_chart["borg_rating"].notna().any() else "—"
                    ]
                })
                st.dataframe(avg_data, use_container_width=True, hide_index=True)
    
    # ============ ВКЛАДКА 3: ОСМОТРЫ ============
    if tab_exams is not None:
        with tab_exams:
            st.header("🏥 Медицинские осмотры")
            
            sub_view, sub_add = st.tabs(["📋 Просмотр осмотров", "✍️ Внести новый осмотр"])
            
            with sub_view:
                st.subheader("⚠️ Просроченные осмотры")
                if not df_overdue.empty:
                    st.error(f"Просрочено: {len(df_overdue)} осмотров")
                    df_overdue_formatted = format_dates(df_overdue, ["Был должен"])
                    st.dataframe(df_overdue_formatted, use_container_width=True, hide_index=True)
                else:
                    st.success("✅ Все медосмотры в порядке!")
                
                st.divider()
                st.subheader("📋 Все осмотры (последние 50)")
                if not df_all_exams.empty:
                    display_cols = ["examination_date", "jersey_number", "full_name", "exam_name", "is_approved", "next_exam_date", "restrictions"]
                    available_cols = [c for c in display_cols if c in df_all_exams.columns]
                    df_exams_to_show = df_all_exams[available_cols].head(50).copy()
                    df_exams_to_show = format_dates(df_exams_to_show, ["examination_date", "next_exam_date"])
                    df_exams_to_show = df_exams_to_show.rename(columns={
                        "examination_date": "Дата осмотра", "jersey_number": "№",
                        "full_name": "ФИО", "exam_name": "Осмотр", "is_approved": "Допуск",
                        "next_exam_date": "Следующий", "restrictions": "Ограничения"
                    })
                    st.dataframe(df_exams_to_show, use_container_width=True, hide_index=True)
                else:
                    st.info("Пока нет ни одного осмотра.")
            
            with sub_add:
                st.subheader("✍️ Внести новый осмотр")
                st.caption("Поля со звёздочкой (*) обязательны.")
                
                with st.form("form_add_examination", clear_on_submit=True):
                    athlete_options_form = {}
                    if not df_athletes.empty:
                        for _, row in df_athletes.iterrows():
                            if pd.notna(row['jersey_number']):
                                jersey = int(row['jersey_number'])
                                label = f"№{jersey} — {row['full_name']}"
                            else:
                                label = f"(без номера) {row['full_name']}"
                            athlete_options_form[label] = row['id']
                    
                    selected_athlete_form = st.selectbox("Спортсменка *", options=list(athlete_options_form.keys()))
                    
                    template_options_form = {}
                    if not df_exam_templates.empty:
                        for _, row in df_exam_templates.iterrows():
                            label = f"{row['name']} ({row['specialist_type']})"
                            template_options_form[label] = {"id": row['id'], "validity_days": row['validity_days']}
                    
                    selected_template_form = st.selectbox("Тип осмотра *", options=list(template_options_form.keys()))
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        exam_date = st.date_input("Дата осмотра *", value=date.today(), format="DD.MM.YYYY")
                    with col2:
                        selected_template_data = template_options_form.get(selected_template_form, {})
                        validity = selected_template_data.get("validity_days", 365)
                        next_date_default = exam_date + timedelta(days=validity) if validity else exam_date
                        next_exam_date = st.date_input("Дата следующего осмотра", value=next_date_default, format="DD.MM.YYYY")
                    
                    result_text = st.text_area("Заключение врача *", height=100)
                    is_approved = st.radio("Допуск получен? *", options=[True, False],
                                          format_func=lambda x: "✅ Да, допущена" if x else "❌ Нет, не допущена", horizontal=True)
                    restrictions = st.text_input("Ограничения (если есть)")
                    
                    submitted = st.form_submit_button("💾 Сохранить осмотр", type="primary")
                    
                    if submitted:
                        if not result_text or len(result_text.strip()) < 3:
                            st.error("❌ Заполните заключение врача")
                        else:
                            try:
                                new_exam = {
                                    "athlete_id": athlete_options_form[selected_athlete_form],
                                    "exam_template_id": template_options_form[selected_template_form]["id"],
                                    "examination_date": exam_date.isoformat(),
                                    "result_text": result_text.strip(),
                                    "is_approved": is_approved,
                                    "restrictions": restrictions.strip() if restrictions else None,
                                    "next_exam_date": next_exam_date.isoformat() if next_exam_date else None
                                }
                                supabase.table("examinations").insert(new_exam).execute()
                                st.success(f"✅ Осмотр сохранён: {selected_athlete_form}")
                                st.cache_data.clear()
                            except Exception as e:
                                st.error(f"❌ Ошибка: {e}")
    
    # ============ ВКЛАДКА 4: ТРАВМЫ ============
    if tab_injuries is not None:
        with tab_injuries:
            st.header("🩹 Травмы и заболевания")
            df_injuries = load_injuries(90)
            if df_injuries.empty:
                st.info("За последние 90 дней травм не зарегистрировано.")
            else:
                st.warning(f"Травм за 90 дней: {len(df_injuries)}")
                display_cols = ["incident_date", "jersey_number", "full_name", "body_part", "side", "severity", "days_lost"]
                available_cols = [c for c in display_cols if c in df_injuries.columns]
                df_injuries_show = format_dates(df_injuries[available_cols], ["incident_date"])
                df_injuries_show = df_injuries_show.rename(columns={
                    "incident_date": "Дата
