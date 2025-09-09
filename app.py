# ================================
# app.py (Streamlit main — updated with top-level admin tabs)
# ================================
import time
import pandas as pd
import datetime
from datetime import date, timedelta
import streamlit as st
from passlib.hash import bcrypt as bcrypt_hasher
from dateutil.relativedelta import relativedelta
from PIL import Image
import requests
try:
    from supabase import create_client
except Exception as e:
    st.stop()

from streamlit_cookies_manager import EncryptedCookieManager
import json


def return_start_and_end(key=None):
    today = datetime.datetime.now()

    # Date selection
    start_date = st.date_input("From (date)", value=(today - timedelta(days=7)).date(), key=f"rf_{key}")
    end_date = st.date_input("To (date)", value=today.date(), key=f"rt_{key}")

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
    user_id=None, start_date=None, end_date=None, user_filter=None, svc_filter=None, all_users=None, all_servs=None
):
    """
    Fetch service logs from Supabase and compute user earnings.

    Args:
        user_id (str): current user ID (optional, for user view)
        start_date (date): filter from
        end_date (date): filter to
        user_filter (str): username filter (for admin)
        svc_filter (str): service name filter (for admin)
        all_users (list): list of all users dicts (for admin)
        all_servs (list): list of all services dicts (for admin)

    Returns:
        list of dicts: each dict contains all fields for display
    """
    q = sb.table("service_logs").select(
        "qty, tip_cents, served_at, users(username, service_percentage), services(name, price_cents, is_active)"
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

    # service filter for admin view
    if svc_filter and all_servs and svc_filter != "All":
        sid = next(s["id"] for s in all_servs if s["name"] == svc_filter)
        q = q.eq("service_id", sid)

    data = q.order("served_at").execute().data
    if not data:
        return []

    rows = []
    for r in data:
        price = r["services"]["price_cents"] / 100.0
        amount = price * r["qty"]
        user_percent = r["users"]["service_percentage"]
        service_earning = amount * (user_percent / 100.0)
        rows.append({
            "Date & Time": pd.to_datetime(r["served_at"]),
            "User": r["users"]["username"],
            "Service": r["services"]["name"],
            "Service Price": price,
            "Inactive": not r["services"]["is_active"],
            "Qty": r["qty"],
            "User Percent": user_percent,
            "Service Amount": amount,
            "Tip": r["tip_cents"] / 100.0,
            "Total": service_earning + (r["tip_cents"] / 100.0)
        })

    return rows



st.set_page_config(page_title="Service Tracker", layout="wide")
# ---- Utilities

def get_supabase():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"].get("service_key") or st.secrets["supabase"].get("anon_key")
    return create_client(url, key)

sb = get_supabase()

# Secure cookies
cookies = EncryptedCookieManager(
    prefix="svc_tracker",
    password=st.secrets["cookies"]["password"],  # store in st.secrets
)
if not cookies.ready():
    st.stop()

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


# ---------------- AUTH ----------------
def login(username: str, password: str):
    u = get_user(username)
    if not u:
        return False, "Invalid username or password"
    if not u.get("is_active", True):
        return False, "Account disabled"
    if not bcrypt_hasher.verify(password, u["password_hash"]):
        return False, "Invalid username or password"

    user_obj = {"id": u["id"], "username": u["username"], "role": u["role"]}
    st.session_state[SESSION_KEY] = user_obj
    cookies["auth_user"] = json.dumps(user_obj)
    cookies.save()
    return True, None


def logout():
    st.session_state.pop(SESSION_KEY, None)
    cookies["auth_user"] = ""
    cookies.save()


def require_auth():
    if SESSION_KEY in st.session_state:
        return st.session_state[SESSION_KEY]

    cookie_user = cookies.get("auth_user")
    if cookie_user:
        try:
            user_obj = json.loads(cookie_user)
            st.session_state[SESSION_KEY] = user_obj
            return user_obj
        except Exception:
            return None
    return None


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


is_admin = user["role"] == "admin"

st.title("💼 Services & Tips Tracker")

main_tabs = ["Log Services", "My Daily Tracker"]
if is_admin:
    main_tabs += ["Users & Services", "Reports", "Data Admin"]

chosen = st.tabs(main_tabs)

# --------------- Log Services (User)
with chosen[0]:
    st.subheader("Log Completed Services")
    col1, col2 = st.columns(2)
    with col1:
        served_date = st.date_input("Date", value=datetime.datetime.now().date(), max_value=datetime.datetime.now().date())
        served_time = st.time_input("Time")

        # Combine into a datetime
        served_at = datetime.datetime.combine(served_date, served_time)
        qty = st.number_input("Quantity", min_value=1, step=1, value=1)
        tip = st.number_input("Tip (in your currency)", min_value=0.0, step=1.0, value=0.0)
    services = sb.table("services").select("id, name, price_cents, is_active").eq("is_active", True).order("name").execute().data
    names = [s["name"] for s in services]
    svc = st.selectbox("Service", options=names)
    svc_row = next((s for s in services if s["name"] == svc), None)
    if svc_row:
        st.caption(f"Price: {svc_row['price_cents']/100.0:,.2f}")
    if st.button("Save entry", type="primary"):
        if not svc_row:
            st.error("Pick a service")
        else:
            sb.table("service_logs").insert({
                "user_id": user["id"],
                "service_id": svc_row["id"],
                "served_at": served_at.isoformat(),
                "qty": int(qty),
                "tip_cents": int(round(float(tip) * 100)),
            }).execute()
            st.success("Saved!")
            time.sleep(0.5)
            st.rerun()
# --------------- My Daily Tracker (User)
with chosen[1]:
    st.subheader("My Daily Tracker")
    start, end = return_start_and_end(key="daily_tracker")

    rows = fetch_service_logs(user_id=user["id"], start_date=start, end_date=end)

    if not rows:
        st.info("No entries in range.")
    else:
        df = pd.DataFrame(rows)
        st.dataframe(df.drop(columns=["User", "Inactive"]))  # only show relevant columns to user

        totals = df[["Service Amount","Tip","Total"]].sum().to_dict()
        st.metric("Total Service Amount", f"{totals['Service Amount']:,.2f}")
        st.metric("Total Tips", f"{totals['Tip']:,.2f}")
        st.metric("Grand Total", f"{totals['Total']:,.2f}")

# --------------- Admin: Users & Services
if is_admin:
    with chosen[2]:
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
        st.dataframe(pd.DataFrame(ulist)[["username","role","is_active","service_percentage", "created_at"]])

        st.markdown("### Services")
        with st.expander("Add service"):
            sname = st.text_input("Name", key="sn")
            sdesc = st.text_area("Description", key="sd")
            simg = st.text_input("Image URL", key="si")
            sprice = st.number_input("Price", min_value=0.0, step=1.0)
            if st.button("Create service"):
                if not sname:
                    st.error("Service name required")
                else:
                    sb.table("services").insert({
                        "name": sname.strip(),
                        "description": sdesc.strip() if sdesc else None,
                        "image_url": simg.strip() if simg else None,
                        "price_cents": int(round(sprice * 100)),
                        "is_active": True
                    }).execute()
                    st.success("Service created")

        servs = sb.table("services").select(
            "id, name, description, image_url, price_cents, is_active, created_at"
        ).order("name").execute().data

        if servs:
            for svc in servs:
                col1, col2, col3, col4 = st.columns([3, 4, 2, 2])
                with col1:
                    st.text(svc["name"])
                with col2:
                    st.caption(svc.get("description") or "")
                with col3:
                    st.text(f"💲 {svc['price_cents'] / 100:.2f}")
                with col4:
                    active_label = "Deactivate" if svc["is_active"] else "Activate"
                    if st.button(active_label, key=f"toggle_{svc['id']}"):
                        sb.table("services").update({"is_active": not svc["is_active"]}).eq("id", svc["id"]).execute()
                        st.rerun()

    # --------------- Admin: Reports
    with chosen[3]:
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

        # ----------------- Service filter: active only or all
        include_deactivated = st.radio(
            "Services to include",
            ["Active only", "Active + Deactivated"],
            index=0,
            horizontal=True
        )

        if include_deactivated == "Active only":
            all_servs = sb.table("services").select("id, name, is_active").eq("is_active", True).order(
                "name").execute().data
        else:
            all_servs = sb.table("services").select("id, name, is_active").order("name").execute().data

        # ----------------- Quick period filters
        colf = st.columns(5)
        today = date.today()
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
                    end = today
                elif period == "Last month":
                    first_this = today.replace(day=1)
                    last_month_end = first_this - timedelta(days=1)
                    start = last_month_end.replace(day=1)
                    end = last_month_end
            else:
                start, end = return_start_and_end()

        with colf[1]:
            user_filter = st.selectbox("User", ["All"] + [u["username"] for u in all_users])
        with colf[2]:
            svc_filter = st.selectbox("Service", ["All"] + [s["name"] for s in all_servs])
        with colf[3]:
            st.write("")
            st.write("")
            if st.button("Run report", type="primary"):
                st.session_state.run_report = True

        # ----------------- Display report only if run_report is True
        if st.session_state.run_report:
            rows = fetch_service_logs(
                start_date=start,
                end_date=end,
                user_filter=user_filter,
                svc_filter=svc_filter,
                all_users=all_users,
                all_servs=all_servs
            )

            if not rows:
                st.info("No data for selection")
            else:
                df = pd.DataFrame(rows)
                st.dataframe(df)

                # Summary per user
                grp_user = df.groupby("User")[["Qty"]].sum().reset_index().rename(columns={"Qty": "Services Completed"})
                st.markdown("#### Services Completed per User")
                st.dataframe(grp_user)

                sums = df.groupby(["User", "User Percent"])[["Service Amount", "Tip", "Total"]].sum().reset_index()
                st.markdown("#### Totals per User")
                st.dataframe(sums)

                st.download_button("Download CSV", data=df.to_csv(index=False), file_name="report.csv", mime="text/csv")

    # --------------- Admin: Data Admin
    with chosen[4]:
        st.markdown("### Data Admin")
        st.caption("Delete users, change passwords, and delete logs")
        st.markdown("**Change user password**")
        all_users = sb.table("users").select("username, service_percentage").execute().data
        target_user = st.selectbox("Pick user", [u["username"] for u in all_users])
        current_percent = next(u["service_percentage"] for u in all_users if u["username"] == target_user)
        new_pass = st.text_input("New password", type="password")
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
            sb.table("users").update(update_values).eq("username", target_user).execute()
            st.success("User updated")
        st.divider()
        st.markdown("**Delete user**")
        del_user = st.selectbox("User to delete", [u["username"] for u in sb.table("users").select("username").order("username").execute().data], key="du")
        if st.button("Delete user", type="secondary"):
            sb.table("users").delete().eq("username", del_user).execute()
            st.success("User deleted (and their logs if any)")
        st.divider()
        st.markdown("**Delete a service log record**")
        recent = sb.table("service_logs").select("id, served_at, users(username), services(name)").order("created_at", desc=True).limit(50).execute().data
        if recent:
            options = {f"{r['served_at']} — {r['users']['username']} — {r['services']['name']}": r["id"] for r in recent}
            pick = st.selectbox("Pick a record", list(options.keys()))
            if st.button("Delete record"):
                sb.table("service_logs").delete().eq("id", options[pick]).execute()
                st.success("Deleted record")
                st.rerun()
        else:
            st.info("No recent logs")
