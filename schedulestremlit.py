import streamlit as st
import pandas as pd
import random
from datetime import datetime, timedelta
from collections import defaultdict
from io import BytesIO
import matplotlib.pyplot as plt

# ---------- Helper Functions ----------
def generate_roster(interns, start_date, end_date, seed=42):
    random.seed(seed)
    date_range = pd.date_range(start=start_date, end=end_date)
    shifts = pd.DataFrame(index=date_range, columns=["Cover", "Late"])
    shift_counts = defaultdict(lambda: {"Cover": 0, "Late": 0, "FreeWeekends": 0})

    # Weekend pairs: Saturday & Sunday
    weekends = [d for d in date_range if d.weekday() in [5, 6]]
    weekend_pairs = [
        (d, d + timedelta(days=1))
        for d in weekends if d.weekday() == 5 and (d + timedelta(days=1)) in date_range
    ]
    random.shuffle(weekend_pairs)

    for pair in weekend_pairs:
        free_interns = [i for i in interns if i not in shifts.loc[pair[0]:pair[1]].values]
        if free_interns:
            intern = min(free_interns, key=lambda i: shift_counts[i]["FreeWeekends"])
            shift_counts[intern]["FreeWeekends"] += 1
            shifts.at[pair[0], "Cover"] = shifts.at[pair[0], "Late"] = intern
            shifts.at[pair[1], "Cover"] = shifts.at[pair[1], "Late"] = intern

    for day in date_range:
        if pd.isna(shifts.at[day, "Cover"]):
            available = [i for i in interns if i not in shifts.loc[day].values]
            cover_candidate = sorted(available, key=lambda i: shift_counts[i]["Cover"])[0]
            shifts.at[day, "Cover"] = cover_candidate
            shift_counts[cover_candidate]["Cover"] += 1
        if pd.isna(shifts.at[day, "Late"]):
            available = [i for i in interns if i not in shifts.loc[day].values]
            late_candidate = sorted(available, key=lambda i: shift_counts[i]["Late"])[0]
            shifts.at[day, "Late"] = late_candidate
            shift_counts[late_candidate]["Late"] += 1

    summary = pd.DataFrame(shift_counts).T.sort_index()
    summary["TotalHours"] = summary["Cover"] * 24 + summary["Late"] * 12
    return shifts, summary

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=True, sheet_name='Roster')
    return output.getvalue()

# ---------- Streamlit UI ----------
st.set_page_config(page_title="Intern Roster Scheduler", layout="centered")
st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    h1 { color: #004466; }
    .stButton>button { background-color: #0073e6; color: white; }
    </style>
""", unsafe_allow_html=True)

st.title("🩺 Intern Shift Scheduler")
st.markdown("Schedule Cover (24h) and Late (12h) shifts, fairly and simply.")

intern_input = st.text_area("👥 Enter intern names (one per line):")
start_date = st.date_input("📅 Start Date", datetime.today())
end_date = st.date_input("📅 End Date", datetime.today() + timedelta(days=30))

if st.button("🚀 Generate Roster"):
    interns = [name.strip() for name in intern_input.split("\n") if name.strip()]
    if not interns:
        st.warning("⚠️ Please enter at least one intern.")
    elif start_date > end_date:
        st.warning("⚠️ Start date must be before end date.")
    else:
        roster_df, summary_df = generate_roster(interns, start_date, end_date)

        st.subheader("📋 Roster Table")
        st.dataframe(roster_df)

        st.download_button(
            label="📥 Download Roster as Excel",
            data=to_excel(roster_df),
            file_name="intern_roster.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.subheader("📊 Summary of Shifts")
        st.dataframe(summary_df)

        # Bar chart: Total Hours
        st.subheader("🕒 Total Hours per Intern")
        fig1, ax1 = plt.subplots()
        summary_df.sort_values("TotalHours", ascending=True)["TotalHours"].plot(
            kind="barh", ax=ax1, color="#004466")
        ax1.set_xlabel("Hours")
        ax1.set_ylabel("Intern")
        st.pyplot(fig1)

        # Bar chart: Free Weekends
        st.subheader("🌴 Free Weekends per Intern")
        fig2, ax2 = plt.subplots()
        summary_df.sort_values("FreeWeekends", ascending=True)["FreeWeekends"].plot(
            kind="barh", ax=ax2, color="#008060")
        ax2.set_xlabel("Free Weekends")
        ax2.set_ylabel("Intern")
        st.pyplot(fig2)

st.markdown("""
---
💡 *Created with ❤️ by Dylan*
""")
