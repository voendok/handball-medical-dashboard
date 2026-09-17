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

def athlete_selectbox(key_suffix):
    """Список спортсменок для формы. Возвращает словарь {label: id}."""
    df_a = load_athletes()
    options = {}
    if not df_a.empty:
        for _, row in df_a.iterrows():
            if pd.notna(row['jersey_number']):
                label = f"№{int(row['jersey_number'])} — {row['full_name']}"
            else:
                label = f"(без номера) {row['full_name']}"
            options[label] = row['id']
    return options

# ============ ЗАГРУЗКА СПРАВОЧНИКОВ ============
@st.cache_data(ttl=300)
def load_athletes():
    r = supabase.table("athletes").select("id, full_name, jersey_number").eq("is_active", True).order("jersey_number").execute()
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
    r = supabase.table("dict_exam_templates").select("id, name, specialist_type, validity_days, is_mandatory").order("name").execute()
    return pd.DataFrame(r.data)

@st.cache_data(ttl=300)
def load_test_types():
    r = supabase.table("dict_test_types").select("id, name, unit").order("name").execute()
    return pd.DataFrame(r.data)

@st.cache_data(ttl=300)
def load_biomarkers():
    r = supabase.table("dict_biomarkers").select("id, name, unit, reference_min, reference_max").order("name").execute()
    return pd.DataFrame(r.data)

