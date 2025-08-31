# app.py
import streamlit as st
import pandas as pd
import sqlite3
import hashlib
from datetime import datetime
import altair as alt
import math
import os

# -------------------------
# CONFIG / UTILITIES
# -------------------------
DB_PATH = "users.db"
FOODS_CSV = "foods.csv"
EXERCISES_CSV = "exercises.csv"

# ----------------------------
# Load foods.csv safely
foods_df = pd.read_csv(FOODS_CSV, encoding="utf-8")

# Normalize column names
foods_df.columns = foods_df.columns.str.strip().str.lower()

# Rename alternative headers to standard ones
rename_map = {
    "name": "food_name",
    "cal_per_100g": "calories",
    "diet_tag": "diet_type"
}
foods_df.rename(columns=rename_map, inplace=True)

# Auto-add meal_type if missing
if "meal_type" not in foods_df.columns:
    import numpy as np
    meal_types = ["breakfast", "lunch", "dinner", "snack"]
    foods_df["meal_type"] = np.resize(meal_types, len(foods_df))

# Auto-add diet_type if missing
if "diet_type" not in foods_df.columns:
    foods_df["diet_type"] = "veg"   # default value

# Debug: confirm schema
st.write("✅ Final Foods CSV columns:", foods_df.columns.tolist())
st.dataframe(foods_df.head())
# ==============================
# Load foods.csv safely
# ==============================
foods_df = pd.read_csv(FOODS_CSV, encoding="utf-8", delimiter=",")
foods_df.columns = foods_df.columns.str.strip().str.lower()

# Debug: Check if file loaded correctly (remove later)
st.write("Foods CSV columns:", foods_df.columns.tolist())
st.dataframe(foods_df.head())

# ==============================
# Load exercises.csv safely
# ==============================
exercises_df = pd.read_csv(EXERCISES_CSV, encoding="utf-8", delimiter=",")
exercises_df.columns = exercises_df.columns.str.strip().str.lower()

# Debug: Check if file loaded correctly (remove later)
st.write("Exercises CSV columns:", exercises_df.columns.tolist())
st.dataframe(exercises_df.head())

# Ensure DB exists and create tables if not
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        full_name TEXT
    );
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS profiles (
        user_id INTEGER PRIMARY KEY,
        age INTEGER,
        sex TEXT,
        height_cm REAL,
        weight_kg REAL,
        activity_level TEXT,
        goal TEXT,
        diet_pref TEXT,
        created_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        date TEXT,
        weight_kg REAL,
        calories_consumed INTEGER,
        completed BOOLEAN,
        notes TEXT
    );
    ''')
    conn.commit()
    return conn

conn = init_db()

def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password, full_name=""):
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password_hash, full_name) VALUES (?, ?, ?)",
                  (username, hash_password(password), full_name))
        conn.commit()
        return True, None
    except sqlite3.IntegrityError as e:
        return False, "Username already exists."

def authenticate(username, password):
    c = conn.cursor()
    c.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    if row and hash_password(password) == row[1]:
        return True, row[0]
    return False, None

def save_profile(user_id, profile):
    c = conn.cursor()
    c.execute('''
    INSERT OR REPLACE INTO profiles (user_id, age, sex, height_cm, weight_kg, activity_level, goal, diet_pref, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, profile['age'], profile['sex'], profile['height_cm'], profile['weight_kg'],
          profile['activity_level'], profile['goal'], profile['diet_pref'], datetime.now().isoformat()))
    conn.commit()

