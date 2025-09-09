# ================================
# app.py (Streamlit main — updated with top-level admin tabs)
# ================================
import os
import time
import pandas as pd
from datetime import date, timedelta
import streamlit as st
from passlib.hash import bcrypt as bcrypt_hasher
from dateutil.relativedelta import relativedelta
from PIL import Image
import requests
from io import BytesIO
try:
    from supabase import create_client
except Exception as e:
    st.stop()

# ---- Utilities
@st.cache_resource(show_spinner=False)
def get_supabase():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"].get("service_key") or st.secrets["supabase"].get("anon_key")
    return create_client(url, key)

sb = get_supabase()

# DB helpers
def upsert_admin_from_secrets():
    cfg = st.secrets.get("app", {})
    username = cfg.get("bootstrap_admin_username")
    password = cfg.get("bootstrap_admin_password")
    if not username or not password:
        return
    existing = sb.table("users").select("id").eq("username", username).execute().data
    pwd_hash = bcrypt_hasher.hash(password)
    if existing:
        sb.table("users").update({"password_hash": pwd_hash, "role": "admin", "is_active": True}).eq("username", username).execute()
    else:
        sb.table("users").insert({"username": username, "password_hash": pwd_hash, "role": "admin"}).execute()

# Authentication
SESSION_KEY = "auth_user"

def login(username: str, password: str):
    recs = sb.table("users").select("id, username, password_hash, role, is_active").eq("username", username).limit(1).execute().data
    if not recs:
        return False, "Invalid username or password"
    u = recs[0]
    if not u.get("is_active", True):
        return False, "Account disabled"
    if not bcrypt_hasher.verify(password, u["password_hash"]):
        return False, "Invalid username or password"
    st.session_state[SESSION_KEY] = {"id": u["id"], "username": u["username"], "role": u["role"]}
    return True, None

def logout():
    st.session_state.pop(SESSION_KEY, None)

def require_auth():
    return st.session_state.get(SESSION_KEY)

st.set_page_config(page_title="Services & Tips Tracker", page_icon="💼", layout="wide")

# Bootstrap admin
upsert_admin_from_secrets()

# Sidebar: Authentication
with st.sidebar:
    st.header("🔐 Sign in")
    user = require_auth()
    if not user:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Sign in")
        if submitted:
            ok, err = login(username, password)
            if ok:
                st.rerun()
            else:
                st.error(err)
    else:
        st.success(f"Signed in as {user['username']} ({user['role']})")
        if st.button("Sign out"):
            logout()
            st.rerun()

user = require_auth()
if not user:
    st.title("Services & Tips Tracker")
    st.info("Please sign in to continue.")
    st.stop()

is_admin = user["role"] == "admin"

st.title("💼 Services & Tips Tracker")

main_tabs = ["Log Services", "My Daily Tracker"]
if is_admin:
    main_tabs += ["Users & Services", "Reports", "Data Admin"]

chosen = st.tabs(main_tabs)

# --------------- Log Services (User)
# with chosen[0]:
#     st.subheader("Log Completed Services")
#     col1, col2 = st.columns(2)
#     with col1:
#         served_at = st.date_input("Date", value=date.today(), max_value=date.today())
#         qty = st.number_input("Quantity", min_value=1, step=1, value=1)
#         tip = st.number_input("Tip (in your currency)", min_value=0.0, step=1.0, value=0.0)
#     services = sb.table("services").select("id, name, price_cents, is_active").eq("is_active", True).order("name").execute().data
#     names = [s["name"] for s in services]
#     svc = st.selectbox("Service", options=names)
#     svc_row = next((s for s in services if s["name"] == svc), None)
#     if svc_row:
#         st.caption(f"Price: {svc_row['price_cents']/100.0:,.2f}")
#     if st.button("Save entry", type="primary"):
#         if not svc_row:
#             st.error("Pick a service")
#         else:
#             sb.table("service_logs").insert({
#                 "user_id": user["id"],
#                 "service_id": svc_row["id"],
#                 "served_at": served_at.isoformat(),
#                 "qty": int(qty),
#                 "tip_cents": int(round(float(tip) * 100)),
#             }).execute()
#             st.success("Saved!")
#             time.sleep(0.5)
#             st.rerun()

