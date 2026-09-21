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
@st.cache_data(ttl=300)
def load_athlete_documents(athlete_id):
    """Загружает список документов спортсменки."""
    try:
        r = supabase.table("documents") \
            .select("id, document_type, file_name, file_path, upload_date, comment") \
            .eq("athlete_id", athlete_id) \
            .order("upload_date", desc=True) \
            .execute()
        return pd.DataFrame(r.data)
    except Exception:
        return pd.DataFrame()


def get_public_file_url(file_path):
    """Возвращает публичный URL файла из Storage."""
    try:
        return supabase.storage.from_("medical_documents").get_public_url(file_path)
    except Exception:
        return None
def render_diagnosis_multiselect(label="Диагнозы (МКБ)", default_labels=None, key_suffix=""):
    """Multiselect диагнозов, сгруппированных по классам МКБ-10. Возвращает список id."""
    df_d = load_diagnoses()
    if df_d.empty or "mkb_class" not in df_d.columns:
        st.warning("Справочник диагнозов пуст или не содержит классов МКБ.")
        return []
    diag_options = []
    diag_map = {}
    for cls in sorted(df_d["mkb_class"].dropna().unique()):
        sub = df_d[df_d["mkb_class"] == cls]
        cls_name = sub["mkb_class_name"].iloc[0] if not sub.empty and pd.notna(sub["mkb_class_name"].iloc[0]) else ""
        diag_options.append(f"📁 Класс {cls} — {cls_name}")
        for _, row in sub.iterrows():
            lbl = f"   {row['mkb_code']} — {row['name']}" if pd.notna(row['mkb_code']) else f"   {row['name']}"
            diag_options.append(lbl)
            diag_map[lbl] = row['id']
    default_choices = [lbl for lbl in (default_labels or []) if lbl in diag_map]
    selected = st.multiselect(
        label,
        options=diag_options,
        default=default_choices,
        help="Выберите один или несколько диагнозов. 📁 — это классы МКБ-10",
        key=f"diag_multiselect_{key_suffix}"
    )
    selected_clean = [s for s in selected if not s.startswith("📁")]
    return [diag_map[lbl] for lbl in selected_clean if lbl in diag_map]

def get_injury_diagnosis_labels(injury_id):
    try:
        resp = supabase.table("injury_diagnoses").select(
            "diagnosis_id, dict_diagnoses(mkb_code, name)"
        ).eq("injury_id", injury_id).execute()
        if not resp.data:
            return []
        labels = []
        for row in resp.data:
            d = row.get("dict_diagnoses") or {}
            code = d.get("mkb_code") or ""
            name = d.get("name") or ""
            labels.append(f"   {code} — {name}" if code else f"   {name}")
        return labels
    except Exception:
        return []

def get_visit_diagnosis_labels(visit_id):
    try:
        resp = supabase.table("visit_diagnoses").select(
            "diagnosis_id, dict_diagnoses(mkb_code, name)"
        ).eq("visit_id", visit_id).execute()
        if not resp.data:
            return []
        labels = []
        for row in resp.data:
            d = row.get("dict_diagnoses") or {}
            code = d.get("mkb_code") or ""
            name = d.get("name") or ""
            labels.append(f"   {code} — {name}" if code else f"   {name}")
        return labels
    except Exception:
        return []

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
    r = supabase.table("dict_diagnoses").select(
        "id, mkb_code, name, mkb_class, mkb_class_name"
    ).order("mkb_class").order("mkb_code").execute()
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
def load_injury_diagnoses_map():
    r = supabase.table("injury_diagnoses").select(
        "injury_id, dict_diagnoses(mkb_code, name)"
    ).execute()
    result = {}
    if r.data:
        for row in r.data:
            iid = row["injury_id"]
            d = row.get("dict_diagnoses") or {}
            label = f"{d.get('mkb_code') or ''} — {d.get('name') or ''}".strip(" —")
            result.setdefault(iid, []).append(label)
        for iid in result:
            result[iid] = "; ".join(result[iid])
    return result

