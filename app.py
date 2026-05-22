import uuid
import datetime as dt

import streamlit as st
import pandas as pd
from supabase import create_client, Client

# ---------- CONFIG ----------

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
BUCKET_NAME = "video-smp"


@st.cache_resource
def get_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


supabase = get_supabase_client()

st.set_page_config(page_title="Video SMP", layout="wide")

PAGES = ["Upload videos", "Browse & manage videos"]
page = st.sidebar.radio("Navigation", PAGES)


# ---------- UPLOAD PAGE ----------

def upload_page():
    st.header("Upload a new video")

    with st.form("upload_form", clear_on_submit=True):
        file = st.file_uploader("Video file",max_upload_size=500, type=["mp4", "mov", "avi", "mkv"])
        name = st.text_input("Name (required)")
        observer = st.text_input("Observer (required)")
        observed_at = st.date_input("Observation date", dt.date.today())
        location = st.text_input("Location (required)")
        project = st.text_input("Project (required)")
        description = st.text_area("Description", height=100)

        submitted = st.form_submit_button("Upload")

    if not submitted:
        return

    # Required fields
    if not name.strip():
        st.error("Name is required.")
        return

    if not file:
        st.error("Please select a video file.")
        return

    if not observer or not location or not project:
        st.error("Observer, location, and project are required.")
        return

    # Unique path
    ext = file.name.split(".")[-1]
    unique_id = str(uuid.uuid4())
    storage_path = f"{unique_id}.{ext}"

    # Upload to storage
    try:
        res = supabase.storage.from_(BUCKET_NAME).upload(
            path=storage_path,
            file=file.getvalue(),
            file_options={"content-type": file.type},
        )
    except Exception as e:
        st.error(f"Storage upload failed: {e}")
        return

    # Insert metadata
    data = {
        "name": name.strip(),
        "storage_path": storage_path,
        "file_name": file.name,
        "observer": observer,
        "observed_at": observed_at.isoformat(),
        "location": location,
        "project": project,
        "description": description,
    }

    resp = supabase.table("video_observations").insert(data).execute()

    if resp.data is None:
        st.error("Database insert failed.")
        return

    st.success("Video uploaded successfully!")
    st.rerun()



# ---------- BROWSE / MANAGE PAGE ----------
def browse_page():
    st.header("Browse & manage videos")

    # -----------------------------
    # FILTERS
    # -----------------------------
    with st.expander("Filters", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            name_filter = st.text_input("Name (contains)")
            observer = st.text_input("Observer (contains)")

        with col2:
            project = st.text_input("Project (contains)")
            use_date_filter = st.checkbox("Filter by date")

            if use_date_filter:
                date_range = st.date_input(
                    "Date range",
                    value=[dt.date.today(), dt.date.today()],
                )
                date_from, date_to = date_range
            else:
                date_from, date_to = None, None

    # -----------------------------
    # BUILD QUERY
    # -----------------------------
    query = supabase.table("video_observations").select("*")

    if name_filter.strip():
        query = query.ilike("name", f"%{name_filter.strip()}%")

    if observer.strip():
        query = query.ilike("observer", f"%{observer.strip()}%")

    if project.strip():
        query = query.ilike("project", f"%{project.strip()}%")

    if date_from:
        query = query.gte("observed_at", date_from.isoformat())

    if date_to:
        query = query.lte("observed_at", date_to.isoformat())

    # -----------------------------
    # EXECUTE QUERY
    # -----------------------------
    resp = query.order("observed_at", desc=True).execute()

    if resp.data is None:
        st.error("Failed to fetch videos.")
        return

    data = resp.data

    if not data:
        st.info("No videos found with current filters.")
        return

    # -----------------------------
    # SELECT VIDEO BY NAME + PROJECT
    # -----------------------------
    select_labels = [f"{row['name']} — {row['project']}" for row in data]
    label_to_row = {f"{row['name']} — {row['project']}": row for row in data}

    selected_label = st.selectbox("Select a video", select_labels)
    row = label_to_row[selected_label]

    # -----------------------------
    # VIDEO PREVIEW
    # -----------------------------
    try:
        url = supabase.storage.from_(BUCKET_NAME).get_public_url(row["storage_path"])
        st.video(url)
    except Exception:
        st.info("Video preview not available.")

    # -----------------------------
    # EDIT METADATA
    # -----------------------------
    with st.expander("Edit metadata", expanded=False):

        name = st.text_input("Name (required)", value=row["name"])
        observer = st.text_input("Observer", value=row["observer"])
        observed_at = st.date_input(
            "Observation date",
            value=dt.date.fromisoformat(str(row["observed_at"])[:10]),
        )
        location = st.text_input("Location", value=row["location"])
        project = st.text_input("Project", value=row["project"])
        description = st.text_area(
            "Description", value=row.get("description") or "", height=100
        )

        if st.button("Save changes"):
            if not name.strip():
                st.error("Name is required.")
                return

            update_data = {
                "name": name.strip(),
                "observer": observer,
                "observed_at": observed_at.isoformat(),
                "location": location,
                "project": project,
                "description": description,
            }

            resp = (
                supabase.table("video_observations")
                .update(update_data)
                .eq("id", row["id"])
                .execute()
            )

            if resp.data is None:
                st.error("Update failed.")
            else:
                st.success("Metadata updated.")
                st.rerun()   # 🔥 AUTO REFRESH

    # -----------------------------
    # DELETE VIDEO (RELIABLE VERSION)
    # -----------------------------
    st.markdown("---")
    st.markdown("### Delete this video")

    if st.button("Delete video"):
        st.session_state["confirm_delete"] = True

    if st.session_state.get("confirm_delete", False):
        st.warning("This action is permanent. Click below to confirm deletion.")

        if st.button("YES, delete permanently"):
            # Delete from storage
            try:
                supabase.storage.from_(BUCKET_NAME).remove([row["storage_path"]])
            except Exception as e:
                st.error(f"Storage delete failed: {e}")
                return

            # Delete DB row
            resp = (
                supabase.table("video_observations")
                .delete()
                .eq("id", row["id"])
                .execute()
            )

            if resp.data is None:
                st.error("Delete failed.")
            else:
                st.success("Video deleted.")
                st.session_state["confirm_delete"] = False
                st.rerun()   # 🔥 AUTO REFRESH



# ---------- ROUTER ----------

if page == "Upload videos":
    upload_page()
else:
    browse_page()