# --------------- Log Services (User)
with chosen[0]:
    st.subheader("Log Completed Services")

    # Fetch services with image & description
    services = sb.table("services").select(
        "id, name, price_cents, description, image_url, is_active"
    ).eq("is_active", True).order("name").execute().data

    if not services:
        st.info("No active services available.")
    else:
        cols = st.columns(3)  # 3 cards per row
        selected_service = None

        IMG_WIDTH, IMG_HEIGHT = 400, 300  # fixed size for all images

        for idx, svc in enumerate(services):
            with cols[idx % 3]:
                # Load and resize image
                img_url = svc.get("image_url") or "https://via.placeholder.com/200x150"
                try:
                    response = requests.get(img_url)
                    img = Image.open(BytesIO(response.content))
                    img = img.resize((IMG_WIDTH, IMG_HEIGHT))  # resize to fixed size
                except:
                    img = Image.new("RGB", (IMG_WIDTH, IMG_HEIGHT), color=(200, 200, 200))

                st.image(img, caption=svc["name"])
                st.caption(svc.get("description") or "")
                st.write(f"💲 {svc['price_cents'] / 100:.2f}")

                if st.button(f"Select {svc['name']}", key=f"svc_{svc['id']}"):
                    selected_service = svc

        # If user picked a service, show tip/date form
        if selected_service:
            st.markdown(f"### Selected: {selected_service['name']}")
            qty = st.number_input("Quantity", min_value=1, step=1, value=1)
            tip = st.number_input("Tip (in your currency)", min_value=0.0, step=1.0, value=0.0)
            served_at = st.date_input("Date", value=date.today(), max_value=date.today())

            if st.button("Save entry", type="primary", key="save_log"):
                sb.table("service_logs").insert({
                    "user_id": user["id"],
                    "service_id": selected_service["id"],
                    "served_at": f"{served_at.isoformat()}T{time.strftime('%H:%M:%S')}",
                    "qty": int(qty),
                    "tip_cents": int(round(float(tip) * 100)),
                }).execute()
                st.success("Service logged!")
                time.sleep(0.5)
                st.rerun()