def get_profile(user_id):
    c = conn.cursor()
    c.execute("SELECT age, sex, height_cm, weight_kg, activity_level, goal, diet_pref FROM profiles WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row:
        keys = ['age','sex','height_cm','weight_kg','activity_level','goal','diet_pref']
        return dict(zip(keys,row))
    return None

def add_progress(user_id, date, weight_kg=None, calories_consumed=None, completed=False, notes=""):
    c = conn.cursor()
    c.execute("INSERT INTO progress (user_id, date, weight_kg, calories_consumed, completed, notes) VALUES (?, ?, ?, ?, ?, ?)",
              (user_id, date, weight_kg, calories_consumed, int(completed), notes))
    conn.commit()

def get_progress(user_id):
    c = conn.cursor()
    c.execute("SELECT date, weight_kg, calories_consumed, completed, notes FROM progress WHERE user_id = ? ORDER BY date", (user_id,))
    rows = c.fetchall()
    df = pd.DataFrame(rows, columns=['date','weight_kg','calories_consumed','completed','notes'])
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
    return df

# -------------------------
# HEALTH CALCS
# -------------------------
def calc_bmi(weight_kg, height_cm):
    h_m = height_cm / 100.0
    if h_m <= 0: return None
    bmi = weight_kg / (h_m * h_m)
    return round(bmi, 1)

def bmi_category(bmi):
    if bmi is None: return "Unknown"
    if bmi < 18.5: return "Underweight"
    if bmi < 25: return "Normal"
    if bmi < 30: return "Overweight"
    return "Obese"

def calc_bmr(sex, weight_kg, height_cm, age):
    # Mifflin-St Jeor
    if sex.lower() in ['male','m','man']:
        bmr = 10*weight_kg + 6.25*height_cm - 5*age + 5
    else:
        bmr = 10*weight_kg + 6.25*height_cm - 5*age - 161
    return int(round(bmr))

ACTIVITY_MULTIPLIER = {
    "Sedentary (little/no exercise)" : 1.2,
    "Lightly active (1-3 days/week)" : 1.375,
    "Moderately active (3-5 days/week)" : 1.55,
    "Very active (6-7 days/week)" : 1.725,
    "Extra active (very intense)" : 1.9
}

GOAL_ADJUSTMENT = {
    "Lose weight": -500,    # target kcal deficit per day
    "Gain weight": 300,     # surplus
    "Maintain": 0,
    "Build muscle": 250
}

def target_calories(bmr, activity_level, goal):
    multiplier = ACTIVITY_MULTIPLIER.get(activity_level, 1.2)
    maintenance = bmr * multiplier
    adjust = GOAL_ADJUSTMENT.get(goal, 0)
    return int(round(maintenance + adjust))

# -------------------------
# LOAD DATASETS
# -------------------------
@st.cache_data
def load_foods():
    if not os.path.exists(FOODS_CSV):
        # if missing, create a tiny default
        df = pd.DataFrame([
            ["Oats porridge", "veg", 200, "breakfast"],
            ["Egg & toast", "non-veg", 350, "breakfast"],
            ["Grilled chicken salad", "non-veg", 400, "lunch"],
            ["Chickpea curry + rice", "veg", 520, "lunch"],
            ["Fruit salad", "vegan", 150, "snack"],
            ["Paneer stir-fry", "veg", 450, "dinner"]
        ], columns=["food_name","diet_type","cal_per_serving","meal_type"])
        df.to_csv(FOODS_CSV, index=False)
    return pd.read_csv(FOODS_CSV)

@st.cache_data
def load_exercises():
    if not os.path.exists(EXERCISES_CSV):
        df = pd.DataFrame([
            ["Brisk walking", "Lose weight,Maintenance", 30, "none","easy"],
            ["Squats", "Build muscle,Gain weight", 20, "bodyweight","medium"],
            ["Plank", "Posture,Flexibility", 5, "none","easy"],
            ["Resistance training (upper)", "Build muscle", 40, "weights","hard"],
            ["Yoga flow", "Flexibility,Maintenance", 30, "none","easy"],
            ["HIIT 20min", "Lose weight", 20, "none","hard"]
        ], columns=["exercise_name","goals","duration_min","equipment","difficulty"])
        df.to_csv(EXERCISES_CSV, index=False)
    return pd.read_csv(EXERCISES_CSV)

foods_df = load_foods()
ex_df = load_exercises()

# -------------------------
# UI / PAGES
# -------------------------
st.set_page_config(page_title="Virtual Health & Diet Planner", layout="wide")

# Simple CSS to make landing pretty
def local_css():
    st.markdown("""
    <style>
    .landing {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        padding: 30px;
        border-radius: 12px;
    }
    .card {
        background: white;
        padding: 18px;
        border-radius: 10px;
        box-shadow: 0 6px 18px rgba(0,0,0,0.08);
    }
    .small {
        font-size:14px; color:#444;
    }
    .title-big {
        font-size:28px; font-weight:700;
    }
    </style>
    """, unsafe_allow_html=True)

local_css()

# --- TOP: Landing / Login selection ---
st.markdown("<div class='landing card'>", unsafe_allow_html=True)
left, mid, right = st.columns([1,2,1])
with left:
    st.image("https://images.unsplash.com/photo-1549576490-b0b4831ef60a?w=800&q=80", caption=None, use_column_width=True)
with mid:
    st.markdown("<div class='title-big'>Virtual Health & Diet Planner</div>", unsafe_allow_html=True)
    st.write("A personalized demo app to calculate BMI, BMR, target calories and give tailored diet & exercise suggestions.")
    st.markdown("**🔹 Objective**")
    st.markdown("""Create a simple and personalized web app where users provide basic details (age, height, weight, lifestyle, goal) and get:
- BMI & calorie needs
- Diet suggestions (veg / non-veg / vegan)
- Exercise recommendations (weight loss, gain, muscle, flexibility, posture, or maintenance)""")
    st.markdown("**🔹 How it works**")
    st.markdown("User Input → Health calculations → Recommendations → Results shown on an easy Dashboard.")
    st.write("")
    # CTA buttons
    col1, col2 = st.columns(2)
    if 'user_id' not in st.session_state:
        if col1.button("🔐 Login"):
            st.session_state.show_login = True
        if col2.button("🆕 Register"):
            st.session_state.show_register = True
    else:
        if col1.button("🚪 Logout"):
            st.session_state.clear()
with right:
    st.image("https://images.unsplash.com/photo-1514996937319-344454492b37?w=800&q=80", use_column_width=True)
st.markdown("</div>", unsafe_allow_html=True)

# Initialize session_state flags
if 'show_login' not in st.session_state: st.session_state.show_login = False
if 'show_register' not in st.session_state: st.session_state.show_register = False

# --- AUTH PANE (modal-like area) ---
if st.session_state.show_register:
    st.header("Create a new account")
    new_user = st.text_input("Choose username")
    new_name = st.text_input("Full name (optional)")
    new_pass = st.text_input("Password", type="password")
    if st.button("Create account"):
        ok, err = register_user(new_user, new_pass, new_name)
        if ok:
            st.success("Account created! Please login.")
            st.session_state.show_register = False
        else:
            st.error(f"Could not register: {err}")

if st.session_state.show_login:
    st.header("Login")
    username = st.text_input("Username", key="login_user")
    password = st.text_input("Password", type="password", key="login_pass")
    if st.button("Login"):
        ok, user_id = authenticate(username, password)
        if ok:
            st.success("Logged in")
            st.session_state.user_id = user_id
            st.session_state.username = username
            st.session_state.show_login = False
        else:
            st.error("Login failed. Check username/password.")

# If logged in, show profile form if profile missing
if 'user_id' in st.session_state:
    uid = st.session_state.user_id
    profile = get_profile(uid)
    if profile is None:
        st.subheader("Complete your profile")
        with st.form("profile_form"):
            age = st.number_input("Age", min_value=8, max_value=120, value=25)
            sex = st.selectbox("Sex", ["Male","Female","Other"])
            height_cm = st.number_input("Height (cm)", min_value=50.0, max_value=250.0, value=170.0)
            weight_kg = st.number_input("Weight (kg)", min_value=20.0, max_value=300.0, value=70.0)
            activity_level = st.selectbox("Activity level", list(ACTIVITY_MULTIPLIER.keys()))
            goal = st.selectbox("Goal", ["Lose weight","Gain weight","Maintain","Build muscle"])
            diet_pref = st.selectbox("Diet preference", ["veg","non-veg","vegan"])
            submitted = st.form_submit_button("Save profile")
            if submitted:
                p = {
                    "age": int(age),
                    "sex": sex,
                    "height_cm": float(height_cm),
                    "weight_kg": float(weight_kg),
                    "activity_level": activity_level,
                    "goal": goal,
                    "diet_pref": diet_pref
                }
                save_profile(uid, p)
                st.success("Profile saved! Redirecting to Dashboard...")
                st.rerun()

# -------------------------
# MAIN APP: Dashboard area
# -------------------------
if 'user_id' in st.session_state:
    uid = st.session_state.user_id
    profile = get_profile(uid)
    if profile:
        st.title(f"Welcome, {st.session_state.get('username','User')} 👋")
        st.markdown("### Your personalized recommendations")
        # Top horizontal menu using tabs (appears just below title)
        tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "🎯 Daily Goals", "📈 Progress"])
        # --- DASHBOARD tab ---
        with tab1:
            # Summary card
            bmi = calc_bmi(profile['weight_kg'], profile['height_cm'])
            bmr = calc_bmr(profile['sex'], profile['weight_kg'], profile['height_cm'], profile['age'])
            tcal = target_calories(bmr, profile['activity_level'], profile['goal'])
            colA, colB, colC, colD = st.columns(4)
            colA.metric("BMI", f"{bmi} ({bmi_category(bmi)})")
            colB.metric("BMR (kcal/day)", f"{bmr}")
            colC.metric("Target calories", f"{tcal} kcal")
            # Diet suggestions (pick 3 meals)
            st.markdown("#### Diet suggestions (sample day)")
            diet_pref = profile['diet_pref']
            meals = []
            # For each meal type get 1-2 suggestions matched to diet_pref if possible
            for meal_type in ["breakfast","lunch","snack","dinner"]:
                if "meal_type" in foods_df.columns:
                    subset = foods_df[foods_df["meal_type"].str.lower() == meal_type]
                else:
                    st.error("⚠️ 'meal_type' column not found in foods_df")
                    st.write("Available columns:", foods_df.columns.tolist())
                    subset = pd.DataFrame()

                pref_matched = subset[subset['diet_type'].str.lower()==diet_pref.lower()]
                choice_df = pref_matched if not pref_matched.empty else subset
                if choice_df.empty:
                    meals.append((meal_type.capitalize(), "No data"))
                else:
                    sample = choice_df.sample(min(1,len(choice_df))).iloc[0]
                    meals.append((meal_type.capitalize(), f"{sample['food_name']} — {int(sample['cal_per_serving'])} kcal"))
            for m in meals:
                st.write(f"**{m[0]}** — {m[1]}")
            st.info("This is a sample meal plan from a small dataset. Replace foods.csv with a larger dataset for more variety.")
            # Exercise recommendations
            st.markdown("#### Exercise recommendations")
            # match exercises by goal
            desired = profile['goal']
            ex_df['match'] = ex_df['goals'].str.lower().str.contains(desired.lower().split()[0])
            # fallback: match any that contain 'maintenance' etc.
            recs = ex_df[ex_df['goals'].str.lower().str.contains(desired.lower().split()[0])]
            if recs.empty:
                recs = ex_df.sample(min(3, len(ex_df)))
            for i, r in recs.head(5).iterrows():
                st.write(f"- **{r['exercise_name']}** ({r['duration_min']} min) — goals: {r['goals']} — difficulty: {r['difficulty']}")
            st.markdown("---")
            # Quick logging box for today's progress
            st.markdown("#### Quick daily log")
            with st.form("daily_log"):
                w = st.number_input("Today's weight (kg)", value=float(profile['weight_kg']))
                calories = st.number_input("Calories consumed today (estimate)", min_value=0, value=int(tcal))
                completed = st.checkbox("Completed planned exercise today?")
                notes = st.text_area("Notes (optional)")
                if st.form_submit_button("Save log"):
                    add_progress(uid, datetime.now().date().isoformat(), float(w), int(calories), completed, notes)
                    st.success("Saved today's log")
                    st.experimental_rerun()

        # --- DAILY GOALS tab ---
        with tab2:
            st.header("Your daily goals")
            st.markdown(f"- **Target calories:** {tcal} kcal/day")
            # Macro suggestion: simple ratio
            if profile['goal'] == "Lose weight":
                st.write("- Aim for moderate calorie deficit (≈500 kcal/day) & maintain protein intake.")
            elif profile['goal'] == "Gain weight":
                st.write("- Aim for small surplus (≈250-350 kcal/day) & focus on protein + resistance training.")
            elif profile['goal'] == "Build muscle":
                st.write("- Eat protein-rich meals distribution across the day; progressive resistance training 3-5x/week.")
            else:
                st.write("- Maintain your calorie intake and keep regular activity.")
            st.markdown("**Micro daily checklist**")
            checklist = {
                "Drink 2L+ water": True,
                "Protein in each meal": False,
                "30 min planned exercise": False,
                "Sleep 7-8 hours": False
            }
            # store checklist in session so user can tick
            for k,v in checklist.items():
                checked = st.checkbox(k, key=f"check_{k}")
                if checked:
                    st.write(f"✅ {k}")
            st.info("These are suggested daily reminders. You can customize them further in future versions.")

        # --- PROGRESS tab ---
        with tab3:
            st.header("Progress over time")
            dfp = get_progress(uid)
            if dfp.empty:
                st.info("No progress logged yet. Add entries from Dashboard -> Quick daily log.")
            else:
                # show weight line chart
                st.markdown("**Weight over time**")
                weight_df = dfp.dropna(subset=['weight_kg'])
                if not weight_df.empty:
                    chart = alt.Chart(weight_df).mark_line(point=True).encode(
                        x='date:T',
                        y='weight_kg:Q'
                    ).properties(width=700, height=300)
                    st.altair_chart(chart, use_container_width=True)
                    st.dataframe(weight_df[['date','weight_kg','calories_consumed','completed']].sort_values('date', ascending=False))
                else:
                    st.write("No weight entries.")
                # calories compliance plot (calories_consumed vs target)
                st.markdown("**Calories consumed vs target**")
                cc = dfp.dropna(subset=['calories_consumed'])
                if not cc.empty:
                    cc2 = cc.copy()
                    cc2['target'] = tcal
                    chart2 = alt.Chart(cc2).transform_fold(['calories_consumed','target'], as_=['type','value']).mark_line(point=True).encode(
                        x='date:T',
                        y='value:Q',
                        color='type:N'
                    ).properties(width=700, height=300)
                    st.altair_chart(chart2, use_container_width=True)
    else:
        st.warning("Profile not set. Please complete the profile to see recommendations.")

# If not logged in, show footer / features
if 'user_id' not in st.session_state:
    st.markdown("---")
    st.markdown("### Want this as a demo you can share?")
    st.markdown("- Use the Register button to create test users.")
    st.markdown("- Replace `foods.csv` and `exercises.csv` with larger datasets for a richer demo.")
    st.markdown("**Developer tips:** create `static/` folder for images and update the landing `st.image(...)` to use local files for faster loading.")

# End
