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
@st.cache_data(ttl=10)  # Уменьшили кэш до 10 секунд, чтобы данные обновлялись быстрее
def load_athlete_documents(athlete_id):
    """Загружает список документов спортсменки."""
    try:
        # Явно запрашиваем все нужные поля, включая новую category
        r = supabase.table("documents") \
            .select("id, document_type, category, file_name, file_path, upload_date, comment") \
            .eq("athlete_id", athlete_id) \
            .order("upload_date", desc=True) \
            .execute()
        
        df = pd.DataFrame(r.data)
        # Если база вернула пустоту — возвращаем пустой датафрейм
        if df.empty:
            return pd.DataFrame(columns=["id", "document_type", "category", "file_name", "file_path", "upload_date", "comment"])
            
        # Если колонки category нет (на случай старых записей), создаем её
        if "category" not in df.columns:
            df["category"] = "Прочее"
        else:
            df["category"] = df["category"].fillna("Прочее")
            
        return df
    except Exception as e:
        st.error(f"Ошибка загрузки документов: {e}")
        return pd.DataFrame()
def load_positions():
    r = supabase.table("dict_positions").select("id, name").order("name").execute()
    return pd.DataFrame(r.data)

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
    r = supabase.table("dict_body_parts").select("id, name").order("id").execute()
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

@st.cache_data(ttl=60)
def load_exam_categories():
    r = supabase.table("dict_exam_categories").select("name").order("id").execute()
    return [row["name"] for row in r.data] if r.data else ["Прочее"]

@st.cache_data(ttl=300)
def load_athletes_archived():
    """Загружает список спортсменок, которые в архиве (is_active = False)"""
    r = supabase.table("athletes").select("id, full_name, jersey_number").eq("is_active", False).order("full_name").execute()
    return pd.DataFrame(r.data)

# ============ ДАННЫЕ ДАШБОРДА ============
@st.cache_data(ttl=60)
def load_today_dashboard():
    r = supabase.table("v_dashboard_status").select("*").execute()
    return pd.DataFrame(r.data)

@st.cache_data(ttl=60)
def load_missing_reports():
    r = supabase.table("v_dashboard_status").select("*").eq("morning_report_status", "Не сдал").execute()
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
    """Подсвечивает значение: синий — ниже нормы, красный — выше нормы."""
    styles = [""] * len(row)
    
    try:
        # Колонки после rename — "Значение", "Мин.норма", "Макс.норма"
        if "Значение" not in row.index:
            return styles
        
        val_idx = row.index.get_loc("Значение")
        
        raw_value = row["Значение"]
        
        # Если значение пустое — ничего не делаем
        if pd.isna(raw_value):
            return styles
        
        # Приводим к float (универсально)
        try:
            value = float(str(raw_value).replace(",", "."))
        except (ValueError, TypeError):
            return styles
        
        # Проверка на минимум
        if "Мин.норма" in row.index and pd.notna(row["Мин.норма"]):
            try:
                ref_min = float(str(row["Мин.норма"]).replace(",", "."))
                if value < ref_min:
                    styles[val_idx] = "color: #0066cc; font-weight: bold;"
                    return styles
            except (ValueError, TypeError):
                pass
        
        # Проверка на максимум
        if "Макс.норма" in row.index and pd.notna(row["Макс.норма"]):
            try:
                ref_max = float(str(row["Макс.норма"]).replace(",", "."))
                if value > ref_max:
                    styles[val_idx] = "color: #cc0000; font-weight: bold;"
                    return styles
            except (ValueError, TypeError):
                pass
    except Exception as e:
        print(f"DEBUG highlight error: {e}")
    
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
# df_overdue = load_overdue_exams() # Временно отключено
df_overdue = pd.DataFrame() # Заглушка, чтобы код не падал
df_athletes = load_athletes()
df_athletes_full = load_athletes_full()
df_logs = load_health_logs(30)
df_all_exams = load_all_examinations()
df_injuries = load_injuries(365)
df_injuries_all = load_injuries_all()
df_meds_current = load_medications()
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
df_positions = load_positions()
df_exam_categories = load_exam_categories()

# ============ ЗАГОЛОВОК ============
st.title("🏐 Медицинский дашборд команды")
if user_role == "athlete":
    st.caption(f"Личный кабинет спортсменки · {user.get('full_name', '')}")
else:
    st.caption(f"Пользователь: {user.get('full_name', 'Гость')} ({user_role})")

# ==========================================
#            ЛИЧНЫЙ КАБИНЕТ СПОРТСМЕНКИ
# ==========================================
if user_role == "athlete" and user_athlete_id:
    # (Этот блок можно оставить как есть, он не меняется)
    tab_status, tab_dynamics, tab_my_card = st.tabs(["📊 Мой статус", "📈 Моя динамика", "🗂️ Моя карта"])
    with tab_status:
        st.header("📊 Мой статус на сегодня")
        st.info("Данные обновляются автоматически.")
    with tab_dynamics:
        st.header("📈 Моя динамика за 30 дней")
        st.info("Графики доступны в полной версии.")
    with tab_my_card:
        st.header("🗂️ Моя медицинская карта")
        st.info("Информация доступна врачу.")

