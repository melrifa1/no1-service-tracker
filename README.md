# ================================
# README.md (usage)
# ================================
# Services & Tips Tracker — Streamlit + Supabase (custom auth)

## 1) Create Supabase project
- Run the SQL from `sql/bootstrap.sql` in the SQL editor.
- (Optional) Disable RLS on the three tables for simplicity. If you keep RLS, create policies for server-side service role access.

## 2) Configure secrets
- Create `.streamlit/secrets.toml` with your Supabase URL and **Service Role** key.
- Set `app.bootstrap_admin_username/password` to bootstrap the first admin.

## 3) Run locally
```bash
pip install -r requirements.txt
no1-service-tracker run app.py
```

## 4) Deploy
- Streamlit Community Cloud / Render / Railway / Fly.io are the simplest options for a Streamlit app.
- If you must use **Vercel**, deploy a Next.js or static frontend there and host this Streamlit app on a separate service; or replace Streamlit with FastAPI/Next.js for a fully-Vercel stack.