@st.cache_data(ttl=60)
def load_injuries(days=365):
    since = (date.today() - timedelta(days=days)).isoformat()
    r = supabase.table("injuries_and_illnesses").select(
        "*, athletes(full_name, jersey_number), dict_body_parts(name)"
    ).gte("incident_date", since).order("incident_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df["body_part"] = df["dict_body_parts"].apply(lambda x: x["name"] if x else None)
        df = df.drop(columns=["athletes", "dict_body_parts"])
        diag_map = load_injury_diagnoses_map()
        df["diagnosis"] = df["id"].apply(lambda iid: diag_map.get(iid, "—"))
    return df

@st.cache_data(ttl=60)
def load_injuries_all():
    r = supabase.table("injuries_and_illnesses").select(
        "*, athletes(full_name, jersey_number), dict_body_parts(name)"
    ).order("incident_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df["body_part"] = df["dict_body_parts"].apply(lambda x: x["name"] if x else None)
        df = df.drop(columns=["athletes", "dict_body_parts"])
        diag_map = load_injury_diagnoses_map()
        df["diagnosis"] = df["id"].apply(lambda iid: diag_map.get(iid, "—"))
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
        "*, athletes(full_name, jersey_number), dict_biomarkers(name, unit, reference_min, reference_max)"
    ).order("measurement_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df["biomarker_name"] = df["dict_biomarkers"].apply(lambda x: x["name"] if x else None)
        df["unit"] = df["dict_biomarkers"].apply(lambda x: x["unit"] if x else None)
        df["reference_min"] = df["dict_biomarkers"].apply(lambda x: x.get("reference_min") if x else None)
        df["reference_max"] = df["dict_biomarkers"].apply(lambda x: x.get("reference_max") if x else None)
        df = df.drop(columns=["athletes", "dict_biomarkers"])
    return df
def highlight_lab_results(row):
    """
    Возвращает стили для строки таблицы анализов:
    - синий шрифт, если значение ниже reference_min
    - красный шрифт, если значение выше reference_max
    """
    styles = [""] * len(row)
    
    try:
        # Находим индексы колонок "Значение", "reference_min", "reference_max"
        val_idx = row.index.get_loc("Значение") if "Значение" in row.index else None
        min_idx = row.index.get_loc("reference_min") if "reference_min" in row.index else None
        max_idx = row.index.get_loc("reference_max") if "reference_max" in row.index else None
        
        if val_idx is None or min_idx is None or max_idx is None:
            return styles
        
        value = row["Значение"]
        ref_min = row["reference_min"]
        ref_max = row["reference_max"]
        
        # Пропускаем, если значение пустое
        if pd.isna(value):
            return styles
        
        # Приводим к числу
        try:
            value = float(value)
        except (ValueError, TypeError):
            return styles
        
        # Подсветка
        if pd.notna(ref_min):
            try:
                if value < float(ref_min):
                    styles[val_idx] = "color: #0066cc; font-weight: bold;"  # синий
                    return styles
            except (ValueError, TypeError):
                pass
        
        if pd.notna(ref_max):
            try:
                if value > float(ref_max):
                    styles[val_idx] = "color: #cc0000; font-weight: bold;"  # красный
                    return styles
            except (ValueError, TypeError):
                pass
    except Exception:
        pass
    
    return styles
@st.cache_data(ttl=60)
def load_doctor_visits():
    r = supabase.table("doctor_visits").select(
        "*, athletes(full_name, jersey_number)"
    ).order("visit_date", desc=True).execute()
    df = pd.DataFrame(r.data)
    if not df.empty:
        df["full_name"] = df["athletes"].apply(lambda x: x["full_name"] if x else None)
        df["jersey_number"] = df["athletes"].apply(lambda x: x["jersey_number"] if x else None)
        df = df.drop(columns=["athletes"])
        vd_resp = supabase.table("visit_diagnoses").select(
            "visit_id, dict_diagnoses(mkb_code, name)"
        ).execute()
        diag_map = {}
        if vd_resp.data:
            for row in vd_resp.data:
                vid = row["visit_id"]
                d = row.get("dict_diagnoses") or {}
                label = f"{d.get('mkb_code') or ''} — {d.get('name') or ''}".strip(" —")
                diag_map.setdefault(vid, []).append(label)
        df["diagnosis"] = df["id"].apply(
            lambda vid: "; ".join(diag_map.get(vid, [])) if diag_map.get(vid) else None
        )
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
    tab_status, tab_dynamics, tab_my_card = st.tabs([
        "📊 Мой статус", "📈 Моя динамика", "🗂️ Моя карта"
    ])

    with tab_status:
        st.header("📊 Мой статус на сегодня")
        if df_athletes.empty or "id" not in df_athletes.columns:
            st.info("Нет данных о спортсменке.")
        else:
            my_row = df_athletes[df_athletes["id"] == user_athlete_id]
            my_jersey = int(my_row["jersey_number"].iloc[0]) if not my_row.empty and pd.notna(my_row["jersey_number"].iloc[0]) else None
            my_dashboard = df_dashboard[df_dashboard["№"] == my_jersey] if my_jersey and not df_dashboard.empty and "№" in df_dashboard.columns else pd.DataFrame()
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

    with tab_my_card:
        st.header("🗂️ Моя медицинская карта")
        st.caption("Здесь отображается вся ваша медицинская история. Данные только для просмотра.")

        row_me = df_athletes_full[df_athletes_full["id"] == user_athlete_id]
        if not row_me.empty:
            r = row_me.iloc[0]
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
                bt = r.get('blood_type')
                rh = r.get('rh_factor')
                blood_str = ""
                if pd.notna(bt) and str(bt) not in ["nan", "None", ""]:
                    blood_str = str(bt)
                if pd.notna(rh) and str(rh) not in ["nan", "None", ""]:
                    blood_str += " " + str(rh)
                if not blood_str:
                    blood_str = "—"
                st.markdown(f"**Группа крови:** {blood_str}")
                st.markdown(f"**Год начала занятий:** {int(r['handball_start_year']) if pd.notna(r.get('handball_start_year')) else '—'}")
            with c3:
                st.markdown(f"**Аллергии:** {r.get('allergies') or '—'}")
                ec = r.get('emergency_contact')
                ec_str = ec if pd.notna(ec) and str(ec) not in ["nan", "None", ""] else '—'
                st.markdown(f"**Экстренный контакт:** {ec_str}")

        st.divider()

        my_tabs = st.tabs([
            "🩺 Приёмы", "🏥 Осмотры", "🩹 Травмы", "💊 Лекарства",
            "💉 Прививки", "📏 Антропометрия", "🏃 Тесты",
            "🩺 Хроники", "🧪 Анализы"
        ])
        (my_visits, my_exams, my_injuries, my_meds,
         my_vacc, my_anthro, my_tests, my_chronic, my_lab) = my_tabs

        # --- Приёмы ---
        with my_visits:
            if not df_visits.empty and "athlete_id" in df_visits.columns:
                my = df_visits[df_visits["athlete_id"] == user_athlete_id]
            else:
                my = pd.DataFrame()
            if my.empty:
                st.info("Приёмов нет.")
            else:
                cols = ["visit_date", "complaints", "diagnosis", "prescriptions", "recommendations"]
                av = [c for c in cols if c in my.columns]
                d = format_dates(my[av].copy(), ["visit_date"])
                d = d.rename(columns={"visit_date": "Дата", "complaints": "Жалобы", "diagnosis": "Диагноз", "prescriptions": "Назначения", "recommendations": "Рекомендации"})
                st.dataframe(d, use_container_width=True, hide_index=True)

        # --- Осмотры ---
        with my_exams:
            if not df_all_exams.empty and "athlete_id" in df_all_exams.columns:
                my = df_all_exams[df_all_exams["athlete_id"] == user_athlete_id]
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

        # --- Травмы ---
        with my_injuries:
            if not df_injuries_all.empty and "athlete_id" in df_injuries_all.columns:
                my = df_injuries_all[df_injuries_all["athlete_id"] == user_athlete_id]
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
        with my_meds:
            if not df_meds_current.empty and "athlete_id" in df_meds_current.columns:
                my = df_meds_current[df_meds_current["athlete_id"] == user_athlete_id]
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
        with my_vacc:
            if not df_vaccinations.empty and "athlete_id" in df_vaccinations.columns:
                my = df_vaccinations[df_vaccinations["athlete_id"] == user_athlete_id]
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
        with my_anthro:
            if not df_anthro.empty and "athlete_id" in df_anthro.columns:
                my = df_anthro[df_anthro["athlete_id"] == user_athlete_id]
            else:
                my = pd.DataFrame()
            if my.empty:
                st.info("Измерений нет.")
            else:
                cols = ["measurement_date", "height", "weight", "bmi", "body_fat", "muscle_mass", "chest_circuit", "thigh_circuit"]
                av = [c for c in cols if c in my.columns]
                d = format_dates(my[av].copy(), ["measurement_date"])
                d = d.rename(columns={"measurement_date": "Дата", "height": "Рост", "weight": "Вес", "bmi": "ИМТ", "body_fat": "% жира", "muscle_mass": "Мышцы", "chest_circuit": "Грудь", "thigh_circuit": "Бедро"})
                st.dataframe(d, use_container_width=True, hide_index=True)

        # --- Тесты ---
        with my_tests:
            if not df_tests.empty and "athlete_id" in df_tests.columns:
                my = df_tests[df_tests["athlete_id"] == user_athlete_id]
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
        with my_chronic:
            if not df_chronic.empty and "athlete_id" in df_chronic.columns:
                my = df_chronic[df_chronic["athlete_id"] == user_athlete_id]
            else:
                my = pd.DataFrame()
            if my.empty:
                st.info("Хроник нет.")
            else:
                cols = ["diagnosis_date", "disease_name", "severity", "current_medication", "clinical_recommendations"]
                av = [c for c in cols if c in my.columns]
                d = format_dates(my[av].copy(), ["diagnosis_date"])
                d = d.rename(columns={"diagnosis_date": "Дата", "disease_name": "Заболевание", "severity": "Тяжесть", "current_medication": "Препараты", "clinical_recommendations": "Рекомендации"})
                st.dataframe(d, use_container_width=True, hide_index=True)

        # --- Анализы ---
        with my_lab:
            if not df_lab.empty and "athlete_id" in df_lab.columns:
                my = df_lab[df_lab["athlete_id"] == user_athlete_id]
            else:
                my = pd.DataFrame()
            if my.empty:
                st.info("Анализов нет.")
            else:
                cols = ["measurement_date", "biomarker_name", "value", "unit", "notes"]
                av = [c for c in cols if c in my.columns]
                d = format_dates(my[av].copy(), ["measurement_date"])
                d = d.rename(columns={"measurement_date": "Дата", "biomarker_name": "Показатель", "value": "Значение", "unit": "Ед.", "notes": "Примечание"})
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
                            bt = row.get('blood_type')
                            rh = row.get('rh_factor')
                            blood_str = ""
                            if pd.notna(bt) and str(bt) not in ["nan", "None", ""]:
                                blood_str = str(bt)
                            if pd.notna(rh) and str(rh) not in ["nan", "None", ""]:
                                blood_str += " " + str(rh)
                            if not blood_str:
                                blood_str = "—"
                            st.markdown(f"**Группа крови:** {blood_str}")
                            st.markdown(f"**Год начала занятий:** {int(row['handball_start_year']) if pd.notna(row.get('handball_start_year')) else '—'}")
                            ec = row.get('emergency_contact')
                            ecp = row.get('emergency_phone')
                            ec_str = ec if pd.notna(ec) and str(ec) not in ["nan", "None", ""] else '—'
                            ecp_str = ecp if pd.notna(ecp) and str(ecp) not in ["nan", "None", ""] else ''
                            st.markdown(f"**🚨 Экстренный контакт:** {ec_str} {ecp_str}".strip())
                        st.markdown(f"**⚠️ Аллергии:** {row.get('allergies') or '—'}")
                        st.markdown(f"**📝 Заметки врача:** {row.get('medical_notes') or '—'}")
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
                        bt = r.get('blood_type')
                        rh = r.get('rh_factor')
                        blood_str = ""
                        if pd.notna(bt) and str(bt) not in ["nan", "None", ""]:
                            blood_str = str(bt)
                        if pd.notna(rh) and str(rh) not in ["nan", "None", ""]:
                            blood_str += " " + str(rh)
                        if not blood_str:
                            blood_str = "—"
                        st.markdown(f"**Группа крови:** {blood_str}")
                        st.markdown(f"**Телефон:** {r.get('phone', '—')}")
                        st.markdown(f"**Год начала занятий:** {int(r['handball_start_year']) if pd.notna(r.get('handball_start_year')) else '—'}")
                    with c3:
                        st.markdown(f"**Аллергии:** {r.get('allergies') or '—'}")
                        ec = r.get('emergency_contact')
                        ecp = r.get('emergency_phone')
                        ec_str = ec if pd.notna(ec) and str(ec) not in ["nan", "None", ""] else '—'
                        ecp_str = ecp if pd.notna(ecp) and str(ecp) not in ["nan", "None", ""] else ''
                        st.markdown(f"**🚨 Экстренный контакт:** {ec_str} {ecp_str}".strip())

                st.divider()

                mc_tabs = st.tabs([
                    "🩺 Приёмы", "🏥 Осмотры", "🩹 Травмы", "💊 Лекарства",
                    "💉 Прививки", "📏 Антропометрия", "🏃 Тесты",
                    "🩺 Хроники", "🧪 Анализы"
                ])
                (mc_visits, mc_exams, mc_injuries, mc_meds,
                 mc_vacc, mc_anthro, mc_tests, mc_chronic, mc_lab) = mc_tabs

                # --- Приёмы ---
                with mc_visits:
                    if not df_visits.empty and "athlete_id" in df_visits.columns:
                        my = df_visits[df_visits["athlete_id"] == mc_aid]
                    else:
                        my = pd.DataFrame()
                    if my.empty:
                        st.info("Приёмов нет.")
                    else:
                        cols = ["visit_date", "complaints", "diagnosis", "prescriptions", "recommendations"]
                        av = [c for c in cols if c in my.columns]
                        d = format_dates(my[av].copy(), ["visit_date"])
                        d = d.rename(columns={"visit_date": "Дата", "complaints": "Жалобы", "diagnosis": "Диагноз", "prescriptions": "Назначения", "recommendations": "Рекомендации"})
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

                # --- Травмы ---
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
                        cols = ["diagnosis_date", "disease_name", "severity", "current_medication", "clinical_recommendations"]
                        av = [c for c in cols if c in my.columns]
                        d = format_dates(my[av].copy(), ["diagnosis_date"])
                        d = d.rename(columns={"diagnosis_date": "Дата", "disease_name": "Заболевание", "severity": "Тяжесть", "current_medication": "Препараты", "clinical_recommendations": "Рекомендации"})
                        st.dataframe(d, use_container_width=True, hide_index=True)

                # --- Анализы ---
                   # --- Анализы ---
                with mc_lab:
                    # === Таблица лабораторных показателей ===
                    if not df_lab.empty and "athlete_id" in df_lab.columns:
                        my = df_lab[df_lab["athlete_id"] == mc_aid]
                    else:
                        my = pd.DataFrame()
                    
                    if my.empty:
                        st.info("Лабораторных анализов нет.")
                    else:
                        cols = ["measurement_date", "biomarker_name", "value", "unit"]
                        av = [c for c in cols if c in my.columns]
                        d = format_dates(my[av].copy(), ["measurement_date"])
                        d = d.rename(columns={
                            "measurement_date": "Дата",
                            "biomarker_name": "Показатель",
                            "value": "Значение",
                            "unit": "Ед."
                        })
                        st.dataframe(d, use_container_width=True, hide_index=True)
                    
                    # === 📄 Прикреплённые документы (PDF) ===
                    st.divider()
                    st.subheader("📄 Прикреплённые документы")
                    
                    df_docs = load_athlete_documents(mc_aid)
                    
                    if df_docs.empty:
                        st.info("Сканы не прикреплены.")
                    else:
                        for _, doc in df_docs.iterrows():
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.markdown(
                                    f"**{doc['document_type']}** — "
                                    f"_{doc['file_name']}_ ({doc.get('upload_date', '')})"
                                )
                            with col2:
                                url = get_public_file_url(doc["file_path"])
                                if url:
                                    st.markdown(f"[📥 Открыть PDF]({url})")
                                else:
                                    st.write("—")

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
                    cols = ["visit_date", "jersey_number", "full_name", "complaints", "diagnosis", "prescriptions"]
                    av = [c for c in cols if c in df_visits.columns]
                    d = format_dates(df_visits[av].copy(), ["visit_date"])
                    d = d.rename(columns={
                        "visit_date": "Дата", "jersey_number": "№", "full_name": "ФИО",
                        "complaints": "Жалобы", "diagnosis": "Диагноз", "prescriptions": "Назначения"
                    })

                    event_v = st.dataframe(d, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)

                    st.divider()
                    st.subheader("👁️ Детальная информация о приёме")

                    visit_labels = []
                    for _, r in df_visits.iterrows():
                        vd = pd.to_datetime(r["visit_date"]).strftime('%d.%m.%Y') if pd.notna(r.get("visit_date")) else "—"
                        lbl = f"{vd} · №{int(r['jersey_number']) if pd.notna(r.get('jersey_number')) else '?'} · {r.get('full_name', '—')}"
                        visit_labels.append((lbl, r["id"]))

                    sel_lbl = None
                    if visit_labels:
                        sel_lbl = st.selectbox("Или выберите приём в списке",
                                                ["— не выбрано —"] + [l[0] for l in visit_labels],
                                                key="visit_view")

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

                                cur_visit_id = cur_v["id"]
                                cur_diag_labels = get_visit_diagnosis_labels(cur_visit_id)
                                selected_diag_ids = render_diagnosis_multiselect(
                                    label="Диагнозы (МКБ) — можно несколько",
                                    default_labels=cur_diag_labels,
                                    key_suffix=f"visit_edit_{edit_vid}"
                                )

                                diagnosis_text = st.text_input("Диагноз текстом", value=cur_v.get("diagnosis_text") or "")
                                prescriptions = st.text_area("Назначения", value=cur_v.get("prescriptions") or "", height=80)
                                recommendations = st.text_area("Рекомендации", value=cur_v.get("recommendations") or "", height=60)

                                if st.form_submit_button("💾 Сохранить", type="primary"):
                                    try:
                                        payload = {
                                            "athlete_id": opts_v[sel_a],
                                            "visit_date": vdate.isoformat(),
                                            "complaints": complaints.strip() or None,
                                            "examination": examination.strip() or None,
                                            "prescriptions": prescriptions.strip() or None,
                                            "recommendations": recommendations.strip() or None,
                                            "next_visit_date": nvdate.isoformat() if nvdate else None,
                                            "diagnosis_text": diagnosis_text.strip() or None
                                        }
                                        supabase.table("doctor_visits").update(payload).eq("id", edit_vid).execute()
                                        supabase.table("visit_diagnoses").delete().eq("visit_id", edit_vid).execute()
                                        for did in selected_diag_ids:
                                            supabase.table("visit_diagnoses").insert({
                                                "visit_id": edit_vid,
                                                "diagnosis_id": did
                                            }).execute()
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

                    selected_diag_ids = render_diagnosis_multiselect(
                        label="Диагнозы (МКБ) — можно несколько",
                        key_suffix="visit_new"
                    )
                    diagnosis_text = st.text_input("Диагноз текстом (если не в МКБ)")
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
                                "next_visit_date": nvdate.isoformat() if nvdate else None,
                                "diagnosis_text": diagnosis_text.strip() or None
                            }
                            resp = supabase.table("doctor_visits").insert(payload).execute()
                            if resp.data:
                                new_vid = resp.data[0]["id"]
                                for did in selected_diag_ids:
                                    supabase.table("visit_diagnoses").insert({
                                        "visit_id": new_vid,
                                        "diagnosis_id": did
                                    }).execute()
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

                    event_e = st.dataframe(d, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)

                    st.divider()
                    st.subheader("👁️ Детальная информация об осмотре")

                    exam_labels = []
                    for _, r in df_all_exams.head(50).iterrows():
                        ed = pd.to_datetime(r["examination_date"]).strftime('%d.%m.%Y') if pd.notna(r.get("examination_date")) else "—"
                        lbl = f"{ed} · №{int(r['jersey_number']) if pd.notna(r.get('jersey_number')) else '?'} · {r.get('exam_name', '—')}"
                        exam_labels.append((lbl, r["id"]))

                    sel_lbl = None
                    if exam_labels:
                        sel_lbl = st.selectbox("Или выберите осмотр в списке",
                                                ["— не выбрано —"] + [l[0] for l in exam_labels],
                                                key="exam_view")

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
                    ap = st.radio("Допуск? *", [True, False], format_func=lambda x: "✅ Да" if x else "❌ Нет", horizontal=True)
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

                    event_i = st.dataframe(d, on_select="rerun", selection_mode="single-row", use_container_width=True, hide_index=True)

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

                                cur_inj_id = cur_i["id"]
                                cur_diag_labels = get_injury_diagnosis_labels(cur_inj_id)
                                selected_diag_ids = render_diagnosis_multiselect(
                                    label="Диагнозы (МКБ) — можно несколько",
                                    default_labels=cur_diag_labels,
                                    key_suffix=f"inj_edit_{edit_iid}"
                                )

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
                                        payload["body_part_id"] = b_opts[sel_b] if sel_b != "— не указана —" else None
                                        supabase.table("injuries_and_illnesses").update(payload).eq("id", edit_iid).execute()
                                        supabase.table("injury_diagnoses").delete().eq("injury_id", edit_iid).execute()
                                        for did in selected_diag_ids:
                                            supabase.table("injury_diagnoses").insert({
                                                "injury_id": edit_iid,
                                                "diagnosis_id": did
                                            }).execute()
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

                    selected_diag_ids = render_diagnosis_multiselect(
                        label="Диагнозы (МКБ) — можно несколько",
                        key_suffix="inj_new"
                    )

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
                            if sel_b != "— не указана —":
                                payload["body_part_id"] = bopts[sel_b]
                            resp = supabase.table("injuries_and_illnesses").insert(payload).execute()
                            if resp.data:
                                new_inj_id = resp.data[0]["id"]
                                for did in selected_diag_ids:
                                    supabase.table("injury_diagnoses").insert({
                                        "injury_id": new_inj_id,
                                        "diagnosis_id": did
                                    }).execute()
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
                    st.dataframe(d, use_container_width=True, hide_index=True)

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
                    st.dataframe(d, use_container_width=True, hide_index=True)
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
                    st.dataframe(d, use_container_width=True, hide_index=True)
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
                    st.dataframe(d, use_container_width=True, hide_index=True)
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
                    st.dataframe(d, use_container_width=True, hide_index=True)
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
                    st.dataframe(d, use_container_width=True, hide_index=True)
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
