import streamlit as st
import pandas as pd
import random
from datetime import datetime, timedelta
from collections import defaultdict
from io import BytesIO
import matplotlib.pyplot as plt
import plotly.express as px

# ---------- South African Public Holidays 2025 ----------
SA_PUBLIC_HOLIDAYS_2025 = [
    "2025-01-01", "2025-03-21", "2025-04-18", "2025-04-21", "2025-04-27", "2025-05-01",
    "2025-06-16", "2025-08-09", "2025-09-24", "2025-12-16", "2025-12-25", "2025-12-26"
]
SA_PUBLIC_HOLIDAYS_2025 = set(pd.to_datetime(SA_PUBLIC_HOLIDAYS_2025))

# ---------- Helper Functions ----------
def select_optimised_leave(interns, leave_preferences, start_date, end_date):
    assigned_weeks = {}
    final_leave = []
    mondays = list(pd.date_range(start=start_date, end=end_date - timedelta(days=4), freq='W-MON'))

    for week_start in mondays:
        candidates = []
        for name in interns:
            if name in [entry["name"] for entry in final_leave]:
                continue
            prefs = leave_preferences[name]
            if prefs["first"] - timedelta(days=prefs["first"].weekday()) == week_start:
                candidates.append((name, "First"))
            elif prefs["second"] - timedelta(days=prefs["second"].weekday()) == week_start:
                candidates.append((name, "Second"))

        if candidates:
            name, choice = candidates[0]
            final_leave.append({"name": name, "start": week_start, "choice": choice})
        else:
            remaining = [name for name in interns if name not in [entry["name"] for entry in final_leave]]
            if remaining:
                final_leave.append({"name": remaining[0], "start": week_start, "choice": "Assigned"})

    return final_leave

def generate_roster(interns, start_date, end_date, previous_summary=None, leave_dates=None, seed=42):
    random.seed(seed)
    date_range = pd.date_range(start=start_date, end=end_date)
    shifts = pd.DataFrame(index=date_range, columns=["Cover", "Late"])

    shift_counts = defaultdict(lambda: {"Cover": 0, "Late": 0, "FreeWeekends": 0})
    if previous_summary is not None:
        for intern in previous_summary.index:
            shift_counts[intern]["Cover"] = int(previous_summary.at[intern, "Cover"])
            shift_counts[intern]["Late"] = int(previous_summary.at[intern, "Late"])
            shift_counts[intern]["FreeWeekends"] = int(previous_summary.at[intern, "FreeWeekends"]) if "FreeWeekends" in previous_summary.columns else 0

    leave_map = defaultdict(set)
    leave_entries = []
    if leave_dates is not None:
        for entry in leave_dates:
            name = entry["name"]
            start = entry["start"]
            days = [start + timedelta(days=i) for i in range(5)]
            leave_map[name].update(days)
            leave_entries.append({"name": name, "start": start, "end": start + timedelta(days=4), "choice": entry["choice"]})

    weekends = [d for d in date_range if d.weekday() in [5, 6]]
    holiday_days = [d for d in date_range if d in SA_PUBLIC_HOLIDAYS_2025]
    off_day_candidates = sorted(set(weekends + holiday_days))
    off_day_pairs = [
        (d, d + timedelta(days=1)) for d in off_day_candidates
        if d.weekday() == 5 and (d + timedelta(days=1)) in off_day_candidates
    ]
    random.shuffle(off_day_pairs)

    for pair in off_day_pairs:
        free_interns = [i for i in interns if i not in shifts.loc[pair[0]:pair[1]].values and not (pair[0] in leave_map[i] or pair[1] in leave_map[i])]
        if free_interns:
            intern = min(free_interns, key=lambda i: shift_counts[i]["FreeWeekends"])
            shift_counts[intern]["FreeWeekends"] += 1
            shifts.at[pair[0], "Cover"] = shifts.at[pair[0], "Late"] = intern
            shifts.at[pair[1], "Cover"] = shifts.at[pair[1], "Late"] = intern

    for day in date_range:
        available = [i for i in interns if day not in leave_map[i] and i not in shifts.loc[day].values]

        if pd.isna(shifts.at[day, "Cover"]):
            cover_candidate = sorted(available, key=lambda i: shift_counts[i]["Cover"])[0]
            shifts.at[day, "Cover"] = cover_candidate
            shift_counts[cover_candidate]["Cover"] += 1

        available = [i for i in interns if day not in leave_map[i] and i not in shifts.loc[day].values]

        if pd.isna(shifts.at[day, "Late"]):
            late_candidate = sorted(available, key=lambda i: shift_counts[i]["Late"])[0]
            shifts.at[day, "Late"] = late_candidate
            shift_counts[late_candidate]["Late"] += 1

    summary = pd.DataFrame(shift_counts).T.sort_index()
    summary['LeaveChoice'] = summary.index.map(
        lambda name: next((entry["choice"] for entry in leave_entries if entry["name"] == name), "None")
    )
    summary["TotalHours"] = summary["Cover"] * 24 + summary["Late"] * 12
    return shifts, summary, leave_entries

