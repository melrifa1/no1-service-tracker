import streamlit as st
from supabase import create_client
from streamlit_cookies_manager import EncryptedCookieManager
from datetime import date, timedelta
from PIL import Image
import requests
from io import BytesIO
import pandas as pd
import time
from passlib.hash import bcrypt as bcrypt_hasher

# ------------------ Initialize Supabase
def get_supabase():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"].get("service_key") or st.secrets["supabase"].get("anon_key")
    return create_client(url, key)

sb = get_supabase()

# ------------------ Initialize cookies
cookies = EncryptedCookieManager(prefix="myapp_", password="A_STRONG_PASSWORD")

# Wait until cookies are loaded
if not cookies.ready():
    st.stop()  # stops execution until cookies are ready
# No .load() needed

# ------------------ Persistent login check
if "user" not in st.session_state:
    if cookies.get("user_id"):
        user_id = cookies.get("user_id")
        user = sb.table("users").select("*").eq("id", user_id).single().execute().data
        if user:
            st.session_state["user"] = user

# ------------------ Login form
if "user" not in st.session_state:
    st.subheader("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = sb.table("users").select("*") \
            .eq("username", username) \
            .maybe_single().execute().data
        if user:
            if not bcrypt_hasher.verify(password, user["password_hash"]):
                st.error("Invalid username or password")
            st.session_state["user"] = user
            cookies["user_id"] = user["id"]
            cookies.save()
            st.rerun()
        else:
            st.error("Invalid username or password")

# ------------------ Logout
if "user" in st.session_state:
    st.sidebar.write(f"Logged in as {st.session_state['user']['username']}")
    if st.sidebar.button("Logout"):
        st.session_state.pop("user")
        cookies["user_id"] = ""
        cookies.save()
        st.rerun()

# ------------------ Main App Tabs
if "user" in st.session_state:
    chosen = st.tabs(["Log Services", "Add/Edit Services", "Reports"])

    # ----------------- LOG SERVICES PAGE
    with chosen[0]:
        st.subheader("Log Completed Services")

        services = sb.table("services").select(
            "id, name, price_cents, description, image_url, is_active"
        ).eq("is_active", True).order("name").execute().data

        if not services:
            st.info("No active services available.")
        else:
            cols = st.columns(3)
            selected_service = None
            IMG_WIDTH, IMG_HEIGHT = 200, 150

            for idx, svc in enumerate(services):
                with cols[idx % 3]:
                    img_url = svc.get("image_url") or "https://via.placeholder.com/200x150"
                    try:
                        response = requests.get(img_url)
                        img = Image.open(BytesIO(response.content))
                        img = img.resize((IMG_WIDTH, IMG_HEIGHT))
                    except:
                        img = Image.new("RGB", (IMG_WIDTH, IMG_HEIGHT), color=(200, 200, 200))
                    st.image(img, caption=svc["name"])
                    st.caption(svc.get("description") or "")
                    st.write(f"💲 {svc['price_cents'] / 100:.2f}")

                    if st.button(f"Select {svc['name']}", key=f"svc_{svc['id']}"):
                        selected_service = svc

            if selected_service:
                st.markdown(f"### Selected: {selected_service['name']}")
                qty = st.number_input("Quantity", min_value=1, step=1, value=1)
                tip = st.number_input("Tip", min_value=0.0, step=1.0, value=0.0)
                served_at = st.date_input("Date", value=date.today(), max_value=date.today())

                if st.button("Save entry", type="primary", key="save_log"):
                    sb.table("service_logs").insert({
                        "user_id": st.session_state["user"]["id"],
                        "service_id": selected_service["id"],
                        "served_at": f"{served_at.isoformat()}T{time.strftime('%H:%M:%S')}",
                        "qty": int(qty),
                        "tip_cents": int(round(float(tip) * 100)),
                    }).execute()
                    st.success("Service logged!")
                    time.sleep(0.5)
                    st.rerun()

    # ----------------- ADD / EDIT / DEACTIVATE SERVICES PAGE
    with chosen[1]:
        st.markdown("### Services Management")

        # Add service
        with st.expander("Add Service"):
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
                    st.rerun()

        # List and edit/deactivate services
        servs = sb.table("services").select(
            "id, name, description, image_url, price_cents, is_active"
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
                    btn_label = "Deactivate" if svc["is_active"] else "Activate"
                    if st.button(btn_label, key=f"toggle_{svc['id']}"):
                        sb.table("services").update({"is_active": not svc["is_active"]}).eq("id", svc["id"]).execute()
                        st.rerun()

    # ----------------- REPORTS PAGE
    with chosen[2]:
        st.markdown("### Reports")
        if "run_report" not in st.session_state:
            st.session_state["run_report"] = False

        # Users and services
        all_users = sb.table("users").select("id, username").eq("is_active", True).order("username").execute().data
        include_deactivated = st.radio(
            "Services to include", ["Active only", "Active + Deactivated"], index=0, horizontal=True
        )
        if include_deactivated == "Active only":
            all_servs = sb.table("services").select("id, name, is_active").eq("is_active", True).order(
                "name").execute().data
        else:
            all_servs = sb.table("services").select("id, name, is_active").order("name").execute().data

        # Filters
        colf = st.columns(4)
        today = date.today()
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
                start = st.date_input("From", value=today - timedelta(days=7))
                end = st.date_input("To", value=today)

        with colf[1]:
            user_filter = st.selectbox("User", ["All"] + [u["username"] for u in all_users])
        with colf[2]:
            svc_filter = st.selectbox("Service", ["All"] + [s["name"] for s in all_servs])
        with colf[3]:
            st.write("")
            st.write("")
            if st.button("Run report"):
                st.session_state["run_report"] = True

        # Display report
        if st.session_state["run_report"]:
            q = sb.table("service_logs").select(
                "qty, tip_cents, served_at, users(username), services(name, price_cents, is_active)"
            ).gte("served_at", start.isoformat()).lte("served_at", end.isoformat())

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
                grp_user = df.groupby("User")[["Qty"]].sum().reset_index().rename(columns={"Qty": "Services Completed"})
                st.markdown("#### Services Completed per User")
                st.dataframe(grp_user)
                sums = df.groupby("User")[["Service Amount", "Tip", "Total"]].sum().reset_index()
                st.markdown("#### Totals per User")
                st.dataframe(sums)
                st.download_button("Download CSV", data=df.to_csv(index=False), file_name="report.csv", mime="text/csv")
