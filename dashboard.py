import streamlit as st
import pandas as pd
from datetime import date, timedelta
from supabase import create_client
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from supabase import create_client

def format_dates(df, date_columns):
    """Преобразует колонки с датами из ISO (2026-09-16) в формат ДД.ММ.ГГГГ"""
    if df.empty:
        return df
    df = df.copy()
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%d.%m.%Y')
            df[col] = df[col].fillna('')
    return df

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
    """Загружает справочник шаблонов осмотров"""
    response = (
        supabase.table("dict_exam_templates")
        .select("id, name, specialist_type, validity_days, is_mandatory")
        .order("name")
        .execute()
    )
    return pd.DataFrame(response.data)

@st.cache_data(ttl=60)
def load_all_examinations():
    """Загружает все осмотры спортсменок"""
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

# ============ ЗАГРУЗКА ВСЕХ ДАННЫХ ============
df_dashboard = load_today_dashboard()
df_missing = load_missing_reports()
df_overdue = load_overdue_exams()
df_athletes = load_athletes()
df_logs = load_health_logs(30)
df_exam_templates = load_exam_templates()
df_all_exams = load_all_examinations()

# ============ ЗАГОЛОВОК ============
st.title("🏐 Медицинский дашборд команды")
st.caption("Мониторинг состояния спортсменок в реальном времени")

# ============ ВКЛАДКИ ============
tab_today, tab_dynamics, tab_exams, tab_injuries, tab_meds = st.tabs([
    "📊 Сегодня",
    "📈 Динамика",
    "🏥 Осмотры",
    "🩹 Травмы",
    "💊 Лекарства"
])

# ============================================================
# ВКЛАДКА 1: СЕГОДНЯ
# ============================================================
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

# ============================================================
# ВКЛАДКА 2: ДИНАМИКА
# ============================================================
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
                "morning_hr": "mean",
                "ortho_hr_after": "mean",
                "sleep_hours": "mean",
                "borg_rating": "mean"
            }).reset_index()
        else:
            df_chart = df_filtered_logs[
                ["log_date", "morning_hr", "ortho_hr_after", "sleep_hours", "borg_rating"]
            ].copy()
        
        df_chart = df_chart.sort_values("log_date").set_index("log_date")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader(f"❤️ Пульс — {chart_title_suffix}")
            if "morning_hr" in df_chart.columns and df_chart["morning_hr"].notna().any():
                pulse_data = df_chart[["morning_hr"]].dropna()
                pulse_data.columns = ["Пульс утром"]
                st.line_chart(pulse_data, use_container_width=True)
            else:
                st.info("Нет данных по пульсу")
        
        with col2:
            st.subheader(f"😴 Сон — {chart_title_suffix}")
            if "sleep_hours" in df_chart.columns and df_chart["sleep_hours"].notna().any():
                sleep_data = df_chart[["sleep_hours"]].dropna()
                sleep_data.columns = ["Часы сна"]
                st.line_chart(sleep_data, use_container_width=True)
            else:
                st.info("Нет данных по сну")
        
        st.subheader(f"📊 Ортостатическая разница — {chart_title_suffix}")
        if "morning_hr" in df_chart.columns and "ortho_hr_after" in df_chart.columns:
            ortho_df = df_chart[["morning_hr", "ortho_hr_after"]].dropna()
            if not ortho_df.empty:
                ortho_df["Разница"] = ortho_df["ortho_hr_after"] - ortho_df["morning_hr"]
                ortho_df = ortho_df[["Разница"]]
                st.line_chart(ortho_df, use_container_width=True)
                st.caption("🔴 > 25 — критическая зона. 🟡 15-25 — внимание.")
            else:
                st.info("Нет данных для расчёта разницы")
        else:
            st.info("Недостаточно данных")
        
        col3, col4 = st.columns(2)
        
        with col3:
            st.subheader(f"💪 Шкала Борга — {chart_title_suffix}")
            if "borg_rating" in df_chart.columns and df_chart["borg_rating"].notna().any():
                borg_data = df_chart[["borg_rating"]].dropna()
                borg_data.columns = ["Борг"]
                st.line_chart(borg_data, use_container_width=True)
                st.caption("🟢 6-11 — легко. 🟡 12-15 — рабочий режим. 🔴 16+ — высоко.")
            else:
                st.info("Нет данных по шкале Борга")
        
        with col4:
            st.subheader("📉 Средние значения за период")
            avg_data = pd.DataFrame({
                "Показатель": ["Средний пульс", "Средний сон", "Средний Борг"],
                "Значение": [
                    round(df_chart["morning_hr"].mean(), 1)
                    if "morning_hr" in df_chart and df_chart["morning_hr"].notna().any() else "—",
                    round(df_chart["sleep_hours"].mean(), 1)
                    if "sleep_hours" in df_chart and df_chart["sleep_hours"].notna().any() else "—",
                    round(df_chart["borg_rating"].mean(), 1)
                    if "borg_rating" in df_chart and df_chart["borg_rating"].notna().any() else "—"
                ]
            })
            st.dataframe(avg_data, use_container_width=True, hide_index=True)