# --------------- My Daily Tracker (User)
with chosen[1]:
    st.subheader("My Daily Tracker")
    start = st.date_input("From", value=date.today() - timedelta(days=7))
    end = st.date_input("To", value=date.today())
    logs = sb.table("service_logs").select("id, served_at, qty, tip_cents, services(name, price_cents)").eq("user_id", user["id"]).gte("served_at", start.isoformat()).lte("served_at", end.isoformat()).order("served_at").execute().data
    if not logs:
        st.info("No entries in range.")
    else:
        rows = []
        for r in logs:
            price = r["services"]["price_cents"]/100.0
            amount = price * r["qty"]
            rows.append({
                "Date": r["served_at"],
                "Service": r["services"]["name"],
                "Qty": r["qty"],
                "Service Amount": amount,
                "Tip": r["tip_cents"]/100.0,
                "Total": amount + (r["tip_cents"]/100.0),
                "_id": r["id"]
            })
        df = pd.DataFrame(rows)
        st.dataframe(df.drop(columns=["_id"]))
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
            nrole = st.selectbox("Role", options=["user","admin"], index=0)
            if st.button("Create user"):
                if not nuser or not npass:
                    st.error("Username & password required")
                else:
                    sb.table("users").insert({"username": nuser, "password_hash": bcrypt_hasher.hash(npass), "role": nrole}).execute()
                    st.success("User created")
        ulist = sb.table("users").select("id, username, role, is_active, created_at").order("created_at", desc=True).execute().data
        st.dataframe(pd.DataFrame(ulist)[["username","role","is_active","created_at"]])

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
    # with chosen[3]:
    #     if "run_report" not in st.session_state:
    #         st.session_state["run_report"] = False
    #     st.markdown("### Reports")
    #     all_users = sb.table("users").select("id, username").eq("is_active", True).order("username").execute().data
    #
    #     # New filter: include deactivated services or not
    #     include_deactivated = st.radio(
    #         "Services to include",
    #         ["Active only", "Active + Deactivated"],
    #         index=0,
    #         horizontal=True
    #     )
    #
    #     if include_deactivated == "Active only":
    #         all_servs = sb.table("services").select("id, name").eq("is_active", True).order("name").execute().data
    #     else:
    #         all_servs = sb.table("services").select("id, name").order("name").execute().data
    #
    #     colf = st.columns(5)
    #     with colf[0]:
    #         period = st.selectbox("Quick range", ["This week", "Last week", "This month", "Last month", "Custom"],
    #                               index=0)
    #
    #     if period != "Custom":
    #         today = date.today()
    #         if period == "This week":
    #             start = today - timedelta(days=today.weekday())
    #             end = today
    #         elif period == "Last week":
    #             end = date.today() - timedelta(days=today.weekday()+1)
    #             start = end - timedelta(days=6)
    #         elif period == "This month":
    #             start = today.replace(day=1)
    #             end = today
    #         elif period == "Last month":
    #             first_this = today.replace(day=1)
    #             last_month_end = first_this - timedelta(days=1)
    #             start = last_month_end.replace(day=1)
    #             end = last_month_end
    #     else:
    #         start = st.date_input("From", value=date.today()-timedelta(days=7), key="rf")
    #         end = st.date_input("To", value=date.today(), key="rt")
    #
    #     with colf[1]:
    #         user_filter = st.selectbox("User", ["All"] + [u["username"] for u in all_users])
    #     with colf[2]:
    #         svc_filter = st.selectbox("Service", ["All"] + [s["name"] for s in all_servs])
    #     with colf[3]:
    #         st.write("")
    #         st.write("")
    #         if st.button("Run report", type="primary"):
    #             st.session_state["run_report"] = True
    #
    # if st.session_state.get("run_report"):
    #     q = sb.table("service_logs").select(
    #         "qty, tip_cents, served_at, users(username), services(name, price_cents)"
    #     ).gte("served_at", start.isoformat()).lte("served_at", end.isoformat())
    #
    #     # ... filters here ...
    #
    #     data = q.execute().data
    #     if not data:
    #         st.info("No data for selection")
    #     else:
    #         rows = []
    #         for r in data:
    #             price = r["services"]["price_cents"] / 100.0
    #             amount = price * r["qty"]
    #             rows.append({
    #                 "Date & Time": pd.to_datetime(r["served_at"]),  # show timestamp
    #                 "User": r["users"]["username"],
    #                 "Service": r["services"]["name"],
    #                 "Qty": r["qty"],
    #                 "Service Amount": amount,
    #                 "Tip": r["tip_cents"] / 100.0,
    #                 "Total": amount + (r["tip_cents"] / 100.0)
    #             })
    #         df = pd.DataFrame(rows)
    #         st.dataframe(df)
    #         grp_user = df.groupby("User")["Qty"].sum().reset_index().rename(columns={"Qty": "Services Completed"})
    #         st.markdown("#### Services completed per user")
    #         st.dataframe(grp_user)
    #         sums = df.groupby("User")[["Service Amount", "Tip", "Total"]].sum().reset_index()
    #         st.markdown("#### Totals per user")
    #         st.dataframe(sums)
    #         st.download_button("Download CSV", data=df.to_csv(index=False), file_name="report.csv", mime="text/csv")
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
                    start = today - timedelta(days=today.weekday())
                    end = today
                elif period == "Last week":
                    end = today - timedelta(days=today.weekday() + 1)
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
                start = st.date_input("From", value=today - timedelta(days=7), key="rf")
                end = st.date_input("To", value=today, key="rt")

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
            q = sb.table("service_logs").select(
                "qty, tip_cents, served_at, users(username), services(name, price_cents, is_active)"
            ).gte("served_at", start.isoformat()).lte("served_at", end.isoformat())

            # Apply filters
            if user_filter != "All":
                uid = next(u["id"] for u in all_users if u["username"] == user_filter)
                q = q.eq("user_id", uid)
            if svc_filter != "All":
                sid = next(s["id"] for s in all_servs if s["name"] == svc_filter)
                q = q.eq("service_id", sid)

            data = q.execute().data

            if not data:
                st.info("No data for selection")
            else:
                rows = []
                for r in data:
                    price = r["services"]["price_cents"] / 100.0
                    amount = price * r["qty"]
                    rows.append({
                        "Date & Time": pd.to_datetime(r["served_at"]),
                        "User": r["users"]["username"],
                        "Service": r["services"]["name"],
                        "Inactive": not r["services"]["is_active"],
                        "Qty": r["qty"],
                        "Service Amount": amount,
                        "Tip": r["tip_cents"] / 100.0,
                        "Total": amount + (r["tip_cents"] / 100.0)
                    })

                df = pd.DataFrame(rows)
                st.dataframe(df)

                # Summary per user
                grp_user = df.groupby("User")[["Qty"]].sum().reset_index().rename(columns={"Qty": "Services Completed"})
                st.markdown("#### Services Completed per User")
                st.dataframe(grp_user)

                sums = df.groupby("User")[["Service Amount", "Tip", "Total"]].sum().reset_index()
                st.markdown("#### Totals per User")
                st.dataframe(sums)

                st.download_button("Download CSV", data=df.to_csv(index=False), file_name="report.csv", mime="text/csv")

    # --------------- Admin: Data Admin
    with chosen[4]:
        st.markdown("### Data Admin")
        st.caption("Delete users, change passwords, and delete logs")
        st.markdown("**Change user password**")
        target_user = st.selectbox("Pick user", [u["username"] for u in sb.table("users").select("username").order("username").execute().data])
        new_pass = st.text_input("New password", type="password")
        if st.button("Update password"):
            sb.table("users").update({"password_hash": bcrypt_hasher.hash(new_pass)}).eq("username", target_user).execute()
            st.success("Password updated")
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
