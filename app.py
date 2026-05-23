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
    st.header("Upload a new media file")

    # -----------------------------
    # MEDIA TYPE SELECTOR (OUTSIDE FORM)
    # -----------------------------
    media_type = st.radio(
        "What are you uploading?",
        ["Video", "Audio"],
        horizontal=True
    )

    # Dynamic uploader (works now!)
    if media_type == "Video":
        file = st.file_uploader(
            "Video file",
            max_upload_size=500,
            type=["mp4", "mov", "avi", "mkv"]
        )
    else:
        file = st.file_uploader(
            "Audio file",
            max_upload_size=200,
            type=["mp3", "wav", "aac", "m4a"]
        )

    # -----------------------------
    # FORM STARTS HERE
    # -----------------------------
    with st.form("upload_form", clear_on_submit=True):

        name = st.text_input("Name (required)")
        observer = st.text_input("Observer (required)")
        observed_at = st.date_input("Observation date", dt.date.today())
        location = st.text_input("Location (required)")
        project = st.text_input("Project (required)")
        description = st.text_area("Description", height=100)

        submitted = st.form_submit_button("Upload")

    if not submitted:
        return

    # -----------------------------
    # VALIDATION
    # -----------------------------
    if not name.strip():
        st.error("Name is required.")
        return

    if not file:
        st.error("Please select a file.")
        return

    if not observer or not location or not project:
        st.error("Observer, location, and project are required.")
        return

    # -----------------------------
    # SELECT BUCKET
    # -----------------------------
    if media_type == "Video":
        bucket = VIDEO_BUCKET_NAME
    else:
        bucket = "callings"

    # -----------------------------
    # UNIQUE STORAGE PATH
    # -----------------------------
    ext = file.name.split(".")[-1]
    unique_id = str(uuid.uuid4())
    storage_path = f"{unique_id}.{ext}"

    # -----------------------------
    # UPLOAD TO STORAGE
    # -----------------------------
    try:
        supabase.storage.from_(bucket).upload(
            path=storage_path,
            file=file.getvalue(),
            file_options={"content-type": file.type},
        )
    except Exception as e:
        st.error(f"Storage upload failed: {e}")
        return

    # -----------------------------
    # INSERT METADATA
    # -----------------------------
    data = {
        "name": name.strip(),
        "media_type": media_type.lower(),  # "video" or "audio"
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

    st.success(f"{media_type} uploaded successfully!")
    st.rerun()





# ---------- BROWSE / MANAGE PAGE ----------
def browse_page():
    st.header("Browse & manage media")

    # -----------------------------
    # MEDIA TYPE FILTER
    # -----------------------------
    media_choice = st.radio(
        "Media type",
        ["All", "Video", "Audio"],
        horizontal=True
    )

    # -----------------------------
    # FILTERS
    # -----------------------------
    with st.expander("Filters", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            name_filter = st.text_input("Name (contains)")
            observer_filter = st.text_input("Observer (contains)")
            location_filter = st.text_input("Location (contains)")

        with col2:
            project_filter = st.text_input("Project (contains)")

            # DATE SLIDER (SAFE)
            dates = supabase.table("video_observations") \
                .select("observed_at") \
                .order("observed_at") \
                .execute().data

            if dates:
                all_dates = sorted([dt.date.fromisoformat(d["observed_at"]) for d in dates])
                min_date, max_date = all_dates[0], all_dates[-1]
            else:
                min_date = max_date = dt.date.today()

            date_range = st.slider(
                "Observation date range",
                min_value=min_date,
                max_value=max_date,
                value=(min_date, max_date)
            )

    # -----------------------------
    # BUILD QUERY
    # -----------------------------
    query = supabase.table("video_observations").select("*")

    # Media type
    if media_choice == "Video":
        query = query.eq("media_type", "video")
    elif media_choice == "Audio":
        query = query.eq("media_type", "audio")

    # Text filters
    if name_filter.strip():
        query = query.ilike("name", f"%{name_filter.strip()}%")

    if observer_filter.strip():
        query = query.ilike("observer", f"%{observer_filter.strip()}%")

    if location_filter.strip():
        query = query.ilike("location", f"%{location_filter.strip()}%")

    if project_filter.strip():
        query = query.ilike("project", f"%{project_filter.strip()}%")

    # Date range filter
    query = query.gte("observed_at", date_range[0].isoformat())
    query = query.lte("observed_at", date_range[1].isoformat())

    # -----------------------------
    # EXECUTE QUERY
    # -----------------------------
    resp = query.order("observed_at", desc=True).execute()

    if resp.data is None:
        st.error("Failed to fetch media.")
        return

    data = resp.data

    if not data:
        st.info("No media found with current filters.")
        return

    # -----------------------------
    # SELECT MEDIA BY NAME + PROJECT
    # -----------------------------
    select_labels = [f"{row['name']} — {row['project']}" for row in data]
    label_to_row = {f"{row['name']} — {row['project']}": row for row in data}

    selected_label = st.selectbox("Select media", select_labels)
    row = label_to_row[selected_label]

    # -----------------------------
    # PREVIEW (VIDEO OR AUDIO)
    # -----------------------------
    bucket = VIDEO_BUCKET_NAME if row["media_type"] == "video" else "callings"

    try:
        url = supabase.storage.from_(bucket).get_public_url(row["storage_path"])
        if row["media_type"] == "video":
            st.video(url)
        else:
            st.audio(url)
    except Exception:
        st.info("Preview not available.")

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
                st.rerun()

    # -----------------------------
    # DELETE MEDIA (SAFE)
    # -----------------------------
    st.markdown("---")
    st.markdown("### Delete this media")

    if st.button("Delete media"):
        st.session_state["confirm_delete"] = True

    if st.session_state.get("confirm_delete", False):
        st.warning("This action is permanent. Click below to confirm deletion.")

        if st.button("YES, delete permanently"):
            try:
                supabase.storage.from_(bucket).remove([row["storage_path"]])
            except Exception as e:
                st.error(f"Storage delete failed: {e}")
                return

            resp = (
                supabase.table("video_observations")
                .delete()
                .eq("id", row["id"])
                .execute()
            )

            if resp.data is None:
                st.error("Delete failed.")
            else:
                st.success("Media deleted.")
                st.session_state["confirm_delete"] = False
                st.rerun()




# ---------- ROUTER ----------

if page == "Upload videos":
    upload_page()
else:
    browse_page()