# ============ ЗАГРУЗКА ДАННЫХ ============
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
    r = supabase.table("injuries_and_illnesses").select("*, athletes(full_name, jersey_number), dict_body_parts(name), dict_diagnoses(name)").gte("incident_date", since).order("incident_date", desc=True).execute()
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
    today = date.today().isoformat()
    r = supabase.table("medication_intake").select("*, athletes(full_name, jersey_number), dict_medicines(name, wada_status)").lte("course_start", today).gte("course_end", today).execute()
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
    r = supabase.table("examinations").select("*, athletes(full_name, jersey_number), dict_exam_templates(name)").order("examination_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df["exam_name"] = df["dict_exam_templates"].apply(lambda x: x["name"] if x else None)
        df = df.drop(columns=["athletes", "dict_exam_templates"])
    return df

@st.cache_data(ttl=60)
def load_vaccinations():
    r = supabase.table("vaccinations").select("*, athletes(full_name, jersey_number)").order("vaccination_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df = df.drop(columns=["athletes"])
    return df

@st.cache_data(ttl=60)
def load_anthropometry():
    r = supabase.table("anthropometry").select("*, athletes(full_name, jersey_number)").order("measurement_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df = df.drop(columns=["athletes"])
    return df

@st.cache_data(ttl=60)
def load_functional_tests():
    r = supabase.table("functional_tests").select("*, athletes(full_name, jersey_number), dict_test_types(name, unit)").order("test_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df["test_name"] = df["dict_test_types"].apply(lambda x: x["name"] if x else None)
        df = df.drop(columns=["athletes", "dict_test_types"])
    return df

@st.cache_data(ttl=60)
def load_chronic_diseases():
    r = supabase.table("chronic_diseases").select("*, athletes(full_name, jersey_number)").order("diagnosis_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df = df.drop(columns=["athletes"])
    return df

@st.cache_data(ttl=60)
def load_lab_results():
    r = supabase.table("lab_results").select("*, athletes(full_name, jersey_number), dict_biomarkers(name, unit)").order("measurement_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df["biomarker_name"] = df["dict_biomarkers"].apply(lambda x: x["name"] if x else None)
        df["unit"] = df["dict_biomarkers"].apply(lambda x: x["unit"] if x else None)
        df = df.drop(columns=["athletes", "dict_biomarkers"])
    return df

# ============ ЗАГРУЗКА ============
df_dashboard = load_today_dashboard()
df_missing = load_missing_reports()
df_overdue = load_overdue_exams()
df_athletes = load_athletes()
df_logs = load_health_logs(30)
df_all_exams = load_all_examinations()
df_injuries = load_injuries(365)
df_meds_current = load_medications()
df_vaccinations = load_vaccinations()
df_anthro = load_anthropometry()
df_tests = load_functional_tests()
df_chronic = load_chronic_diseases()
df_lab = load_lab_results()

df_body_parts = load_body_parts()
df_diagnoses = load_diagnoses()
df_medicines = load_medicines()
df_exam_templates = load_exam_templates()
df_test_types = load_test_types()
df_biomarkers = load_biomarkers()

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
        my_row = df_athletes[df_athletes["id"] == user_athlete_id]
        my_jersey = int(my_row["jersey_number"].iloc[0]) if not my_row.empty and pd.notna(my_row["jersey_number"].iloc[0]) else None
        my_dashboard = df_dashboard[df_dashboard["№"] == my_jersey] if my_jersey else pd.DataFrame()

        if not my_dashboard.empty:
            r = my_dashboard.iloc[0]
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Статус", f"{r.get('icon', '⚪')} {r.get('status', 'grey')}")
            col2.metric("Пульс", r.get("Пульс", "—"))
            col3.metric("Разница", r.get("Разница", "—"))
            col4.metric("Сон", r.get("Сон", "—"))
            if "Причина" in r:
                st.info(f"**Причина:** {r['Причина']}")
        else:
            st.info("📭 Сегодня вы ещё не отправляли утренний отчёт.")

    with tab_dynamics:
        st.header("📈 Моя динамика")
        my_logs = df_logs[df_logs["athlete_id"] == user_athlete_id]
        if my_logs.empty:
            st.info("Нет данных за 30 дней.")
        else:
            df_chart = my_logs[["log_date", "morning_hr", "ortho_hr_after", "sleep_hours", "borg_rating"]].sort_values("log_date").set_index("log_date")
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("❤️ Пульс")
                if df_chart["morning_hr"].notna().any():
                    d = df_chart[["morning_hr"]].dropna(); d.columns = ["Пульс"]
                    st.line_chart(d, use_container_width=True)
            with c2:
                st.subheader("😴 Сон")
                if df_chart["sleep_hours"].notna().any():
                    d = df_chart[["sleep_hours"]].dropna(); d.columns = ["Сон"]
                    st.line_chart(d, use_container_width=True)

    with tab_exams_self:
        st.header("🏥 Мои осмотры")
        my_exams = df_all_exams[df_all_exams["athlete_id"] == user_athlete_id]
        if my_exams.empty:
            st.info("Осмотры пока не внесены.")
        else:
            cols = ["examination_date", "exam_name", "is_approved", "next_exam_date", "restrictions"]
            av = [c for c in cols if c in my_exams.columns]
            df_show = format_dates(my_exams[av], ["examination_date", "next_exam_date"])
            df_show = df_show.rename(columns={"examination_date": "Дата", "exam_name": "Осмотр", "is_approved": "Допуск", "next_exam_date": "Следующий", "restrictions": "Ограничения"})
            st.dataframe(df_show, use_container_width=True, hide_index=True)

# ============ ДАШБОРД ВРАЧА / ТРЕНЕРА / АДМИНА ============
else:
    # Вкладки по ролям
    if user_role == "coach":
        tabs = st.tabs(["📊 Сегодня", "📈 Динамика"])
        tab_today, tab_dynamics = tabs
        tab_exams = tab_injuries = tab_meds = tab_vaccines = tab_anthro = tab_tests = tab_chronic = tab_lab = None
    elif user_role == "masseur":
        tabs = st.tabs(["📊 Сегодня", "📈 Динамика", "🏥 Осмотры", "🩹 Травмы", "📏 Антропометрия"])
        tab_today, tab_dynamics, tab_exams, tab_injuries, tab_anthro = tabs
        tab_meds = tab_vaccines = tab_tests = tab_chronic = tab_lab = None
    elif user_role == "athlete":
        tabs = st.tabs(["📊 Сегодня", "📈 Динамика"])
        tab_today, tab_dynamics = tabs
        tab_exams = tab_injuries = tab_meds = tab_vaccines = tab_anthro = tab_tests = tab_chronic = tab_lab = None
    else:  # admin, doctor
        tabs = st.tabs([
            "📊 Сегодня", "📈 Динамика", "🏥 Осмотры", "🩹 Травмы",
            "💊 Лекарства", "💉 Прививки", "📏 Антропометрия",
            "🏃 Тесты", "🩺 Хроники", "🧪 Анализы"
        ])
        (tab_today, tab_dynamics, tab_exams, tab_injuries,
         tab_meds, tab_vaccines, tab_anthro, tab_tests, tab_chronic, tab_lab) = tabs

    # --- Сегодня ---
    with tab_today:
        st.header("📊 Сводка за сегодня")
        rc = len(df_dashboard[df_dashboard["status"] == "red"]) if not df_dashboard.empty else 0
        yc = len(df_dashboard[df_dashboard["status"] == "yellow"]) if not df_dashboard.empty else 0
        gc = len(df_dashboard[df_dashboard["status"] == "green"]) if not df_dashboard.empty else 0
        grc = len(df_dashboard[df_dashboard["status"] == "grey"]) if not df_dashboard.empty else 0
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🔴 Проблемы", rc); c2.metric("🟡 Внимание", yc)
        c3.metric("🟢 Норма", gc); c4.metric("⚪ Нет данных", grc)

        st.divider()
        st.subheader("🚦 Статус спортсменок")
        if not df_dashboard.empty:
            filt = st.selectbox("Фильтр", ["Все", "🔴 Только красные", "🟡 Только жёлтые", "🟢 Только зелёные", "⚪ Только без данных"])
            if filt == "🔴 Только красные": df_d = df_dashboard[df_dashboard["status"] == "red"]
            elif filt == "🟡 Только жёлтые": df_d = df_dashboard[df_dashboard["status"] == "yellow"]
            elif filt == "🟢 Только зелёные": df_d = df_dashboard[df_dashboard["status"] == "green"]
            elif filt == "⚪ Только без данных": df_d = df_dashboard[df_dashboard["status"] == "grey"]
            else: df_d = df_dashboard
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

    # --- Динамика ---
    with tab_dynamics:
        st.header("📈 Динамика за 30 дней")
        opts = ["👥 Вся команда"]; amap = {}
        if not df_athletes.empty:
            for _, row in df_athletes.iterrows():
                j = int(row['jersey_number']) if pd.notna(row['jersey_number']) else None
                label = f"№{j} — {row['full_name']}" if j else f"(без номера) {row['full_name']}"
                opts.append(label); amap[label] = row['id']
        sel = st.selectbox("Спортсменка", opts)
        if sel == "👥 Вся команда":
            df_f = df_logs; suf = "команды"
        else:
            df_f = df_logs[df_logs["athlete_id"] == amap[sel]]; suf = f"— {sel}"
        if df_f.empty:
            st.info(f"Нет данных для {suf}.")
        else:
            if sel == "👥 Вся команда":
                dfc = df_f.groupby("log_date").agg({"morning_hr":"mean","ortho_hr_after":"mean","sleep_hours":"mean","borg_rating":"mean"}).reset_index()
            else:
                dfc = df_f[["log_date","morning_hr","ortho_hr_after","sleep_hours","borg_rating"]].copy()
            dfc = dfc.sort_values("log_date").set_index("log_date")
            c1, c2 = st.columns(2)
            with c1:
                st.subheader(f"❤️ Пульс")
                if dfc["morning_hr"].notna().any():
                    d = dfc[["morning_hr"]].dropna(); d.columns = ["Пульс"]; st.line_chart(d, use_container_width=True)
            with c2:
                st.subheader(f"😴 Сон")
                if dfc["sleep_hours"].notna().any():
                    d = dfc[["sleep_hours"]].dropna(); d.columns = ["Сон"]; st.line_chart(d, use_container_width=True)
            st.subheader(f"📊 Ортостатическая разница")
            o = dfc[["morning_hr","ortho_hr_after"]].dropna()
            if not o.empty:
                o["Разница"] = o["ortho_hr_after"] - o["morning_hr"]
                st.line_chart(o[["Разница"]], use_container_width=True)
            c3, c4 = st.columns(2)
            with c3:
                st.subheader(f"💪 Шкала Борга")
                if dfc["borg_rating"].notna().any():
                    d = dfc[["borg_rating"]].dropna(); d.columns = ["Борг"]; st.line_chart(d, use_container_width=True)

    # --- ОСМОТРЫ ---
    if tab_exams is not None:
        with tab_exams:
            st.header("🏥 Осмотры")
            sv, sa = st.tabs(["📋 Просмотр", "✍️ Внести осмотр"])

            with sv:
                st.subheader("⚠️ Просроченные")
                if not df_overdue.empty:
                    st.error(f"Просрочено: {len(df_overdue)}")
                    d = format_dates(df_overdue, ["Был должен"])
                    st.dataframe(d, use_container_width=True, hide_index=True)
                else:
                    st.success("✅ Всё в порядке")

                st.subheader("📋 Все осмотры (последние 50)")
                if not df_all_exams.empty:
                    cols = ["examination_date","jersey_number","full_name","exam_name","is_approved","next_exam_date","restrictions"]
                    av = [c for c in cols if c in df_all_exams.columns]
                    d = format_dates(df_all_exams[av].head(50).copy(), ["examination_date","next_exam_date"])
                    d = d.rename(columns={"examination_date":"Дата","jersey_number":"№","full_name":"ФИО","exam_name":"Осмотр","is_approved":"Допуск","next_exam_date":"Следующий","restrictions":"Ограничения"})
                    st.dataframe(d, use_container_width=True, hide_index=True)
                else:
                    st.info("Осмотров пока нет.")

            with sa:
                st.subheader("✍️ Внести новый осмотр")
                with st.form("f_exam", clear_on_submit=True):
                    aopts = athlete_selectbox("exam")
                    sel_a = st.selectbox("Спортсменка *", list(aopts.keys()))
                    topts = {}
                    if not df_exam_templates.empty:
                        for _, row in df_exam_templates.iterrows():
                            topts[f"{row['name']} ({row['specialist_type']})"] = {"id":row['id'],"validity":row['validity_days']}
                    sel_t = st.selectbox("Тип осмотра *", list(topts.keys()))
                    c1, c2 = st.columns(2)
                    with c1: ed = st.date_input("Дата осмотра *", value=date.today(), format="DD.MM.YYYY")
                    with c2:
                        v = topts.get(sel_t, {}).get("validity", 365)
                        nd = ed + timedelta(days=v) if v else ed
                        ned = st.date_input("Следующий осмотр", value=nd, format="DD.MM.YYYY")
                    rt = st.text_area("Заключение *", height=100)
                    ap = st.radio("Допуск? *", [True, False], format_func=lambda x: "✅ Да" if x else "❌ Нет", horizontal=True)
                    res = st.text_input("Ограничения")
                    if st.form_submit_button("💾 Сохранить", type="primary"):
                        if len(rt.strip()) < 3:
                            st.error("Заполните заключение")
                        else:
                            try:
                                supabase.table("examinations").insert({
                                    "athlete_id": aopts[sel_a],
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
                    st.info("За 365 дней травм не зарегистрировано.")
                else:
                    st.warning(f"Травм: {len(df_injuries)}")
                    cols = ["incident_date","jersey_number","full_name","diagnosis","body_part","side","severity","days_lost"]
                    av = [c for c in cols if c in df_injuries.columns]
                    d = format_dates(df_injuries[av].copy(), ["incident_date"])
                    d = d.rename(columns={"incident_date":"Дата","jersey_number":"№","full_name":"ФИО","diagnosis":"Диагноз","body_part":"Часть тела","side":"Сторона","severity":"Тяжесть","days_lost":"Пропущено"})
                    st.dataframe(d, use_container_width=True, hide_index=True)

            with sa:
                st.subheader("✍️ Внести травму или заболевание")
                with st.form("f_inj", clear_on_submit=True):
                    aopts = athlete_selectbox("inj")
                    sel_a = st.selectbox("Спортсменка *", list(aopts.keys()))

                    dopts = {}
                    if not df_diagnoses.empty:
                        for _, row in df_diagnoses.iterrows():
                            lbl = f"{row['mkb_code']} — {row['name']}" if pd.notna(row['mkb_code']) else row['name']
                            dopts[lbl] = row['id']
                    if not dopts:
                        st.warning("Справочник диагнозов пуст. Добавьте диагнозы через Supabase.")
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

                    is_rec = st.checkbox("Рецидив (травма повторная)")
                    treat = st.text_area("Описание лечения", height=80)
                    d_lost = st.number_input("Пропущено дней", min_value=0, value=0)

                    if st.form_submit_button("💾 Сохранить", type="primary"):
                        try:
                            payload = {
                                "athlete_id": aopts[sel_a],
                                "incident_date": idate.isoformat(),
                                "side": side,
                                "mechanism": mech,
                                "severity": sev,
                                "is_recurrent": is_rec,
                                "treatment_description": treat.strip() if treat else None,
                                "days_lost": int(d_lost)
                            }
                            if sel_d != "— не указан —": payload["diagnosis_id"] = dopts[sel_d]
                            if sel_b != "— не указана —": payload["body_part_id"] = bopts[sel_b]

                            supabase.table("injuries_and_illnesses").insert(payload).execute()
                            st.success(f"✅ Травма сохранена: {sel_a}")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")

    # --- ЛЕКАРСТВА ---
    if tab_meds is not None:
        with tab_meds:
            st.header("💊 Лекарства")
            sv, sa = st.tabs(["📋 Текущие приёмы", "✍️ Назначить лекарство"])

            with sv:
                if df_meds_current.empty:
                    st.info("Сейчас никто не принимает лекарства.")
                else:
                    st.warning(f"Принимают: {len(df_meds_current)}")
                    cols = ["jersey_number","full_name","medicine_name","dosage","course_end","wada_status"]
                    av = [c for c in cols if c in df_meds_current.columns]
                    d = format_dates(df_meds_current[av].copy(), ["course_end"])
                    d = d.rename(columns={"jersey_number":"№","full_name":"ФИО","medicine_name":"Препарат","dosage":"Дозировка","course_end":"До","wada_status":"WADA"})
                    st.dataframe(d, use_container_width=True, hide_index=True)

            with sa:
                st.subheader("✍️ Назначить лекарство")
                with st.form("f_med", clear_on_submit=True):
                    aopts = athlete_selectbox("med")
                    sel_a = st.selectbox("Спортсменка *", list(aopts.keys()))

                    mopts = {}
                    if not df_medicines.empty:
                        for _, row in df_medicines.iterrows():
                            lbl = f"{row['name']} [{row['wada_status']}]"
                            mopts[lbl] = row['id']
                    sel_m = st.selectbox("Препарат *", list(mopts.keys()))

                    c1, c2 = st.columns(2)
                    with c1:
                        pd_ = st.date_input("Дата назначения", value=date.today(), format="DD.MM.YYYY")
                        cs = st.date_input("Начало курса", value=date.today(), format="DD.MM.YYYY")
                    with c2:
                        ce = st.date_input("Конец курса", value=date.today() + timedelta(days=7), format="DD.MM.YYYY")
                        rt = st.selectbox("Способ", ["Перорально", "Внутримышечно", "Внутривенно", "Местно", "Ингаляционно"])

                    dose = st.text_input("Дозировка", placeholder="500 мг")
                    freq = st.text_input("Кратность", placeholder="2 раза в день")
                    tue = st.text_input("Ссылка на TUE (если требуется)")

                    if st.form_submit_button("💾 Сохранить", type="primary"):
                        try:
                            supabase.table("medication_intake").insert({
                                "athlete_id": aopts[sel_a],
                                "medicine_id": mopts[sel_m],
                                "prescribed_date": pd_.isoformat(),
                                "course_start": cs.isoformat(),
                                "course_end": ce.isoformat(),
                                "dosage": dose.strip() if dose else None,
                                "frequency": freq.strip() if freq else None,
                                "administration_route": rt,
                                "tue_document_link": tue.strip() if tue else None
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
                    st.info("Прививок пока нет.")
                else:
                    cols = ["vaccination_date","jersey_number","full_name","vaccine_name","booster_date","batch_number"]
                    av = [c for c in cols if c in df_vaccinations.columns]
                    d = format_dates(df_vaccinations[av].copy(), ["vaccination_date","booster_date"])
                    d = d.rename(columns={"vaccination_date":"Дата","jersey_number":"№","full_name":"ФИО","vaccine_name":"Вакцина","booster_date":"Ревакцинация","batch_number":"Серия"})
                    st.dataframe(d, use_container_width=True, hide_index=True)

            with sa:
                st.subheader("✍️ Добавить прививку")
                with st.form("f_vac", clear_on_submit=True):
                    aopts = athlete_selectbox("vac")
                    sel_a = st.selectbox("Спортсменка *", list(aopts.keys()))
                    vn = st.text_input("Название вакцины *", placeholder="АДС-М, Гепатит B, Грипп")

                    c1, c2 = st.columns(2)
                    with c1: vd = st.date_input("Дата прививки *", value=date.today(), format="DD.MM.YYYY")
                    with c2: bd = st.date_input("Дата ревакцинации", value=None, format="DD.MM.YYYY")

                    bn = st.text_input("Номер серии")
                    if st.form_submit_button("💾 Сохранить", type="primary"):
                        if not vn.strip():
                            st.error("Введите название вакцины")
                        else:
                            try:
                                supabase.table("vaccinations").insert({
                                    "athlete_id": aopts[sel_a],
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
                    st.info("Измерений пока нет.")
                else:
                    cols = ["measurement_date","jersey_number","full_name","height","weight","bmi","body_fat","muscle_mass","thigh_circuit"]
                    av = [c for c in cols if c in df_anthro.columns]
                    d = format_dates(df_anthro[av].copy(), ["measurement_date"])
                    d = d.rename(columns={"measurement_date":"Дата","jersey_number":"№","full_name":"ФИО","height":"Рост","weight":"Вес","bmi":"ИМТ","body_fat":"% жира","muscle_mass":"Мышцы","thigh_circuit":"Бедро"})
                    st.dataframe(d, use_container_width=True, hide_index=True)

            with sa:
                st.subheader("✍️ Новое измерение")
                with st.form("f_ant", clear_on_submit=True):
                    aopts = athlete_selectbox("ant")
                    sel_a = st.selectbox("Спортсменка *", list(aopts.keys()))
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
                            bmi = round(w / ((h/100) ** 2), 1) if h > 0 and w > 0 else None
                            supabase.table("anthropometry").insert({
                                "athlete_id": aopts[sel_a],
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

    # --- ФУНКЦИОНАЛЬНЫЕ ТЕСТЫ ---
    if tab_tests is not None:
        with tab_tests:
            st.header("🏃 Функциональные тесты")
            sv, sa = st.tabs(["📋 Просмотр", "✍️ Внести тест"])

            with sv:
                if df_tests.empty:
                    st.info("Тестов пока нет.")
                else:
                    cols = ["test_date","jersey_number","full_name","test_name","result_raw","result_score","evaluation"]
                    av = [c for c in cols if c in df_tests.columns]
                    d = format_dates(df_tests[av].copy(), ["test_date"])
                    d = d.rename(columns={"test_date":"Дата","jersey_number":"№","full_name":"ФИО","test_name":"Тест","result_raw":"Результат","result_score":"Балл","evaluation":"Оценка"})
                    st.dataframe(d, use_container_width=True, hide_index=True)

            with sa:
                st.subheader("✍️ Внести тест")
                with st.form("f_test", clear_on_submit=True):
                    aopts = athlete_selectbox("test")
                    sel_a = st.selectbox("Спортсменка *", list(aopts.keys()))

                    topts = {}
                    if not df_test_types.empty:
                        for _, row in df_test_types.iterrows():
                            topts[f"{row['name']} ({row['unit']})"] = row['id']
                    sel_t = st.selectbox("Тип теста *", list(topts.keys()))

                    td = st.date_input("Дата теста *", value=date.today(), format="DD.MM.YYYY")
                    tc = st.text_input("Условия проведения", placeholder="Утром до тренировки")
                    rr = st.text_area("Сырые данные", placeholder="Например: 150 вт, ЧСС 145", height=60)
                    rs = st.number_input("Итоговый балл", min_value=0.0, value=0.0, step=0.1)
                    ev = st.selectbox("Оценка", ["— не указана —", "Высокая", "Средняя", "Низкая", "Норма", "Патология", "Отлично", "Хорошо", "Удовлетворительно", "Неудовлетворительно"])

                    if st.form_submit_button("💾 Сохранить", type="primary"):
                        try:
                            payload = {
                                "athlete_id": aopts[sel_a],
                                "test_type_id": topts[sel_t],
                                "test_date": td.isoformat(),
                                "test_condition": tc.strip() if tc else None,
                                "result_raw": rr.strip() if rr else None,
                                "result_score": rs if rs > 0 else None,
                            }
                            if ev != "— не указана —": payload["evaluation"] = ev
                            supabase.table("functional_tests").insert(payload).execute()
                            st.success(f"✅ Тест сохранён: {sel_a}")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")

    # --- ХРОНИЧЕСКИЕ ЗАБОЛЕВАНИЯ ---
    if tab_chronic is not None:
        with tab_chronic:
            st.header("🩺 Хронические заболевания")
            sv, sa = st.tabs(["📋 Просмотр", "✍️ Добавить"])

            with sv:
                if df_chronic.empty:
                    st.info("Хронических заболеваний не зарегистрировано.")
                else:
                    cols = ["diagnosis_date","jersey_number","full_name","disease_name","severity","current_medication","clinical_recommendations"]
                    av = [c for c in cols if c in df_chronic.columns]
                    d = format_dates(df_chronic[av].copy(), ["diagnosis_date"])
                    d = d.rename(columns={"diagnosis_date":"Дата","jersey_number":"№","full_name":"ФИО","disease_name":"Заболевание","severity":"Тяжесть","current_medication":"Лекарства","clinical_recommendations":"Рекомендации"})
                    st.dataframe(d, use_container_width=True, hide_index=True)

            with sa:
                st.subheader("✍️ Добавить хроническое заболевание")
                with st.form("f_chr", clear_on_submit=True):
                    aopts = athlete_selectbox("chr")
                    sel_a = st.selectbox("Спортсменка *", list(aopts.keys()))
                    dn = st.text_input("Название заболевания *", placeholder="Бронхиальная астма")
                    dd = st.date_input("Дата постановки диагноза *", value=date.today(), format="DD.MM.YYYY")
                    sev = st.selectbox("Тяжесть", ["Легкая", "Средняя", "Тяжелая"])
                    cm = st.text_area("Постоянные препараты", height=60)
                    cr = st.text_area("Клинические рекомендации", height=60)

                    if st.form_submit_button("💾 Сохранить", type="primary"):
                        if not dn.strip():
                            st.error("Введите название")
                        else:
                            try:
                                supabase.table("chronic_diseases").insert({
                                    "athlete_id": aopts[sel_a],
                                    "disease_name": dn.strip(),
                                    "diagnosis_date": dd.isoformat(),
                                    "severity": sev,
                                    "current_medication": cm.strip() if cm else None,
                                    "clinical_recommendations": cr.strip() if cr else None
                                }).execute()
                                st.success(f"✅ Заболевание добавлено: {sel_a}")
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
                    st.info("Результатов анализов нет.")
                else:
                    cols = ["measurement_date","jersey_number","full_name","biomarker_name","value","unit"]
                    av = [c for c in cols if c in df_lab.columns]
                    d = format_dates(df_lab[av].copy(), ["measurement_date"])
                    d = d.rename(columns={"measurement_date":"Дата","jersey_number":"№","full_name":"ФИО","biomarker_name":"Показатель","value":"Значение","unit":"Ед."})
                    st.dataframe(d, use_container_width=True, hide_index=True)

            with sa:
                st.subheader("✍️ Внести результат анализа")
                with st.form("f_lab", clear_on_submit=True):
                    aopts = athlete_selectbox("lab")
                    sel_a = st.selectbox("Спортсменка *", list(aopts.keys()))

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
                                "athlete_id": aopts[sel_a],
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
