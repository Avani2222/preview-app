import streamlit as st
import pandas as pd
import numpy as np
import os
import zipfile
from io import BytesIO
from streamlit_drawable_canvas import st_canvas
from PIL import Image

st.set_page_config(page_title="HSD Lite Annotator", layout="wide")

# ==========================================
# 1. STATE MANAGEMENT
# ==========================================
if "scan_complete" not in st.session_state:
    st.session_state.scan_complete = False
if "file_tree" not in st.session_state:
    st.session_state.file_tree = {} 
if "annotations" not in st.session_state:
    st.session_state.annotations = pd.DataFrame(columns=["Folder", "Base_Filename", "Tag", "Mask_Saved", "Notes"])
if "current_folder" not in st.session_state:
    st.session_state.current_folder = None
if "current_img_idx" not in st.session_state:
    st.session_state.current_img_idx = 0

# Default to the precomputed data folder in the same directory
DATA_DIR = os.path.join(os.getcwd(), "_precomputed_data")
MASKS_DIR = os.path.join(os.getcwd(), "_masks")

# ==========================================
# 2. LOGIC FUNCTIONS
# ==========================================
def scan_png_directory(root_path):
    """Scans the _precomputed_data folder for valid image sets."""
    tree = {}
    if not os.path.exists(root_path):
        st.error(f"Cannot find `{root_path}`. Please ensure your precomputed data is uploaded.")
        return

    for dirpath, _, filenames in os.walk(root_path):
        # Identify base images by looking for _raw.png
        raw_files = [f for f in filenames if f.endswith('_raw.png')]
        if raw_files:
            folder_name = os.path.basename(dirpath)
            # Extract base names (e.g., "img01" from "img01_raw.png")
            base_names = sorted([f.replace('_raw.png', '') for f in raw_files])
            tree[folder_name] = {"path": dirpath, "base_names": base_names}
    
    if tree:
        st.session_state.file_tree = tree
        st.session_state.current_folder = list(tree.keys())[0]
        st.session_state.current_img_idx = 0
        st.session_state.scan_complete = True
    else:
        st.error("No valid PNG sets found. Make sure files end with `_raw.png`.")

def save_annotation_and_next(folder, base_name, tag, notes, mask_data):
    """Saves the binary mask and updates the logging dataframe."""
    mask_saved_status = "No"
    
    if mask_data is not None:
        folder_mask_dir = os.path.join(MASKS_DIR, folder)
        os.makedirs(folder_mask_dir, exist_ok=True)
        
        mask_path = os.path.join(folder_mask_dir, f"{base_name}_mask.png")
        
        # Extract the drawn mask (RGBA format from canvas)
        mask_img = Image.fromarray(mask_data.astype("uint8"), mode="RGBA")
        mask_img.save(mask_path)
        mask_saved_status = "Yes"

    new_data = pd.DataFrame([{
        "Folder": folder, 
        "Base_Filename": base_name, 
        "Tag": tag, 
        "Mask_Saved": mask_saved_status,
        "Notes": notes
    }])
    st.session_state.annotations = pd.concat([st.session_state.annotations, new_data], ignore_index=True)
    st.session_state.annotations.drop_duplicates(subset=['Folder', 'Base_Filename'], keep='last', inplace=True)
    
    base_names = st.session_state.file_tree[folder]["base_names"]
    if st.session_state.current_img_idx < len(base_names) - 1:
        st.session_state.current_img_idx += 1
    else:
        folders = list(st.session_state.file_tree.keys())
        current_folder_idx = folders.index(folder)
        if current_folder_idx < len(folders) - 1:
            st.session_state.current_folder = folders[current_folder_idx + 1]
            st.session_state.current_img_idx = 0
        else:
            st.success("🎉 All folders completed!")
            
    st.rerun()

def create_export_zip():
    """Bundles the _masks folder and the Excel log into a single ZIP for cloud download."""
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # Add Excel File
        excel_buffer = BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
            st.session_state.annotations.to_excel(writer, index=False, sheet_name='Annotations')
        zip_file.writestr("hsd_annotations.xlsx", excel_buffer.getvalue())
        
        # Add Masks
        if os.path.exists(MASKS_DIR):
            for root, _, files in os.walk(MASKS_DIR):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, os.getcwd())
                    zip_file.write(file_path, arcname)
                    
    return zip_buffer.getvalue()