def to_excel(roster_df, summary_df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        roster_df.to_excel(writer, index=True, sheet_name='Roster')
        summary_df.to_excel(writer, index=True, sheet_name='Summary')
    return output.getvalue()

st.set_page_config(page_title="Intern Roster Scheduler", layout="centered")
st.title("🩺 Intern Shift Scheduler")
st.markdown("Schedule Cover (24h) and Late (12h) shifts fairly, with public holidays and leave.")

intern_input = st.text_area("👥 Enter intern names (one per line):")
start_date = st.date_input("📅 Start Date", datetime.today())
end_date = st.date_input("📅 End Date", datetime.today() + timedelta(days=30))

uploaded_file = st.file_uploader("📤 Upload Previous Summary (optional, CSV only)", type=["csv"])
previous_summary = None
if uploaded_file is not None:
    previous_summary = pd.read_csv(uploaded_file, index_col=0)

st.subheader("🌴 Leave Preferences (Each gets 1 week)")
leave_preferences = {}
intern_names_preview = [name.strip() for name in intern_input.split("\n") if name.strip()]
if intern_names_preview:
    for name in intern_names_preview:
        with st.expander(f"🗓️ Leave preferences for {name}"):
            first = st.date_input(f"First choice leave week for {name}", value=start_date, key=f"leave_first_{name}")
            second = st.date_input(f"Second choice leave week for {name}", value=start_date + timedelta(days=7), key=f"leave_second_{name}")
            leave_preferences[name] = {"first": first, "second": second}

if st.button("🚀 Generate Roster"):
    interns = intern_names_preview
    if not interns:
        st.warning("⚠️ Please enter at least one intern.")
    elif start_date > end_date:
        st.warning("⚠️ Start date must be before end date.")
    else:
        optimised_leave = select_optimised_leave(interns, leave_preferences, start_date, end_date)
        roster_df, summary_df, leave_entries = generate_roster(interns, start_date, end_date, previous_summary, optimised_leave)

        st.subheader("📋 Roster Table")
        st.dataframe(roster_df)

        st.download_button(
            label="📥 Download Full Excel File",
            data=to_excel(roster_df, summary_df),
            file_name="intern_roster.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.subheader("📊 Summary of Shifts")
        st.dataframe(summary_df)

        st.subheader("🕒 Total Hours per Intern")
        fig1, ax1 = plt.subplots()
        summary_df.sort_values("TotalHours", ascending=True)["TotalHours"].plot(
            kind="barh", ax=ax1, color="#004466")
        ax1.set_xlabel("Hours")
        ax1.set_ylabel("Intern")
        st.pyplot(fig1)

        st.subheader("🌴 Free Weekends per Intern")
        fig2, ax2 = plt.subplots()
        summary_df.sort_values("FreeWeekends", ascending=True)["FreeWeekends"].plot(
            kind="barh", ax=ax2, color="#008060")
        ax2.set_xlabel("Free Weekends")
        ax2.set_ylabel("Intern")
        st.pyplot(fig2)

        st.subheader("📆 Visual Calendar of Shifts and Leave")
        calendar_df = roster_df.copy().reset_index().melt(id_vars=["index"], value_vars=["Cover", "Late"], var_name="ShiftType", value_name="Intern")
        calendar_df.rename(columns={"index": "Date"}, inplace=True)
        calendar_df["EndDate"] = calendar_df["Date"] + pd.Timedelta(days=1)

        for leave_entry in leave_entries:
            name = leave_entry["name"]
            start = leave_entry["start"]
            end = leave_entry["end"]
            choice_label = leave_entry["choice"]
            for day in pd.date_range(start, end):
                calendar_df = pd.concat([calendar_df, pd.DataFrame({
                    "Date": [day],
                    "EndDate": [day + pd.Timedelta(days=1)],
                    "ShiftType": [f"Leave ({choice_label})"],
                    "Intern": [name]
                })])

        fig3 = px.timeline(
            calendar_df,
            x_start="Date",
            x_end="EndDate",
            y="Intern",
            color="ShiftType",
            title="Roster Calendar",
            color_discrete_map={
                "Cover": "#004466",
                "Late": "#3399ff",
                "Leave (First)": "#e67676",
                "Leave (Second)": "#f4b400",
                "Leave (Assigned)": "#999999"
            },
            height=600
        )

        fig3.update_yaxes(autorange="reversed")
        fig3.update_layout(
    xaxis=dict(
        tickformat="%a",
        tickangle=-45,
        dtick=86400000.0
    ),
    margin=dict(l=20, r=20, t=40, b=80),
    bargap=0.2
)
        fig3.update_layout(
            xaxis=dict(
                tickformat="%a
%d-%b",
                tickangle=-45,
                dtick=86400000.0 * 1  # daily ticks
            ),
            margin=dict(l=20, r=20, t=40, b=80),
            bargap=0.2
        )
        st.plotly_chart(fig3, use_container_width=True)

st.markdown("""
---
💡 *Created with ❤️ by Dylan*
""")
