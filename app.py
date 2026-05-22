import os
import uuid
import datetime as dt

import streamlit as st
import pandas as pd

from supabase import create_client, Client




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


def upload_video():
    st.header("Upload a new video")

    with st.form("upload_form", clear_on_submit=True):
        file = st.file_uploader("Video file", type=["mp4", "mov", "avi", "mkv"])
        observer = st.text_input("Observer name")
        observed_at = st.date_input("Observation date", dt.date.today())
        location = st.text_input("Location")
        project = st.text_input("Project")
        description = st.text_area("Description", height=100)

        submitted = st.form_submit_button("Upload")

    if submitted:
        if not file:
            st.error("Please select a video file.")
            return
        if not observer or not location or not project:
            st.error("Observer, location, and project are required.")
            return

        # Generate a unique path in the bucket
        ext = os.path.splitext(file.name)[1]
        unique_id = str(uuid.uuid4())
        storage_path = f"{unique_id}{ext}"

        # Upload to Supabase Storage
        try:
            res = supabase.storage.from_(BUCKET_NAME).upload(
                path=storage_path,
                file=file.getvalue(),
                file_options={"content-type": file.type},
            )
            if res.get("error"):
                st.error(f"Upload error: {res['error']['message']}")
                return
        except Exception as e:
            st.error(f"Upload failed: {e}")
            return

        # Insert metadata row
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
            if resp.error:
                st.error(f"DB insert error: {resp.error.message}")
                return
        except Exception as e:
            st.error(f"DB insert failed: {e}")
            return

        st.success("Video and metadata uploaded successfully.")


def fetch_videos(filters: dict):
    query = supabase.table("video_observations").select("*")

    if filters.get("observer"):
        query = query.ilike("observer", f"%{filters['observer']}%")
    if filters.get("project"):
        query = query.ilike("project", f"%{filters['project']}%")
    if filters.get("date_from"):
        query = query.gte("observed_at", filters["date_from"].isoformat())
    if filters.get("date_to"):
        query = query.lte("observed_at", filters["date_to"].isoformat())

    resp = query.order("observed_at", desc=True).execute()
    if resp.error:
        st.error(f"Error fetching videos: {resp.error.message}")
        return []
    return resp.data or []


def get_public_url(storage_path: str) -> str:
    # If bucket is private, you may want signed URLs instead
    res = supabase.storage.from_(BUCKET_NAME).get_public_url(storage_path)
    return res


def browse_videos():
    st.header("Browse & manage videos")

    with st.expander("Filters", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            observer = st.text_input("Observer (contains)")
        with col2:
            project = st.text_input("Project (contains)")
        with col3:
            date_from = st.date_input("From date", value=None)
            date_to = st.date_input("To date", value=None)

    filters = {
        "observer": observer.strip() or None,
        "project": project.strip() or None,
        "date_from": date_from if isinstance(date_from, dt.date) else None,
        "date_to": date_to if isinstance(date_to, dt.date) else None,
    }

    data = fetch_videos(filters)

    if not data:
        st.info("No videos found with current filters.")
        return

    df = pd.DataFrame(data)
    df_display = df[["observer", "observed_at", "project", "location", "file_name", "id"]]
    st.dataframe(df_display, use_container_width=True)

    st.markdown("---")
    st.subheader("Edit / delete a video")

    ids = df["id"].tolist()
    id_to_row = {row["id"]: row for row in data}

    selected_id = st.selectbox("Select a video by ID", ids)
    if not selected_id:
        return

    row = id_to_row[selected_id]

    # Show video (if accessible via public URL)
    try:
        url = get_public_url(row["storage_path"])
        st.video(url)
    except Exception:
        st.info("Video preview not available (check bucket access).")

    with st.form("edit_form"):
        observer = st.text_input("Observer", value=row["observer"])
        observed_at = st.date_input(
            "Observation date",
            value=dt.date.fromisoformat(row["observed_at"][:10]),
        )
        location = st.text_input("Location", value=row["location"])
        project = st.text_input("Project", value=row["project"])
        description = st.text_area("Description", value=row.get("description") or "", height=100)

        col_a, col_b = st.columns(2)
        with col_a:
            save_btn = st.form_submit_button("Save changes")
        with col_b:
            delete_btn = st.form_submit_button("Delete video", type="secondary")

    if save_btn:
        try:
            update_data = {
                "observer": observer,
                "observed_at": observed_at.isoformat(),
                "location": location,
                "project": project,
                "description": description,
            }
            resp = supabase.table("video_observations").update(update_data).eq("id", selected_id).execute()
            if resp.error:
                st.error(f"Update error: {resp.error.message}")
            else:
                st.success("Metadata updated. Refresh to see changes.")
        except Exception as e:
            st.error(f"Update failed: {e}")

    if delete_btn:
        st.warning("You are about to delete this video and its metadata.")
        confirm1 = st.checkbox("Yes, I really want to delete this video.")
        confirm2 = st.checkbox("Yes, I understand this cannot be undone.")

        if confirm1 and confirm2:
            # Delete from storage first
            try:
                supabase.storage.from_(BUCKET_NAME).remove([row["storage_path"]])
            except Exception as e:
                st.error(f"Storage delete failed: {e}")
                return

            # Then delete DB row
            try:
                resp = supabase.table("video_observations").delete().eq("id", selected_id).execute()
                if resp.error:
                    st.error(f"DB delete error: {resp.error.message}")
                else:
                    st.success("Video and metadata deleted. Refresh to update list.")
            except Exception as e:
                st.error(f"DB delete failed: {e}")


if page == "Upload videos":
    upload_video()
else:
    browse_videos()
