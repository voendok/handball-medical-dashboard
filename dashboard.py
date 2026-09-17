import streamlit as st
import pandas as pd
import hashlib
from datetime import date, timedelta
from supabase import create_client

# ============ НАСТРОЙКА ============
st.set_page_config(page_title="Медицинский дашборд — Гандбол", page_icon="🏐", layout="wide")

@st.cache_resource
def init_supabase():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_supabase()

# ============ АВТОРИЗАЦИЯ ============
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def check_login(username: str, password: str):
    try:
        response = supabase.table("app_users").select("*").eq("username", username).eq("is_active", True).execute()
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

# ============ ВСПОМОГАТЕЛЬНЫЕ ============
def format_dates(df, date_columns):
    if df.empty:
        return df
    df = df.copy()
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%d.%m.%Y')
            df[col] = df[col].fillna('')
    return df

def athlete_options_dict():
    df_a = load_athletes()
    opts = {}
    if not df_a.empty:
        for _, row in df_a.iterrows():
            j = int(row['jersey_number']) if pd.notna(row['jersey_number']) else None
            label = f"№{j} — {row['full_name']}" if j else f"(без номера) {row['full_name']}"
            opts[label] = row['id']
    return opts

# ============ СПРАВОЧНИКИ ============
@st.cache_data(ttl=300)
def load_athletes():
    r = supabase.table("athletes").select("id, full_name, jersey_number").eq("is_active", True).order("jersey_number").execute()
    return pd.DataFrame(r.data)

@st.cache_data(ttl=60)
def load_athletes_full():
    r = supabase.table("athletes").select("*").eq("is_active", True).order("jersey_number").execute()
    return pd.DataFrame(r.data)

@st.cache_data(ttl=300)
def load_body_parts():
    r = supabase.table("dict_body_parts").select("id, name").order("name").execute()
    return pd.DataFrame(r.data)

@st.cache_data(ttl=300)
def load_diagnoses():
    r = supabase.table("dict_diagnoses").select("id, mkb_code, name").order("name").execute()
    return pd.DataFrame(r.data)

@st.cache_data(ttl=300)
def load_medicines():
    r = supabase.table("dict_medicines").select("id, name, wada_status, tue_required").order("name").execute()
    return pd.DataFrame(r.data)

@st.cache_data(ttl=300)
def load_exam_templates():
    r = supabase.table("dict_exam_templates").select("id, name, specialist_type, validity_days").order("name").execute()
    return pd.DataFrame(r.data)

@st.cache_data(ttl=300)
def load_test_types():
    r = supabase.table("dict_test_types").select("id, name, unit").order("name").execute()
    return pd.DataFrame(r.data)

@st.cache_data(ttl=300)
def load_biomarkers():
    r = supabase.table("dict_biomarkers").select("id, name, unit").order("name").execute()
    return pd.DataFrame(r.data)

@st.cache_data(ttl=300)
def load_staff():
    r = supabase.table("staff").select("id, full_name, role").order("full_name").execute()
    return pd.DataFrame(r.data)

# ============ ДАННЫЕ ДАШБОРДА ============
@st.cache_data(ttl=60)
def load_today_dashboard():
    r = supabase.table("v_today_dashboard").select("*").execute()
    return pd.DataFrame(r.data)

@st.cache_data(ttl=60)
def load_missing_reports():
    r = supabase.table("v_missing_reports").select("*").execute()
    return pd.DataFrame(r.data)

@st.cache_data(ttl=60)
def load_overdue_exams():
    r = supabase.table("v_overdue_exams").select("*").execute()
    return pd.DataFrame(r.data)

@st.cache_data(ttl=60)
def load_health_logs(days=30):
    since = (date.today() - timedelta(days=days)).isoformat()
    r = supabase.table("daily_health_logs").select("*, athletes(full_name, jersey_number)").gte("log_date", since).order("log_date").execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df = df.drop(columns=["athletes"])
    return df