# ==========================================
# 3. UI: SIDEBAR
# ==========================================
with st.sidebar:
    st.header("⚙️ Configuration")
    
    if st.button("Load Dataset", type="primary", use_container_width=True):
        scan_png_directory(DATA_DIR)

    st.divider()

    if st.session_state.scan_complete:
        st.subheader("📂 Navigation")
        folders = list(st.session_state.file_tree.keys())
        selected_folder = st.selectbox(
            "Current Folder", 
            options=folders, 
            index=folders.index(st.session_state.current_folder) if st.session_state.current_folder in folders else 0
        )
        
        if selected_folder != st.session_state.current_folder:
            st.session_state.current_folder = selected_folder
            st.session_state.current_img_idx = 0
            st.rerun()

        st.divider()
        st.subheader("💾 Cloud Export")
        st.info("If running in the cloud, download your work frequently so you don't lose data!")
        
        if not st.session_state.annotations.empty:
            st.dataframe(st.session_state.annotations.tail(3), use_container_width=True)
            
            zip_data = create_export_zip()
            st.download_button(
                label="📥 Download Masks & Excel (.zip)",
                data=zip_data,
                file_name="Annotation_Export.zip",
                mime="application/zip",
                use_container_width=True
            )

# ==========================================
# 4. UI: MAIN WORKSPACE
# ==========================================
if st.session_state.scan_complete:
    folder = st.session_state.current_folder
    folder_path = st.session_state.file_tree[folder]["path"]
    base_names = st.session_state.file_tree[folder]["base_names"]
    
    idx = st.session_state.current_img_idx
    current_base = base_names[idx]
    
    st.markdown(f"### 📍 `{folder}` / **{current_base}**")
    st.progress((idx + 1) / len(base_names), text=f"Image {idx + 1} of {len(base_names)} in folder")
    
    col_canvas, col_controls = st.columns([3, 1])
    
    with col_canvas:
        # View Selector
        view_mode = st.radio(
            "Background Layer", 
            ["Corrected RGB", "KMeans Clustering", "Raw RGB"], 
            horizontal=True
        )
        
        view_map = {
            "Raw RGB": f"{current_base}_raw.png",
            "Corrected RGB": f"{current_base}_norm.png",
            "KMeans Clustering": f"{current_base}_kmeans.png"
        }
        
        bg_image_path = os.path.join(folder_path, view_map[view_mode])
        
        try:
            bg_pil = Image.open(bg_image_path)

            img_w, img_h = bg_pil.size

            # --- Detect usable width ---
            MAX_WIDTH = 750   

            scale = min(MAX_WIDTH / img_w, 1.0)

            new_w = int(img_w * scale)
            new_h = int(img_h * scale)

            resized_img = bg_pil.resize((new_w, new_h))

            canvas_result = st_canvas(
                fill_color="rgba(255, 0, 0, 0.3)",
                stroke_color="#ff0000",
                stroke_width=2,
                background_image=resized_img,
                update_streamlit=True,
                width=new_w,
                height=new_h,
                drawing_mode="polygon",
                key=f"canvas_{current_base}",
                display_toolbar=True
            )
        except Exception as e:
            st.error(f"Error loading image layer: {e}")

    with col_controls:
        st.subheader("📝 Metadata")
        
        existing_tag = ""
        existing_notes = ""
        match = st.session_state.annotations[
            (st.session_state.annotations['Folder'] == folder) & 
            (st.session_state.annotations['Base_Filename'] == current_base)
        ]
        if not match.empty:
            existing_tag = match.iloc[0]['Tag']
            existing_notes = match.iloc[0]['Notes']
            st.info("✓ Previously Tagged")

        tag_options = ["Benign", "Cancerous", "Anomaly", "Background", "Discard", "Keep"]
        selected_tag = st.selectbox(
            "Classification", 
            options=tag_options,
            index=tag_options.index(existing_tag) if existing_tag in tag_options else 0
        )
        notes_input = st.text_area("Notes", value=existing_notes, height=100)
        
        st.write("")
        st.info("💡 **Tips:**\n- Select Polygon tool (left of image).\n- Click points to outline.\n- **Right-click** to close shape.\n- Toggle layers to see boundaries.")
        st.divider()
        
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("⬅️ Previous", use_container_width=True, disabled=(idx == 0)):
                st.session_state.current_img_idx -= 1
                st.rerun()
                
        with btn_col2:
            button_label = "Save & Next ➡️" if idx < len(base_names) - 1 else "Finish Folder ⏭️"
            if st.button(button_label, type="primary", use_container_width=True):
                mask_data = canvas_result.image_data if canvas_result.image_data is not None else None
                save_annotation_and_next(folder, current_base, selected_tag, notes_input, mask_data)

else:
    st.title("HSD Lite Annotator")
    st.markdown("This lightweight app relies on precomputed PNG data. Ensure your `_precomputed_data` folder is available, then click **Load Dataset**.")