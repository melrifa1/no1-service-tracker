# ================================
# app.py (Streamlit main — updated with top-level admin tabs)
# ================================
import time
import pandas as pd
import datetime
from datetime import date, timedelta
import streamlit as st
from passlib.hash import bcrypt as bcrypt_hasher
try:
    from supabase import create_client
except Exception as e:
    st.stop()

import pytz
central_tz = pytz.timezone("US/Central")
UTC_TZ = pytz.utc


def return_start_and_end(key=None):
    today_r = datetime.datetime.now(central_tz)

    # Date selection
    start_date = st.date_input("From (date)", value=(today_r - timedelta(days=7)).date(), key=f"rf_{key}")
    end_date = st.date_input("To (date)", value=today_r.date(), key=f"rt_{key}")

    # Time selection
    start_time = st.time_input("From (time)", value=datetime.time(0, 0), key=f"rf_time_{key}")  # default midnight
    end_time = st.time_input("To (time)", value=datetime.time(23, 59, 59), key=f"rt_time_{key}")  # default end of day

    # Merge into datetime
    start_date_time = datetime.datetime.combine(start_date, start_time)
    end_date_time = datetime.datetime.combine(end_date, end_time)
    return start_date_time, end_date_time

# ===============================
# Utility function for fetching logs
# ===============================
def fetch_service_logs(
    user_id=None, start_date=None, end_date=None, user_filter=None, all_users=None, all_servs=None
):
    """
    Fetch service logs from Supabase and compute user earnings.

    Args:
        user_id (str): current user ID (optional, for user view)
        start_date (date): filter from
        end_date (date): filter to
        user_filter (str): username filter (for admin)
        all_users (list): list of all users dicts (for admin)
    Returns:
        list of dicts: each dict contains all fields for display
    """
    q = sb.table("service_logs").select(
        "qty, tip_cents, amount_cents, served_at, payment_type, users(username, service_percentage)"
    )

    if start_date:
        q = q.gte("served_at", start_date.isoformat())
    if end_date:
        q = q.lte("served_at", end_date.isoformat())
    # user filter for admin view
    if user_filter and all_users and user_filter != "All":
        uid = next(u["id"] for u in all_users if u["username"] == user_filter)
        q = q.eq("user_id", uid)
    elif user_id:
        q = q.eq("user_id", user_id)

    data = q.order("served_at").execute().data
    if not data:
        return []

    rows = []
    for r in data:
        # price = r["services"]["price_cents"] / 100.0
        amount = r["amount_cents"] * r["qty"]
        user_percent = r["users"]["service_percentage"]
        service_earning = amount * (user_percent / 100.0)
        rows.append({
            "Date & Time": pd.to_datetime(r["served_at"]).tz_convert("UTC").astimezone(central_tz).strftime("%Y-%m-%d %I:%M:%S %p"),
            "User": r["users"]["username"],
            "Qty": r["qty"],
            "User Percent": user_percent,
            "Service Amount": r["amount_cents"],
            "Total Service Amount": amount,
            "Tip": r["tip_cents"],
            "Payment Type": r["payment_type"],
            "Total": service_earning + (r["tip_cents"])
        })

    return rows



st.set_page_config(page_title="Service Tracker", layout="wide")
# ---- Utilities

def get_supabase():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"].get("service_key") or st.secrets["supabase"].get("anon_key")
    return create_client(url, key)

sb = get_supabase()
SESSION_KEY = "auth_user"

# ---------------- CACHING ----------------

def get_user(username: str):
    """Fetch user record from Supabase"""
    recs = (
        sb.table("users")
        .select("id, username, password_hash, role, is_active")
        .eq("username", username)
        .limit(1)
        .execute()
        .data
    )
    return recs[0] if recs else None

def login(username: str, password: str):
    u = get_user(username)
    if not u:
        return False, "Invalid username or password"
    if not u.get("is_active", True):
        return False, "Account disabled"
    if not bcrypt_hasher.verify(password, u["password_hash"]):
        return False, "Invalid username or password"

    user_obj = {"id": u["id"], "username": u["username"], "role": u["role"]}
    st.session_state[SESSION_KEY] = user_obj  # SESSION only, no localStorage
    return True, None

def logout():
    st.session_state.pop(SESSION_KEY, None)
    st.rerun()

def require_auth():
    return st.session_state.get(SESSION_KEY)



# ---------------- UI ----------------
# st.title("🚑 Service Tracker")

user = require_auth()

if not user:
    st.subheader("Login")
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        if submit:
            success, msg = login(username, password)
            if success:
                st.success("Login successful ✅. Please refresh if not redirected.")
                st.rerun()
            else:
                st.error(msg)
    st.stop()