@st.cache_data(ttl=60)
def load_injuries(days=365):
    since = (date.today() - timedelta(days=days)).isoformat()
    r = supabase.table("injuries_and_illnesses").select(
        "*, athletes(full_name, jersey_number), dict_body_parts(name), dict_diagnoses(name)"
    ).gte("incident_date", since).order("incident_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df["body_part"] = df["dict_body_parts"].apply(lambda x: x["name"] if x else None)
        df["diagnosis"] = df["dict_diagnoses"].apply(lambda x: x["name"] if x else None)
        df = df.drop(columns=["athletes", "dict_body_parts", "dict_diagnoses"])
    return df
@st.cache_data(ttl=60)
def load_injuries_all():
    r = supabase.table("injuries_and_illnesses").select(
        "*, athletes(full_name, jersey_number), dict_body_parts(name), dict_diagnoses(name)"
    ).order("incident_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df["body_part"] = df["dict_body_parts"].apply(lambda x: x["name"] if x else None)
        df["diagnosis"] = df["dict_diagnoses"].apply(lambda x: x["name"] if x else None)
        df = df.drop(columns=["athletes", "dict_body_parts", "dict_diagnoses"])
    return df
@st.cache_data(ttl=60)
def load_medications():
    r = supabase.table("medication_intake").select(
        "*, athletes(full_name, jersey_number), dict_medicines(name, wada_status)"
    ).order("course_start", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df["medicine_name"] = df["dict_medicines"].apply(lambda x: x["name"] if x else None)
        df["wada_status"] = df["dict_medicines"].apply(lambda x: x["wada_status"] if x else None)
        df = df.drop(columns=["athletes", "dict_medicines"])
    return df

@st.cache_data(ttl=60)
def load_all_examinations():
    r = supabase.table("examinations").select(
        "*, athletes(full_name, jersey_number), dict_exam_templates(name)"
    ).order("examination_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df["exam_name"] = df["dict_exam_templates"].apply(lambda x: x["name"] if x else None)
        df = df.drop(columns=["athletes", "dict_exam_templates"])
    return df

@st.cache_data(ttl=60)
def load_vaccinations():
    r = supabase.table("vaccinations").select(
        "*, athletes(full_name, jersey_number)"
    ).order("vaccination_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df = df.drop(columns=["athletes"])
    return df

@st.cache_data(ttl=60)
def load_anthropometry():
    r = supabase.table("anthropometry").select(
        "*, athletes(full_name, jersey_number)"
    ).order("measurement_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df = df.drop(columns=["athletes"])
    return df

@st.cache_data(ttl=60)
def load_functional_tests():
    r = supabase.table("functional_tests").select(
        "*, athletes(full_name, jersey_number), dict_test_types(name, unit)"
    ).order("test_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df["test_name"] = df["dict_test_types"].apply(lambda x: x["name"] if x else None)
        df = df.drop(columns=["athletes", "dict_test_types"])
    return df

@st.cache_data(ttl=60)
def load_chronic_diseases():
    r = supabase.table("chronic_diseases").select(
        "*, athletes(full_name, jersey_number)"
    ).order("diagnosis_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df = df.drop(columns=["athletes"])
    return df

@st.cache_data(ttl=60)
def load_lab_results():
    r = supabase.table("lab_results").select(
        "*, athletes(full_name, jersey_number), dict_biomarkers(name, unit)"
    ).order("measurement_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df["biomarker_name"] = df["dict_biomarkers"].apply(lambda x: x["name"] if x else None)
        df["unit"] = df["dict_biomarkers"].apply(lambda x: x["unit"] if x else None)
        df = df.drop(columns=["athletes", "dict_biomarkers"])
    return df

@st.cache_data(ttl=60)
def load_doctor_visits():
    r = supabase.table("doctor_visits").select(
        "*, athletes(full_name, jersey_number), dict_diagnoses(name, mkb_code)"
    ).order("visit_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df["diagnosis"] = df["dict_diagnoses"].apply(
            lambda x: f"{x.get('mkb_code') or ''} — {x.get('name') or ''}" if x else None
        )
        df = df.drop(columns=["athletes", "dict_diagnoses"])
    return df

# ============ ЗАГРУЗКА ============
df_dashboard = load_today_dashboard()
df_missing = load_missing_reports()
df_overdue = load_overdue_exams()
df_athletes = load_athletes()
df_athletes_full = load_athletes_full()
df_logs = load_health_logs(30)
df_all_exams = load_all_examinations()
df_injuries = load_injuries(365)
df_injuries_all = load_injuries_all()
df_meds_current = load_medications()
df_vaccinations = load_vaccinations()
df_anthro = load_anthropometry()
df_tests = load_functional_tests()
df_chronic = load_chronic_diseases()
df_lab = load_lab_results()
df_visits = load_doctor_visits()
df_body_parts = load_body_parts()
df_diagnoses = load_diagnoses()
df_medicines = load_medicines()
df_exam_templates = load_exam_templates()
df_test_types = load_test_types()
df_biomarkers = load_biomarkers()
df_staff = load_staff()

# ============ ЗАГОЛОВОК ============
st.title("🏐 Медицинский дашборд команды")
if user_role == "athlete":
    st.caption(f"Личный кабинет спортсменки · {user.get('full_name', '')}")
else:
    st.caption(f"Пользователь: {user.get('full_name', 'Гость')} ({user_role})")

# ============ ЛИЧНЫЙ КАБИНЕТ СПОРТСМЕНКИ ============
if user_role == "athlete" and user_athlete_id:
    tab_status, tab_dynamics, tab_exams_self = st.tabs(["📊 Мой статус", "📈 Моя динамика", "🏥 Мои осмотры"])

    with tab_status:
        st.header("📊 Мой статус на сегодня")
        if df_athletes.empty or "id" not in df_athletes.columns:
            st.info("Нет данных о спортсменке.")
        else:
            my_row = df_athletes[df_athletes["id"] == user_athlete_id]
            my_jersey = int(my_row["jersey_number"].iloc[0]) if not my_row.empty and pd.notna(my_row["jersey_number"].iloc[0]) else None
            my_dashboard = df_dashboard[df_dashboard["№"] == my_jersey] if my_jersey and not df_dashboard.empty else pd.DataFrame()
            if not my_dashboard.empty:
                r = my_dashboard.iloc[0]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Статус", f"{r.get('icon', '⚪')} {r.get('status', 'grey')}")
                c2.metric("Пульс", r.get("Пульс", "—"))
                c3.metric("Разница", r.get("Разница", "—"))
                c4.metric("Сон", r.get("Сон", "—"))
                if "Причина" in r and pd.notna(r["Причина"]):
                    st.info(f"**Причина:** {r['Причина']}")
            else:
                st.info("📭 Сегодня вы ещё не отправляли утренний отчёт.")

    with tab_dynamics:
        st.header("📈 Моя динамика за 30 дней")
        if df_logs.empty or "athlete_id" not in df_logs.columns:
            st.info("Нет данных за 30 дней.")
        else:
            my_logs = df_logs[df_logs["athlete_id"] == user_athlete_id]
            if my_logs.empty:
                st.info("Нет данных за 30 дней.")
            else:
                dfc = my_logs[["log_date", "morning_hr", "ortho_hr_after", "sleep_hours", "borg_rating"]].sort_values("log_date").set_index("log_date")
                c1, c2 = st.columns(2)
                with c1:
                    st.subheader("❤️ Пульс")
                    if dfc["morning_hr"].notna().any():
                        d = dfc[["morning_hr"]].dropna()
                        d.columns = ["Пульс утром"]
                        st.line_chart(d, use_container_width=True)
                with c2:
                    st.subheader("😴 Сон")
                    if dfc["sleep_hours"].notna().any():
                        d = dfc[["sleep_hours"]].dropna()
                        d.columns = ["Часы сна"]
                        st.line_chart(d, use_container_width=True)
                st.subheader("📊 Ортостатическая разница")
                o = dfc[["morning_hr", "ortho_hr_after"]].dropna()
                if not o.empty:
                    o["Разница"] = o["ortho_hr_after"] - o["morning_hr"]
                    st.line_chart(o[["Разница"]], use_container_width=True)

    with tab_exams_self:
        st.header("🏥 Мои медицинские осмотры")
        if df_all_exams.empty or "athlete_id" not in df_all_exams.columns:
            st.info("Осмотры пока не внесены.")
        else:
            my_exams = df_all_exams[df_all_exams["athlete_id"] == user_athlete_id]
            if my_exams.empty:
                st.info("Осмотры пока не внесены.")
            else:
                cols = ["examination_date", "exam_name", "is_approved", "next_exam_date", "restrictions"]
                av = [c for c in cols if c in my_exams.columns]
                d = format_dates(my_exams[av].copy(), ["examination_date", "next_exam_date"])
                d = d.rename(columns={
                    "examination_date": "Дата", "exam_name": "Осмотр",
                    "is_approved": "Допуск", "next_exam_date": "Следующий",
                    "restrictions": "Ограничения"
                })
                st.dataframe(d, use_container_width=True, hide_index=True)

# ============ ДАШБОРД ВРАЧА / ТРЕНЕРА / АДМИНА ============
else:
    if user_role == "coach":
        tabs = st.tabs(["📊 Сегодня", "📈 Динамика"])
        tab_today, tab_dynamics = tabs
        tab_cards = tab_medcard = tab_visits = tab_exams = tab_injuries = None
        tab_meds = tab_vaccines = tab_anthro = tab_tests = None
        tab_chronic = tab_lab = None
    elif user_role == "masseur":
        tabs = st.tabs(["📊 Сегодня", "📈 Динамика", "🩹 Травмы", "📏 Антропометрия"])
        tab_today, tab_dynamics, tab_injuries, tab_anthro = tabs
        tab_cards = tab_medcard = tab_visits = tab_exams = None
        tab_meds = tab_vaccines = tab_tests = tab_chronic = tab_lab = None
    else:
        tabs = st.tabs([
            "📊 Сегодня", "📈 Динамика",
            "👤 Карточки", "🗂️ Карта спортсменки",
            "🩺 Приёмы", "🏥 Осмотры",
            "🩹 Травмы", "💊 Лекарства", "💉 Прививки",
            "📏 Антропометрия", "🏃 Тесты",
            "🩺 Хроники", "🧪 Анализы"
        ])
        (tab_today, tab_dynamics, tab_cards, tab_medcard, tab_visits, tab_exams,
         tab_injuries, tab_meds, tab_vaccines, tab_anthro, tab_tests,
         tab_chronic, tab_lab) = tabs

    # --- СЕГОДНЯ ---
    with tab_today:
        st.header("📊 Сводка за сегодня")
        rc = len(df_dashboard[df_dashboard["status"] == "red"]) if not df_dashboard.empty else 0
        yc = len(df_dashboard[df_dashboard["status"] == "yellow"]) if not df_dashboard.empty else 0
        gc = len(df_dashboard[df_dashboard["status"] == "green"]) if not df_dashboard.empty else 0
        grc = len(df_dashboard[df_dashboard["status"] == "grey"]) if not df_dashboard.empty else 0
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🔴 Проблемы", rc)
        c2.metric("🟡 Внимание", yc)
        c3.metric("🟢 Норма", gc)
        c4.metric("⚪ Нет данных", grc)
        st.divider()
        st.subheader("🚦 Статус спортсменок")
        if not df_dashboard.empty:
            filt = st.selectbox("Фильтр", ["Все", "🔴 Только красные", "🟡 Только жёлтые", "🟢 Только зелёные", "⚪ Только без данных"])
            if filt == "🔴 Только красные":
                df_d = df_dashboard[df_dashboard["status"] == "red"]
            elif filt == "🟡 Только жёлтые":
                df_d = df_dashboard[df_dashboard["status"] == "yellow"]
            elif filt == "🟢 Только зелёные":
                df_d = df_dashboard[df_dashboard["status"] == "green"]
            elif filt == "⚪ Только без данных":
                df_d = df_dashboard[df_dashboard["status"] == "grey"]
            else:
                df_d = df_dashboard
            cols = ["icon", "№", "ФИО", "Пульс", "Разница", "Борг", "Сон", "Причина"]
            av = [c for c in cols if c in df_d.columns]
            st.dataframe(df_d[av], use_container_width=True, hide_index=True)
        else:
            st.info("Нет данных за сегодня.")
        st.divider()
        st.subheader("📵 Не сдали утренний отчёт")
        if not df_missing.empty:
            st.warning(f"Не сдали: {len(df_missing)}")
            st.dataframe(df_missing, use_container_width=True, hide_index=True)
        else:
            st.success("✅ Все сдали!")

    # --- ДИНАМИКА ---
    with tab_dynamics:
        st.header("📈 Динамика за 30 дней")
        opts = ["👥 Вся команда"]
        amap = {}
        if not df_athletes.empty:
            for _, row in df_athletes.iterrows():
                j = int(row['jersey_number']) if pd.notna(row['jersey_number']) else None
                label = f"№{j} — {row['full_name']}" if j else f"(без номера) {row['full_name']}"
                opts.append(label)
                amap[label] = row['id']
        sel = st.selectbox("Спортсменка", opts)
        if sel == "👥 Вся команда":
            df_f = df_logs
            suf = "команды"
        else:
            df_f = df_logs[df_logs["athlete_id"] == amap[sel]]
            suf = f"— {sel}"
        if df_f.empty:
            st.info(f"Нет данных для {suf}.")
        else:
            if sel == "👥 Вся команда":
                dfc = df_f.groupby("log_date").agg({
                    "morning_hr": "mean", "ortho_hr_after": "mean",
                    "sleep_hours": "mean", "borg_rating": "mean"
                }).reset_index()
            else:
                dfc = df_f[["log_date", "morning_hr", "ortho_hr_after", "sleep_hours", "borg_rating"]].copy()
            dfc = dfc.sort_values("log_date").set_index("log_date")
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("❤️ Пульс")
                if dfc["morning_hr"].notna().any():
                    d = dfc[["morning_hr"]].dropna()
                    d.columns = ["Пульс"]
                    st.line_chart(d, use_container_width=True)
            with c2:
                st.subheader("😴 Сон")
                if dfc["sleep_hours"].notna().any():
                    d = dfc[["sleep_hours"]].dropna()
                    d.columns = ["Сон"]
                    st.line_chart(d, use_container_width=True)
            st.subheader("📊 Ортостатическая разница")
            o = dfc[["morning_hr", "ortho_hr_after"]].dropna()
            if not o.empty:
                o["Разница"] = o["ortho_hr_after"] - o["morning_hr"]
                st.line_chart(o[["Разница"]], use_container_width=True)
            c3, c4 = st.columns(2)
            with c3:
                st.subheader("💪 Шкала Борга")
                if dfc["borg_rating"].notna().any():
                    d = dfc[["borg_rating"]].dropna()
                    d.columns = ["Борг"]
                    st.line_chart(d, use_container_width=True)

    # --- КАРТОЧКИ ---
    if tab_cards is not None:
        with tab_cards:
            st.header("👤 Карточки спортсменок")
            sv, sa = st.tabs(["📋 Просмотр", "✍️ Добавить / Редактировать"])

            with sv:
                if df_athletes_full.empty:
                    st.info("Нет активных спортсменок.")
                else:
                    st.caption(f"Всего спортсменок: {len(df_athletes_full)}")
                    cols_show = ["jersey_number", "full_name", "birth_date", "blood_type", "rh_factor", "handball_start_year", "phone"]
                    av = [c for c in cols_show if c in df_athletes_full.columns]
                    d = df_athletes_full[av].copy()
                    if "birth_date" in d.columns:
                        d["Возраст"] = pd.to_datetime(d["birth_date"], errors='coerce').apply(
                            lambda x: date.today().year - x.year - ((date.today().month, date.today().day) < (x.month, x.day)) if pd.notna(x) else None
                        )
                    if "handball_start_year" in d.columns:
                        d["Стаж"] = date.today().year - d["handball_start_year"]
                    d = d.rename(columns={
                        "jersey_number": "№", "full_name": "ФИО", "birth_date": "Дата рождения",
                        "blood_type": "Кровь", "rh_factor": "Резус",
                        "handball_start_year": "Год начала", "phone": "Телефон"
                    })
                    if "Дата рождения" in d.columns:
                        d["Дата рождения"] = pd.to_datetime(d["Дата рождения"], errors='coerce').dt.strftime('%d.%m.%Y')
                    desired_order = ["№", "ФИО", "Дата рождения", "Возраст", "Кровь", "Резус", "Год начала", "Стаж", "Телефон"]
                    final_cols = [c for c in desired_order if c in d.columns]
                    d = d[final_cols]

                    event = st.dataframe(
                        d,
                        on_select="rerun",
                        selection_mode="single-row",
                        use_container_width=True,
                        hide_index=True
                    )

                    st.divider()
                    st.subheader("👁️ Детальная информация")

                    opts = athlete_options_dict()
                    sel_key = st.selectbox("Выберите спортсменку", ["— не выбрано —"] + list(opts.keys()), key="card_view")

                    selected_aid = None
                    if event.selection.rows:
                        idx = event.selection.rows[0]
                        if "№" in d.columns and idx < len(df_athletes_full):
                            selected_jersey = d.iloc[idx]["№"]
                            row_match = df_athletes_full[df_athletes_full["jersey_number"] == selected_jersey]
                            if not row_match.empty:
                                selected_aid = row_match.iloc[0]["id"]
                    elif sel_key != "— не выбрано —":
                        selected_aid = opts[sel_key]

                    if selected_aid:
                        row = df_athletes_full[df_athletes_full["id"] == selected_aid].iloc[0]
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown(f"**ФИО:** {row.get('full_name', '—')}")
                            bd = pd.to_datetime(row.get('birth_date')).strftime('%d.%m.%Y') if pd.notna(row.get('birth_date')) else '—'
                            st.markdown(f"**Дата рождения:** {bd}")
                            if pd.notna(row.get('birth_date')):
                                bd_dt = pd.to_datetime(row['birth_date'])
                                today = pd.Timestamp.today()
                                age = today.year - bd_dt.year - ((today.month, today.day) < (bd_dt.month, bd_dt.day))
                                st.markdown(f"**Возраст:** {age} лет")
                            st.markdown(f"**Игровой номер:** {int(row['jersey_number']) if pd.notna(row.get('jersey_number')) else '—'}")
                            st.markdown(f"**Телефон:** {row.get('phone', '—')}")
                            st.markdown(f"**Адрес:** {row.get('address', '—')}")
                        with c2:
                            st.markdown(f"**Группа крови:** {row.get('blood_type', '—')}")
                            st.markdown(f"**Резус:** {row.get('rh_factor', '—')}")
                            st.markdown(f"**Год начала занятий:** {int(row['handball_start_year']) if pd.notna(row.get('handball_start_year')) else '—'}")
                            st.markdown(f"**🚨 Экстренный контакт:** {row.get('emergency_contact', '—')} · {row.get('emergency_phone', '—')}")
                        st.markdown(f"**⚠️ Аллергии:** {row.get('allergies') or '—'}")
                        st.markdown(f"**📝 Заметки врача:** {row.get('medical_notes') or '—'}")
                        st.divider()
                        st.subheader(f"🗂️ Медицинская карта: {row.get('full_name', '')}")

                        mc_tabs = st.tabs([
                            "🩺 Приёмы", "🏥 Осмотры", "🩹 Травмы", "💊 Лекарства",
                            "💉 Прививки", "📏 Антропометрия", "🏃 Тесты",
                            "🩺 Хроники", "🧪 Анализы"
                        ])
                        (mc_visits, mc_exams, mc_injuries, mc_meds,
                         mc_vacc, mc_anthro, mc_tests, mc_chronic, mc_lab) = mc_tabs

                        mc_aid = selected_aid  # текущая выбранная спортсменка

                        # --- Приёмы ---
                        with mc_visits:
                            if not df_visits.empty and "athlete_id" in df_visits.columns:
                                my = df_visits[df_visits["athlete_id"] == mc_aid]
                            else:
                                my = pd.DataFrame()
                            if my.empty:
                                st.info("Приёмов нет.")
                            else:
                                cols = ["visit_date", "complaints", "diagnosis", "prescriptions"]
                                av = [c for c in cols if c in my.columns]
                                d = format_dates(my[av].copy(), ["visit_date"])
                                d = d.rename(columns={"visit_date": "Дата", "complaints": "Жалобы", "diagnosis": "Диагноз", "prescriptions": "Назначения"})
                                st.dataframe(d, use_container_width=True, hide_index=True)

                        # --- Осмотры ---
                        with mc_exams:
                            if not df_all_exams.empty and "athlete_id" in df_all_exams.columns:
                                my = df_all_exams[df_all_exams["athlete_id"] == mc_aid]
                            else:
                                my = pd.DataFrame()
                            if my.empty:
                                st.info("Осмотров нет.")
                            else:
                                cols = ["examination_date", "exam_name", "is_approved", "next_exam_date", "restrictions"]
                                av = [c for c in cols if c in my.columns]
                                d = format_dates(my[av].copy(), ["examination_date", "next_exam_date"])
                                d = d.rename(columns={"examination_date": "Дата", "exam_name": "Осмотр", "is_approved": "Допуск", "next_exam_date": "Следующий", "restrictions": "Ограничения"})
                                st.dataframe(d, use_container_width=True, hide_index=True)

                        # --- Травмы (все) ---
                        with mc_injuries:
                            if not df_injuries_all.empty and "athlete_id" in df_injuries_all.columns:
                                my = df_injuries_all[df_injuries_all["athlete_id"] == mc_aid]
                            else:
                                my = pd.DataFrame()
                            if my.empty:
                                st.info("Травм нет.")
                            else:
                                cols = ["incident_date", "diagnosis", "body_part", "side", "severity", "days_lost"]
                                av = [c for c in cols if c in my.columns]
                                d = format_dates(my[av].copy(), ["incident_date"])
                                d = d.rename(columns={"incident_date": "Дата", "diagnosis": "Диагноз", "body_part": "Часть тела", "side": "Сторона", "severity": "Тяжесть", "days_lost": "Пропущено"})
                                st.dataframe(d, use_container_width=True, hide_index=True)

                        # --- Лекарства ---
                        with mc_meds:
                            if not df_meds_current.empty and "athlete_id" in df_meds_current.columns:
                                my = df_meds_current[df_meds_current["athlete_id"] == mc_aid]
                            else:
                                my = pd.DataFrame()
                            if my.empty:
                                st.info("Назначений нет.")
                            else:
                                cols = ["medicine_name", "dosage", "frequency", "course_start", "course_end", "wada_status"]
                                av = [c for c in cols if c in my.columns]
                                d = format_dates(my[av].copy(), ["course_start", "course_end"])
                                d = d.rename(columns={"medicine_name": "Препарат", "dosage": "Дозировка", "frequency": "Кратность", "course_start": "С", "course_end": "По", "wada_status": "WADA"})
                                st.dataframe(d, use_container_width=True, hide_index=True)

                        # --- Прививки ---
                        with mc_vacc:
                            if not df_vaccinations.empty and "athlete_id" in df_vaccinations.columns:
                                my = df_vaccinations[df_vaccinations["athlete_id"] == mc_aid]
                            else:
                                my = pd.DataFrame()
                            if my.empty:
                                st.info("Прививок нет.")
                            else:
                                cols = ["vaccination_date", "vaccine_name", "booster_date", "batch_number"]
                                av = [c for c in cols if c in my.columns]
                                d = format_dates(my[av].copy(), ["vaccination_date", "booster_date"])
                                d = d.rename(columns={"vaccination_date": "Дата", "vaccine_name": "Вакцина", "booster_date": "Ревакцинация", "batch_number": "Серия"})
                                st.dataframe(d, use_container_width=True, hide_index=True)

                        # --- Антропометрия ---
                        with mc_anthro:
                            if not df_anthro.empty and "athlete_id" in df_anthro.columns:
                                my = df_anthro[df_anthro["athlete_id"] == mc_aid]
                            else:
                                my = pd.DataFrame()
                            if my.empty:
                                st.info("Измерений нет.")
                            else:
                                cols = ["measurement_date", "height", "weight", "bmi", "body_fat", "muscle_mass"]
                                av = [c for c in cols if c in my.columns]
                                d = format_dates(my[av].copy(), ["measurement_date"])
                                d = d.rename(columns={"measurement_date": "Дата", "height": "Рост", "weight": "Вес", "bmi": "ИМТ", "body_fat": "% жира", "muscle_mass": "Мышцы"})
                                st.dataframe(d, use_container_width=True, hide_index=True)

                        # --- Тесты ---
                        with mc_tests:
                            if not df_tests.empty and "athlete_id" in df_tests.columns:
                                my = df_tests[df_tests["athlete_id"] == mc_aid]
                            else:
                                my = pd.DataFrame()
                            if my.empty:
                                st.info("Тестов нет.")
                            else:
                                cols = ["test_date", "test_name", "result_raw", "result_score", "evaluation"]
                                av = [c for c in cols if c in my.columns]
                                d = format_dates(my[av].copy(), ["test_date"])
                                d = d.rename(columns={"test_date": "Дата", "test_name": "Тест", "result_raw": "Результат", "result_score": "Балл", "evaluation": "Оценка"})
                                st.dataframe(d, use_container_width=True, hide_index=True)

                        # --- Хроники ---
                        with mc_chronic:
                            if not df_chronic.empty and "athlete_id" in df_chronic.columns:
                                my = df_chronic[df_chronic["athlete_id"] == mc_aid]
                            else:
                                my = pd.DataFrame()
                            if my.empty:
                                st.info("Хроник нет.")
                            else:
                                cols = ["diagnosis_date", "disease_name", "severity", "current_medication"]
                                av = [c for c in cols if c in my.columns]
                                d = format_dates(my[av].copy(), ["diagnosis_date"])
                                d = d.rename(columns={"diagnosis_date": "Дата", "disease_name": "Заболевание", "severity": "Тяжесть", "current_medication": "Лекарства"})
                                st.dataframe(d, use_container_width=True, hide_index=True)

                        # --- Анализы ---
                        with mc_lab:
                            if not df_lab.empty and "athlete_id" in df_lab.columns:
                                my = df_lab[df_lab["athlete_id"] == mc_aid]
                            else:
                                my = pd.DataFrame()
                            if my.empty:
                                st.info("Анализов нет.")
                            else:
                                cols = ["measurement_date", "biomarker_name", "value", "unit"]
                                av = [c for c in cols if c in my.columns]
                                d = format_dates(my[av].copy(), ["measurement_date"])
                                d = d.rename(columns={"measurement_date": "Дата", "biomarker_name": "Показатель", "value": "Значение", "unit": "Ед."})
                                st.dataframe(d, use_container_width=True, hide_index=True)
                    else:
                        st.info("👆 Выберите спортсменку в таблице или в списке выше")

            with sa:
                st.subheader("✍️ Добавить или отредактировать спортсменку")
                mode = st.radio("Режим", ["✏️ Редактировать", "➕ Создать новую"], horizontal=True)

                if mode == "✏️ Редактировать":
                    if df_athletes_full.empty:
                        st.warning("Нет спортсменок.")
                    else:
                        opts_e = athlete_options_dict()
                        sel_e = st.selectbox("Спортсменка *", list(opts_e.keys()), key="card_edit")
                        edit_id = opts_e[sel_e] if sel_e else None
                        cur = df_athletes_full[df_athletes_full["id"] == edit_id].iloc[0] if edit_id else None

                        if cur is not None:
                            with st.form("form_edit_athlete"):
                                st.markdown("### 👤 Основные данные")
                                c1, c2 = st.columns(2)
                                with c1:
                                    full_name = st.text_input("ФИО *", value=cur.get("full_name", "") or "")
                                    bd_val = pd.to_datetime(cur.get("birth_date")).date() if pd.notna(cur.get("birth_date")) else date(2008, 1, 1)
                                    birth_date = st.date_input("Дата рождения *", value=bd_val, format="DD.MM.YYYY")
                                    jersey = st.number_input("Игровой номер", min_value=0, max_value=999, value=int(cur["jersey_number"]) if pd.notna(cur.get("jersey_number")) else 0)
                                    hy = st.number_input("Год начала занятий гандболом", min_value=1950, max_value=date.today().year, value=int(cur["handball_start_year"]) if pd.notna(cur.get("handball_start_year")) else date.today().year)
                                with c2:
                                    phone = st.text_input("Телефон", value=cur.get("phone", "") or "")
                                    address = st.text_input("Адрес", value=cur.get("address", "") or "")

                                st.markdown("### 🩸 Медицинские данные")
                                c3, c4 = st.columns(2)
                                with c3:
                                    bt_list = ["— не указана —", "1", "2", "3", "4"]
                                    bt_idx = bt_list.index(str(cur.get("blood_type"))) if str(cur.get("blood_type")) in bt_list else 0
                                    blood_type = st.selectbox("Группа крови", bt_list, index=bt_idx)
                                    rh_list = ["— не указан —", "+", "−"]
                                    rh_idx = rh_list.index(cur.get("rh_factor")) if cur.get("rh_factor") in ["+", "−"] else 0
                                    rh = st.selectbox("Резус-фактор", rh_list, index=rh_idx)
                                with c4:
                                    emergency_contact = st.text_input("Экстренный контакт (ФИО)", value=cur.get("emergency_contact", "") or "")
                                    emergency_phone = st.text_input("Телефон экстренного контакта", value=cur.get("emergency_phone", "") or "")

                                st.markdown("### ⚠️ Аллергии и заметки")
                                allergies = st.text_area("Аллергии", value=cur.get("allergies", "") or "", height=60)
                                medical_notes = st.text_area("Заметки врача", value=cur.get("medical_notes", "") or "", height=80)

                                st.markdown("### 📞 Telegram")
                                telegram_id = st.text_input("Telegram ID", value=cur.get("telegram_user_id", "") or "")

                                if st.form_submit_button("💾 Сохранить изменения", type="primary"):
                                    if not full_name.strip():
                                        st.error("ФИО обязательно")
                                    else:
                                        try:
                                            supabase.table("athletes").update({
                                                "full_name": full_name.strip(),
                                                "birth_date": birth_date.isoformat(),
                                                "jersey_number": int(jersey) if jersey > 0 else None,
                                                "handball_start_year": int(hy),
                                                "phone": phone.strip() or None,
                                                "address": address.strip() or None,
                                                "blood_type": blood_type if blood_type != "— не указана —" else None,
                                                "rh_factor": rh if rh != "— не указан —" else None,
                                                "emergency_contact": emergency_contact.strip() or None,
                                                "emergency_phone": emergency_phone.strip() or None,
                                                "allergies": allergies.strip() or None,
                                                "medical_notes": medical_notes.strip() or None,
                                                "telegram_user_id": telegram_id.strip() or None
                                            }).eq("id", edit_id).execute()
                                            st.success(f"✅ Обновлено: {full_name}")
                                            st.cache_data.clear()
                                        except Exception as e:
                                            st.error(f"Ошибка: {e}")

                else:
                    with st.form("form_new_athlete"):
                        st.markdown("### 👤 Основные данные")
                        c1, c2 = st.columns(2)
                        with c1:
                            full_name = st.text_input("ФИО *", placeholder="Иванова Анна Сергеевна")
                            birth_date = st.date_input("Дата рождения *", value=date(2008, 1, 1), format="DD.MM.YYYY")
                            jersey = st.number_input("Игровой номер", min_value=0, max_value=999, value=0)
                            hy = st.number_input("Год начала занятий гандболом", min_value=1950, max_value=date.today().year, value=date.today().year)
                        with c2:
                            phone = st.text_input("Телефон", placeholder="+375 29 123-45-67")
                            address = st.text_input("Адрес")
                        st.markdown("### 🩸 Медицинские данные")
                        c3, c4 = st.columns(2)
                        with c3:
                            blood_type = st.selectbox("Группа крови", ["— не указана —", "1", "2", "3", "4"])
                            rh = st.selectbox("Резус-фактор", ["— не указан —", "+", "−"])
                        with c4:
                            emergency_contact = st.text_input("Экстренный контакт (ФИО)")
                            emergency_phone = st.text_input("Телефон экстренного контакта")
                        st.markdown("### ⚠️ Аллергии и заметки")
                        allergies = st.text_area("Аллергии", height=60)
                        medical_notes = st.text_area("Заметки врача", height=80)
                        st.markdown("### 📞 Telegram")
                        telegram_id = st.text_input("Telegram ID", placeholder="470812340")
                        if st.form_submit_button("💾 Создать спортсменку", type="primary"):
                            if not full_name.strip():
                                st.error("ФИО обязательно")
                            else:
                                try:
                                    supabase.table("athletes").insert({
                                        "full_name": full_name.strip(),
                                        "birth_date": birth_date.isoformat(),
                                        "jersey_number": int(jersey) if jersey > 0 else None,
                                        "handball_start_year": int(hy),
                                        "phone": phone.strip() or None,
                                        "address": address.strip() or None,
                                        "blood_type": blood_type if blood_type != "— не указана —" else None,
                                        "rh_factor": rh if rh != "— не указан —" else None,
                                        "emergency_contact": emergency_contact.strip() or None,
                                        "emergency_phone": emergency_phone.strip() or None,
                                        "allergies": allergies.strip() or None,
                                        "medical_notes": medical_notes.strip() or None,
                                        "telegram_user_id": telegram_id.strip() or None,
                                        "is_active": True
                                    }).execute()
                                    st.success(f"✅ Создано: {full_name}")
                                    st.cache_data.clear()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")
    # --- КАРТА СПОРТСМЕНКИ ---
    if tab_medcard is not None:
        with tab_medcard:
            st.header("🗂️ Медицинская карта спортсменки")

            opts_mc = athlete_options_dict()
            if not opts_mc:
                st.info("Нет активных спортсменок.")
            else:
                sel_mc = st.selectbox("Выберите спортсменку", list(opts_mc.keys()), key="medcard_select")
                mc_aid = opts_mc[sel_mc]

                # Краткая карточка спортсменки
                row_mc = df_athletes_full[df_athletes_full["id"] == mc_aid]
                if not row_mc.empty:
                    r = row_mc.iloc[0]
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown(f"**ФИО:** {r.get('full_name', '—')}")
                        bd = pd.to_datetime(r.get('birth_date')).strftime('%d.%m.%Y') if pd.notna(r.get('birth_date')) else '—'
                        st.markdown(f"**Дата рождения:** {bd}")
                        if pd.notna(r.get('birth_date')):
                            bd_dt = pd.to_datetime(r['birth_date'])
                            today = pd.Timestamp.today()
                            age = today.year - bd_dt.year - ((today.month, today.day) < (bd_dt.month, bd_dt.day))
                            st.markdown(f"**Возраст:** {age} лет")
                    with c2:
                        st.markdown(f"**Игровой номер:** {int(r['jersey_number']) if pd.notna(r.get('jersey_number')) else '—'}")
                        st.markdown(f"**Группа крови:** {r.get('blood_type', '—')} {r.get('rh_factor', '')}")
                        st.markdown(f"**Телефон:** {r.get('phone', '—')}")
                    with c3:
                        st.markdown(f"**Аллергии:** {r.get('allergies') or '—'}")
                        st.markdown(f"**Экстренный контакт:** {r.get('emergency_contact', '—')} · {r.get('emergency_phone', '—')}")

                st.divider()

                # Подвкладки по типам данных
                mc_tabs = st.tabs([
                    "🩺 Приёмы", "🏥 Осмотры", "🩹 Травмы", "💊 Лекарства",
                    "💉 Прививки", "📏 Антропометрия", "🏃 Тесты",
                    "🩺 Хроники", "🧪 Анализы"
                ])
                (mc_visits, mc_exams, mc_injuries, mc_meds,
                 mc_vacc, mc_anthro, mc_tests, mc_chronic, mc_lab) = mc_tabs

                # --- Приёмы ---
                with mc_visits:
                    my = df_visits[df_visits["athlete_id"] == mc_aid] if not df_visits.empty else pd.DataFrame()
                    if my.empty:
                        st.info("Приёмов нет.")
                    else:
                        cols = ["visit_date", "complaints", "diagnosis", "prescriptions"]
                        av = [c for c in cols if c in my.columns]
                        d = format_dates(my[av].copy(), ["visit_date"])
                        d = d.rename(columns={"visit_date": "Дата", "complaints": "Жалобы", "diagnosis": "Диагноз", "prescriptions": "Назначения"})
                        ev = st.dataframe(d, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)
                        if ev.selection.rows:
                            idx = ev.selection.rows[0]
                            if idx < len(my):
                                v = my.iloc[idx]
                                st.markdown("---")
                                st.markdown(f"**Дата:** {pd.to_datetime(v['visit_date']).strftime('%d.%m.%Y') if pd.notna(v.get('visit_date')) else '—'}")
                                st.markdown(f"**Жалобы:** {v.get('complaints') or '—'}")
                                st.markdown(f"**Осмотр:** {v.get('examination') or '—'}")
                                st.markdown(f"**Диагноз:** {v.get('diagnosis') or v.get('diagnosis_text') or '—'}")
                                st.markdown(f"**Назначения:** {v.get('prescriptions') or '—'}")
                                st.markdown(f"**Рекомендации:** {v.get('recommendations') or '—'}")

                # --- Осмотры ---
                with mc_exams:
                    my = df_all_exams[df_all_exams["athlete_id"] == mc_aid] if not df_all_exams.empty else pd.DataFrame()
                    if my.empty:
                        st.info("Осмотров нет.")
                    else:
                        cols = ["examination_date", "exam_name", "is_approved", "next_exam_date"]
                        av = [c for c in cols if c in my.columns]
                        d = format_dates(my[av].copy(), ["examination_date", "next_exam_date"])
                        d = d.rename(columns={"examination_date": "Дата", "exam_name": "Осмотр", "is_approved": "Допуск", "next_exam_date": "Следующий"})
                        ev = st.dataframe(d, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)
                        if ev.selection.rows:
                            idx = ev.selection.rows[0]
                            if idx < len(my):
                                e = my.iloc[idx]
                                st.markdown("---")
                                st.markdown(f"**Дата:** {pd.to_datetime(e['examination_date']).strftime('%d.%m.%Y') if pd.notna(e.get('examination_date')) else '—'}")
                                st.markdown(f"**Тип:** {e.get('exam_name') or '—'}")
                                st.markdown(f"**Заключение:** {e.get('result_text') or '—'}")
                                ap = e.get("is_approved")
                                st.markdown(f"**Допуск:** {'✅ Да' if ap else '❌ Нет' if ap is False else '—'}")
                                st.markdown(f"**Ограничения:** {e.get('restrictions') or '—'}")
                                if pd.notna(e.get("next_exam_date")):
                                    st.markdown(f"**Следующий:** {pd.to_datetime(e['next_exam_date']).strftime('%d.%m.%Y')}")

                # --- Травмы (все, за всё время) ---
                with mc_injuries:
                    my = df_injuries_all[df_injuries_all["athlete_id"] == mc_aid] if not df_injuries_all.empty else pd.DataFrame()
                    if my.empty:
                        st.info("Травм нет.")
                    else:
                        cols = ["incident_date", "diagnosis", "body_part", "side", "severity", "days_lost"]
                        av = [c for c in cols if c in my.columns]
                        d = format_dates(my[av].copy(), ["incident_date"])
                        d = d.rename(columns={"incident_date": "Дата", "diagnosis": "Диагноз", "body_part": "Часть тела", "side": "Сторона", "severity": "Тяжесть", "days_lost": "Пропущено"})
                        ev = st.dataframe(d, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)
                        if ev.selection.rows:
                            idx = ev.selection.rows[0]
                            if idx < len(my):
                                i = my.iloc[idx]
                                st.markdown("---")
                                st.markdown(f"**Дата:** {pd.to_datetime(i['incident_date']).strftime('%d.%m.%Y') if pd.notna(i.get('incident_date')) else '—'}")
                                st.markdown(f"**Диагноз:** {i.get('diagnosis') or '—'}")
                                st.markdown(f"**Часть тела:** {i.get('body_part') or '—'} · **Сторона:** {i.get('side') or '—'}")
                                st.markdown(f"**Тяжесть:** {i.get('severity') or '—'} · **Рецидив:** {'Да' if i.get('is_recurrent') else 'Нет'}")
                                st.markdown(f"**Механизм:** {i.get('mechanism') or '—'}")
                                st.markdown(f"**Лечение:** {i.get('treatment_description') or '—'}")
                                st.markdown(f"**Пропущено дней:** {i.get('days_lost', 0)}")

                # --- Лекарства ---
                with mc_meds:
                    my = df_meds_current[df_meds_current["athlete_id"] == mc_aid] if not df_meds_current.empty else pd.DataFrame()
                    if my.empty:
                        st.info("Назначений нет.")
                    else:
                        cols = ["medicine_name", "dosage", "frequency", "course_start", "course_end", "wada_status"]
                        av = [c for c in cols if c in my.columns]
                        d = format_dates(my[av].copy(), ["course_start", "course_end"])
                        d = d.rename(columns={"medicine_name": "Препарат", "dosage": "Дозировка", "frequency": "Кратность", "course_start": "С", "course_end": "По", "wada_status": "WADA"})
                        ev = st.dataframe(d, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)
                        if ev.selection.rows:
                            idx = ev.selection.rows[0]
                            if idx < len(my):
                                m = my.iloc[idx]
                                st.markdown("---")
                                st.markdown(f"**Препарат:** {m.get('medicine_name') or '—'}")
                                st.markdown(f"**Дозировка:** {m.get('dosage') or '—'} · **Кратность:** {m.get('frequency') or '—'}")
                                st.markdown(f"**Способ:** {m.get('administration_route') or '—'}")
                                st.markdown(f"**Курс:** {pd.to_datetime(m['course_start']).strftime('%d.%m.%Y') if pd.notna(m.get('course_start')) else '—'} — {pd.to_datetime(m['course_end']).strftime('%d.%m.%Y') if pd.notna(m.get('course_end')) else '—'}")
                                st.markdown(f"**WADA:** {m.get('wada_status') or '—'}")

                # --- Прививки ---
                with mc_vacc:
                    my = df_vaccinations[df_vaccinations["athlete_id"] == mc_aid] if not df_vaccinations.empty else pd.DataFrame()
                    if my.empty:
                        st.info("Прививок нет.")
                    else:
                        cols = ["vaccination_date", "vaccine_name", "booster_date", "batch_number"]
                        av = [c for c in cols if c in my.columns]
                        d = format_dates(my[av].copy(), ["vaccination_date", "booster_date"])
                        d = d.rename(columns={"vaccination_date": "Дата", "vaccine_name": "Вакцина", "booster_date": "Ревакцинация", "batch_number": "Серия"})
                        ev = st.dataframe(d, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)
                        if ev.selection.rows:
                            idx = ev.selection.rows[0]
                            if idx < len(my):
                                v = my.iloc[idx]
                                st.markdown("---")
                                st.markdown(f"**Вакцина:** {v.get('vaccine_name') or '—'}")
                                st.markdown(f"**Дата:** {pd.to_datetime(v['vaccination_date']).strftime('%d.%m.%Y') if pd.notna(v.get('vaccination_date')) else '—'}")
                                st.markdown(f"**Ревакцинация:** {pd.to_datetime(v['booster_date']).strftime('%d.%m.%Y') if pd.notna(v.get('booster_date')) else '—'}")
                                st.markdown(f"**Серия:** {v.get('batch_number') or '—'}")

                # --- Антропометрия ---
                with mc_anthro:
                    my = df_anthro[df_anthro["athlete_id"] == mc_aid] if not df_anthro.empty else pd.DataFrame()
                    if my.empty:
                        st.info("Измерений нет.")
                    else:
                        cols = ["measurement_date", "height", "weight", "bmi", "body_fat", "muscle_mass"]
                        av = [c for c in cols if c in my.columns]
                        d = format_dates(my[av].copy(), ["measurement_date"])
                        d = d.rename(columns={"measurement_date": "Дата", "height": "Рост", "weight": "Вес", "bmi": "ИМТ", "body_fat": "% жира", "muscle_mass": "Мышцы"})
                        ev = st.dataframe(d, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)
                        if ev.selection.rows:
                            idx = ev.selection.rows[0]
                            if idx < len(my):
                                a = my.iloc[idx]
                                st.markdown("---")
                                st.markdown(f"**Дата:** {pd.to_datetime(a['measurement_date']).strftime('%d.%m.%Y') if pd.notna(a.get('measurement_date')) else '—'}")
                                st.markdown(f"**Рост:** {a.get('height') or '—'} см")
                                st.markdown(f"**Вес:** {a.get('weight') or '—'} кг")
                                st.markdown(f"**ИМТ:** {a.get('bmi') or '—'}")
                                st.markdown(f"**% жира:** {a.get('body_fat') or '—'}")
                                st.markdown(f"**Мышцы:** {a.get('muscle_mass') or '—'} кг")

                # --- Тесты ---
                with mc_tests:
                    my = df_tests[df_tests["athlete_id"] == mc_aid] if not df_tests.empty else pd.DataFrame()
                    if my.empty:
                        st.info("Тестов нет.")
                    else:
                        cols = ["test_date", "test_name", "result_raw", "result_score", "evaluation"]
                        av = [c for c in cols if c in my.columns]
                        d = format_dates(my[av].copy(), ["test_date"])
                        d = d.rename(columns={"test_date": "Дата", "test_name": "Тест", "result_raw": "Результат", "result_score": "Балл", "evaluation": "Оценка"})
                        ev = st.dataframe(d, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)
                        if ev.selection.rows:
                            idx = ev.selection.rows[0]
                            if idx < len(my):
                                t = my.iloc[idx]
                                st.markdown("---")
                                st.markdown(f"**Дата:** {pd.to_datetime(t['test_date']).strftime('%d.%m.%Y') if pd.notna(t.get('test_date')) else '—'}")
                                st.markdown(f"**Тест:** {t.get('test_name') or '—'}")
                                st.markdown(f"**Условия:** {t.get('test_condition') or '—'}")
                                st.markdown(f"**Результат:** {t.get('result_raw') or '—'}")
                                st.markdown(f"**Балл:** {t.get('result_score') or '—'}")
                                st.markdown(f"**Оценка:** {t.get('evaluation') or '—'}")

                # --- Хроники ---
                with mc_chronic:
                    my = df_chronic[df_chronic["athlete_id"] == mc_aid] if not df_chronic.empty else pd.DataFrame()
                    if my.empty:
                        st.info("Хроник нет.")
                    else:
                        cols = ["diagnosis_date", "disease_name", "severity", "current_medication"]
                        av = [c for c in cols if c in my.columns]
                        d = format_dates(my[av].copy(), ["diagnosis_date"])
                        d = d.rename(columns={"diagnosis_date": "Дата", "disease_name": "Заболевание", "severity": "Тяжесть", "current_medication": "Лекарства"})
                        ev = st.dataframe(d, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)
                        if ev.selection.rows:
                            idx = ev.selection.rows[0]
                            if idx < len(my):
                                ch = my.iloc[idx]
                                st.markdown("---")
                                st.markdown(f"**Дата:** {pd.to_datetime(ch['diagnosis_date']).strftime('%d.%m.%Y') if pd.notna(ch.get('diagnosis_date')) else '—'}")
                                st.markdown(f"**Заболевание:** {ch.get('disease_name') or '—'}")
                                st.markdown(f"**Тяжесть:** {ch.get('severity') or '—'}")
                                st.markdown(f"**Постоянные препараты:** {ch.get('current_medication') or '—'}")
                                st.markdown(f"**Рекомендации:** {ch.get('clinical_recommendations') or '—'}")

                # --- Анализы ---
                with mc_lab:
                    my = df_lab[df_lab["athlete_id"] == mc_aid] if not df_lab.empty else pd.DataFrame()
                    if my.empty:
                        st.info("Анализов нет.")
                    else:
                        cols = ["measurement_date", "biomarker_name", "value", "unit"]
                        av = [c for c in cols if c in my.columns]
                        d = format_dates(my[av].copy(), ["measurement_date"])
                        d = d.rename(columns={"measurement_date": "Дата", "biomarker_name": "Показатель", "value": "Значение", "unit": "Ед."})
                        ev = st.dataframe(d, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)
                        if ev.selection.rows:
                            idx = ev.selection.rows[0]
                            if idx < len(my):
                                l = my.iloc[idx]
                                st.markdown("---")
                                st.markdown(f"**Дата:** {pd.to_datetime(l['measurement_date']).strftime('%d.%m.%Y') if pd.notna(l.get('measurement_date')) else '—'}")
                                st.markdown(f"**Показатель:** {l.get('biomarker_name') or '—'}")
                                st.markdown(f"**Значение:** {l.get('value')} {l.get('unit') or ''}")
                                st.markdown(f"**Примечание:** {l.get('notes') or '—'}")
    # --- ПРИЁМЫ ---
    if tab_visits is not None:
        with tab_visits:
            st.header("🩺 Журнал приёмов врача")
            sv, sa = st.tabs(["📋 Просмотр приёмов", "✍️ Внести приём"])

            with sv:
                if df_visits.empty:
                    st.info("Приёмов пока не зарегистрировано.")
                else:
                    st.caption(f"Всего приёмов: {len(df_visits)}")
                    cols = ["visit_date", "jersey_number", "full_name", "complaints", "diagnosis", "prescriptions", "next_visit_date"]
                    av = [c for c in cols if c in df_visits.columns]
                    d = format_dates(df_visits[av].copy(), ["visit_date", "next_visit_date"])
                    d = d.rename(columns={
                        "visit_date": "Дата", "jersey_number": "№", "full_name": "ФИО",
                        "complaints": "Жалобы", "diagnosis": "Диагноз",
                        "prescriptions": "Назначения", "next_visit_date": "Следующий"
                    })

                    event_v = st.dataframe(
                        d,
                        on_select="rerun",
                        selection_mode="single-row",
                        use_container_width=True,
                        hide_index=True
                    )

                    st.divider()
                    st.subheader("👁️ Детальная информация о приёме")

                    visit_labels = []
                    for _, r in df_visits.iterrows():
                        vd = pd.to_datetime(r["visit_date"]).strftime('%d.%m.%Y') if pd.notna(r.get("visit_date")) else "—"
                        lbl = f"{vd} · №{int(r['jersey_number']) if pd.notna(r.get('jersey_number')) else '?'} · {r.get('full_name', '—')}"
                        visit_labels.append((lbl, r["id"]))

                    sel_lbl = None
                    if visit_labels:
                        sel_lbl = st.selectbox(
                            "Или выберите приём в списке",
                            ["— не выбрано —"] + [l[0] for l in visit_labels],
                            key="visit_view"
                        )

                    selected_visit_id = None
                    if event_v.selection.rows:
                        idx = event_v.selection.rows[0]
                        if idx < len(df_visits):
                            selected_visit_id = df_visits.iloc[idx]["id"]
                    elif sel_lbl and sel_lbl != "— не выбрано —":
                        selected_visit_id = next(i for l, i in visit_labels if l == sel_lbl)

                    if selected_visit_id:
                        v = df_visits[df_visits["id"] == selected_visit_id].iloc[0]
                        st.markdown(f"**Дата:** {pd.to_datetime(v['visit_date']).strftime('%d.%m.%Y') if pd.notna(v.get('visit_date')) else '—'}")
                        st.markdown(f"**Спортсменка:** №{int(v['jersey_number']) if pd.notna(v.get('jersey_number')) else '?'} — {v.get('full_name')}")
                        st.markdown(f"**Жалобы:** {v.get('complaints') or '—'}")
                        st.markdown(f"**Осмотр:** {v.get('examination') or '—'}")
                        st.markdown(f"**Диагноз:** {v.get('diagnosis') or v.get('diagnosis_text') or '—'}")
                        st.markdown(f"**Назначения:** {v.get('prescriptions') or '—'}")
                        st.markdown(f"**Рекомендации:** {v.get('recommendations') or '—'}")
                        if pd.notna(v.get("next_visit_date")):
                            st.markdown(f"**Следующий приём:** {pd.to_datetime(v['next_visit_date']).strftime('%d.%m.%Y')}")

                        col_a, col_b = st.columns([1, 1])
                        with col_a:
                            if st.button("✏️ Редактировать", key=f"edit_visit_{selected_visit_id}"):
                                st.session_state["edit_visit_id"] = selected_visit_id
                        with col_b:
                            if st.button("🗑️ Удалить", key=f"del_visit_{selected_visit_id}"):
                                try:
                                    supabase.table("doctor_visits").delete().eq("id", selected_visit_id).execute()
                                    st.success("✅ Приём удалён")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")
                    else:
                        st.info("👆 Выберите приём в таблице или в списке выше")

                    if "edit_visit_id" in st.session_state and st.session_state["edit_visit_id"]:
                        edit_vid = st.session_state["edit_visit_id"]
                        v_edit = df_visits[df_visits["id"] == edit_vid]
                        if not v_edit.empty:
                            cur_v = v_edit.iloc[0]
                            st.divider()
                            st.subheader(f"✏️ Редактирование приёма от {pd.to_datetime(cur_v['visit_date']).strftime('%d.%m.%Y')}")
                            with st.form("form_edit_visit"):
                                opts_v = athlete_options_dict()
                                cur_aid = cur_v["athlete_id"]
                                cur_label = None
                                for lbl, aid in opts_v.items():
                                    if aid == cur_aid:
                                        cur_label = lbl
                                        break
                                cur_idx = list(opts_v.keys()).index(cur_label) if cur_label else 0
                                sel_a = st.selectbox("Спортсменка *", list(opts_v.keys()), index=cur_idx)
                                c1, c2 = st.columns(2)
                                with c1:
                                    vdate = st.date_input("Дата приёма *", value=pd.to_datetime(cur_v["visit_date"]).date(), format="DD.MM.YYYY")
                                with c2:
                                    nv = cur_v.get("next_visit_date")
                                    nvdate = st.date_input("Дата следующего приёма", value=pd.to_datetime(nv).date() if pd.notna(nv) else None, format="DD.MM.YYYY")
                                complaints = st.text_area("Жалобы", value=cur_v.get("complaints") or "", height=80)
                                examination = st.text_area("Данные осмотра", value=cur_v.get("examination") or "", height=100)
                                dopts = {}
                                if not df_diagnoses.empty:
                                    for _, row in df_diagnoses.iterrows():
                                        lbl = f"{row['mkb_code']} — {row['name']}" if pd.notna(row['mkb_code']) else row['name']
                                        dopts[lbl] = row['id']
                                cur_did = cur_v.get("diagnosis_id")
                                cur_dlbl = None
                                for lbl, did in dopts.items():
                                    if did == cur_did:
                                        cur_dlbl = lbl
                                        break
                                d_list = ["— не указан —"] + list(dopts.keys())
                                d_idx = d_list.index(cur_dlbl) if cur_dlbl else 0
                                sel_d = st.selectbox("Диагноз (МКБ)", d_list, index=d_idx)
                                diagnosis_text = st.text_input("Диагноз текстом", value=cur_v.get("diagnosis_text") or "")
                                prescriptions = st.text_area("Назначения", value=cur_v.get("prescriptions") or "", height=80)
                                recommendations = st.text_area("Рекомендации", value=cur_v.get("recommendations") or "", height=60)
                                save = st.form_submit_button("💾 Сохранить", type="primary")
                                if save:
                                    try:
                                        payload = {
                                            "athlete_id": opts_v[sel_a],
                                            "visit_date": vdate.isoformat(),
                                            "complaints": complaints.strip() or None,
                                            "examination": examination.strip() or None,
                                            "prescriptions": prescriptions.strip() or None,
                                            "recommendations": recommendations.strip() or None,
                                            "next_visit_date": nvdate.isoformat() if nvdate else None
                                        }
                                        if sel_d != "— не указан —":
                                            payload["diagnosis_id"] = dopts[sel_d]
                                        if diagnosis_text.strip():
                                            payload["diagnosis_text"] = diagnosis_text.strip()
                                        supabase.table("doctor_visits").update(payload).eq("id", edit_vid).execute()
                                        st.success("✅ Приём обновлён")
                                        st.session_state["edit_visit_id"] = None
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Ошибка: {e}")

            with sa:
                st.subheader("✍️ Внести новый приём")
                with st.form("form_visit", clear_on_submit=True):
                    opts_v = athlete_options_dict()
                    sel_a = st.selectbox("Спортсменка *", list(opts_v.keys()))
                    c1, c2 = st.columns(2)
                    with c1:
                        vdate = st.date_input("Дата приёма *", value=date.today(), format="DD.MM.YYYY")
                    with c2:
                        nvdate = st.date_input("Дата следующего приёма", value=None, format="DD.MM.YYYY")
                    complaints = st.text_area("Жалобы", height=80)
                    examination = st.text_area("Данные осмотра", height=100)
                    dopts = {}
                    if not df_diagnoses.empty:
                        for _, row in df_diagnoses.iterrows():
                            lbl = f"{row['mkb_code']} — {row['name']}" if pd.notna(row['mkb_code']) else row['name']
                            dopts[lbl] = row['id']
                    sel_d = st.selectbox("Диагноз (МКБ)", ["— не указан —"] + list(dopts.keys()))
                    diagnosis_text = st.text_input("Диагноз текстом")
                    prescriptions = st.text_area("Назначения", height=80)
                    recommendations = st.text_area("Рекомендации", height=60)
                    if st.form_submit_button("💾 Сохранить приём", type="primary"):
                        try:
                            payload = {
                                "athlete_id": opts_v[sel_a],
                                "visit_date": vdate.isoformat(),
                                "complaints": complaints.strip() or None,
                                "examination": examination.strip() or None,
                                "prescriptions": prescriptions.strip() or None,
                                "recommendations": recommendations.strip() or None,
                                "next_visit_date": nvdate.isoformat() if nvdate else None
                            }
                            if sel_d != "— не указан —":
                                payload["diagnosis_id"] = dopts[sel_d]
                            if diagnosis_text.strip():
                                payload["diagnosis_text"] = diagnosis_text.strip()
                            supabase.table("doctor_visits").insert(payload).execute()
                            st.success(f"✅ Приём сохранён: {sel_a}")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")

    # --- ОСМОТРЫ ---
    if tab_exams is not None:
        with tab_exams:
            st.header("🏥 Медицинские осмотры")
            sv, sa = st.tabs(["📋 Просмотр", "✍️ Внести осмотр"])

            with sv:
                st.subheader("⚠️ Просроченные")
                if not df_overdue.empty:
                    st.error(f"Просрочено: {len(df_overdue)}")
                    st.dataframe(format_dates(df_overdue, ["Был должен"]), use_container_width=True, hide_index=True)
                else:
                    st.success("✅ Всё в порядке")

                st.divider()
                st.subheader("📋 Все осмотры (последние 50)")
                if not df_all_exams.empty:
                    cols = ["examination_date", "jersey_number", "full_name", "exam_name", "is_approved", "next_exam_date", "restrictions"]
                    av = [c for c in cols if c in df_all_exams.columns]
                    d = format_dates(df_all_exams[av].head(50).copy(), ["examination_date", "next_exam_date"])
                    d = d.rename(columns={
                        "examination_date": "Дата", "jersey_number": "№", "full_name": "ФИО",
                        "exam_name": "Осмотр", "is_approved": "Допуск",
                        "next_exam_date": "Следующий", "restrictions": "Ограничения"
                    })

                    event_e = st.dataframe(
                        d,
                        on_select="rerun",
                        selection_mode="single-row",
                        use_container_width=True,
                        hide_index=True
                    )

                    st.divider()
                    st.subheader("👁️ Детальная информация об осмотре")

                    exam_labels = []
                    for _, r in df_all_exams.head(50).iterrows():
                        ed = pd.to_datetime(r["examination_date"]).strftime('%d.%m.%Y') if pd.notna(r.get("examination_date")) else "—"
                        lbl = f"{ed} · №{int(r['jersey_number']) if pd.notna(r.get('jersey_number')) else '?'} · {r.get('exam_name', '—')}"
                        exam_labels.append((lbl, r["id"]))

                    sel_lbl = None
                    if exam_labels:
                        sel_lbl = st.selectbox(
                            "Или выберите осмотр в списке",
                            ["— не выбрано —"] + [l[0] for l in exam_labels],
                            key="exam_view"
                        )

                    selected_exam_id = None
                    if event_e.selection.rows:
                        idx = event_e.selection.rows[0]
                        if idx < len(df_all_exams.head(50)):
                            selected_exam_id = df_all_exams.head(50).iloc[idx]["id"]
                    elif sel_lbl and sel_lbl != "— не выбрано —":
                        selected_exam_id = next(i for l, i in exam_labels if l == sel_lbl)

                    if selected_exam_id:
                        ex = df_all_exams[df_all_exams["id"] == selected_exam_id].iloc[0]
                        st.markdown(f"**Дата:** {pd.to_datetime(ex['examination_date']).strftime('%d.%m.%Y') if pd.notna(ex.get('examination_date')) else '—'}")
                        st.markdown(f"**Спортсменка:** №{int(ex['jersey_number']) if pd.notna(ex.get('jersey_number')) else '?'} — {ex.get('full_name')}")
                        st.markdown(f"**Тип осмотра:** {ex.get('exam_name') or '—'}")
                        st.markdown(f"**Заключение:** {ex.get('result_text') or '—'}")
                        approved = ex.get("is_approved")
                        st.markdown(f"**Допуск:** {'✅ Да' if approved else '❌ Нет' if approved is False else '—'}")
                        st.markdown(f"**Ограничения:** {ex.get('restrictions') or '—'}")
                        if pd.notna(ex.get("next_exam_date")):
                            st.markdown(f"**Следующий:** {pd.to_datetime(ex['next_exam_date']).strftime('%d.%m.%Y')}")

                        col_a, col_b = st.columns([1, 1])
                        with col_a:
                            if st.button("✏️ Редактировать", key=f"edit_exam_{selected_exam_id}"):
                                st.session_state["edit_exam_id"] = selected_exam_id
                        with col_b:
                            if st.button("🗑️ Удалить", key=f"del_exam_{selected_exam_id}"):
                                try:
                                    supabase.table("examinations").delete().eq("id", selected_exam_id).execute()
                                    st.success("✅ Осмотр удалён")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")
                    else:
                        st.info("👆 Выберите осмотр в таблице или в списке выше")

                    if "edit_exam_id" in st.session_state and st.session_state["edit_exam_id"]:
                        edit_eid = st.session_state["edit_exam_id"]
                        ex_edit = df_all_exams[df_all_exams["id"] == edit_eid]
                        if not ex_edit.empty:
                            cur_e = ex_edit.iloc[0]
                            st.divider()
                            st.subheader("✏️ Редактирование осмотра")
                            with st.form("form_edit_exam"):
                                opts_e = athlete_options_dict()
                                cur_aid = cur_e["athlete_id"]
                                cur_label = None
                                for lbl, aid in opts_e.items():
                                    if aid == cur_aid:
                                        cur_label = lbl
                                        break
                                cur_idx = list(opts_e.keys()).index(cur_label) if cur_label else 0
                                sel_a = st.selectbox("Спортсменка *", list(opts_e.keys()), index=cur_idx)
                                topts = {}
                                if not df_exam_templates.empty:
                                    for _, row in df_exam_templates.iterrows():
                                        topts[f"{row['name']} ({row['specialist_type']})"] = {
                                            "id": row['id'], "validity": row['validity_days']
                                        }
                                cur_tid = cur_e.get("exam_template_id")
                                cur_tlbl = None
                                for lbl, t in topts.items():
                                    if t["id"] == cur_tid:
                                        cur_tlbl = lbl
                                        break
                                t_list = list(topts.keys())
                                t_idx = t_list.index(cur_tlbl) if cur_tlbl else 0
                                sel_t = st.selectbox("Тип осмотра *", t_list, index=t_idx)
                                c1, c2 = st.columns(2)
                                with c1:
                                    ed = st.date_input("Дата осмотра *", value=pd.to_datetime(cur_e["examination_date"]).date(), format="DD.MM.YYYY")
                                with c2:
                                    nv = cur_e.get("next_exam_date")
                                    ned = st.date_input("Следующий осмотр", value=pd.to_datetime(nv).date() if pd.notna(nv) else None, format="DD.MM.YYYY")
                                rt = st.text_area("Заключение *", value=cur_e.get("result_text") or "", height=100)
                                cur_ap = cur_e.get("is_approved")
                                ap_idx = 0 if cur_ap else 1
                                ap = st.radio("Допуск? *", [True, False], index=ap_idx,
                                              format_func=lambda x: "✅ Да" if x else "❌ Нет", horizontal=True)
                                res = st.text_input("Ограничения", value=cur_e.get("restrictions") or "")
                                save = st.form_submit_button("💾 Сохранить", type="primary")
                                if save:
                                    if len(rt.strip()) < 3:
                                        st.error("Заполните заключение")
                                    else:
                                        try:
                                            supabase.table("examinations").update({
                                                "athlete_id": opts_e[sel_a],
                                                "exam_template_id": topts[sel_t]["id"],
                                                "examination_date": ed.isoformat(),
                                                "result_text": rt.strip(),
                                                "is_approved": ap,
                                                "restrictions": res.strip() if res else None,
                                                "next_exam_date": ned.isoformat() if ned else None
                                            }).eq("id", edit_eid).execute()
                                            st.success("✅ Осмотр обновлён")
                                            st.session_state["edit_exam_id"] = None
                                            st.cache_data.clear()
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Ошибка: {e}")
                else:
                    st.info("Осмотров пока нет.")

            with sa:
                st.subheader("✍️ Внести новый осмотр")
                with st.form("f_exam", clear_on_submit=True):
                    opts = athlete_options_dict()
                    sel_a = st.selectbox("Спортсменка *", list(opts.keys()))
                    topts = {}
                    if not df_exam_templates.empty:
                        for _, row in df_exam_templates.iterrows():
                            topts[f"{row['name']} ({row['specialist_type']})"] = {
                                "id": row['id'], "validity": row['validity_days']
                            }
                    sel_t = st.selectbox("Тип осмотра *", list(topts.keys()))
                    c1, c2 = st.columns(2)
                    with c1:
                        ed = st.date_input("Дата осмотра *", value=date.today(), format="DD.MM.YYYY")
                    with c2:
                        v = topts.get(sel_t, {}).get("validity", 365)
                        nd = ed + timedelta(days=v) if v else ed
                        ned = st.date_input("Следующий осмотр", value=nd, format="DD.MM.YYYY")
                    rt = st.text_area("Заключение *", height=100)
                    ap = st.radio("Допуск? *", [True, False],
                                  format_func=lambda x: "✅ Да" if x else "❌ Нет", horizontal=True)
                    res = st.text_input("Ограничения")
                    if st.form_submit_button("💾 Сохранить", type="primary"):
                        if len(rt.strip()) < 3:
                            st.error("Заполните заключение")
                        else:
                            try:
                                supabase.table("examinations").insert({
                                    "athlete_id": opts[sel_a],
                                    "exam_template_id": topts[sel_t]["id"],
                                    "examination_date": ed.isoformat(),
                                    "result_text": rt.strip(),
                                    "is_approved": ap,
                                    "restrictions": res.strip() if res else None,
                                    "next_exam_date": ned.isoformat() if ned else None
                                }).execute()
                                st.success(f"✅ Осмотр сохранён: {sel_a}")
                                st.cache_data.clear()
                            except Exception as e:
                                st.error(f"Ошибка: {e}")

    # --- ТРАВМЫ ---
    if tab_injuries is not None:
        with tab_injuries:
            st.header("🩹 Травмы и заболевания")
            sv, sa = st.tabs(["📋 Просмотр (365 дней)", "✍️ Внести травму"])

            with sv:
                if df_injuries.empty:
                    st.info("За 365 дней травм нет.")
                else:
                    st.warning(f"Травм: {len(df_injuries)}")
                    cols = ["incident_date", "jersey_number", "full_name", "diagnosis", "body_part", "side", "severity", "days_lost"]
                    av = [c for c in cols if c in df_injuries.columns]
                    d = format_dates(df_injuries[av].copy(), ["incident_date"])
                    d = d.rename(columns={
                        "incident_date": "Дата", "jersey_number": "№", "full_name": "ФИО",
                        "diagnosis": "Диагноз", "body_part": "Часть тела",
                        "side": "Сторона", "severity": "Тяжесть", "days_lost": "Пропущено"
                    })

                    event_i = st.dataframe(
                        d,
                        on_select="rerun",
                        selection_mode="single-row",
                        use_container_width=True,
                        hide_index=True
                    )

                    st.divider()
                    st.subheader("👁️ Детальная информация")

                    inj_labels = []
                    for _, r in df_injuries.iterrows():
                        dt = pd.to_datetime(r["incident_date"]).strftime('%d.%m.%Y') if pd.notna(r.get("incident_date")) else "—"
                        lbl = f"{dt} · №{int(r['jersey_number']) if pd.notna(r.get('jersey_number')) else '?'} · {r.get('diagnosis') or '—'}"
                        inj_labels.append((lbl, r["id"]))

                    sel_lbl = None
                    if inj_labels:
                        sel_lbl = st.selectbox("Или выберите в списке",
                                                ["— не выбрано —"] + [l[0] for l in inj_labels],
                                                key="inj_view")

                    selected_inj_id = None
                    if event_i.selection.rows:
                        idx = event_i.selection.rows[0]
                        if idx < len(df_injuries):
                            selected_inj_id = df_injuries.iloc[idx]["id"]
                    elif sel_lbl and sel_lbl != "— не выбрано —":
                        selected_inj_id = next(i for l, i in inj_labels if l == sel_lbl)

                    if selected_inj_id:
                        inj = df_injuries[df_injuries["id"] == selected_inj_id].iloc[0]
                        st.markdown(f"**Дата:** {pd.to_datetime(inj['incident_date']).strftime('%d.%m.%Y') if pd.notna(inj.get('incident_date')) else '—'}")
                        st.markdown(f"**Спортсменка:** №{int(inj['jersey_number']) if pd.notna(inj.get('jersey_number')) else '?'} — {inj.get('full_name')}")
                        st.markdown(f"**Диагноз:** {inj.get('diagnosis') or '—'}")
                        st.markdown(f"**Часть тела:** {inj.get('body_part') or '—'} · **Сторона:** {inj.get('side') or '—'}")
                        st.markdown(f"**Тяжесть:** {inj.get('severity') or '—'} · **Рецидив:** {'Да' if inj.get('is_recurrent') else 'Нет'}")
                        st.markdown(f"**Механизм:** {inj.get('mechanism') or '—'}")
                        st.markdown(f"**Лечение:** {inj.get('treatment_description') or '—'}")
                        st.markdown(f"**Пропущено дней:** {inj.get('days_lost', 0)}")

                        col_a, col_b = st.columns([1, 1])
                        with col_a:
                            if st.button("✏️ Редактировать", key=f"edit_inj_{selected_inj_id}"):
                                st.session_state["edit_inj_id"] = selected_inj_id
                        with col_b:
                            if st.button("🗑️ Удалить", key=f"del_inj_{selected_inj_id}"):
                                try:
                                    supabase.table("injuries_and_illnesses").delete().eq("id", selected_inj_id).execute()
                                    st.success("✅ Травма удалена")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")
                    else:
                        st.info("👆 Выберите травму в таблице или в списке")

                    if "edit_inj_id" in st.session_state and st.session_state["edit_inj_id"]:
                        edit_iid = st.session_state["edit_inj_id"]
                        inj_edit = df_injuries[df_injuries["id"] == edit_iid]
                        if not inj_edit.empty:
                            cur_i = inj_edit.iloc[0]
                            st.divider()
                            st.subheader("✏️ Редактирование травмы")
                            with st.form("form_edit_inj"):
                                opts_a = athlete_options_dict()
                                cur_aid = cur_i["athlete_id"]
                                cur_al = None
                                for lbl, aid in opts_a.items():
                                    if aid == cur_aid:
                                        cur_al = lbl
                                        break
                                cur_aidx = list(opts_a.keys()).index(cur_al) if cur_al else 0
                                sel_a = st.selectbox("Спортсменка *", list(opts_a.keys()), index=cur_aidx)

                                d_opts = {}
                                if not df_diagnoses.empty:
                                    for _, row in df_diagnoses.iterrows():
                                        lbl = f"{row['mkb_code']} — {row['name']}" if pd.notna(row['mkb_code']) else row['name']
                                        d_opts[lbl] = row['id']
                                cur_did = cur_i.get("diagnosis_id")
                                cur_dl = None
                                for lbl, did in d_opts.items():
                                    if did == cur_did:
                                        cur_dl = lbl
                                        break
                                d_list = ["— не указан —"] + list(d_opts.keys())
                                d_idx = d_list.index(cur_dl) if cur_dl else 0
                                sel_d = st.selectbox("Диагноз (МКБ)", d_list, index=d_idx)

                                b_opts = {}
                                if not df_body_parts.empty:
                                    for _, row in df_body_parts.iterrows():
                                        b_opts[row['name']] = row['id']
                                cur_bid = cur_i.get("body_part_id")
                                cur_bl = None
                                for lbl, bid in b_opts.items():
                                    if bid == cur_bid:
                                        cur_bl = lbl
                                        break
                                b_list = ["— не указана —"] + list(b_opts.keys())
                                b_idx = b_list.index(cur_bl) if cur_bl else 0
                                sel_b = st.selectbox("Часть тела", b_list, index=b_idx)

                                c1, c2 = st.columns(2)
                                with c1:
                                    idate = st.date_input("Дата травмы *", value=pd.to_datetime(cur_i["incident_date"]).date(), format="DD.MM.YYYY")
                                    side_list = ["Не применимо", "Правая", "Левая"]
                                    side_idx = side_list.index(cur_i.get("side")) if cur_i.get("side") in side_list else 0
                                    side = st.selectbox("Сторона", side_list, index=side_idx)
                                with c2:
                                    mech_list = ["Не уточнено", "Контакт с соперником", "Падение", "Резкое движение без контакта", "Хроническая перегрузка"]
                                    mech_idx = mech_list.index(cur_i.get("mechanism")) if cur_i.get("mechanism") in mech_list else 0
                                    mech = st.selectbox("Механизм", mech_list, index=mech_idx)
                                    sev_list = ["Легкая", "Средняя", "Тяжелая"]
                                    sev_idx = sev_list.index(cur_i.get("severity")) if cur_i.get("severity") in sev_list else 0
                                    sev = st.selectbox("Тяжесть", sev_list, index=sev_idx)

                                is_rec = st.checkbox("Рецидив", value=bool(cur_i.get("is_recurrent")))
                                treat = st.text_area("Описание лечения", value=cur_i.get("treatment_description") or "", height=80)
                                d_lost = st.number_input("Пропущено дней", min_value=0, value=int(cur_i.get("days_lost") or 0))

                                if st.form_submit_button("💾 Сохранить", type="primary"):
                                    try:
                                        payload = {
                                            "athlete_id": opts_a[sel_a],
                                            "incident_date": idate.isoformat(),
                                            "side": side, "mechanism": mech, "severity": sev,
                                            "is_recurrent": is_rec,
                                            "treatment_description": treat.strip() or None,
                                            "days_lost": int(d_lost)
                                        }
                                        payload["diagnosis_id"] = d_opts[sel_d] if sel_d != "— не указан —" else None
                                        payload["body_part_id"] = b_opts[sel_b] if sel_b != "— не указана —" else None
                                        supabase.table("injuries_and_illnesses").update(payload).eq("id", edit_iid).execute()
                                        st.success("✅ Травма обновлена")
                                        st.session_state["edit_inj_id"] = None
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Ошибка: {e}")

            with sa:
                st.subheader("✍️ Внести травму")
                with st.form("f_inj", clear_on_submit=True):
                    opts = athlete_options_dict()
                    sel_a = st.selectbox("Спортсменка *", list(opts.keys()))
                    dopts = {}
                    if not df_diagnoses.empty:
                        for _, row in df_diagnoses.iterrows():
                            lbl = f"{row['mkb_code']} — {row['name']}" if pd.notna(row['mkb_code']) else row['name']
                            dopts[lbl] = row['id']
                    sel_d = st.selectbox("Диагноз (МКБ)", ["— не указан —"] + list(dopts.keys()))
                    bopts = {}
                    if not df_body_parts.empty:
                        for _, row in df_body_parts.iterrows():
                            bopts[row['name']] = row['id']
                    sel_b = st.selectbox("Часть тела", ["— не указана —"] + list(bopts.keys()))
                    c1, c2 = st.columns(2)
                    with c1:
                        idate = st.date_input("Дата травмы *", value=date.today(), format="DD.MM.YYYY")
                        side = st.selectbox("Сторона", ["Не применимо", "Правая", "Левая"])
                    with c2:
                        mech = st.selectbox("Механизм", ["Не уточнено", "Контакт с соперником", "Падение", "Резкое движение без контакта", "Хроническая перегрузка"])
                        sev = st.selectbox("Тяжесть", ["Легкая", "Средняя", "Тяжелая"])
                    is_rec = st.checkbox("Рецидив")
                    treat = st.text_area("Описание лечения", height=80)
                    d_lost = st.number_input("Пропущено дней", min_value=0, value=0)
                    if st.form_submit_button("💾 Сохранить", type="primary"):
                        try:
                            payload = {
                                "athlete_id": opts[sel_a],
                                "incident_date": idate.isoformat(),
                                "side": side, "mechanism": mech, "severity": sev,
                                "is_recurrent": is_rec,
                                "treatment_description": treat.strip() if treat else None,
                                "days_lost": int(d_lost)
                            }
                            if sel_d != "— не указан —":
                                payload["diagnosis_id"] = dopts[sel_d]
                            if sel_b != "— не указана —":
                                payload["body_part_id"] = bopts[sel_b]
                            supabase.table("injuries_and_illnesses").insert(payload).execute()
                            st.success(f"✅ Травма сохранена: {sel_a}")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")

    # --- ЛЕКАРСТВА ---
    if tab_meds is not None:
        with tab_meds:
            st.header("💊 Лекарства")
            sv, sa = st.tabs(["📋 Все назначения", "✍️ Назначить"])

            with sv:
                if df_meds_current.empty:
                    st.info("Назначений нет.")
                else:
                    st.caption(f"Всего: {len(df_meds_current)}")
                    cols = ["jersey_number", "full_name", "medicine_name", "dosage", "course_start", "course_end", "wada_status"]
                    av = [c for c in cols if c in df_meds_current.columns]
                    d = format_dates(df_meds_current[av].copy(), ["course_start", "course_end"])
                    d = d.rename(columns={
                        "jersey_number": "№", "full_name": "ФИО", "medicine_name": "Препарат",
                        "dosage": "Дозировка", "course_start": "С", "course_end": "По",
                        "wada_status": "WADA"
                    })

                    event_m = st.dataframe(
                        d,
                        on_select="rerun",
                        selection_mode="single-row",
                        use_container_width=True,
                        hide_index=True
                    )

                    st.divider()
                    st.subheader("👁️ Детальная информация")

                    med_labels = []
                    for _, r in df_meds_current.iterrows():
                        dt = pd.to_datetime(r["course_start"]).strftime('%d.%m.%Y') if pd.notna(r.get("course_start")) else "—"
                        lbl = f"{dt} · №{int(r['jersey_number']) if pd.notna(r.get('jersey_number')) else '?'} · {r.get('medicine_name') or '—'}"
                        med_labels.append((lbl, r["id"]))

                    sel_lbl = None
                    if med_labels:
                        sel_lbl = st.selectbox("Или выберите в списке",
                                                ["— не выбрано —"] + [l[0] for l in med_labels],
                                                key="med_view")

                    selected_med_id = None
                    if event_m.selection.rows:
                        idx = event_m.selection.rows[0]
                        if idx < len(df_meds_current):
                            selected_med_id = df_meds_current.iloc[idx]["id"]
                    elif sel_lbl and sel_lbl != "— не выбрано —":
                        selected_med_id = next(i for l, i in med_labels if l == sel_lbl)

                    if selected_med_id:
                        med = df_meds_current[df_meds_current["id"] == selected_med_id].iloc[0]
                        st.markdown(f"**Спортсменка:** №{int(med['jersey_number']) if pd.notna(med.get('jersey_number')) else '?'} — {med.get('full_name')}")
                        st.markdown(f"**Препарат:** {med.get('medicine_name') or '—'}")
                        st.markdown(f"**Дозировка:** {med.get('dosage') or '—'} · **Кратность:** {med.get('frequency') or '—'}")
                        st.markdown(f"**Способ:** {med.get('administration_route') or '—'}")
                        st.markdown(f"**Курс:** {pd.to_datetime(med['course_start']).strftime('%d.%m.%Y') if pd.notna(med.get('course_start')) else '—'} — {pd.to_datetime(med['course_end']).strftime('%d.%m.%Y') if pd.notna(med.get('course_end')) else '—'}")
                        st.markdown(f"**Статус WADA:** {med.get('wada_status') or '—'}")
                        if med.get("tue_document_link"):
                            st.markdown(f"**TUE:** {med.get('tue_document_link')}")

                        col_a, col_b = st.columns([1, 1])
                        with col_a:
                            if st.button("✏️ Редактировать", key=f"edit_med_{selected_med_id}"):
                                st.session_state["edit_med_id"] = selected_med_id
                        with col_b:
                            if st.button("🗑️ Удалить", key=f"del_med_{selected_med_id}"):
                                try:
                                    supabase.table("medication_intake").delete().eq("id", selected_med_id).execute()
                                    st.success("✅ Назначение удалено")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")
                    else:
                        st.info("👆 Выберите назначение в таблице или в списке")

                    if "edit_med_id" in st.session_state and st.session_state["edit_med_id"]:
                        edit_mid = st.session_state["edit_med_id"]
                        med_edit = df_meds_current[df_meds_current["id"] == edit_mid]
                        if not med_edit.empty:
                            cur_m = med_edit.iloc[0]
                            st.divider()
                            st.subheader("✏️ Редактирование назначения")
                            with st.form("form_edit_med"):
                                opts_a = athlete_options_dict()
                                cur_aid = cur_m["athlete_id"]
                                cur_al = None
                                for lbl, aid in opts_a.items():
                                    if aid == cur_aid:
                                        cur_al = lbl
                                        break
                                cur_aidx = list(opts_a.keys()).index(cur_al) if cur_al else 0
                                sel_a = st.selectbox("Спортсменка *", list(opts_a.keys()), index=cur_aidx)

                                m_opts = {}
                                if not df_medicines.empty:
                                    for _, row in df_medicines.iterrows():
                                        m_opts[f"{row['name']} [{row['wada_status']}]"] = row['id']
                                cur_mid = cur_m.get("medicine_id")
                                cur_ml = None
                                for lbl, mid in m_opts.items():
                                    if mid == cur_mid:
                                        cur_ml = lbl
                                        break
                                m_list = list(m_opts.keys())
                                m_idx = m_list.index(cur_ml) if cur_ml else 0
                                sel_m = st.selectbox("Препарат *", m_list, index=m_idx)

                                c1, c2 = st.columns(2)
                                with c1:
                                    pd_ = st.date_input("Дата назначения", value=pd.to_datetime(cur_m["prescribed_date"]).date() if pd.notna(cur_m.get("prescribed_date")) else date.today(), format="DD.MM.YYYY")
                                    cs = st.date_input("Начало курса", value=pd.to_datetime(cur_m["course_start"]).date() if pd.notna(cur_m.get("course_start")) else date.today(), format="DD.MM.YYYY")
                                with c2:
                                    ce = st.date_input("Конец курса", value=pd.to_datetime(cur_m["course_end"]).date() if pd.notna(cur_m.get("course_end")) else date.today(), format="DD.MM.YYYY")
                                    rt_list = ["Перорально", "Внутримышечно", "Внутривенно", "Местно", "Ингаляционно"]
                                    rt_idx = rt_list.index(cur_m.get("administration_route")) if cur_m.get("administration_route") in rt_list else 0
                                    rt = st.selectbox("Способ", rt_list, index=rt_idx)

                                dose = st.text_input("Дозировка", value=cur_m.get("dosage") or "")
                                freq = st.text_input("Кратность", value=cur_m.get("frequency") or "")
                                tue = st.text_input("Ссылка на TUE", value=cur_m.get("tue_document_link") or "")

                                if st.form_submit_button("💾 Сохранить", type="primary"):
                                    try:
                                        supabase.table("medication_intake").update({
                                            "athlete_id": opts_a[sel_a],
                                            "medicine_id": m_opts[sel_m],
                                            "prescribed_date": pd_.isoformat(),
                                            "course_start": cs.isoformat(),
                                            "course_end": ce.isoformat(),
                                            "dosage": dose.strip() or None,
                                            "frequency": freq.strip() or None,
                                            "administration_route": rt,
                                            "tue_document_link": tue.strip() or None
                                        }).eq("id", edit_mid).execute()
                                        st.success("✅ Назначение обновлено")
                                        st.session_state["edit_med_id"] = None
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Ошибка: {e}")

            with sa:
                st.subheader("✍️ Назначить лекарство")
                with st.form("f_med", clear_on_submit=True):
                    opts = athlete_options_dict()
                    sel_a = st.selectbox("Спортсменка *", list(opts.keys()))
                    mopts = {}
                    if not df_medicines.empty:
                        for _, row in df_medicines.iterrows():
                            mopts[f"{row['name']} [{row['wada_status']}]"] = row['id']
                    sel_m = st.selectbox("Препарат *", list(mopts.keys()))
                    c1, c2 = st.columns(2)
                    with c1:
                        pd_ = st.date_input("Дата назначения", value=date.today(), format="DD.MM.YYYY")
                        cs = st.date_input("Начало курса", value=date.today(), format="DD.MM.YYYY")
                    with c2:
                        ce = st.date_input("Конец курса", value=date.today() + timedelta(days=7), format="DD.MM.YYYY")
                        rt = st.selectbox("Способ", ["Перорально", "Внутримышечно", "Внутривенно", "Местно", "Ингаляционно"])
                    dose = st.text_input("Дозировка")
                    freq = st.text_input("Кратность")
                    tue = st.text_input("Ссылка на TUE")
                    if st.form_submit_button("💾 Сохранить", type="primary"):
                        try:
                            supabase.table("medication_intake").insert({
                                "athlete_id": opts[sel_a],
                                "medicine_id": mopts[sel_m],
                                "prescribed_date": pd_.isoformat(),
                                "course_start": cs.isoformat(),
                                "course_end": ce.isoformat(),
                                "dosage": dose.strip() or None,
                                "frequency": freq.strip() or None,
                                "administration_route": rt,
                                "tue_document_link": tue.strip() or None
                            }).execute()
                            st.success(f"✅ Назначено: {sel_a}")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")

    # --- ПРИВИВКИ ---
    if tab_vaccines is not None:
        with tab_vaccines:
            st.header("💉 Прививки")
            sv, sa = st.tabs(["📋 Просмотр", "✍️ Добавить"])

            with sv:
                if df_vaccinations.empty:
                    st.info("Прививок нет.")
                else:
                    cols = ["vaccination_date", "jersey_number", "full_name", "vaccine_name", "booster_date", "batch_number"]
                    av = [c for c in cols if c in df_vaccinations.columns]
                    d = format_dates(df_vaccinations[av].copy(), ["vaccination_date", "booster_date"])
                    d = d.rename(columns={
                        "vaccination_date": "Дата", "jersey_number": "№", "full_name": "ФИО",
                        "vaccine_name": "Вакцина", "booster_date": "Ревакцинация",
                        "batch_number": "Серия"
                    })

                    event_vac = st.dataframe(
                        d,
                        on_select="rerun",
                        selection_mode="single-row",
                        use_container_width=True,
                        hide_index=True
                    )

                    st.divider()
                    st.subheader("👁️ Детальная информация")

                    vac_labels = []
                    for _, r in df_vaccinations.iterrows():
                        dt = pd.to_datetime(r["vaccination_date"]).strftime('%d.%m.%Y') if pd.notna(r.get("vaccination_date")) else "—"
                        lbl = f"{dt} · №{int(r['jersey_number']) if pd.notna(r.get('jersey_number')) else '?'} · {r.get('vaccine_name') or '—'}"
                        vac_labels.append((lbl, r["id"]))

                    sel_lbl = None
                    if vac_labels:
                        sel_lbl = st.selectbox("Или выберите в списке",
                                                ["— не выбрано —"] + [l[0] for l in vac_labels],
                                                key="vac_view")

                    selected_vac_id = None
                    if event_vac.selection.rows:
                        idx = event_vac.selection.rows[0]
                        if idx < len(df_vaccinations):
                            selected_vac_id = df_vaccinations.iloc[idx]["id"]
                    elif sel_lbl and sel_lbl != "— не выбрано —":
                        selected_vac_id = next(i for l, i in vac_labels if l == sel_lbl)

                    if selected_vac_id:
                        vac = df_vaccinations[df_vaccinations["id"] == selected_vac_id].iloc[0]
                        st.markdown(f"**Спортсменка:** №{int(vac['jersey_number']) if pd.notna(vac.get('jersey_number')) else '?'} — {vac.get('full_name')}")
                        st.markdown(f"**Вакцина:** {vac.get('vaccine_name') or '—'}")
                        st.markdown(f"**Дата прививки:** {pd.to_datetime(vac['vaccination_date']).strftime('%d.%m.%Y') if pd.notna(vac.get('vaccination_date')) else '—'}")
                        st.markdown(f"**Ревакцинация:** {pd.to_datetime(vac['booster_date']).strftime('%d.%m.%Y') if pd.notna(vac.get('booster_date')) else '—'}")
                        st.markdown(f"**Серия:** {vac.get('batch_number') or '—'}")

                        col_a, col_b = st.columns([1, 1])
                        with col_a:
                            if st.button("✏️ Редактировать", key=f"edit_vac_{selected_vac_id}"):
                                st.session_state["edit_vac_id"] = selected_vac_id
                        with col_b:
                            if st.button("🗑️ Удалить", key=f"del_vac_{selected_vac_id}"):
                                try:
                                    supabase.table("vaccinations").delete().eq("id", selected_vac_id).execute()
                                    st.success("✅ Прививка удалена")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")
                    else:
                        st.info("👆 Выберите прививку в таблице или в списке")

                    if "edit_vac_id" in st.session_state and st.session_state["edit_vac_id"]:
                        edit_vacid = st.session_state["edit_vac_id"]
                        vac_edit = df_vaccinations[df_vaccinations["id"] == edit_vacid]
                        if not vac_edit.empty:
                            cur_vac = vac_edit.iloc[0]
                            st.divider()
                            st.subheader("✏️ Редактирование прививки")
                            with st.form("form_edit_vac"):
                                opts_a = athlete_options_dict()
                                cur_aid = cur_vac["athlete_id"]
                                cur_al = None
                                for lbl, aid in opts_a.items():
                                    if aid == cur_aid:
                                        cur_al = lbl
                                        break
                                cur_aidx = list(opts_a.keys()).index(cur_al) if cur_al else 0
                                sel_a = st.selectbox("Спортсменка *", list(opts_a.keys()), index=cur_aidx)
                                vn = st.text_input("Название вакцины *", value=cur_vac.get("vaccine_name") or "")
                                c1, c2 = st.columns(2)
                                with c1:
                                    vd = st.date_input("Дата прививки *", value=pd.to_datetime(cur_vac["vaccination_date"]).date(), format="DD.MM.YYYY")
                                with c2:
                                    bd_val = pd.to_datetime(cur_vac["booster_date"]).date() if pd.notna(cur_vac.get("booster_date")) else None
                                    bd = st.date_input("Дата ревакцинации", value=bd_val, format="DD.MM.YYYY")
                                bn = st.text_input("Номер серии", value=cur_vac.get("batch_number") or "")
                                if st.form_submit_button("💾 Сохранить", type="primary"):
                                    if not vn.strip():
                                        st.error("Введите название")
                                    else:
                                        try:
                                            supabase.table("vaccinations").update({
                                                "athlete_id": opts_a[sel_a],
                                                "vaccine_name": vn.strip(),
                                                "vaccination_date": vd.isoformat(),
                                                "booster_date": bd.isoformat() if bd else None,
                                                "batch_number": bn.strip() or None
                                            }).eq("id", edit_vacid).execute()
                                            st.success("✅ Прививка обновлена")
                                            st.session_state["edit_vac_id"] = None
                                            st.cache_data.clear()
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Ошибка: {e}")

            with sa:
                st.subheader("✍️ Добавить прививку")
                with st.form("f_vac", clear_on_submit=True):
                    opts = athlete_options_dict()
                    sel_a = st.selectbox("Спортсменка *", list(opts.keys()))
                    vn = st.text_input("Название вакцины *")
                    c1, c2 = st.columns(2)
                    with c1:
                        vd = st.date_input("Дата прививки *", value=date.today(), format="DD.MM.YYYY")
                    with c2:
                        bd = st.date_input("Дата ревакцинации", value=None, format="DD.MM.YYYY")
                    bn = st.text_input("Номер серии")
                    if st.form_submit_button("💾 Сохранить", type="primary"):
                        if not vn.strip():
                            st.error("Введите название")
                        else:
                            try:
                                supabase.table("vaccinations").insert({
                                    "athlete_id": opts[sel_a],
                                    "vaccine_name": vn.strip(),
                                    "vaccination_date": vd.isoformat(),
                                    "booster_date": bd.isoformat() if bd else None,
                                    "batch_number": bn.strip() if bn else None
                                }).execute()
                                st.success(f"✅ Прививка добавлена: {sel_a}")
                                st.cache_data.clear()
                            except Exception as e:
                                st.error(f"Ошибка: {e}")
    # --- АНТРОПОМЕТРИЯ ---
    if tab_anthro is not None:
        with tab_anthro:
            st.header("📏 Антропометрия")
            sv, sa = st.tabs(["📋 Просмотр", "✍️ Новое измерение"])

            with sv:
                if df_anthro.empty:
                    st.info("Измерений нет.")
                else:
                    cols = ["measurement_date", "jersey_number", "full_name", "height", "weight", "bmi", "body_fat", "muscle_mass", "thigh_circuit"]
                    av = [c for c in cols if c in df_anthro.columns]
                    d = format_dates(df_anthro[av].copy(), ["measurement_date"])
                    d = d.rename(columns={
                        "measurement_date": "Дата", "jersey_number": "№", "full_name": "ФИО",
                        "height": "Рост", "weight": "Вес", "bmi": "ИМТ",
                        "body_fat": "% жира", "muscle_mass": "Мышцы", "thigh_circuit": "Бедро"
                    })

                    event_ant = st.dataframe(
                        d,
                        on_select="rerun",
                        selection_mode="single-row",
                        use_container_width=True,
                        hide_index=True
                    )

                    st.divider()
                    st.subheader("👁️ Детальная информация")

                    ant_labels = []
                    for _, r in df_anthro.iterrows():
                        dt = pd.to_datetime(r["measurement_date"]).strftime('%d.%m.%Y') if pd.notna(r.get("measurement_date")) else "—"
                        lbl = f"{dt} · №{int(r['jersey_number']) if pd.notna(r.get('jersey_number')) else '?'} · {r.get('full_name') or '—'}"
                        ant_labels.append((lbl, r["id"]))

                    sel_lbl = None
                    if ant_labels:
                        sel_lbl = st.selectbox("Или выберите в списке",
                                                ["— не выбрано —"] + [l[0] for l in ant_labels],
                                                key="ant_view")

                    selected_ant_id = None
                    if event_ant.selection.rows:
                        idx = event_ant.selection.rows[0]
                        if idx < len(df_anthro):
                            selected_ant_id = df_anthro.iloc[idx]["id"]
                    elif sel_lbl and sel_lbl != "— не выбрано —":
                        selected_ant_id = next(i for l, i in ant_labels if l == sel_lbl)

                    if selected_ant_id:
                        ant = df_anthro[df_anthro["id"] == selected_ant_id].iloc[0]
                        st.markdown(f"**Дата:** {pd.to_datetime(ant['measurement_date']).strftime('%d.%m.%Y') if pd.notna(ant.get('measurement_date')) else '—'}")
                        st.markdown(f"**Спортсменка:** №{int(ant['jersey_number']) if pd.notna(ant.get('jersey_number')) else '?'} — {ant.get('full_name')}")
                        st.markdown(f"**Рост:** {ant.get('height') or '—'} см")
                        st.markdown(f"**Вес:** {ant.get('weight') or '—'} кг")
                        st.markdown(f"**ИМТ:** {ant.get('bmi') or '—'}")
                        st.markdown(f"**% жира:** {ant.get('body_fat') or '—'}")
                        st.markdown(f"**Мышечная масса:** {ant.get('muscle_mass') or '—'} кг")
                        st.markdown(f"**Обхват груди:** {ant.get('chest_circuit') or '—'} см")
                        st.markdown(f"**Обхват бедра:** {ant.get('thigh_circuit') or '—'} см")

                        col_a, col_b = st.columns([1, 1])
                        with col_a:
                            if st.button("✏️ Редактировать", key=f"edit_ant_{selected_ant_id}"):
                                st.session_state["edit_ant_id"] = selected_ant_id
                        with col_b:
                            if st.button("🗑️ Удалить", key=f"del_ant_{selected_ant_id}"):
                                try:
                                    supabase.table("anthropometry").delete().eq("id", selected_ant_id).execute()
                                    st.success("✅ Измерение удалено")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")
                    else:
                        st.info("👆 Выберите измерение в таблице или в списке")

                    if "edit_ant_id" in st.session_state and st.session_state["edit_ant_id"]:
                        edit_antid = st.session_state["edit_ant_id"]
                        ant_edit = df_anthro[df_anthro["id"] == edit_antid]
                        if not ant_edit.empty:
                            cur_ant = ant_edit.iloc[0]
                            st.divider()
                            st.subheader("✏️ Редактирование измерения")
                            with st.form("form_edit_ant"):
                                opts_a = athlete_options_dict()
                                cur_aid = cur_ant["athlete_id"]
                                cur_al = None
                                for lbl, aid in opts_a.items():
                                    if aid == cur_aid:
                                        cur_al = lbl
                                        break
                                cur_aidx = list(opts_a.keys()).index(cur_al) if cur_al else 0
                                sel_a = st.selectbox("Спортсменка *", list(opts_a.keys()), index=cur_aidx)
                                md = st.date_input("Дата измерения *", value=pd.to_datetime(cur_ant["measurement_date"]).date(), format="DD.MM.YYYY")
                                c1, c2, c3 = st.columns(3)
                                with c1:
                                    h = st.number_input("Рост (см)", min_value=0.0, max_value=250.0, step=0.5, value=float(cur_ant.get("height") or 0))
                                    w = st.number_input("Вес (кг)", min_value=0.0, max_value=200.0, step=0.1, value=float(cur_ant.get("weight") or 0))
                                with c2:
                                    bf = st.number_input("% жира", min_value=0.0, max_value=60.0, step=0.1, value=float(cur_ant.get("body_fat") or 0))
                                    mm = st.number_input("Мышечная масса (кг)", min_value=0.0, max_value=100.0, step=0.1, value=float(cur_ant.get("muscle_mass") or 0))
                                with c3:
                                    cc = st.number_input("Обхват груди (см)", min_value=0.0, max_value=200.0, step=0.5, value=float(cur_ant.get("chest_circuit") or 0))
                                    tc = st.number_input("Обхват бедра (см)", min_value=0.0, max_value=120.0, step=0.5, value=float(cur_ant.get("thigh_circuit") or 0))
                                if st.form_submit_button("💾 Сохранить", type="primary"):
                                    try:
                                        bmi = round(w / ((h / 100) ** 2), 1) if h > 0 and w > 0 else None
                                        supabase.table("anthropometry").update({
                                            "athlete_id": opts_a[sel_a],
                                            "measurement_date": md.isoformat(),
                                            "height": h if h > 0 else None,
                                            "weight": w if w > 0 else None,
                                            "bmi": bmi,
                                            "body_fat": bf if bf > 0 else None,
                                            "muscle_mass": mm if mm > 0 else None,
                                            "chest_circuit": cc if cc > 0 else None,
                                            "thigh_circuit": tc if tc > 0 else None
                                        }).eq("id", edit_antid).execute()
                                        st.success("✅ Измерение обновлено")
                                        st.session_state["edit_ant_id"] = None
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Ошибка: {e}")

            with sa:
                st.subheader("✍️ Новое измерение")
                with st.form("f_ant", clear_on_submit=True):
                    opts = athlete_options_dict()
                    sel_a = st.selectbox("Спортсменка *", list(opts.keys()))
                    md = st.date_input("Дата измерения *", value=date.today(), format="DD.MM.YYYY")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        h = st.number_input("Рост (см)", min_value=0.0, max_value=250.0, step=0.5, value=0.0)
                        w = st.number_input("Вес (кг)", min_value=0.0, max_value=200.0, step=0.1, value=0.0)
                    with c2:
                        bf = st.number_input("% жира", min_value=0.0, max_value=60.0, step=0.1, value=0.0)
                        mm = st.number_input("Мышечная масса (кг)", min_value=0.0, max_value=100.0, step=0.1, value=0.0)
                    with c3:
                        cc = st.number_input("Обхват груди (см)", min_value=0.0, max_value=200.0, step=0.5, value=0.0)
                        tc = st.number_input("Обхват бедра (см)", min_value=0.0, max_value=120.0, step=0.5, value=0.0)
                    if st.form_submit_button("💾 Сохранить", type="primary"):
                        try:
                            bmi = round(w / ((h / 100) ** 2), 1) if h > 0 and w > 0 else None
                            supabase.table("anthropometry").insert({
                                "athlete_id": opts[sel_a],
                                "measurement_date": md.isoformat(),
                                "height": h if h > 0 else None,
                                "weight": w if w > 0 else None,
                                "bmi": bmi,
                                "body_fat": bf if bf > 0 else None,
                                "muscle_mass": mm if mm > 0 else None,
                                "chest_circuit": cc if cc > 0 else None,
                                "thigh_circuit": tc if tc > 0 else None
                            }).execute()
                            st.success(f"✅ Измерение сохранено: {sel_a}")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")

    # --- ТЕСТЫ ---
    if tab_tests is not None:
        with tab_tests:
            st.header("🏃 Функциональные тесты")
            sv, sa = st.tabs(["📋 Просмотр", "✍️ Внести тест"])

            with sv:
                if df_tests.empty:
                    st.info("Тестов нет.")
                else:
                    cols = ["test_date", "jersey_number", "full_name", "test_name", "result_raw", "result_score", "evaluation"]
                    av = [c for c in cols if c in df_tests.columns]
                    d = format_dates(df_tests[av].copy(), ["test_date"])
                    d = d.rename(columns={
                        "test_date": "Дата", "jersey_number": "№", "full_name": "ФИО",
                        "test_name": "Тест", "result_raw": "Результат",
                        "result_score": "Балл", "evaluation": "Оценка"
                    })

                    event_t = st.dataframe(
                        d,
                        on_select="rerun",
                        selection_mode="single-row",
                        use_container_width=True,
                        hide_index=True
                    )

                    st.divider()
                    st.subheader("👁️ Детальная информация")

                    test_labels = []
                    for _, r in df_tests.iterrows():
                        dt = pd.to_datetime(r["test_date"]).strftime('%d.%m.%Y') if pd.notna(r.get("test_date")) else "—"
                        lbl = f"{dt} · №{int(r['jersey_number']) if pd.notna(r.get('jersey_number')) else '?'} · {r.get('test_name') or '—'}"
                        test_labels.append((lbl, r["id"]))

                    sel_lbl = None
                    if test_labels:
                        sel_lbl = st.selectbox("Или выберите в списке",
                                                ["— не выбрано —"] + [l[0] for l in test_labels],
                                                key="test_view")

                    selected_test_id = None
                    if event_t.selection.rows:
                        idx = event_t.selection.rows[0]
                        if idx < len(df_tests):
                            selected_test_id = df_tests.iloc[idx]["id"]
                    elif sel_lbl and sel_lbl != "— не выбрано —":
                        selected_test_id = next(i for l, i in test_labels if l == sel_lbl)

                    if selected_test_id:
                        tst = df_tests[df_tests["id"] == selected_test_id].iloc[0]
                        st.markdown(f"**Дата:** {pd.to_datetime(tst['test_date']).strftime('%d.%m.%Y') if pd.notna(tst.get('test_date')) else '—'}")
                        st.markdown(f"**Спортсменка:** №{int(tst['jersey_number']) if pd.notna(tst.get('jersey_number')) else '?'} — {tst.get('full_name')}")
                        st.markdown(f"**Тест:** {tst.get('test_name') or '—'}")
                        st.markdown(f"**Условия:** {tst.get('test_condition') or '—'}")
                        st.markdown(f"**Результат:** {tst.get('result_raw') or '—'}")
                        st.markdown(f"**Балл:** {tst.get('result_score') or '—'}")
                        st.markdown(f"**Оценка:** {tst.get('evaluation') or '—'}")

                        col_a, col_b = st.columns([1, 1])
                        with col_a:
                            if st.button("✏️ Редактировать", key=f"edit_test_{selected_test_id}"):
                                st.session_state["edit_test_id"] = selected_test_id
                        with col_b:
                            if st.button("🗑️ Удалить", key=f"del_test_{selected_test_id}"):
                                try:
                                    supabase.table("functional_tests").delete().eq("id", selected_test_id).execute()
                                    st.success("✅ Тест удалён")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")
                    else:
                        st.info("👆 Выберите тест в таблице или в списке")

                    if "edit_test_id" in st.session_state and st.session_state["edit_test_id"]:
                        edit_testid = st.session_state["edit_test_id"]
                        test_edit = df_tests[df_tests["id"] == edit_testid]
                        if not test_edit.empty:
                            cur_test = test_edit.iloc[0]
                            st.divider()
                            st.subheader("✏️ Редактирование теста")
                            with st.form("form_edit_test"):
                                opts_a = athlete_options_dict()
                                cur_aid = cur_test["athlete_id"]
                                cur_al = None
                                for lbl, aid in opts_a.items():
                                    if aid == cur_aid:
                                        cur_al = lbl
                                        break
                                cur_aidx = list(opts_a.keys()).index(cur_al) if cur_al else 0
                                sel_a = st.selectbox("Спортсменка *", list(opts_a.keys()), index=cur_aidx)

                                t_opts = {}
                                if not df_test_types.empty:
                                    for _, row in df_test_types.iterrows():
                                        t_opts[f"{row['name']} ({row['unit']})"] = row['id']
                                cur_tid = cur_test.get("test_type_id")
                                cur_tl = None
                                for lbl, tid in t_opts.items():
                                    if tid == cur_tid:
                                        cur_tl = lbl
                                        break
                                t_list = list(t_opts.keys())
                                t_idx = t_list.index(cur_tl) if cur_tl else 0
                                sel_t = st.selectbox("Тип теста *", t_list, index=t_idx)

                                td = st.date_input("Дата теста *", value=pd.to_datetime(cur_test["test_date"]).date(), format="DD.MM.YYYY")
                                tc = st.text_input("Условия проведения", value=cur_test.get("test_condition") or "")
                                rr = st.text_area("Сырые данные", value=cur_test.get("result_raw") or "", height=60)
                                rs = st.number_input("Итоговый балл", min_value=0.0, value=float(cur_test.get("result_score") or 0), step=0.1)
                                ev_list = ["— не указана —", "Высокая", "Средняя", "Низкая", "Норма", "Патология", "Отлично", "Хорошо", "Удовлетворительно", "Неудовлетворительно"]
                                cur_ev = cur_test.get("evaluation")
                                ev_idx = ev_list.index(cur_ev) if cur_ev in ev_list else 0
                                ev = st.selectbox("Оценка", ev_list, index=ev_idx)
                                if st.form_submit_button("💾 Сохранить", type="primary"):
                                    try:
                                        payload = {
                                            "athlete_id": opts_a[sel_a],
                                            "test_type_id": t_opts[sel_t],
                                            "test_date": td.isoformat(),
                                            "test_condition": tc.strip() or None,
                                            "result_raw": rr.strip() or None,
                                            "result_score": rs if rs > 0 else None
                                        }
                                        if ev != "— не указана —":
                                            payload["evaluation"] = ev
                                        else:
                                            payload["evaluation"] = None
                                        supabase.table("functional_tests").update(payload).eq("id", edit_testid).execute()
                                        st.success("✅ Тест обновлён")
                                        st.session_state["edit_test_id"] = None
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Ошибка: {e}")

            with sa:
                st.subheader("✍️ Внести тест")
                with st.form("f_test", clear_on_submit=True):
                    opts = athlete_options_dict()
                    sel_a = st.selectbox("Спортсменка *", list(opts.keys()))
                    topts = {}
                    if not df_test_types.empty:
                        for _, row in df_test_types.iterrows():
                            topts[f"{row['name']} ({row['unit']})"] = row['id']
                    sel_t = st.selectbox("Тип теста *", list(topts.keys()))
                    td = st.date_input("Дата теста *", value=date.today(), format="DD.MM.YYYY")
                    tc = st.text_input("Условия проведения")
                    rr = st.text_area("Сырые данные", height=60)
                    rs = st.number_input("Итоговый балл", min_value=0.0, value=0.0, step=0.1)
                    ev = st.selectbox("Оценка", ["— не указана —", "Высокая", "Средняя", "Низкая", "Норма", "Патология", "Отлично", "Хорошо", "Удовлетворительно", "Неудовлетворительно"])
                    if st.form_submit_button("💾 Сохранить", type="primary"):
                        try:
                            payload = {
                                "athlete_id": opts[sel_a],
                                "test_type_id": topts[sel_t],
                                "test_date": td.isoformat(),
                                "test_condition": tc.strip() if tc else None,
                                "result_raw": rr.strip() if rr else None,
                                "result_score": rs if rs > 0 else None
                            }
                            if ev != "— не указана —":
                                payload["evaluation"] = ev
                            supabase.table("functional_tests").insert(payload).execute()
                            st.success(f"✅ Тест сохранён: {sel_a}")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")

    # --- ХРОНИКИ ---
    if tab_chronic is not None:
        with tab_chronic:
            st.header("🩺 Хронические заболевания")
            sv, sa = st.tabs(["📋 Просмотр", "✍️ Добавить"])

            with sv:
                if df_chronic.empty:
                    st.info("Хроник нет.")
                else:
                    cols = ["diagnosis_date", "jersey_number", "full_name", "disease_name", "severity", "current_medication"]
                    av = [c for c in cols if c in df_chronic.columns]
                    d = format_dates(df_chronic[av].copy(), ["diagnosis_date"])
                    d = d.rename(columns={
                        "diagnosis_date": "Дата", "jersey_number": "№", "full_name": "ФИО",
                        "disease_name": "Заболевание", "severity": "Тяжесть",
                        "current_medication": "Лекарства"
                    })

                    event_ch = st.dataframe(
                        d,
                        on_select="rerun",
                        selection_mode="single-row",
                        use_container_width=True,
                        hide_index=True
                    )

                    st.divider()
                    st.subheader("👁️ Детальная информация")

                    ch_labels = []
                    for _, r in df_chronic.iterrows():
                        dt = pd.to_datetime(r["diagnosis_date"]).strftime('%d.%m.%Y') if pd.notna(r.get("diagnosis_date")) else "—"
                        lbl = f"{dt} · №{int(r['jersey_number']) if pd.notna(r.get('jersey_number')) else '?'} · {r.get('disease_name') or '—'}"
                        ch_labels.append((lbl, r["id"]))

                    sel_lbl = None
                    if ch_labels:
                        sel_lbl = st.selectbox("Или выберите в списке",
                                                ["— не выбрано —"] + [l[0] for l in ch_labels],
                                                key="ch_view")

                    selected_ch_id = None
                    if event_ch.selection.rows:
                        idx = event_ch.selection.rows[0]
                        if idx < len(df_chronic):
                            selected_ch_id = df_chronic.iloc[idx]["id"]
                    elif sel_lbl and sel_lbl != "— не выбрано —":
                        selected_ch_id = next(i for l, i in ch_labels if l == sel_lbl)

                    if selected_ch_id:
                        ch = df_chronic[df_chronic["id"] == selected_ch_id].iloc[0]
                        st.markdown(f"**Дата:** {pd.to_datetime(ch['diagnosis_date']).strftime('%d.%m.%Y') if pd.notna(ch.get('diagnosis_date')) else '—'}")
                        st.markdown(f"**Спортсменка:** №{int(ch['jersey_number']) if pd.notna(ch.get('jersey_number')) else '?'} — {ch.get('full_name')}")
                        st.markdown(f"**Заболевание:** {ch.get('disease_name') or '—'}")
                        st.markdown(f"**Тяжесть:** {ch.get('severity') or '—'}")
                        st.markdown(f"**Постоянные препараты:** {ch.get('current_medication') or '—'}")
                        st.markdown(f"**Рекомендации:** {ch.get('clinical_recommendations') or '—'}")

                        col_a, col_b = st.columns([1, 1])
                        with col_a:
                            if st.button("✏️ Редактировать", key=f"edit_ch_{selected_ch_id}"):
                                st.session_state["edit_ch_id"] = selected_ch_id
                        with col_b:
                            if st.button("🗑️ Удалить", key=f"del_ch_{selected_ch_id}"):
                                try:
                                    supabase.table("chronic_diseases").delete().eq("id", selected_ch_id).execute()
                                    st.success("✅ Удалено")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")
                    else:
                        st.info("👆 Выберите в таблице или в списке")

                    if "edit_ch_id" in st.session_state and st.session_state["edit_ch_id"]:
                        edit_chid = st.session_state["edit_ch_id"]
                        ch_edit = df_chronic[df_chronic["id"] == edit_chid]
                        if not ch_edit.empty:
                            cur_ch = ch_edit.iloc[0]
                            st.divider()
                            st.subheader("✏️ Редактирование")
                            with st.form("form_edit_ch"):
                                opts_a = athlete_options_dict()
                                cur_aid = cur_ch["athlete_id"]
                                cur_al = None
                                for lbl, aid in opts_a.items():
                                    if aid == cur_aid:
                                        cur_al = lbl
                                        break
                                cur_aidx = list(opts_a.keys()).index(cur_al) if cur_al else 0
                                sel_a = st.selectbox("Спортсменка *", list(opts_a.keys()), index=cur_aidx)
                                dn = st.text_input("Название *", value=cur_ch.get("disease_name") or "")
                                dd = st.date_input("Дата постановки *", value=pd.to_datetime(cur_ch["diagnosis_date"]).date(), format="DD.MM.YYYY")
                                sev_list = ["Легкая", "Средняя", "Тяжелая"]
                                sev_idx = sev_list.index(cur_ch.get("severity")) if cur_ch.get("severity") in sev_list else 0
                                sev = st.selectbox("Тяжесть", sev_list, index=sev_idx)
                                cm = st.text_area("Постоянные препараты", value=cur_ch.get("current_medication") or "", height=60)
                                cr = st.text_area("Рекомендации", value=cur_ch.get("clinical_recommendations") or "", height=60)
                                if st.form_submit_button("💾 Сохранить", type="primary"):
                                    if not dn.strip():
                                        st.error("Введите название")
                                    else:
                                        try:
                                            supabase.table("chronic_diseases").update({
                                                "athlete_id": opts_a[sel_a],
                                                "disease_name": dn.strip(),
                                                "diagnosis_date": dd.isoformat(),
                                                "severity": sev,
                                                "current_medication": cm.strip() or None,
                                                "clinical_recommendations": cr.strip() or None
                                            }).eq("id", edit_chid).execute()
                                            st.success("✅ Обновлено")
                                            st.session_state["edit_ch_id"] = None
                                            st.cache_data.clear()
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Ошибка: {e}")

            with sa:
                st.subheader("✍️ Добавить заболевание")
                with st.form("f_chr", clear_on_submit=True):
                    opts = athlete_options_dict()
                    sel_a = st.selectbox("Спортсменка *", list(opts.keys()))
                    dn = st.text_input("Название *")
                    dd = st.date_input("Дата постановки *", value=date.today(), format="DD.MM.YYYY")
                    sev = st.selectbox("Тяжесть", ["Легкая", "Средняя", "Тяжелая"])
                    cm = st.text_area("Постоянные препараты", height=60)
                    cr = st.text_area("Клинические рекомендации", height=60)
                    if st.form_submit_button("💾 Сохранить", type="primary"):
                        if not dn.strip():
                            st.error("Введите название")
                        else:
                            try:
                                supabase.table("chronic_diseases").insert({
                                    "athlete_id": opts[sel_a],
                                    "disease_name": dn.strip(),
                                    "diagnosis_date": dd.isoformat(),
                                    "severity": sev,
                                    "current_medication": cm.strip() if cm else None,
                                    "clinical_recommendations": cr.strip() if cr else None
                                }).execute()
                                st.success(f"✅ Сохранено: {sel_a}")
                                st.cache_data.clear()
                            except Exception as e:
                                st.error(f"Ошибка: {e}")

    # --- АНАЛИЗЫ ---
    if tab_lab is not None:
        with tab_lab:
            st.header("🧪 Лабораторные анализы")
            sv, sa = st.tabs(["📋 Просмотр", "✍️ Внести результат"])

            with sv:
                if df_lab.empty:
                    st.info("Анализов нет.")
                else:
                    cols = ["measurement_date", "jersey_number", "full_name", "biomarker_name", "value", "unit"]
                    av = [c for c in cols if c in df_lab.columns]
                    d = format_dates(df_lab[av].copy(), ["measurement_date"])
                    d = d.rename(columns={
                        "measurement_date": "Дата", "jersey_number": "№", "full_name": "ФИО",
                        "biomarker_name": "Показатель", "value": "Значение", "unit": "Ед."
                    })

                    event_l = st.dataframe(
                        d,
                        on_select="rerun",
                        selection_mode="single-row",
                        use_container_width=True,
                        hide_index=True
                    )

                    st.divider()
                    st.subheader("👁️ Детальная информация")

                    lab_labels = []
                    for _, r in df_lab.iterrows():
                        dt = pd.to_datetime(r["measurement_date"]).strftime('%d.%m.%Y') if pd.notna(r.get("measurement_date")) else "—"
                        lbl = f"{dt} · №{int(r['jersey_number']) if pd.notna(r.get('jersey_number')) else '?'} · {r.get('biomarker_name') or '—'}"
                        lab_labels.append((lbl, r["id"]))

                    sel_lbl = None
                    if lab_labels:
                        sel_lbl = st.selectbox("Или выберите в списке",
                                                ["— не выбрано —"] + [l[0] for l in lab_labels],
                                                key="lab_view")

                    selected_lab_id = None
                    if event_l.selection.rows:
                        idx = event_l.selection.rows[0]
                        if idx < len(df_lab):
                            selected_lab_id = df_lab.iloc[idx]["id"]
                    elif sel_lbl and sel_lbl != "— не выбрано —":
                        selected_lab_id = next(i for l, i in lab_labels if l == sel_lbl)

                    if selected_lab_id:
                        lab = df_lab[df_lab["id"] == selected_lab_id].iloc[0]
                        st.markdown(f"**Дата:** {pd.to_datetime(lab['measurement_date']).strftime('%d.%m.%Y') if pd.notna(lab.get('measurement_date')) else '—'}")
                        st.markdown(f"**Спортсменка:** №{int(lab['jersey_number']) if pd.notna(lab.get('jersey_number')) else '?'} — {lab.get('full_name')}")
                        st.markdown(f"**Показатель:** {lab.get('biomarker_name') or '—'}")
                        st.markdown(f"**Значение:** {lab.get('value')} {lab.get('unit') or ''}")
                        st.markdown(f"**Примечание:** {lab.get('notes') or '—'}")

                        col_a, col_b = st.columns([1, 1])
                        with col_a:
                            if st.button("✏️ Редактировать", key=f"edit_lab_{selected_lab_id}"):
                                st.session_state["edit_lab_id"] = selected_lab_id
                        with col_b:
                            if st.button("🗑️ Удалить", key=f"del_lab_{selected_lab_id}"):
                                try:
                                    supabase.table("lab_results").delete().eq("id", selected_lab_id).execute()
                                    st.success("✅ Удалено")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")
                    else:
                        st.info("👆 Выберите в таблице или в списке")

                    if "edit_lab_id" in st.session_state and st.session_state["edit_lab_id"]:
                        edit_labid = st.session_state["edit_lab_id"]
                        lab_edit = df_lab[df_lab["id"] == edit_labid]
                        if not lab_edit.empty:
                            cur_lab = lab_edit.iloc[0]
                            st.divider()
                            st.subheader("✏️ Редактирование анализа")
                            with st.form("form_edit_lab"):
                                opts_a = athlete_options_dict()
                                cur_aid = cur_lab["athlete_id"]
                                cur_al = None
                                for lbl, aid in opts_a.items():
                                    if aid == cur_aid:
                                        cur_al = lbl
                                        break
                                cur_aidx = list(opts_a.keys()).index(cur_al) if cur_al else 0
                                sel_a = st.selectbox("Спортсменка *", list(opts_a.keys()), index=cur_aidx)

                                b_opts = {}
                                if not df_biomarkers.empty:
                                    for _, row in df_biomarkers.iterrows():
                                        b_opts[f"{row['name']} ({row['unit']})"] = row['id']
                                cur_bid = cur_lab.get("biomarker_id")
                                cur_bl = None
                                for lbl, bid in b_opts.items():
                                    if bid == cur_bid:
                                        cur_bl = lbl
                                        break
                                b_list = list(b_opts.keys())
                                b_idx = b_list.index(cur_bl) if cur_bl else 0
                                sel_b = st.selectbox("Показатель *", b_list, index=b_idx)

                                md = st.date_input("Дата сдачи *", value=pd.to_datetime(cur_lab["measurement_date"]).date(), format="DD.MM.YYYY")
                                val = st.number_input("Значение *", value=float(cur_lab.get("value") or 0), step=0.01)
                                nt = st.text_input("Примечание", value=cur_lab.get("notes") or "")
                                if st.form_submit_button("💾 Сохранить", type="primary"):
                                    try:
                                        supabase.table("lab_results").update({
                                            "athlete_id": opts_a[sel_a],
                                            "biomarker_id": b_opts[sel_b],
                                            "measurement_date": md.isoformat(),
                                            "value": val,
                                            "notes": nt.strip() or None
                                        }).eq("id", edit_labid).execute()
                                        st.success("✅ Обновлено")
                                        st.session_state["edit_lab_id"] = None
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Ошибка: {e}")

            with sa:
                st.subheader("✍️ Внести результат анализа")
                with st.form("f_lab", clear_on_submit=True):
                    opts = athlete_options_dict()
                    sel_a = st.selectbox("Спортсменка *", list(opts.keys()))
                    bopts = {}
                    if not df_biomarkers.empty:
                        for _, row in df_biomarkers.iterrows():
                            bopts[f"{row['name']} ({row['unit']})"] = row['id']
                    sel_b = st.selectbox("Показатель *", list(bopts.keys()))
                    md = st.date_input("Дата сдачи *", value=date.today(), format="DD.MM.YYYY")
                    val = st.number_input("Значение *", value=0.0, step=0.01)
                    nt = st.text_input("Примечание")
                    if st.form_submit_button("💾 Сохранить", type="primary"):
                        try:
                            supabase.table("lab_results").insert({
                                "athlete_id": opts[sel_a],
                                "biomarker_id": bopts[sel_b],
                                "measurement_date": md.isoformat(),
                                "value": val,
                                "notes": nt.strip() if nt else None
                            }).execute()
                            st.success(f"✅ Анализ сохранён: {sel_a}")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")

# ============ ФУТЕР ============
st.divider()
c1, c2 = st.columns([4, 1])
with c1:
    if st.button("🔄 Обновить данные"):
        st.cache_data.clear()
        st.rerun()
with c2:
    if st.button("🚪 Выйти"):
        st.session_state["authenticated"] = False
        st.session_state.pop("user", None)
        st.rerun()

st.caption(f"Последнее обновление: {pd.Timestamp.now().strftime('%H:%M:%S')}")