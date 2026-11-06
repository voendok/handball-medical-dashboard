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
df_positions = load_positions()

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
        mode = st.radio("Режим работы", ["📋 Выбрать существующую", "➕ Добавить новую"], horizontal=True)

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

                st.divider()

                # --- ПОДВКЛАДКИ КАРТОЧКИ ---                
                st.divider()

                # --- ПОДВКЛАДКИ КАРТОЧКИ ---
                c_tabs = st.tabs([
                    "📊 Мониторинг", "🩺 Приёмы", "🧪 Анализы", 
                    "🩹 Травмы", "🏥 Осмотры", "📏 Антропометрия", 
                    "💊 Лекарства", "💉 Прививки"
                ])
                (c_mon, c_visits, c_labs, c_inj, c_exams, c_anthro, c_meds, c_vacc) = c_tabs

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
                        
                        visit_options = {f"{pd.to_datetime(row['visit_date']).strftime('%d.%m.%Y')} — {row['complaints'][:30] if pd.notna(row['complaints']) else '—'}...": row['id'] for _, row in my_v.iterrows()}
                        selected_visit_label = st.selectbox("Выберите приём для изменения", list(visit_options.keys()), key="edit_visit_select")
                        
                        if selected_visit_label:
                            selected_visit_id = visit_options[selected_visit_label]
                            cur_v = my_v[my_v["id"] == selected_visit_id].iloc[0]
                            
                            with st.form("edit_visit_form"):
                                e_c1, e_c2 = st.columns(2)
                                with e_c1:
                                    e_date = st.date_input("Дата", value=pd.to_datetime(cur_v["visit_date"]).date())
                                    e_complaints = st.text_area("Жалобы", value=cur_v.get("complaints") or "")
                                with e_c2:
                                    e_diagnosis = st.text_input("Диагноз", value=cur_v.get("diagnosis_text") or cur_v.get("diagnosis") or "")
                                    e_prescriptions = st.text_input("Назначения", value=cur_v.get("prescriptions") or "")
                                
                                e_recs = st.text_area("Рекомендации", value=cur_v.get("recommendations") or "")
                                
                                col_save, col_del = st.columns([1, 1])
                                with col_save:
                                    if st.form_submit_button("💾 Сохранить", type="primary"):
                                        supabase.table("doctor_visits").update({
                                            "visit_date": e_date.isoformat(),
                                            "complaints": e_complaints.strip() or None,
                                            "diagnosis_text": e_diagnosis.strip() or None,
                                            "prescriptions": e_prescriptions.strip() or None,
                                            "recommendations": e_recs.strip() or None,
                                        }).eq("id", selected_visit_id).execute()
                                        st.success("✅ Приём обновлен!")
                                        st.cache_data.clear()
                                        st.rerun()
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

                # 3. АНАЛИЗЫ
                with c_labs:
                    st.subheader("🧪 Лабораторные анализы")
                    my_l = df_lab[df_lab["athlete_id"] == selected_aid] if not df_lab.empty else pd.DataFrame()
                    
                    if my_l.empty:
                        st.info("Анализов нет.")
                    else:
                        d = my_l[["measurement_date", "biomarker_name", "value", "unit", "reference_min", "reference_max"]].copy()
                        d = d.rename(columns={"measurement_date": "Дата", "biomarker_name": "Показатель", "value": "Значение", "unit": "Ед.", "reference_min": "Мин.норма", "reference_max": "Макс.норма"})
                        d["Дата"] = pd.to_datetime(d["Дата"]).dt.strftime('%d.%m.%Y')
                        st.dataframe(d, use_container_width=True, hide_index=True)

                    with st.expander("➕ Добавить анализ"):
                        with st.form("new_lab_form"):
                            l_c1, l_c2 = st.columns(2)
                            with l_c1:
                                l_date = st.date_input("Дата анализа", value=date.today())
                                # Загружаем список биомаркеров
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

                # 4. ТРАВМЫ
                with c_inj:
                    st.subheader("🩹 Травмы")
                    my_i = df_injuries_all[df_injuries_all["athlete_id"] == selected_aid] if not df_injuries_all.empty else pd.DataFrame()
                    if my_i.empty:
                        st.info("Травм нет.")
                    else:
                        d = my_i[["incident_date", "diagnosis", "body_part", "side", "severity", "days_lost"]].copy()
                        d = d.rename(columns={"incident_date": "Дата", "diagnosis": "Диагноз", "body_part": "Часть тела", "side": "Сторона", "severity": "Тяжесть", "days_lost": "Пропущено"})
                        d["Дата"] = pd.to_datetime(d["Дата"]).dt.strftime('%d.%m.%Y')
                        d = d.fillna("—")
                        st.dataframe(d, use_container_width=True, hide_index=True)
                    
                    with st.expander("➕ Добавить травму"):
                        st.info("Форма добавления травмы будет здесь.")

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
                        d = my_a[["measurement_date", "height", "weight", "bmi", "body_fat", "muscle_mass"]].copy()
                        d = d.rename(columns={"measurement_date": "Дата", "height": "Рост", "weight": "Вес", "bmi": "ИМТ", "body_fat": "% жира", "muscle_mass": "Мышцы"})
                        d["Дата"] = pd.to_datetime(d["Дата"]).dt.strftime('%d.%m.%Y')
                        st.dataframe(d, use_container_width=True, hide_index=True)

                    # ДОБАВИЛИ КНОПКУ ДЛЯ АНТРОПОМЕТРИИ
                    with st.expander("➕ Добавить измерение"):
                        st.info("Форма добавления антропометрии будет здесь.")

                # 7. ЛЕКАРСТВА
                with c_meds:
                    st.subheader("💊 Лекарства")
                    my_m = df_meds_current[df_meds_current["athlete_id"] == selected_aid] if not df_meds_current.empty else pd.DataFrame()
                    if my_m.empty:
                        st.info("Назначений нет.")
                    else:
                        d = my_m[["medicine_name", "dosage", "frequency", "course_start", "course_end", "wada_status"]].copy()
                        d = d.rename(columns={"medicine_name": "Препарат", "dosage": "Дозировка", "frequency": "Кратность", "course_start": "С", "course_end": "По", "wada_status": "WADA"})
                        d["С"] = pd.to_datetime(d["С"]).dt.strftime('%d.%m.%Y')
                        d["По"] = pd.to_datetime(d["По"]).dt.strftime('%d.%m.%Y')
                        d = d.fillna("—")
                        st.dataframe(d, use_container_width=True, hide_index=True)

                    # ДОБАВИЛИ КНОПКУ ДЛЯ ЛЕКАРСТВ
                    with st.expander("➕ Назначить лекарство"):
                        st.info("Форма назначения лекарства будет здесь.")

                # 8. ПРИВИВКИ
                with c_vacc:
                    st.subheader("💉 Прививки")
                    my_vac = df_vaccinations[df_vaccinations["athlete_id"] == selected_aid] if not df_vaccinations.empty else pd.DataFrame()
                    if my_vac.empty:
                        st.info("Прививок нет.")
                    else:
                        d = my_vac[["vaccination_date", "vaccine_name", "booster_date", "batch_number"]].copy()
                        d = d.rename(columns={"vaccination_date": "Дата", "vaccine_name": "Вакцина", "booster_date": "Ревакцинация", "batch_number": "Серия"})
                        d["Дата"] = pd.to_datetime(d["Дата"]).dt.strftime('%d.%m.%Y')
                        d = d.fillna("—")
                        st.dataframe(d, use_container_width=True, hide_index=True)

                    # ДОБАВИЛИ КНОПКУ ДЛЯ ПРИВИВОК
                    with st.expander("➕ Добавить прививку"):
                        st.info("Форма добавления прививки будет здесь.")


    # ------------------------------------------
    # ВКЛАДКА 3: АНАЛИТИКА
    # ------------------------------------------
    with tab_analytics:
        st.header("📈 Аналитика по команде")
        st.info("Здесь будут общие графики: травматизм за сезон, общая динамика пульса и т.д.")