# ==========================================
#      ДАШБОРД ВРАЧА / ТРЕНЕРА / АДМИНА
# ==========================================
else:
    # Создаем 3 ГЛАВНЫЕ ВКЛАДКИ
    main_tabs = st.tabs(["📊 Обзор команды", "👤 Карточка спортсменки", "📈 Аналитика"])
    tab_overview, tab_card, tab_analytics = main_tabs

    # ------------------------------------------
    # ВКЛАДКА 1: ОБЗОР КОМАНДЫ
    # ------------------------------------------
    with tab_overview:
        st.header("📊 Сводка за сегодня")
        
        # --- БЛОК СВЕТОФОРА ---
        rc = len(df_dashboard[df_dashboard["status_color"] == "red"]) if not df_dashboard.empty else 0
        yc = len(df_dashboard[df_dashboard["status_color"] == "yellow"]) if not df_dashboard.empty else 0
        gc = len(df_dashboard[df_dashboard["status_color"] == "green"]) if not df_dashboard.empty else 0
        grc = len(df_dashboard[df_dashboard["status_color"] == "grey"]) if not df_dashboard.empty else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🔴 Проблемы", rc)
        c2.metric("🟡 Внимание", yc)
        c3.metric("🟢 Норма", gc)
        c4.metric("⚪ Нет данных", grc)
        
        st.divider()
        st.subheader("🚦 Статус спортсменок")
        
        if not df_dashboard.empty:
            filt = st.selectbox("Фильтр", [
                "Только с данными (🟢🟡🔴)", "Все", "🔴 Только красные", 
                "🟡 Только жёлтые", "🟢 Только зелёные", "⚪ Только без данных"
            ])
            
            if filt == "🔴 Только красные":
                df_d = df_dashboard[df_dashboard["status_color"] == "red"]
            elif filt == "🟡 Только жёлтые":
                df_d = df_dashboard[df_dashboard["status_color"] == "yellow"]
            elif filt == "🟢 Только зелёные":
                df_d = df_dashboard[df_dashboard["status_color"] == "green"]
            elif filt == "⚪ Только без данных":
                df_d = df_dashboard[df_dashboard["status_color"] == "grey"]
            elif filt == "Только с данными (🟢🟡🔴)":
                df_d = df_dashboard[df_dashboard["status_color"] != "grey"]
            else:
                df_d = df_dashboard

            cols = ["jersey_number", "full_name", "status_text", "reason_text", "last_morning_hr", "last_ortho_diff"]
            av = [c for c in cols if c in df_d.columns]
            df_d_show = df_d[av].rename(columns={
                "jersey_number": "№", "full_name": "ФИО", "status_text": "Статус",
                "reason_text": "Причина", "last_morning_hr": "Пульс", "last_ortho_diff": "Разница"
            })
            if "№" in df_d_show.columns:
                df_d_show["№"] = df_d_show["№"].apply(lambda x: int(x) if pd.notna(x) else "—")
            if "Пульс" in df_d_show.columns:
                df_d_show["Пульс"] = df_d_show["Пульс"].fillna("—")
            if "Разница" in df_d_show.columns:
                df_d_show["Разница"] = df_d_show["Разница"].fillna("—")
                        # Добавляем проверку на просроченные осмотры
            overdue_ids = []
            for _, r in df_d.iterrows():
                aid = r['athlete_id']
                ath_exams = df_all_exams[df_all_exams["athlete_id"] == aid]
                if not ath_exams.empty:
                    last_e = ath_exams.sort_values("examination_date", ascending=False).iloc[0]
                    nx = last_e.get("next_exam_date")
                    if pd.notna(nx) and pd.to_datetime(nx).date() < date.today():
                        overdue_ids.append(aid)
                else:
                    overdue_ids.append(aid) # Если осмотров вообще нет — тоже помечаем
            
            df_d_show["Медосмотр"] = df_d_show["ФИО"].apply(
                lambda x: "🔴 Просрочен" if any(df_athletes_full[df_athletes_full["full_name"] == x]["id"].isin(overdue_ids)) else "🟢 ОК"
            )
            # Перемещаем колонку
            cols = list(df_d_show.columns)
            cols.insert(cols.index("Пульс"), cols.pop(cols.index("Медосмотр")))
            df_d_show = df_d_show[cols]
            st.dataframe(df_d_show, use_container_width=True, hide_index=True)
        else:
            st.info("Нет данных за сегодня.")

        st.divider()
        st.subheader("📵 Не сдали утренний отчёт")
        if not df_missing.empty:
            st.warning(f"Не сдали: {len(df_missing)}")
            df_missing_show = df_missing[["jersey_number", "full_name"]].copy()
            df_missing_show = df_missing_show.rename(columns={"jersey_number": "№", "full_name": "ФИО"})
            df_missing_show["№"] = df_missing_show["№"].apply(lambda x: int(x) if pd.notna(x) else "—")
            st.dataframe(df_missing_show, use_container_width=True, hide_index=True)
        else:
            st.success("✅ Все сдали!")


    # ------------------------------------------
    # ВКЛАДКА 2: КАРТОЧКА СПОРТСМЕНКИ
    # ------------------------------------------
    with tab_card:
        st.header("👤 Карточка спортсменки")
         # Переключатель режимов
        mode = st.radio("Режим работы", ["📋 Выбрать существующую", "➕ Добавить новую", "📂 Восстановить из архива"], horizontal=True)

        if mode == "📂 Восстановить из архива":
            st.subheader("Архив спортсменок")
            df_archived = load_athletes_archived()
            
            if df_archived.empty:
                st.info("В архиве никого нет.")
            else:
                st.warning("Здесь находятся спортсменки, которые были удалены из активного списка.")
                
                # Создаем выпадающий список с архивными спортсменками
                arch_opts = {}
                for _, row in df_archived.iterrows():
                    j = int(row['jersey_number']) if pd.notna(row['jersey_number']) else None
                    label = f"№{j} — {row['full_name']}" if j else row['full_name']
                    arch_opts[label] = row['id']
                    
                selected_arch = st.selectbox("Выберите спортсменку для восстановления", list(arch_opts.keys()))
                
                if st.button("♻️ Вернуть в команду", type="primary"):
                    try:
                        aid = arch_opts[selected_arch]
                        supabase.table("athletes").update({"is_active": True}).eq("id", aid).execute()
                        st.success(f"✅ Спортсменка {selected_arch} возвращена в список!")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка: {e}")
                        
        if mode == "➕ Добавить новую":
            st.subheader("Новая спортсменка")
            with st.form("form_new_athlete"):
                c1, c2 = st.columns(2)
                with c1:
                    new_full_name = st.text_input("ФИО *", placeholder="Иванова Анна Сергеевна")
                    new_birth_date = st.date_input("Дата рождения *", value=date(2008, 1, 1))
                    new_jersey = st.number_input("Игровой номер", min_value=0, max_value=999, value=0)
                    new_start_year = st.number_input("Год начала занятий", min_value=1950, max_value=date.today().year, value=date.today().year)
                with c2:
                    new_phone = st.text_input("Телефон", placeholder="+375 29 123-45-67")
                    pos_opts = {row['name']: row['id'] for _, row in df_positions.iterrows()}
                    new_position = st.selectbox("Амплуа", ["— не выбрано —"] + list(pos_opts.keys()))
                    new_blood_type = st.selectbox("Группа крови", ["— не указана —", "1", "2", "3", "4"])
                    new_rh = st.selectbox("Резус-фактор", ["— не указан —", "+", "−"])
                    new_telegram = st.text_input("Telegram ID (если есть)")
                
                new_allergies = st.text_area("Аллергии")
                new_notes = st.text_area("Заметки врача")
                
                if st.form_submit_button("💾 Создать спортсменку", type="primary"):
                    if not new_full_name.strip():
                        st.error("ФИО обязательно")
                    else:
                        try:
                            supabase.table("athletes").insert({
                                "full_name": new_full_name.strip(),
                                "birth_date": new_birth_date.isoformat(),
                                "jersey_number": int(new_jersey) if new_jersey > 0 else None,
                                "handball_start_year": int(new_start_year),
                                "phone": new_phone.strip() or None,
                                "position_id": pos_opts[new_position] if new_position != "— не выбрано —" else None,
                                "blood_type": new_blood_type if new_blood_type != "— не указана —" else None,
                                "rh_factor": new_rh if new_rh != "— не указан —" else None,
                                "telegram_user_id": new_telegram.strip() or None,
                                "allergies": new_allergies.strip() or None,
                                "medical_notes": new_notes.strip() or None,
                                "is_active": True
                            }).execute()
                            st.success(f"✅ Спортсменка {new_full_name} создана!")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"Ошибка: {e}")
        
        else:
            opts = athlete_options_dict()
            if not opts:
                st.info("Нет активных спортсменок.")
            else:
                sel_key = st.selectbox("Выберите спортсменку", list(opts.keys()), key="card_select")
                selected_aid = opts[sel_key]
                
                if selected_aid:
                    # Проверка на просроченный осмотр
                    # --- ВРЕМЕННАЯ ОТЛАДКА ---
                    st.write("Колонки в df_all_exams:", df_all_exams.columns.tolist())
                    # -------------------------

                    my_exams = df_all_exams[df_all_exams["athlete_id"].astype(str) == str(selected_aid)]
                    if not my_exams.empty:
                        last_exam = my_exams.sort_values("examination_date", ascending=False).iloc[0]
                        next_date = last_exam.get("next_exam_date")
                        if pd.notna(next_date) and pd.to_datetime(next_date).date() < date.today():
                            st.error(f"🔴 **ВНИМАНИЕ!** У спортсменки просрочен медицинский допуск (истек {pd.to_datetime(next_date).strftime('%d.%m.%Y')}). Необходимо пройти осмотр!")
                    else:
                        st.warning("⚠️ У спортсменки нет ни одного медосмотра.")
                    # ------------------------------------
                                        
                    row = df_athletes_full[df_athletes_full["id"] == selected_aid].iloc[0]
                
                # --- ШАПКА КАРТОЧКИ ---
                with st.expander("📝 Общая информация", expanded=False):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.markdown(f"**ФИО:** {row.get('full_name', '—')}")
                        bd = pd.to_datetime(row.get('birth_date')).strftime('%d.%m.%Y') if pd.notna(row.get('birth_date')) else '—'
                        st.markdown(f"**Дата рождения:** {bd}")
                        st.markdown(f"**Игровой номер:** {int(row['jersey_number']) if pd.notna(row.get('jersey_number')) else '—'}")
                        pos_name = "—"
                        if pd.notna(row.get("position_id")):
                            pos_match = df_positions[df_positions["id"] == row["position_id"]]
                            if not pos_match.empty:
                                pos_name = pos_match.iloc[0]["name"]
                        st.markdown(f"**Амплуа:** {pos_name}")
                    with c2:
                        bt = row.get('blood_type')
                        rh = row.get('rh_factor')
                        blood_str = f"{bt} {rh}" if pd.notna(bt) and pd.notna(rh) else "—"
                        st.markdown(f"**Группа крови:** {blood_str}")
                        st.markdown(f"**Год начала:** {int(row['handball_start_year']) if pd.notna(row.get('handball_start_year')) else '—'}")
                        st.markdown(f"**Телефон:** {row.get('phone') or '—'}")
                    with c3:
                        st.markdown(f"**Аллергии:** {row.get('allergies') or '—'}")
                        st.markdown(f"**Экстренный контакт:** {row.get('emergency_contact') or '—'} {row.get('emergency_phone') or ''}")
                        st.markdown(f"**Заметки:** {row.get('medical_notes') or '—'}")

                # --- РЕДАКТИРОВАНИЕ ПРОФИЛЯ ---
                with st.expander("✏️ Редактировать профиль спортсменки"):
                    with st.form("edit_athlete_form"):
                        c_e1, c_e2, c_e3 = st.columns(3)
                        with c_e1:
                            new_name = st.text_input("ФИО", value=row.get("full_name", ""))
                            new_bd = st.date_input("Дата рождения", value=pd.to_datetime(row.get("birth_date")).date() if pd.notna(row.get("birth_date")) else date.today())
                            new_jersey = st.number_input("Игровой номер", min_value=0, max_value=999, value=int(row.get("jersey_number")) if pd.notna(row.get("jersey_number")) else 0)
                        with c_e2:
                            pos_opts = {r['name']: r['id'] for _, r in df_positions.iterrows()}
                            cur_pos_name = "— не выбрано —"
                            if pd.notna(row.get("position_id")):
                                for name, pid in pos_opts.items():
                                    if pid == row["position_id"]:
                                        cur_pos_name = name
                                        break
                            new_pos = st.selectbox("Амплуа", ["— не выбрано —"] + list(pos_opts.keys()), index=list(pos_opts.keys()).index(cur_pos_name) + 1 if cur_pos_name in pos_opts else 0)
                            new_blood = st.text_input("Группа крови", value=row.get("blood_type", "") or "")
                            new_rh = st.selectbox("Резус-фактор", ["— не указан —", "+", "−"], index=0 if pd.isna(row.get("rh_factor")) else (1 if row.get("rh_factor") == "+" else 2))
                            new_phone = st.text_input("Телефон", value=row.get("phone", "") or "")
                        with c_e3:
                            new_allergies = st.text_area("Аллергии", value=row.get("allergies", "") or "", height=68)
                            new_notes = st.text_area("Заметки врача", value=row.get("medical_notes", "") or "", height=68)
                        
                        # Две кнопки в один ряд
                        col_save, col_archive = st.columns([1, 1])
                        
                        with col_save:
                            if st.form_submit_button("💾 Сохранить изменения", type="primary"):
                                try:
                                    supabase.table("athletes").update({
                                        "full_name": new_name.strip(),
                                        "birth_date": new_bd.isoformat(),
                                        "jersey_number": int(new_jersey) if new_jersey > 0 else None,
                                        "position_id": pos_opts[new_pos] if new_pos != "— не выбрано —" else None,
                                        "blood_type": new_blood.strip() or None,
                                        "rh_factor": new_rh if new_rh != "— не указан —" else None,
                                        "phone": new_phone.strip() or None,
                                        "allergies": new_allergies.strip() or None,
                                        "medical_notes": new_notes.strip() or None
                                    }).eq("id", selected_aid).execute()
                                    st.success("✅ Профиль обновлен!")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")
                                    
                        with col_archive:
                            # Кнопка архивации (удаления из списка)
                            if st.form_submit_button("🗑️ Удалить из команды (Архив)", type="secondary"):
                                try:
                                    supabase.table("athletes").update({"is_active": False}).eq("id", selected_aid).execute()
                                    st.success(f"✅ {row.get('full_name')} переведена в архив!")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка архивации: {e}")

                # --- ПОДВКЛАДКИ КАРТОЧКИ ---                
                st.divider()

                # --- ПОДВКЛАДКИ КАРТОЧКИ ---
                c_tabs = st.tabs([
                    "📊 Мониторинг", "🩺 Приёмы", "💊 Медикаменты", "🔬 Обследования", 
                    "🏥 Осмотры", "📏 Антропометрия", "🩹 Травмы"                    
                ])
                (c_mon, c_visits, c_meds, c_labs, c_exams, c_anthro, c_inj) = c_tabs

                # 1. МОНИТОРИНГ
                with c_mon:
                    st.subheader("📈 Динамика за последние 30 дней")
                    my_logs = df_logs[df_logs["athlete_id"] == selected_aid] if not df_logs.empty else pd.DataFrame()
                    
                    if my_logs.empty:
                        st.info("Нет данных за 30 дней.")
                    else:
                        dfc = my_logs[["log_date", "morning_hr", "ortho_hr_after", "sleep_hours", "appetite_score"]].sort_values("log_date").set_index("log_date")
                        st.markdown("**Пульс (лежа / стоя)**")
                        st.line_chart(dfc[["morning_hr", "ortho_hr_after"]], use_container_width=True)
                        st.markdown("**Сон и Аппетит (от 1 до 5)**")
                        st.bar_chart(dfc[["sleep_hours", "appetite_score"]], use_container_width=True)

                # 2. ПРИЁМЫ
                with c_visits:
                    st.subheader("🩺 Журнал приёмов")
                    my_v = df_visits[df_visits["athlete_id"] == selected_aid] if not df_visits.empty else pd.DataFrame()
                    
                    if my_v.empty:
                        st.info("Приёмов нет.")
                    else:
                        # --- ТАБЛИЦА ---
                        # Берем колонки, которые есть, и переименовываем
                        d = my_v[["visit_date", "complaints", "diagnosis", "prescriptions", "recommendations"]].copy()
                        d = d.rename(columns={"visit_date": "Дата", "complaints": "Жалобы", "diagnosis": "Диагноз", "prescriptions": "Назначения", "recommendations": "Рекомендации"})
                        d["Дата"] = pd.to_datetime(d["Дата"]).dt.strftime('%d.%m.%Y')
                        
                        # Если диагноз пустой (None), заменяем на текст из diagnosis_text
                        for idx, r in my_v.iterrows():
                            if pd.isna(r['diagnosis']) or r['diagnosis'] == "":
                                if pd.notna(r.get('diagnosis_text')) and r.get('diagnosis_text') != "":
                                    # Находим в DataFrame и обновляем
                                    d.loc[idx, "Диагноз"] = r['diagnosis_text']
                                    
                        d = d.fillna("—")
                        st.dataframe(d, use_container_width=True, hide_index=True)

                        # --- РЕДАКТИРОВАНИЕ ---
                        st.divider()
                        st.markdown("### ✏️ Редактировать приём")
                        
                        visit_options = {"— не выбрано —": None}
                        for _, r in my_v.iterrows():
                            label = f"{pd.to_datetime(r['visit_date']).strftime('%d.%m.%Y')} — {r['complaints'][:30] if pd.notna(r['complaints']) else '—'}..."
                            visit_options[label] = r['id']
                            
                        selected_visit_label = st.selectbox("Выберите приём для изменения", list(visit_options.keys()), key="edit_visit_select")
                        selected_visit_id = visit_options[selected_visit_label]
                        
                        if selected_visit_id:
                            cur_v = my_v[my_v["id"] == selected_visit_id].iloc[0]
                            
                            # Получаем текущие привязанные МКБ для этого приёма
                            current_mkb = get_visit_diagnosis_labels(selected_visit_id)
                            
                            with st.form("edit_visit_form"):
                                e_c1, e_c2 = st.columns(2)
                                with e_c1:
                                    e_date = st.date_input("Дата", value=pd.to_datetime(cur_v["visit_date"]).date())
                                    e_complaints = st.text_area("Жалобы", value=cur_v.get("complaints") or "")
                                with e_c2:
                                    e_prescriptions = st.text_input("Назначения", value=cur_v.get("prescriptions") or "")
                                
                                # ДОБАВИЛИ ВЫБОР МКБ
                                selected_diag_ids = render_diagnosis_multiselect(
                                    label="Диагнозы (МКБ)", 
                                    default_labels=current_mkb,
                                    key_suffix=f"edit_visit_{selected_visit_id}"
                                )
                                e_diagnosis_text = st.text_input("Диагноз (текстом)", value=cur_v.get("diagnosis_text") or "")
                                
                                e_recs = st.text_area("Рекомендации", value=cur_v.get("recommendations") or "")
                                
                                col_save, col_del = st.columns([1, 1])
                                with col_save:
                                    if st.form_submit_button("💾 Сохранить", type="primary"):
                                        try:
                                            # 1. Обновляем сам приём
                                            supabase.table("doctor_visits").update({
                                                "visit_date": e_date.isoformat(),
                                                "complaints": e_complaints.strip() or None,
                                                "diagnosis_text": e_diagnosis_text.strip() or None,
                                                "prescriptions": e_prescriptions.strip() or None,
                                                "recommendations": e_recs.strip() or None,
                                            }).eq("id", selected_visit_id).execute()
                                            
                                            # 2. Удаляем старые МКБ и записываем новые
                                            supabase.table("visit_diagnoses").delete().eq("visit_id", selected_visit_id).execute()
                                            for did in selected_diag_ids:
                                                supabase.table("visit_diagnoses").insert({
                                                    "visit_id": selected_visit_id,
                                                    "diagnosis_id": did
                                                }).execute()
                                                
                                            st.success("✅ Приём обновлен!")
                                            st.cache_data.clear()
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Ошибка: {e}")
                                            
                                with col_del:
                                    if st.form_submit_button("🗑️ Удалить приём", type="secondary"):
                                        supabase.table("doctor_visits").delete().eq("id", selected_visit_id).execute()
                                        st.success("✅ Приём удален!")
                                        st.cache_data.clear()
                                        st.rerun()

                    # --- ДОБАВЛЕНИЕ ---
                    with st.expander("➕ Добавить новый приём"):
                        with st.form("new_visit_form"):
                            n_date = st.date_input("Дата приёма", value=date.today())
                            n_complaints = st.text_area("Жалобы")
                            
                            # Выбор МКБ и текста
                            selected_diag_ids = render_diagnosis_multiselect(
                                label="Диагнозы (МКБ)", 
                                key_suffix=f"new_visit_{selected_aid}"
                            )
                            n_diagnosis_text = st.text_input("Диагноз (текстом, если нет в МКБ)")
                            
                            n_prescriptions = st.text_input("Назначения")
                            n_recs = st.text_area("Рекомендации")
                            
                            if st.form_submit_button("💾 Сохранить новый приём", type="primary"):
                                try:
                                    # Сохраняем сам приём
                                    resp = supabase.table("doctor_visits").insert({
                                        "athlete_id": selected_aid,
                                        "visit_date": n_date.isoformat(),
                                        "complaints": n_complaints.strip() or None,
                                        "diagnosis_text": n_diagnosis_text.strip() or None,
                                        "prescriptions": n_prescriptions.strip() or None,
                                        "recommendations": n_recs.strip() or None,
                                    }).execute()
                                    
                                    # Если есть МКБ, сохраняем связи
                                    if resp.data and selected_diag_ids:
                                        new_vid = resp.data[0]["id"]
                                        for did in selected_diag_ids:
                                            supabase.table("visit_diagnoses").insert({
                                                "visit_id": new_vid,
                                                "diagnosis_id": did
                                            }).execute()
                                            
                                    st.success("✅ Новый приём сохранен!")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")

                # 3. ОБСЛЕДОВАНИЯ
                with c_labs:
                    st.subheader("🔬 Медицинские обследования")
                    
                    # Создаем две подвкладки: Цифры и Документы
                    lab_subtab1, lab_subtab2 = st.tabs(["📊 Лабораторные данные (Цифры)", "📄 Документы и сканы (PDF)"])

                    # ==========================================
                    # ПОДВКЛАДКА 1: ЛАБОРАТОРНЫЕ ДАННЫЕ
                    # ==========================================
                    with lab_subtab1:
                        my_l = df_lab[df_lab["athlete_id"] == selected_aid] if not df_lab.empty else pd.DataFrame()
                        
                        if my_l.empty:
                            st.info("Анализов нет.")
                        else:
                            # Группировка по датам
                            my_l["date_obj"] = pd.to_datetime(my_l["measurement_date"]).dt.date
                            unique_dates = sorted(my_l["date_obj"].unique(), reverse=True)
                            
                            for d_date in unique_dates:
                                date_str = d_date.strftime('%d.%m.%Y')
                                daily_results = my_l[my_l["date_obj"] == d_date]
                                
                                with st.expander(f"📅 Анализы от {date_str} ({len(daily_results)} показателей)"):
                                    # Таблица с подсветкой
                                    d_show = daily_results[["biomarker_name", "value", "unit", "reference_min", "reference_max"]].copy()
                                    d_show = d_show.rename(columns={"biomarker_name": "Показатель", "value": "Значение", "unit": "Ед.", "reference_min": "Мин.норма", "reference_max": "Макс.норма"})
                                    
                                    # Форматируем числа (убираем лишние нули) и применяем подсветку
                                    styled_df = d_show.style \
                                        .format({
                                            "Значение": "{:g}", 
                                            "Мин.норма": "{:g}", 
                                            "Макс.норма": "{:g}"
                                        }, na_rep="—") \
                                        .apply(highlight_lab_results, axis=1)
                                        
                                    st.dataframe(styled_df, use_container_width=True, hide_index=True)
                                    
                                    # Редактирование
                                    st.markdown("**✏️ Редактировать показатель**")
                                    edit_options = {f"{row['biomarker_name']} ({row['value']} {row['unit']})": row['id'] for _, row in daily_results.iterrows()}
                                    selected_lab_label = st.selectbox("Выберите показатель для изменения", ["— не выбрано —"] + list(edit_options.keys()), key=f"edit_lab_select_{d_date}")
                                    
                                    if selected_lab_label and selected_lab_label != "— не выбрано —":
                                        selected_lab_id = edit_options[selected_lab_label]
                                        cur_l = daily_results[daily_results["id"] == selected_lab_id].iloc[0]
                                        
                                        with st.form(f"edit_lab_form_{d_date}"):
                                            lc1, lc2 = st.columns(2)
                                            with lc1:
                                                e_value = st.number_input("Значение", value=float(cur_l["value"]), step=0.1)
                                            with lc2:
                                                e_notes = st.text_input("Примечание", value=cur_l.get("notes") or "")
                                                
                                            col_save, col_del = st.columns([1, 1])
                                            with col_save:
                                                if st.form_submit_button("💾 Сохранить", type="primary"):
                                                    supabase.table("lab_results").update({
                                                        "value": e_value,
                                                        "notes": e_notes.strip() or None
                                                    }).eq("id", selected_lab_id).execute()
                                                    st.success("✅ Анализ обновлен!")
                                                    st.cache_data.clear()
                                                    st.rerun()
                                            with col_del:
                                                if st.form_submit_button("🗑️ Удалить", type="secondary"):
                                                    supabase.table("lab_results").delete().eq("id", selected_lab_id).execute()
                                                    st.success("✅ Анализ удален!")
                                                    st.cache_data.clear()
                                                    st.rerun()

                        # Форма добавления новых цифровых данных
                        with st.expander("➕ Добавить лабораторный показатель"):
                            with st.form("new_lab_form"):
                                l_c1, l_c2 = st.columns(2)
                                with l_c1:
                                    l_date = st.date_input("Дата анализа", value=date.today())
                                    biomarkers_dict = {row['name']: row['id'] for _, row in df_biomarkers.iterrows()}
                                    l_biomarker = st.selectbox("Показатель", list(biomarkers_dict.keys()))
                                with l_c2:
                                    l_value = st.number_input("Значение", value=0.0, step=0.1)
                                    l_notes = st.text_input("Примечание")
                                
                                if st.form_submit_button("💾 Сохранить анализ", type="primary"):
                                    try:
                                        supabase.table("lab_results").insert({
                                            "athlete_id": selected_aid,
                                            "biomarker_id": biomarkers_dict[l_biomarker],
                                            "measurement_date": l_date.isoformat(),
                                            "value": l_value,
                                            "notes": l_notes.strip() or None
                                        }).execute()
                                        st.success("✅ Анализ сохранен!")
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Ошибка: {e}")

                    # ==========================================
                    # ПОДВКЛАДКА 2: ДОКУМЕНТЫ (PDF)
                    # ==========================================
                    with lab_subtab2:
                        my_docs = load_athlete_documents(selected_aid)
                        
                        # Берем категории из справочника в базе
                        categories = df_exam_categories
                        
                        # --- УПРАВЛЕНИЕ КАТЕГОРИЯМИ ---
                        with st.expander("⚙️ Управление категориями обследований"):
                            new_cat_name = st.text_input("Новая категория", placeholder="Например: Мануальное тестирование")
                            if st.button("➕ Добавить категорию"):
                                if new_cat_name.strip():
                                    try:
                                        supabase.table("dict_exam_categories").insert({"name": new_cat_name.strip()}).execute()
                                        st.success("Категория добавлена!")
                                        st.cache_data.clear()
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Ошибка (возможно, категория уже существует): {e}")
                        
                        doc_categories = {}
                        for cat in categories:
                            if not my_docs.empty:
                                if "category" in my_docs.columns:
                                    my_docs["category"] = my_docs["category"].fillna("Прочее")
                                    docs_in_cat = my_docs[my_docs["category"] == cat]
                                else:
                                    docs_in_cat = pd.DataFrame()
                            else:
                                docs_in_cat = pd.DataFrame()
                                
                            if not docs_in_cat.empty:
                                doc_categories[cat] = docs_in_cat
                        else:
                            for cat_name, docs_df in doc_categories.items():
                                st.markdown(f"### 📁 {cat_name}")
                                for _, doc in docs_df.iterrows():
                                    url = get_public_file_url(doc["file_path"])
                                    
                                    with st.expander(f"📄 {doc['file_name']} (от {pd.to_datetime(doc['upload_date']).strftime('%d.%m.%Y')})"):
                                        st.markdown(f"**Тип:** {doc.get('document_type', '—')}")
                                        if pd.notna(doc.get("comment")):
                                            st.markdown(f"**Комментарий:** {doc['comment']}")
                                        
                                        # --- ДОБАВИЛИ РЕДАКТИРОВАНИЕ МЕТАДАННЫХ ---
                                        with st.form(f"edit_doc_meta_{doc['id']}"):
                                            ec1, ec2 = st.columns(2)
                                            with ec1:
                                                new_cat = st.selectbox("Категория", categories, index=categories.index(doc["category"]) if doc["category"] in categories else 3)
                                                new_date = st.date_input("Дата", value=pd.to_datetime(doc["upload_date"]).date())
                                            with ec2:
                                                new_comment = st.text_input("Комментарий", value=doc.get("comment") or "")
                                            
                                            if st.form_submit_button("💾 Обновить данные"):
                                                supabase.table("documents").update({
                                                    "category": new_cat,
                                                    "upload_date": new_date.isoformat(),
                                                    "comment": new_comment.strip() or None
                                                }).eq("id", doc["id"]).execute()
                                                st.success("✅ Данные обновлены!")
                                                st.cache_data.clear()
                                                st.rerun()

                                        # Ссылка на файл
                                        if url:
                                            st.markdown(f"[📥 Открыть/Скачать PDF]({url})", unsafe_allow_html=True)
                                        else:
                                            st.warning("Файл не найден в хранилище.")

                                        # Кнопка удаления
                                        if st.button("🗑️ Удалить документ", key=f"del_doc_{doc['id']}"):
                                            try:
                                                supabase.storage.from_("medical_documents").remove([doc["file_path"]])
                                                supabase.table("documents").delete().eq("id", doc["id"]).execute()
                                                st.success("Документ удален!")
                                                st.cache_data.clear()
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"Ошибка: {e}")
                                st.divider()

                        # Форма загрузки НОВОГО документа
                        with st.expander("➕ Загрузить новый PDF-файл"):
                            with st.form("new_doc_form", clear_on_submit=True):
                                d_c1, d_c2 = st.columns(2)
                                with d_c1:
                                    d_date = st.date_input("Дата обследования", value=date.today())
                                    d_cat = st.selectbox("Категория", categories)
                                    d_type = st.text_input("Наименование (ОАК, МРТ, ЭКГ...)")
                                with d_c2:
                                    d_comment = st.text_area("Комментарий")
                                    uploaded_file = st.file_uploader("Выберите PDF-файл", type=["pdf"])
                                
                                if st.form_submit_button("💾 Загрузить", type="primary"):
                                    if not uploaded_file:
                                        st.error("Выберите файл.")
                                    else:
                                        try:
                                            file_name = uploaded_file.name
                                            file_path = f"{selected_aid}/{file_name}"
                                            
                                            # Загружаем в Storage
                                            supabase.storage.from_("medical_documents").upload(
                                                path=file_path,
                                                file=uploaded_file.getvalue(),
                                                file_options={"content-type": "application/pdf"}
                                            )
                                            
                                            # Сохраняем в БД
                                            supabase.table("documents").insert({
                                                "athlete_id": selected_aid,
                                                "upload_date": d_date.isoformat(),
                                                "document_type": d_type if d_type else "Прочее", # Должно совпадать с CHECK
                                                "category": d_cat,
                                                "file_path": file_path,
                                                "file_name": file_name,
                                                "comment": d_comment.strip() or None
                                            }).execute()
                                            
                                            st.success("✅ Документ загружен!")
                                            st.cache_data.clear()
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Ошибка загрузки: {e}")

                # 4. ТРАВМЫ
                with c_inj:
                    st.subheader("🩹 Травмы и заболевания")
                    my_i = df_injuries_all[df_injuries_all["athlete_id"] == selected_aid] if not df_injuries_all.empty else pd.DataFrame()
                    
                    if my_i.empty:
                        st.info("Травм нет.")
                    else:
                        # 1. Таблица
                        d = my_i[["incident_date", "diagnosis", "body_part", "side", "severity", "days_lost"]].copy()
                        d = d.rename(columns={
                            "incident_date": "Дата", "diagnosis": "Диагноз", 
                            "body_part": "Часть тела", "side": "Сторона", 
                            "severity": "Тяжесть", "days_lost": "Пропущено"
                        })
                        d["Дата"] = pd.to_datetime(d["Дата"]).dt.strftime('%d.%m.%Y')
                        d = d.fillna("—")
                        st.dataframe(d, use_container_width=True, hide_index=True)

                        # 2. Редактирование
                        st.divider()
                        st.markdown("### ✏️ Редактировать травму")
                        
                        inj_options = {"— не выбрано —": None}
                        for _, r in my_i.iterrows():
                            label = f"{pd.to_datetime(r['incident_date']).strftime('%d.%m.%Y')} — {r['body_part'] or '—'} ({r['severity'] or '—'})"
                            inj_options[label] = r['id']
                            
                        selected_inj_label = st.selectbox("Выберите травму для изменения", list(inj_options.keys()), key="edit_inj_select")
                        selected_inj_id = inj_options[selected_inj_label]
                        
                        if selected_inj_id:
                            cur_i = my_i[my_i["id"] == selected_inj_id].iloc[0]
                            
                            # Получаем текущие МКБ
                            current_mkb = get_injury_diagnosis_labels(selected_inj_id)
                            
                            with st.form("edit_inj_form"):
                                e_c1, e_c2 = st.columns(2)
                                with e_c1:
                                    e_date = st.date_input("Дата", value=pd.to_datetime(cur_i["incident_date"]).date())
                                    
                                    # Выбор МКБ
                                    selected_diag_ids = render_diagnosis_multiselect(
                                        label="Диагнозы (МКБ)", 
                                        default_labels=current_mkb,
                                        key_suffix=f"edit_inj_{selected_inj_id}"
                                    )
                                    
                                    # Часть тела
                                    b_opts = {row['name']: row['id'] for _, row in df_body_parts.iterrows()}
                                    cur_b_name = "— не указана —"
                                    if pd.notna(cur_i.get("body_part_id")):
                                        for name, bid in b_opts.items():
                                            if bid == cur_i["body_part_id"]:
                                                cur_b_name = name
                                                break
                                    e_body = st.selectbox("Часть тела", ["— не указана —"] + list(b_opts.keys()), index=list(b_opts.keys()).index(cur_b_name) + 1 if cur_b_name in b_opts else 0)
                                with e_c2:
                                    side_opts = ["Не применимо", "Правая", "Левая"]
                                    e_side = st.selectbox("Сторона", side_opts, index=side_opts.index(cur_i["side"]) if cur_i["side"] in side_opts else 0)
                                    sev_opts = ["Легкая", "Средняя", "Тяжелая"]
                                    e_sev = st.selectbox("Тяжесть", sev_opts, index=sev_opts.index(cur_i["severity"]) if cur_i["severity"] in sev_opts else 0)
                                
                                e_mech = st.selectbox("Механизм", ["Не уточнено", "Контакт с соперником", "Падение", "Резкое движение без контакта", "Хроническая перегрузка"], index=0)
                                e_treat = st.text_area("Лечение", value=cur_i.get("treatment_description") or "")
                                e_days = st.number_input("Пропущено дней", value=int(cur_i.get("days_lost") or 0), min_value=0)
                                
                                col_save, col_del = st.columns([1, 1])
                                with col_save:
                                    if st.form_submit_button("💾 Сохранить", type="primary"):
                                        try:
                                            supabase.table("injuries_and_illnesses").update({
                                                "incident_date": e_date.isoformat(),
                                                "body_part_id": b_opts[e_body] if e_body != "— не указана —" else None,
                                                "side": e_side, "severity": e_sev, "mechanism": e_mech,
                                                "treatment_description": e_treat.strip() or None,
                                                "days_lost": e_days
                                            }).eq("id", selected_inj_id).execute()
                                            
                                            # Обновляем МКБ
                                            supabase.table("injury_diagnoses").delete().eq("injury_id", selected_inj_id).execute()
                                            for did in selected_diag_ids:
                                                supabase.table("injury_diagnoses").insert({
                                                    "injury_id": selected_inj_id, "diagnosis_id": did
                                                }).execute()
                                                
                                            st.success("✅ Травма обновлена!")
                                            st.cache_data.clear()
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Ошибка: {e}")
                                with col_del:
                                    if st.form_submit_button("🗑️ Удалить", type="secondary"):
                                        supabase.table("injuries_and_illnesses").delete().eq("id", selected_inj_id).execute()
                                        st.success("✅ Травма удалена!")
                                        st.cache_data.clear()
                                        st.rerun()

                    # 3. Добавление
                    with st.expander("➕ Добавить травму"):
                        with st.form("new_inj_form"):
                            n_c1, n_c2 = st.columns(2)
                            with n_c1:
                                n_date = st.date_input("Дата травмы", value=date.today())
                                n_diag_ids = render_diagnosis_multiselect(label="Диагнозы (МКБ)", key_suffix=f"new_inj_{selected_aid}")
                                
                                # Часть тела
                                b_opts = {row['name']: row['id'] for _, row in df_body_parts.iterrows()}
                                n_body = st.selectbox("Часть тела", ["— не указана —"] + list(b_opts.keys()))
                            with n_c2:
                                n_side = st.selectbox("Сторона", ["Не применимо", "Правая", "Левая"])
                                n_sev = st.selectbox("Тяжесть", ["Легкая", "Средняя", "Тяжелая"])
                                n_mech = st.selectbox("Механизм", ["Не уточнено", "Контакт с соперником", "Падение", "Резкое движение без контакта", "Хроническая перегрузка"])
                            
                            n_treat = st.text_area("Лечение")
                            n_days = st.number_input("Пропущено дней", value=0, min_value=0)
                            
                            if st.form_submit_button("💾 Сохранить травму", type="primary"):
                                try:
                                    resp = supabase.table("injuries_and_illnesses").insert({
                                        "athlete_id": selected_aid,
                                        "incident_date": n_date.isoformat(),
                                        "body_part_id": b_opts[n_body] if n_body != "— не указана —" else None,
                                        "side": n_side, "severity": n_sev, "mechanism": n_mech,
                                        "treatment_description": n_treat.strip() or None,
                                        "days_lost": n_days
                                    }).execute()
                                    
                                    if resp.data and n_diag_ids:
                                        new_iid = resp.data[0]["id"]
                                        for did in n_diag_ids:
                                            supabase.table("injury_diagnoses").insert({
                                                "injury_id": new_iid, "diagnosis_id": did
                                            }).execute()
                                            
                                    st.success("✅ Травма сохранена!")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")

                # 5. ОСМОТРЫ
                with c_exams:
                    st.subheader("🏥 Осмотры")
                    my_e = df_all_exams[df_all_exams["athlete_id"] == selected_aid] if not df_all_exams.empty else pd.DataFrame()
                    if my_e.empty:
                        st.info("Осмотров нет.")
                    else:
                        d = my_e[["examination_date", "exam_name", "is_approved", "next_exam_date", "restrictions"]].copy()
                        d = d.rename(columns={"examination_date": "Дата", "exam_name": "Осмотр", "is_approved": "Допуск", "next_exam_date": "Следующий", "restrictions": "Ограничения"})
                        d["Дата"] = pd.to_datetime(d["Дата"]).dt.strftime('%d.%m.%Y')
                        d["Следующий"] = pd.to_datetime(d["Следующий"]).dt.strftime('%d.%m.%Y')
                        d = d.fillna("—")
                        st.dataframe(d, use_container_width=True, hide_index=True)
                        
                    with st.expander("➕ Добавить осмотр"):
                        st.info("Форма добавления осмотра будет здесь.")

                # 6. АНТРОПОМЕТРИЯ
                with c_anthro:
                    st.subheader("📏 Антропометрия")
                    my_a = df_anthro[df_anthro["athlete_id"] == selected_aid] if not df_anthro.empty else pd.DataFrame()
                    
                    if my_a.empty:
                        st.info("Измерений нет.")
                    else:
                        # 1. Таблица
                        d = my_a[["measurement_date", "height", "weight", "bmi", "body_fat", "muscle_mass", "chest_circuit", "thigh_circuit"]].copy()
                        d = d.rename(columns={
                            "measurement_date": "Дата", "height": "Рост", "weight": "Вес", 
                            "bmi": "ИМТ", "body_fat": "% жира", "muscle_mass": "Мышцы",
                            "chest_circuit": "Грудь", "thigh_circuit": "Бедро"
                        })
                        d["Дата"] = pd.to_datetime(d["Дата"]).dt.strftime('%d.%m.%Y')
                        st.dataframe(d, use_container_width=True, hide_index=True)

                        # 2. Редактирование
                        st.divider()
                        st.markdown("### ✏️ Редактировать измерение")
                        
                        anthro_options = {"— не выбрано —": None}
                        for _, r in my_a.iterrows():
                            label = f"{pd.to_datetime(r['measurement_date']).strftime('%d.%m.%Y')} — Вес: {r['weight']} кг"
                            anthro_options[label] = r['id']
                            
                        selected_anthro_label = st.selectbox("Выберите измерение для изменения", list(anthro_options.keys()), key="edit_anthro_select")
                        selected_anthro_id = anthro_options[selected_anthro_label]
                        
                        if selected_anthro_id:
                            cur_a = my_a[my_a["id"] == selected_anthro_id].iloc[0]
                            
                            with st.form("edit_anthro_form"):
                                e_c1, e_c2, e_c3 = st.columns(3)
                                with e_c1:
                                    e_date = st.date_input("Дата", value=pd.to_datetime(cur_a["measurement_date"]).date())
                                    e_h = st.number_input("Рост (см)", value=float(cur_a["height"]) if pd.notna(cur_a["height"]) else 0.0, step=0.5)
                                with e_c2:
                                    e_w = st.number_input("Вес (кг)", value=float(cur_a["weight"]) if pd.notna(cur_a["weight"]) else 0.0, step=0.1)
                                    e_bf = st.number_input("% жира", value=float(cur_a["body_fat"]) if pd.notna(cur_a["body_fat"]) else 0.0, step=0.1)
                                with e_c3:
                                    e_mm = st.number_input("Мышцы (кг)", value=float(cur_a["muscle_mass"]) if pd.notna(cur_a["muscle_mass"]) else 0.0, step=0.1)
                                    e_cc = st.number_input("Обхват груди (см)", value=float(cur_a["chest_circuit"]) if pd.notna(cur_a["chest_circuit"]) else 0.0, step=0.5)
                                    e_tc = st.number_input("Обхват бедра (см)", value=float(cur_a["thigh_circuit"]) if pd.notna(cur_a["thigh_circuit"]) else 0.0, step=0.5)
                                
                                col_save, col_del = st.columns([1, 1])
                                with col_save:
                                    if st.form_submit_button("💾 Сохранить", type="primary"):
                                        try:
                                            # Пересчитываем ИМТ
                                            bmi = round(e_w / ((e_h / 100) ** 2), 1) if e_h > 0 and e_w > 0 else None
                                            
                                            supabase.table("anthropometry").update({
                                                "measurement_date": e_date.isoformat(),
                                                "height": e_h if e_h > 0 else None,
                                                "weight": e_w if e_w > 0 else None,
                                                "bmi": bmi,
                                                "body_fat": e_bf if e_bf > 0 else None,
                                                "muscle_mass": e_mm if e_mm > 0 else None,
                                                "chest_circuit": e_cc if e_cc > 0 else None,
                                                "thigh_circuit": e_tc if e_tc > 0 else None
                                            }).eq("id", selected_anthro_id).execute()
                                            st.success("✅ Измерение обновлено!")
                                            st.cache_data.clear()
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Ошибка: {e}")
                                with col_del:
                                    if st.form_submit_button("🗑️ Удалить", type="secondary"):
                                        supabase.table("anthropometry").delete().eq("id", selected_anthro_id).execute()
                                        st.success("✅ Измерение удалено!")
                                        st.cache_data.clear()
                                        st.rerun()

                    # 3. Добавление
                    with st.expander("➕ Добавить новое измерение"):
                        with st.form("new_anthro_form"):
                            a_c1, a_c2, a_c3 = st.columns(3)
                            with a_c1:
                                n_date = st.date_input("Дата измерения", value=date.today())
                                n_h = st.number_input("Рост (см)", value=0.0, step=0.5)
                            with a_c2:
                                n_w = st.number_input("Вес (кг)", value=0.0, step=0.1)
                                n_bf = st.number_input("% жира", value=0.0, step=0.1)
                            with a_c3:
                                n_mm = st.number_input("Мышечная масса (кг)", value=0.0, step=0.1)
                                n_cc = st.number_input("Обхват груди (см)", value=0.0, step=0.5)
                                n_tc = st.number_input("Обхват бедра (см)", value=0.0, step=0.5)
                            
                            if st.form_submit_button("💾 Сохранить измерение", type="primary"):
                                try:
                                    bmi = round(n_w / ((n_h / 100) ** 2), 1) if n_h > 0 and n_w > 0 else None
                                    
                                    supabase.table("anthropometry").insert({
                                        "athlete_id": selected_aid,
                                        "measurement_date": n_date.isoformat(),
                                        "height": n_h if n_h > 0 else None,
                                        "weight": n_w if n_w > 0 else None,
                                        "bmi": bmi,
                                        "body_fat": n_bf if n_bf > 0 else None,
                                        "muscle_mass": n_mm if n_mm > 0 else None,
                                        "chest_circuit": n_cc if n_cc > 0 else None,
                                        "thigh_circuit": n_tc if n_tc > 0 else None
                                    }).execute()
                                    st.success("✅ Измерение сохранено!")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")

                # 7. ЛЕКАРСТВА
                with c_meds:
                    st.subheader("💊 Назначения лекарств")
                    my_m = df_meds_current[df_meds_current["athlete_id"] == selected_aid] if not df_meds_current.empty else pd.DataFrame()
                    
                    if my_m.empty:
                        st.info("Назначений нет.")
                    else:
                        # 1. Таблица
                        d = my_m[["medicine_name", "dosage", "frequency", "course_start", "course_end", "wada_status"]].copy()
                        d = d.rename(columns={
                            "medicine_name": "Препарат", "dosage": "Дозировка", 
                            "frequency": "Кратность", "course_start": "С", 
                            "course_end": "По", "wada_status": "WADA"
                        })
                        d["С"] = pd.to_datetime(d["С"]).dt.strftime('%d.%m.%Y')
                        d["По"] = pd.to_datetime(d["По"]).dt.strftime('%d.%m.%Y')
                        d = d.fillna("—")
                        st.dataframe(d, use_container_width=True, hide_index=True)

                        # 2. Редактирование
                        st.divider()
                        st.markdown("### ✏️ Редактировать назначение")
                        
                        med_options = {"— не выбрано —": None}
                        for _, r in my_m.iterrows():
                            label = f"{pd.to_datetime(r['course_start']).strftime('%d.%m.%Y')} — {r['medicine_name']}"
                            med_options[label] = r['id']
                            
                        selected_med_label = st.selectbox("Выберите назначение для изменения", list(med_options.keys()), key="edit_med_select")
                        selected_med_id = med_options[selected_med_label]
                        
                        if selected_med_id:
                            cur_m = my_m[my_m["id"] == selected_med_id].iloc[0]
                            
                            with st.form("edit_med_form"):
                                e_c1, e_c2 = st.columns(2)
                                with e_c1:
                                    # Выбор препарата
                                    meds_dict = {row['name']: row['id'] for _, row in df_medicines.iterrows()}
                                    cur_med_name = "— не выбрано —"
                                    for name, mid in meds_dict.items():
                                        if mid == cur_m["medicine_id"]:
                                            cur_med_name = name
                                            break
                                    
                                    e_med = st.selectbox("Препарат", list(meds_dict.keys()), index=list(meds_dict.keys()).index(cur_med_name) if cur_med_name in meds_dict else 0)
                                    
                                    e_dosage = st.text_input("Дозировка", value=cur_m.get("dosage") or "")
                                    e_freq = st.text_input("Кратность (например, 2 раза в день)", value=cur_m.get("frequency") or "")
                                    
                                with e_c2:
                                    e_start = st.date_input("Начало курса", value=pd.to_datetime(cur_m["course_start"]).date())
                                    e_end = st.date_input("Конец курса", value=pd.to_datetime(cur_m["course_end"]).date())
                                    
                                    route_opts = ["Перорально", "Внутримышечно", "Внутривенно", "Местно", "Ингаляционно"]
                                    e_route = st.selectbox("Способ введения", route_opts, index=route_opts.index(cur_m["administration_route"]) if cur_m.get("administration_route") in route_opts else 0)
                                
                                e_notes = st.text_area("Примечания", value=cur_m.get("notes") or "")
                                
                                col_save, col_del = st.columns([1, 1])
                                with col_save:
                                    if st.form_submit_button("💾 Сохранить", type="primary"):
                                        try:
                                            supabase.table("medication_intake").update({
                                                "medicine_id": meds_dict[e_med],
                                                "dosage": e_dosage.strip() or None,
                                                "frequency": e_freq.strip() or None,
                                                "course_start": e_start.isoformat(),
                                                "course_end": e_end.isoformat(),
                                                "administration_route": e_route,
                                                "notes": e_notes.strip() or None
                                            }).eq("id", selected_med_id).execute()
                                            st.success("✅ Назначение обновлено!")
                                            st.cache_data.clear()
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Ошибка: {e}")
                                with col_del:
                                    if st.form_submit_button("🗑️ Удалить", type="secondary"):
                                        supabase.table("medication_intake").delete().eq("id", selected_med_id).execute()
                                        st.success("✅ Назначение удалено!")
                                        st.cache_data.clear()
                                        st.rerun()

                    # 3. Добавление
                    with st.expander("➕ Назначить лекарство"):
                        with st.form("new_med_form"):
                            n_c1, n_c2 = st.columns(2)
                            with n_c1:
                                meds_dict = {row['name']: row['id'] for _, row in df_medicines.iterrows()}
                                n_med = st.selectbox("Препарат *", list(meds_dict.keys()))
                                
                                n_dosage = st.text_input("Дозировка (например, 500 мг)")
                                n_freq = st.text_input("Кратность (например, 2 раза в день)")
                            with n_c2:
                                n_start = st.date_input("Начало курса", value=date.today())
                                n_end = st.date_input("Конец курса", value=date.today() + timedelta(days=7))
                                n_route = st.selectbox("Способ введения", ["Перорально", "Внутримышечно", "Внутривенно", "Местно", "Ингаляционно"])
                            
                            n_notes = st.text_area("Примечания")
                            
                            if st.form_submit_button("💾 Сохранить назначение", type="primary"):
                                try:
                                    supabase.table("medication_intake").insert({
                                        "athlete_id": selected_aid,
                                        "medicine_id": meds_dict[n_med],
                                        "prescribed_date": date.today().isoformat(),
                                        "course_start": n_start.isoformat(),
                                        "course_end": n_end.isoformat(),
                                        "dosage": n_dosage.strip() or None,
                                        "frequency": n_freq.strip() or None,
                                        "administration_route": n_route,
                                        "notes": n_notes.strip() or None
                                    }).execute()
                                    st.success("✅ Лекарство назначено!")
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка: {e}")

    # ------------------------------------------
    # ВКЛАДКА 3: АНАЛИТИКА
    # ------------------------------------------
    with tab_analytics:
        st.header("📈 Аналитика по команде")
        st.info("Здесь будут общие графики: травматизм за сезон, общая динамика пульса и т.д.")