# If logged in
st.sidebar.success(f"Logged in as: {user['username']}")
if st.sidebar.button("Logout"):
    logout()
    st.rerun()

is_admin = False
if user:
    is_admin = user["role"] == "admin"

st.title("💼 Services & Tips Tracker")

main_tabs = ["My Daily Tracker"]
if is_admin:
    main_tabs += ["Log Services", "Users Management", "Reports", "Edit Services"]

tab = st.sidebar.radio("Navigation", main_tabs, key="active_tab")
active_tab_index = main_tabs.index(st.session_state.active_tab)

if st.sidebar.button("🔄 Refresh"):
    st.rerun()

# --------------- My Daily Tracker (User)
if tab == "My Daily Tracker":
    st.subheader("My Daily Tracker")
    start, end = return_start_and_end(key="daily_tracker")
    start_utc = start.astimezone(UTC_TZ)
    end_utc = end.astimezone(UTC_TZ)

    rows = fetch_service_logs(user_id=user["id"], start_date=start_utc, end_date=end_utc)

    if not rows:
        st.info("No entries in range.")
    else:
        df = pd.DataFrame(rows).sort_values("Date & Time", ascending=False)
        df.index = df.index + 1
        st.dataframe(df.drop(columns=["User"]))  # only show relevant columns to user

        # Show totals by payment type
        st.markdown("#### Totals by Payment Type")
        by_type = df.groupby(["Payment Type", "User Percent"])[["Total"]].sum().reset_index()
        st.dataframe(by_type)

        # Show grand totals
        totals = df[["Total Service Amount", "Tip", "Total"]].sum().to_dict()
        st.metric("Total Service Amount", f"{totals['Total Service Amount']:,.2f}")
        st.metric("Total Tips", f"{totals['Tip']:,.2f}")
        st.metric("Grand Total", f"{totals['Total']:,.2f}")