# ============================================================
# ВКЛАДКА 3: ОСМОТРЫ (С ФОРМОЙ ДЛЯ ВРАЧА)
# ============================================================
with tab_exams:
    st.header("🏥 Медицинские осмотры")
    
    sub_view, sub_add = st.tabs(["📋 Просмотр осмотров", "✍️ Внести новый осмотр"])
    
    # ============ ПОДВКЛАДКА: ПРОСМОТР ============
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
            
            # Переименовываем заголовки для красоты
            df_exams_to_show = df_exams_to_show.rename(columns={
                "examination_date": "Дата осмотра",
                "jersey_number": "№",
                "full_name": "ФИО",
                "exam_name": "Осмотр",
                "is_approved": "Допуск",
                "next_exam_date": "Следующий",
                "restrictions": "Ограничения"
            })
            
            st.dataframe(df_exams_to_show, use_container_width=True, hide_index=True)
        else:
            st.info("В базе пока нет ни одного осмотра. Добавьте первый через форму во второй подвкладке.")
    
    # ============ ПОДВКЛАДКА: ДОБАВЛЕНИЕ ============
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
            
            selected_athlete_form = st.selectbox(
                "Спортсменка *",
                options=list(athlete_options_form.keys()),
                index=0
            )
            
            template_options_form = {}
            if not df_exam_templates.empty:
                for _, row in df_exam_templates.iterrows():
                    label = f"{row['name']} ({row['specialist_type']})"
                    template_options_form[label] = {
                        "id": row['id'],
                        "validity_days": row['validity_days']
                    }
            
            selected_template_form = st.selectbox(
                "Тип осмотра *",
                options=list(template_options_form.keys()),
                index=0
            )
            
            col1, col2 = st.columns(2)
            with col1:
                exam_date = st.date_input(
                    "Дата осмотра *", 
                    value=date.today(),
                    format="DD.MM.YYYY"
                )
            with col2:
                selected_template_data = template_options_form.get(selected_template_form, {})
                validity = selected_template_data.get("validity_days", 365)
                next_date_default = exam_date + timedelta(days=validity) if validity else exam_date
                next_exam_date = st.date_input(
                    "Дата следующего осмотра", 
                    value=next_date_default,
                    format="DD.MM.YYYY"
                )
            
            result_text = st.text_area(
                "Заключение врача *",
                placeholder="Например: Сократительная функция сердца сохранена, патологий не выявлено",
                height=100
            )
            
            is_approved = st.radio(
                "Допуск получен? *",
                options=[True, False],
                format_func=lambda x: "✅ Да, допущена" if x else "❌ Нет, не допущена",
                horizontal=True
            )
            
            restrictions = st.text_input(
                "Ограничения (если есть)",
                placeholder="Например: не играть в линзах, только очки"
            )
            
            submitted = st.form_submit_button("💾 Сохранить осмотр", type="primary")
            
            if submitted:
                if not result_text or len(result_text.strip()) < 3:
                    st.error("❌ Заполните заключение врача (минимум 3 символа)")
                else:
                    try:
                        athlete_id = athlete_options_form[selected_athlete_form]
                        template_id = template_options_form[selected_template_form]["id"]
                        
                        new_exam = {
                            "athlete_id": athlete_id,
                            "exam_template_id": template_id,
                            "examination_date": exam_date.isoformat(),
                            "result_text": result_text.strip(),
                            "is_approved": is_approved,
                            "restrictions": restrictions.strip() if restrictions else None,
                            "next_exam_date": next_exam_date.isoformat() if next_exam_date else None
                        }
                        
                        supabase.table("examinations").insert(new_exam).execute()
                        
                        st.success(f"✅ Осмотр сохранён: {selected_athlete_form}")
                        st.info("Нажмите «🔄 Обновить данные» внизу, чтобы увидеть запись в таблице.")
                        st.cache_data.clear()
                        
                    except Exception as e:
                        st.error(f"❌ Ошибка при сохранении: {e}")
# ============================================================
# ВКЛАДКА 4: ТРАВМЫ
# ============================================================
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
            "incident_date": "Дата",
            "jersey_number": "№",
            "full_name": "ФИО",
            "body_part": "Часть тела",
            "side": "Сторона",
            "severity": "Тяжесть",
            "days_lost": "Пропущено дней"
        })
        
        st.dataframe(df_injuries_show, use_container_width=True, hide_index=True)

# ============================================================
# ВКЛАДКА 5: ЛЕКАРСТВА
# ============================================================
with tab_meds:
    st.header("💊 Лекарственные препараты")
    
    df_meds = load_medications()
    
    if df_meds.empty:
        st.info("Сейчас никто не принимает лекарства.")
    else:
        st.warning(f"Принимают лекарства: {len(df_meds)} спортсменок")
        
        display_cols = ["jersey_number", "full_name", "medicine_name", "dosage", "course_end", "wada_status", "tue_required"]
        available_cols = [c for c in display_cols if c in df_meds.columns]
        
        df_meds_show = format_dates(df_meds[available_cols], ["course_end"])
        df_meds_show = df_meds_show.rename(columns={
            "jersey_number": "№",
            "full_name": "ФИО",
            "medicine_name": "Препарат",
            "dosage": "Дозировка",
            "course_end": "До",
            "wada_status": "WADA",
            "tue_required": "TUE"
        })
        
        st.dataframe(df_meds_show, use_container_width=True, hide_index=True)
        
        # Антидопинговый контроль
        if "wada_status" in df_meds.columns:
            risky = df_meds[df_meds["wada_status"] != "Разрешен"]
            if not risky.empty:
                st.error(f"⚠️ Антидопинговый риск: {len(risky)} случаев")
                st.dataframe(risky[available_cols], use_container_width=True, hide_index=True)
# ============ ОБНОВЛЕНИЕ ============
st.divider()
if st.button("🔄 Обновить данные"):
    st.cache_data.clear()
    st.rerun()

st.caption(f"Последнее обновление: {pd.Timestamp.now().strftime('%H:%M:%S')}")