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
        file = st.file_uploader("Video file", type=["mp4", "mov", "avi", "mkv"])
        observer = st.text_input("Observer name")
        observed_at = st.date_input("Observation date", dt.date.today())
        location = st.text_input("Location")
        project = st.text_input("Project")
        description = st.text_area("Description", height=100)

        submitted = st.form_submit_button("Upload")

    if not submitted:
        return

    if not file:
        st.error("Please select a video file.")
        return

    if not observer or not location or not project:
        st.error("Observer, location, and project are required.")
        return

    # Unique path in bucket
    ext = file.name.split(".")[-1]
    unique_id = str(uuid.uuid4())
    storage_path = f"{unique_id}.{ext}"

    # 1) Upload to storage
    try:
        res = supabase.storage.from_(BUCKET_NAME).upload(
            path=storage_path,
            file=file.getvalue(),
            file_options={"content-type": file.type},
        )
        if isinstance(res, dict) and res.get("error"):
            st.error(f"Storage upload error: {res['error']['message']}")
            return
    except Exception as e:
        st.error(f"Storage upload failed: {e}")
        return

    # 2) Insert metadata
    try:
        data = {
            "storage_path": storage_path,
            "file_name": file.name,
            "observer": observer,
            "observed_at": observed_at.isoformat(),
            "location": location,
            "project": project,
            "description": description,
        }
        resp = supabase.table("video_observations").insert(data).execute()
        if not resp.data:
            st.error("Insert failed")
            return

    except Exception as e:
        st.error(f"DB insert failed: {e}")
        return

    st.success("Video and metadata uploaded successfully.")


# ---------- BROWSE / MANAGE PAGE ----------
def browse_page():
    st.header("Browse & manage videos")

    # -----------------------------
    # FILTERS
    # -----------------------------
    with st.expander("Filters", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            observer = st.text_input("Observer (contains)")
            project = st.text_input("Project (contains)")

        with col2:
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
    # TABLE VIEW
    # -----------------------------
    df = pd.DataFrame(data)
    df_display = df[["observer", "observed_at", "project", "location", "file_name", "id"]]
    st.dataframe(df_display, use_container_width=True)

    st.markdown("---")
    st.subheader("Edit / delete a video")

    # -----------------------------
    # SELECT VIDEO
    # -----------------------------
    ids = df["id"].tolist()
    id_to_row = {row["id"]: row for row in data}

    selected_id = st.selectbox("Select a video by ID", ids)
    if not selected_id:
        return

    row = id_to_row[selected_id]

    # -----------------------------
    # VIDEO PREVIEW
    # -----------------------------
    try:
        url = supabase.storage.from_(BUCKET_NAME).get_public_url(row["storage_path"])
        st.video(url)
    except Exception:
        st.info("Video preview not available.")

    # -----------------------------
    # EDIT METADATA (INSIDE DROPDOWN)
    # -----------------------------
    with st.expander("Edit metadata", expanded=False):

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
            update_data = {
                "observer": observer,
                "observed_at": observed_at.isoformat(),
                "location": location,
                "project": project,
                "description": description,
            }

            resp = (
                supabase.table("video_observations")
                .update(update_data)
                .eq("id", selected_id)
                .execute()
            )

            if resp.data is None:
                st.error("Update failed.")
            else:
                st.success("Metadata updated. Refresh to see changes.")

    # -----------------------------
    # DELETE VIDEO (SIMPLE & SAFE)
    # -----------------------------
    st.markdown("---")
    st.markdown("### Delete this video")

    if st.button("Delete video"):
        st.warning("This action is permanent. Click below to confirm.")

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
                .eq("id", selected_id)
                .execute()
            )

            if resp.data is None:
                st.error("Delete failed.")
            else:
                st.success("Video and metadata deleted. Refresh to update list.")


# ---------- ROUTER ----------

if page == "Upload videos":
    upload_page()
else:
    browse_page()

