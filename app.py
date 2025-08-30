# app.py
import streamlit as st
import pandas as pd

# -------------------------
# Helper functions (logic)
# -------------------------
def calc_bmi(weight_kg, height_cm):
    height_m = height_cm / 100
    if height_m <= 0:
        return None
    return weight_kg / (height_m ** 2)

def calc_bmr(age, gender, weight_kg, height_cm):
    if gender.lower() == "male":
        return 88.36 + (13.4 * weight_kg) + (4.8 * height_cm) - (5.7 * age)
    else:
        return 447.6 + (9.2 * weight_kg) + (3.1 * height_cm) - (4.3 * age)

# -------------------------
# Page Configuration
# -------------------------
st.set_page_config(page_title="Virtual Health & Diet Planner", layout="centered")

# Session state to switch between pages
if "page" not in st.session_state:
    st.session_state.page = "landing"

# -------------------------
# Landing Page
# -------------------------
if st.session_state.page == "landing":
    st.markdown(
        """
        <style>
        .landing {
            text-align: center;
            color: white;
            padding: 150px 20px;
            background: linear-gradient(135deg, black, darkblue, darkgreen);
            border-radius: 20px;
        }
        .pop-up {
            font-size: 42px;
            font-weight: bold;
            animation: pop 2s ease-in-out forwards;
        }
        @keyframes pop {
            0% {opacity: 0; transform: scale(0.5);}
            100% {opacity: 1; transform: scale(1);}
        }
        </style>
        <div class="landing">
            <div class="pop-up">Welcome to</div>
            <div class="pop-up">Virtual Health & Diet Planner</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Continue button
    if st.button("👉 Continue to App"):
        st.session_state.page = "calculator"
        st.experimental_rerun()



# -------------------------
# Custom CSS for dark theme
# -------------------------
page_bg = """
<style>
/* Background with dark gradient */
.stApp {
    background: linear-gradient(to right, #000000, #0f2027, #203a43, #2c5364); /* black to dark blue */
    background-attachment: fixed;
    background-size: cover;
    color: #ffffff;
}

/* Card-like look for forms and results */
div[data-testid="stForm"], .stMarkdown, .stTextInput, .stNumberInput, .stSelectbox {
    background-color: rgba(20, 20, 20, 0.85);
    padding: 15px;
    border-radius: 12px;
    box-shadow: 2px 2px 12px rgba(0,0,0,0.6);
    color: #e0e0e0;
}

/* Header styling */
h1, h2, h3 {
    color: #4fc3f7; /* bright cyan-blue */
    font-family: 'Segoe UI', sans-serif;
    text-align: center;
}
</style>
"""
st.markdown(page_bg, unsafe_allow_html=True)







# -------------------------
# Helper functions (logic)
# -------------------------
def calc_bmi(weight_kg, height_cm):
    height_m = height_cm / 100
    if height_m <= 0:
        return None
    return weight_kg / (height_m ** 2)

def calc_bmr(age, gender, weight_kg, height_cm):
    # Mifflin-St Jeor
    if gender.lower() == "male":
        return 10*weight_kg + 6.25*height_cm - 5*age + 5
    else:
        return 10*weight_kg + 6.25*height_cm - 5*age - 161

def activity_factor(level):
    mapping = {
        "Sedentary": 1.2,
        "Lightly Active": 1.375,
        "Moderately Active": 1.55,
        "Very Active": 1.725
    }
    return mapping.get(level, 1.2)

def target_calories(bmr, activity_level, goal):
    tdee = bmr * activity_factor(activity_level)
    if goal == "Lose Weight":
        return tdee - 400
    elif goal in ("Gain Weight", "Build Muscle"):
        return tdee + 400
    else:
        return tdee

# -------------------------
# Data functions (CSV)
# -------------------------
def load_foods(path="foods.csv"):
    try:
        return pd.read_csv(path)
    except FileNotFoundError:
        return pd.DataFrame(columns=["name","cal_per_100g","protein_g","diet_tag","cost_level"])

def load_exercises(path="exercises.csv"):
    try:
        return pd.read_csv(path)
    except FileNotFoundError:
        return pd.DataFrame(columns=["name","goal_tag","body_area","level","duration_min","notes"])

def recommend_foods(df_foods, diet_pref, want_high_cal=False, n=4):
    # filter by diet
    df = df_foods[df_foods['diet_tag'].str.contains(diet_pref, case=False, na=False)]
    if df.empty:
        df = df_foods.copy()
    # prefer higher calories for gainers, lower calories for losers
    if want_high_cal:
        df = df.sort_values('cal_per_100g', ascending=False)
    else:
        df = df.sort_values('cal_per_100g', ascending=True)
    return df.head(n).to_dict('records')

def recommend_exercises(df_ex, goal, n=4):
    df2 = df_ex[df_ex['goal_tag'].str.contains(goal, case=False, na=False)]
    if df2.empty:
        df2 = df_ex.copy()
    return df2.head(n).to_dict('records')

# -------------------------
# Streamlit UI
# -------------------------
st.title("Virtual Health Check & Diet Planner")

st.header("Enter your details")
with st.form("user_form"):
    age = st.number_input("Age (years)", min_value=10, max_value=100, value=20)
    gender = st.selectbox("Gender", ["Female", "Male"])
    height_cm = st.number_input("Height (cm)", min_value=100, max_value=220, value=160)
    weight_kg = st.number_input("Weight (kg)", min_value=20, max_value=200, value=50)
    activity = st.selectbox("Activity Level", ["Sedentary","Lightly Active","Moderately Active","Very Active"])
    goal = st.selectbox("Goal", ["Lose Weight","Gain Weight","Build Muscle","Improve Flexibility","Better Posture","Maintain"])
    diet = st.selectbox("Diet Preference", ["Vegetarian","Non-Vegetarian","Vegan"])
    submitted = st.form_submit_button("Calculate My Plan")

if submitted:
    # calculations
    bmi = calc_bmi(weight_kg, height_cm)
    bmr = calc_bmr(age, gender, weight_kg, height_cm)
    tdee = bmr * activity_factor(activity)
    targ_cal = target_calories(bmr, activity, goal)

    # Show results
    st.subheader("Your Health Numbers")
    st.write(f"**BMI:** {bmi:.2f}" if bmi else "Invalid height")
    st.write(f"**BMR:** {bmr:.0f} kcal/day")
    st.write(f"**TDEE (maintenance):** {tdee:.0f} kcal/day")
    st.write(f"**Target Calories (for {goal}):** {targ_cal:.0f} kcal/day")

    # load CSVs and recommend
    foods = load_foods()
    exercises = load_exercises()

    want_high_cal = goal in ("Gain Weight","Build Muscle")
    food_reco = recommend_foods(foods, diet, want_high_cal=want_high_cal, n=4)
    ex_reco = recommend_exercises(exercises, goal, n=4)

    st.subheader("Diet Suggestions (sample)")
    for item in food_reco:
        st.write(f"- {item.get('name')} — {item.get('cal_per_100g')} kcal /100g, {item.get('protein_g')} g protein")

    st.subheader("Exercise Suggestions (sample)")
    for ex in ex_reco:
        st.write(f"- {ex.get('name')} — {ex.get('duration_min')} min — {ex.get('notes')}")