# --------------- Admin: Users & Services
if is_admin:
    # --------------- Log Services (User)
    if tab == "Log Services":
        st.subheader("Log Completed Services")
        # Fetch active users
        all_users = sb.table("users").select("id, username").eq("is_active", True).order("username").execute().data
        user_map = {u["username"]: u["id"] for u in all_users}
        with st.form("log_service_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                served_at = datetime.datetime.now(UTC_TZ)
                qty = 1
                amount_str = st.text_input("Service Amount")
                tip_str = st.text_input("Tip")
                payment_type = st.radio(
                    "Payment Type",
                    ["Credit", "Cash"],
                    index=0,  # Default to "Credit"
                    horizontal=True
                )
                selected_user = st.selectbox(
                    "Select user",
                    options=[u["username"] for u in all_users],
                    index=[i for i,u in enumerate(all_users) if u["id"] == user["id"]][0]
                )
                served_date = st.date_input("Service Date (optional)", value=None)
                served_time = st.time_input("Service Time (optional)", value=None)
            submitted = st.form_submit_button("Save entry", type="primary")

            if submitted:
                # Determine served_at
                if served_date and served_time:
                    served_at = datetime.datetime.combine(served_date, served_time)
                    served_at = served_at.replace(tzinfo=UTC_TZ)
                else:
                    served_at = datetime.datetime.now(UTC_TZ)
                try:
                    amount = float(amount_str) if amount_str.strip() else None
                except Exception:
                    st.error("Service Amount must be a number.")
                    amount = None

                try:
                    tip = float(tip_str) if tip_str.strip() else 0.0
                except Exception:
                    st.error("Tip must be a number.")
                    tip = 0.0

                # Validation
                if qty is None or qty <= 0:
                    st.error("Quantity is required and must be greater than zero.")
                elif amount is None or amount <= 0:
                    st.error("Service Amount is required and must be greater than zero.")
                elif tip is None or tip < 0:
                    st.error("Tip cannot be negative.")
                else:
                    # Save entry
                    sb.table("service_logs").insert({
                        "user_id": user_map[selected_user],
                        "served_at": served_at.isoformat(),
                        "qty": int(qty),
                        "amount_cents": amount,
                        "tip_cents": tip,
                        "payment_type": payment_type
                    }).execute()
                    st.success("Saved!")
                    time.sleep(0.5)
                    st.rerun()

    if tab == "Users Management":
        st.markdown("### Users")
        with st.expander("Add user"):
            nuser = st.text_input("Username", key="nu")
            npass = st.text_input("Temp password", key="np", type="password")
            nrole = st.selectbox("Role", options=["user", "admin"], index=0)
            npercent = st.number_input("Service %", min_value=0, max_value=100, value=100, step=1,
                                       help="Percentage of service price this user will earn")
            if st.button("Create user"):
                if not nuser or not npass:
                    st.error("Username & password required")
                else:
                    sb.table("users").insert({
                        "username": nuser,
                        "password_hash": bcrypt_hasher.hash(npass),
                        "role": nrole,
                        "service_percentage": npercent
                    }).execute()
                    st.success("User created")
        ulist = sb.table("users").select("id, username, role, service_percentage, is_active, created_at").order("created_at", desc=True).execute().data
        df = pd.DataFrame(ulist)[["username","role","is_active","service_percentage", "created_at"]]
        df.index = df.index + 1
        st.dataframe(df)

        st.markdown("### Change user password")
        all_users = sb.table("users").select("username, service_percentage").execute().data
        target_user = st.selectbox("Pick user", [u["username"] for u in all_users])
        current_percent = next(u["service_percentage"] for u in all_users if u["username"] == target_user)
        new_pass = st.text_input("New password", type="password")
        new_pin = st.text_input("New PIN", type="password", placeholder="Leave blank to keep current")
        new_percent = st.number_input(
            "Service %",
            min_value=0,
            max_value=100,
            value=current_percent,  # pre-fill with current value
            step=1
        )
        if st.button("Update user"):
            update_values = {"service_percentage": new_percent}
            if new_pass:
                update_values["password_hash"] = bcrypt_hasher.hash(new_pass)
            if new_pin:
                update_values["pin"] = new_pin
            sb.table("users").update(update_values).eq("username", target_user).execute()
            st.success("User updated")
        st.divider()
        st.markdown("### Delete user")
        del_user = st.selectbox("User to delete", [u["username"] for u in sb.table("users").select("username").order("username").execute().data], key="du")
        if st.button("Delete user", type="secondary"):
            sb.table("users").delete().eq("username", del_user).execute()
            st.success("User deleted (and their logs if any)")

    # --------------- Admin: Reports
    if tab == "Reports":
        st.markdown("### Reports")

        # ----------------- Session state for tab & report
        if "active_tab_index" not in st.session_state:
            st.session_state.active_tab_index = 3  # Reports tab index
        if "run_report" not in st.session_state:
            st.session_state.run_report = False

        # Detect tab switch (reset report flag)
        if st.session_state.active_tab_index != 3:
            st.session_state.run_report = False
        st.session_state.active_tab_index = 3

        # ----------------- Fetch users
        all_users = sb.table("users").select("id, username").eq("is_active", True).order("username").execute().data

        # ----------------- Quick period filters
        colf = st.columns(5)
        now_central = datetime.datetime.now(central_tz)
        today = now_central.replace(hour=0, minute=0, second=0, microsecond=0)  # start of today in Central
        start, end = None, None

        with colf[0]:
            period = st.selectbox("Quick range", ["This week", "Last week", "This month", "Last month", "Custom"],
                                  index=0)
            if period != "Custom":
                if period == "This week":
                    # Sunday of this week
                    start = today - timedelta(days=today.weekday() + 1 if today.weekday() < 6 else 0)
                    end = start + timedelta(days=6)
                elif period == "Last week":
                    # Sunday of last week
                    end = today - timedelta(days=today.weekday() + 2 if today.weekday() < 6 else 1)
                    start = end - timedelta(days=6)
                elif period == "This month":
                    start = today.replace(day=1)
                    end = today + timedelta(days=1)
                elif period == "Last month":
                    first_this = today.replace(day=1)
                    last_month_end = first_this - timedelta(days=1)
                    start = last_month_end.replace(day=1)
                    end = last_month_end
                if end:
                    end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
            else:
                start, end = return_start_and_end()

        with colf[1]:
            user_filter = st.selectbox("User", ["All"] + [u["username"] for u in all_users])
        with colf[2]:
            st.write("")
            st.write("")
            if st.button("Run report", type="primary"):
                st.session_state.run_report = True

        # ----------------- Display report only if run_report is True
        if st.session_state.run_report:
            start_utc = start.astimezone(UTC_TZ)
            end_utc = end.astimezone(UTC_TZ)
            rows = fetch_service_logs(
                start_date=start_utc,
                end_date=end_utc,
                user_filter=user_filter,
                all_users=all_users,
            )

            if not rows:
                st.info("No data for selection")
            else:
                df = pd.DataFrame(rows).sort_values("Date & Time", ascending=False)
                df.index = df.index + 1
                st.dataframe(df)

                # Summary per user
                grp_user = df.groupby("User")[["Qty"]].sum().reset_index().rename(columns={"Qty": "Services Completed"})
                st.markdown("#### Services Completed per User")
                st.dataframe(grp_user)

                # Summary by user and payment type
                st.markdown("#### Totals per User & Payment Type")
                sums = df.groupby(["User", "Payment Type", "User Percent"])[["Service Amount", "Tip", "Total"]].sum().reset_index()
                df_renamed = sums.rename(columns={'Service Amount': 'Total Service Amount', 'Tip': 'Total Tip', 'Total': 'Total with Percent + tip'})
                st.dataframe(df_renamed)

                st.markdown("#### Overall Totals per User")
                user_summary = df.groupby(["User", "User Percent"]).agg(
                    total_services=("Qty", "sum"),
                    total_tip=("Tip", "sum"),
                    total_service=("Service Amount", "sum")
                ).reset_index()

                # Apply percentage calculation
                user_summary["Total with Percent + Tip"] = (
                        user_summary["total_service"] * (user_summary["User Percent"] / 100.0)
                        + user_summary["total_tip"]
                )

                # Rename for clarity
                user_summary = user_summary.rename(columns={
                    "User": "User",
                    "User Percent": "Percentage",
                    "total_services": "Total Services",
                    "total_tip": "Total Tip",
                    "total_service": "Total Service Amount"
                })

                st.dataframe(user_summary)

                st.download_button("Download CSV", data=df.to_csv(index=False), file_name="report.csv", mime="text/csv")

    if tab == "Edit Services":
        st.markdown("### Edit Services")
        st.caption("Filter, edit, or delete service logs")

        # ----------------- Fetch users
        all_users = sb.table("users").select("id, username").eq("is_active", True).order("username").execute().data
        user_map = {u["username"]: u["id"] for u in all_users}
        id_to_username = {u["id"]: u["username"] for u in all_users}

        # ----------------- Filter by user & date
        colf = st.columns(2)
        with colf[0]:
            selected_user = st.selectbox("Filter by user", ["All"] + [u["username"] for u in all_users], index=0)
        with colf[1]:
            start_date, end_date = return_start_and_end(key="edit_services")

        # Convert to UTC for Supabase query
        start_utc = start_date.astimezone(UTC_TZ)
        end_utc = end_date.astimezone(UTC_TZ)

        # ----------------- Fetch all services in one query
        query = sb.table("service_logs").select(
            "id, user_id, served_at, qty, amount_cents, tip_cents, payment_type"
        ).gte("served_at", start_utc.isoformat()).lte("served_at", end_utc.isoformat())
        if selected_user != "All":
            query = query.eq("user_id", user_map[selected_user])
        raw_services = query.order("served_at").execute().data

        if not raw_services:
            st.info("No service logs found for the selected filters.")
        else:
            # Build service picker options
            options = {}
            for svc in raw_services:
                served_at_central = datetime.datetime.fromisoformat(svc["served_at"]).astimezone(central_tz)
                served_at_str = served_at_central.strftime("%Y-%m-%d %I:%M %p")
                username = id_to_username.get(svc["user_id"], "Unknown")
                label = f"{served_at_str} — {username} — {svc['amount_cents']} — {svc['tip_cents']}"
                options[label] = svc["id"]

            st.markdown("#### Edit or Delete a Service")
            selected_label = st.selectbox("Pick a service", list(options.keys()))
            service_id = options[selected_label]

            # Fetch selected service from already fetched list
            svc = next(s for s in raw_services if s["id"] == service_id)
            served_at_central = datetime.datetime.fromisoformat(svc["served_at"]).astimezone(central_tz)

            # Editable fields
            new_amount = st.number_input("Service Amount", min_value=0.0, value=svc["amount_cents"])
            new_tip = st.number_input("Tip", min_value=0.0, value=svc["tip_cents"])
            new_payment_type = st.radio(
                "Payment Type",
                ["Credit", "Cash"],
                index=0 if svc["payment_type"] == "Credit" else 1,
                horizontal=True
            )

            new_served_at_date = st.date_input("Service Date", value=served_at_central.date())
            new_served_at_time = st.time_input("Service Time (AM/PM)", value=served_at_central.time())
            st.caption(f"Current Time (AM/PM): {served_at_central.strftime('%I:%M:%S %p')}")

            col_edit = st.columns(2)
            with col_edit[0]:
                if st.button("Update Service"):
                    new_served_at = central_tz.localize(
                        datetime.datetime.combine(new_served_at_date, new_served_at_time)
                    ).astimezone(UTC_TZ)
                    sb.table("service_logs").update({
                        "amount_cents": new_amount,
                        "tip_cents": new_tip,
                        "payment_type": new_payment_type,
                        "served_at": new_served_at.isoformat()
                    }).eq("id", service_id).execute()
                    st.success("Service updated!")
                    st.rerun()

            with col_edit[1]:
                if st.button("Delete Service"):
                    sb.table("service_logs").delete().eq("id", service_id).execute()
                    st.success("Service deleted!")
                    st.rerun()
