import uuid
import datetime as dt

import streamlit as st
import pandas as pd
from supabase import create_client, Client

# ---------- CONFIG ----------

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
VIDEO_BUCKET_NAME = "video-smp"


@st.cache_resource
def get_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


supabase = get_supabase_client()

st.set_page_config(page_title="Video SMP", layout="wide")

PAGES = ["Upload medias", "Browse & manage medias"]
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
        species = st.text_input("Species (required)")
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

    if not species.strip():
        st.error("Species is required.")
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
        "species": species.strip(),
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
        ["Video", "Audio"],
        horizontal=True
    )

    # -----------------------------
    # FETCH ALL DATA FOR THIS MEDIA TYPE
    # -----------------------------
    base_rows = (
        supabase.table("video_observations")
        .select("*")
        .eq("media_type", media_choice.lower())
        .execute()
        .data
        or []
    )

    # -----------------------------
    # CASCADE FILTER LOGIC
    # -----------------------------
    with st.expander("Filters", expanded=True):

        # 1. NAME FILTER
        name_filter = st.text_input("Name (contains)")

        # Filter rows by name first
        rows_after_name = [
            r for r in base_rows
            if name_filter.lower() in r["name"].lower()
        ] if name_filter else base_rows

        # 2. PROJECT FILTER
        project_options = sorted({r["project"] for r in rows_after_name})
        project_filter = st.multiselect("Project", project_options)

        rows_after_project = [
            r for r in rows_after_name
            if (not project_filter or r["project"] in project_filter)
        ]

        # 3. LOCATION FILTER
        location_options = sorted({r["location"] for r in rows_after_project})
        location_filter = st.multiselect("Location", location_options)

        rows_after_location = [
            r for r in rows_after_project
            if (not location_filter or r["location"] in location_filter)
        ]

        # 4. OBSERVER FILTER
        observer_options = sorted({r["observer"] for r in rows_after_location})
        observer_filter = st.multiselect("Observer", observer_options)

        rows_after_observer = [
            r for r in rows_after_location
            if (not observer_filter or r["observer"] in observer_filter)
        ]

        # 5. SPECIES FILTER
        species_options = sorted({r["species"] for r in rows_after_observer})
        species_filter = st.multiselect("Species", species_options)

        final_rows = [
            r for r in rows_after_observer
            if (not species_filter or r["species"] in species_filter)
        ]

    # -----------------------------
    # NO RESULTS?
    # -----------------------------
    if not final_rows:
        st.info("No media found with current filters.")
        return

    # -----------------------------
    # SELECT MEDIA BY NAME + PROJECT
    # -----------------------------
    select_labels = [f"{r['name']} — {r['project']}" for r in final_rows]
    label_to_row = {label: row for label, row in zip(select_labels, final_rows)}

    selected_label = st.selectbox("Select media", select_labels)
    row = label_to_row[selected_label]

    # -----------------------------
    # PREVIEW + DESCRIPTION LAYOUT (2/1)
    # -----------------------------
    col_media, col_info = st.columns([2, 1])

    bucket = BUCKET_NAME if row["media_type"] == "video" else "callings"

    # LEFT COLUMN: VIDEO OR AUDIO
    with col_media:
        try:
            url = supabase.storage.from_(bucket).get_public_url(row["storage_path"])
            if row["media_type"] == "video":
                st.video(url)
            else:
                st.audio(url)
        except Exception:
            st.info("Preview not available.")

    # RIGHT COLUMN: DESCRIPTION + METADATA
    with col_info:
        st.markdown("<h3 style='color:#007BFF;'>Details</h3>", unsafe_allow_html=True)
        st.write(f"**Name:** {row['name']}")
        st.write(f"**Species:** {row['species']}")
        st.write(f"**Observer:** {row['observer']}")
        st.write(f"**Location:** {row['location']}")
        st.write(f"**Project:** {row['project']}")
        st.write(f"**Date:** {row['observed_at']}")
        st.write("**Description:**")
        st.write(row.get("description") or "_No description_")

    # -----------------------------
    # EDIT METADATA
    # -----------------------------
    with st.expander("Edit metadata", expanded=False):

        name = st.text_input("Name (required)", value=row["name"])
        species = st.text_input("Species", value=row["species"])
        observer = st.text_input("Observer", value=row["observer"])
        observed_at = st.date_input(
            "Observation date",
            value=dt.date.fromisoformat(row["observed_at"])
        )
        location = st.text_input("Location", value=row["location"])
        project = st.text_input("Project", value=row["project"])
        description = st.text_area("Description", value=row.get("description") or "")

        if st.button("Save changes"):
            if not name.strip():
                st.error("Name is required.")
                return

            update_data = {
                "name": name.strip(),
                "species": species.strip(),
                "observer": observer,
                "observed_at": observed_at.isoformat(),
                "location": location,
                "project": project,
                "description": description,
            }

            supabase.table("video_observations") \
                .update(update_data) \
                .eq("id", row["id"]) \
                .execute()

            st.success("Metadata updated.")
            st.rerun()

    # -----------------------------
    # DELETE MEDIA
    # -----------------------------
    st.markdown("---")
    st.subheader("Delete this media")

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

            supabase.table("video_observations") \
                .delete() \
                .eq("id", row["id"]) \
                .execute()

            st.success("Media deleted.")
            st.session_state["confirm_delete"] = False
            st.rerun()


# ---------- ROUTER ----------

if page == "Upload medias":
    upload_page()
else:
    browse_page()

