import re
import io
import csv
import shutil
import datetime
import subprocess
import requests
import urllib3
import streamlit as st
from pathlib import Path
import mammoth
from markdownify import markdownify as html_to_md
import pymupdf4llm
from markitdown import MarkItDown

# Suppress SSL warnings for institutional self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(
    page_title="eLabFTW Ingestion Studio",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================= MODERN EDITORIAL / PRECISION UI CSS =================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

code, pre, .mono {
    font-family: 'JetBrains Mono', monospace;
}

/* Clean up Streamlit default chrome and padding */
.block-container {
    padding-top: 2rem;
    padding-bottom: 3rem;
    max-width: 1440px;
}

/* Page Masthead */
.app-masthead {
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 1.25rem;
    margin-bottom: 1.75rem;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
}
.app-eyebrow {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #64748b;
    margin-bottom: 0.35rem;
}
.app-title {
    font-size: 1.65rem;
    font-weight: 600;
    letter-spacing: -0.025em;
    color: #0f172a;
    margin: 0;
    line-height: 1.2;
}
.app-subtitle {
    font-size: 0.9rem;
    color: #475569;
    margin-top: 0.35rem;
}

/* Section Headers */
.section-label {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #475569;
    margin-bottom: 0.75rem;
}

/* Sidebar refinement */
.sidebar-section {
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #64748b;
    margin-top: 0.5rem;
    margin-bottom: 0.5rem;
}

/* Simulated eLabFTW Document Preview Card */
.elab-card-header {
    background-color: #0f172a;
    color: #f8fafc;
    padding: 18px 22px;
    border-radius: 6px 6px 0 0;
    border-bottom: 1px solid #1e293b;
}
.elab-card-title {
    font-size: 1.15rem;
    font-weight: 600;
    letter-spacing: -0.015em;
    margin: 0 0 8px 0;
    color: #ffffff;
}
.elab-card-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: #94a3b8;
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
}
.elab-tag-row {
    margin-top: 12px;
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
}
.elab-tag {
    display: inline-block;
    background-color: #1e293b;
    color: #cbd5e1;
    border: 1px solid #334155;
    padding: 2px 9px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.01em;
}

/* Attachment Row */
.elab-attachment {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    padding: 10px 14px;
    border-radius: 5px;
    margin-top: 6px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.elab-attachment-name {
    font-size: 0.84rem;
    font-weight: 500;
    color: #0f172a;
}
.elab-attachment-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    color: #64748b;
}

/* Subtle Button Styling */
div.stButton > button {
    border-radius: 5px;
    font-weight: 500;
    font-size: 0.85rem;
    transition: all 0.15s ease;
}
</style>
""", unsafe_allow_html=True)

# Initialize Session State
if "parsed_docs" not in st.session_state:
    st.session_state.parsed_docs = {}
if "resource_categories" not in st.session_state:
    st.session_state.resource_categories = {}
if "folder_path_val" not in st.session_state:
    st.session_state.folder_path_val = ""


# ================= NATIVE OS FOLDER PICKER (UBUNTU / WINDOWS) =================
def open_native_folder_dialog() -> str:
    """Opens native OS folder explorer popup on Ubuntu (zenity/tkinter) or Windows (tkinter)."""
    if shutil.which("zenity"):
        try:
            res = subprocess.run(
                ["zenity", "--file-selection", "--directory", "--title=Select Protocol or Project Directory"],
                capture_output=True,
                text=True,
                check=False
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
            return ""
        except Exception:
            pass

    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        folder_selected = filedialog.askdirectory(title="Select Protocol or Project Directory")
        root.destroy()
        return folder_selected or ""
    except Exception as e:
        st.warning(
            f"Native directory dialog unavailable ({e}). "
            "Install `zenity` or `python3-tk` on Linux, or enter the directory path directly."
        )
        return ""


# ================= SCIENTIFIC NOTATION & PARSING ENGINE =================
def repair_scientific_notation(md_text: str) -> str:
    """Deterministically repairs flattened exponents, unicode superscripts, and chemical formulas."""
    text = md_text

    def uni_to_sup(match):
        sup_map = {'⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4', '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9', '⁻': '-'}
        val = "".join(sup_map.get(c, c) for c in match.group(1))
        return f"<sup>{val}</sup>"
    text = re.sub(r'([⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+)', uni_to_sup, text)

    text = re.sub(r'(\b\d+(?:\.\d+)?\s*)[xX×\*]\s*10\^?([-−]?\d{1,2})\b', r'\1× 10<sup>\2</sup>', text)
    text = re.sub(r'\b10\^([-−]?\d{1,2})\b', r'10<sup>\1</sup>', text)
    text = re.sub(r'\b10([3-9])\s+(cells|parasites|CFU|PFU)\b', r'10<sup>\1</sup> \2', text, flags=re.IGNORECASE)

    chem_replacements = {
        r'\bddH2O\b': 'ddH<sub>2</sub>O',
        r'\bdH2O\b': 'dH<sub>2</sub>O',
        r'\bH2O\b': 'H<sub>2</sub>O',
        r'\bH2O2\b': 'H<sub>2</sub>O<sub>2</sub>',
        r'\bCO2\b': 'CO<sub>2</sub>',
        r'\bO2\b': 'O<sub>2</sub>',
        r'\bN2\b': 'N<sub>2</sub>',
        r'\bMgCl2\b': 'MgCl<sub>2</sub>',
        r'\bCaCl2\b': 'CaCl<sub>2</sub>',
        r'\bNa2HPO4\b': 'Na<sub>2</sub>HPO<sub>4</sub>',
        r'\bKH2PO4\b': 'KH<sub>2</sub>PO<sub>4</sub>',
        r'\bNaH2PO4\b': 'NaH<sub>2</sub>PO<sub>4</sub>',
        r'\b(NH4)2SO4\b': '(NH<sub>4</sub>)<sub>2</sub>SO<sub>4</sub>',
        r'\bNa2CO3\b': 'Na<sub>2</sub>CO<sub>3</sub>',
        r'\bNaHCO3\b': 'NaHCO<sub>3</sub>',
        r'\bK2HPO4\b': 'K<sub>2</sub>HPO<sub>4</sub>',
        r'\bMgSO4\b': 'MgSO<sub>4</sub>',
    }
    for pattern, sub_val in chem_replacements.items():
        text = re.sub(pattern, sub_val, text)

    text = re.sub(r'(\b\d+(?:\.\d+)?\s*)u([lLmMgG]\b)', r'\1µ\2', text)
    text = re.sub(r'(\b\d+(?:\.\d+)?)\s*deg\s*C\b', r'\1 °C', text, flags=re.IGNORECASE)
    text = re.sub(r'(\b\d+)\s*[xX×]\s*g\b', r'\1 × *g*', text)

    return text


def extract_docx_preserve_scripts(file_path: Path) -> str:
    """Extracts DOCX via Mammoth preserving <sup>, <sub>, and tables safely."""
    with open(file_path, "rb") as docx_file:
        result = mammoth.convert_to_html(docx_file)
        html_str = result.value

    html_str = (
        html_str.replace("<sup>", "XYZSUPOPENXYZ")
                .replace("</sup>", "XYZSUPCLOSEXYZ")
                .replace("<sub>", "XYZSUBOPENXYZ")
                .replace("</sub>", "XYZSUBCLOSEXYZ")
    )
    md_text = html_to_md(html_str, heading_style="ATX", bullets="-")
    return (
        md_text.replace("XYZSUPOPENXYZ", "<sup>")
               .replace("XYZSUPCLOSEXYZ", "</sup>")
               .replace("XYZSUBOPENXYZ", "<sub>")
               .replace("XYZSUBCLOSEXYZ", "</sub>")
    )


def extract_checklist_steps(md_text: str) -> list[str]:
    """Extract numbered steps or task list items for eLabFTW Steps checklist."""
    steps = []
    for line in md_text.splitlines():
        stripped = line.strip()
        match = re.match(r"^(?:\d+[\.\)]\s+|[-*]\s*\[[ xX]?\]\s+)(.+)$", stripped)
        if match:
            step_str = match.group(1).strip()
            if 5 < len(step_str) < 220:
                steps.append(step_str)
    return steps[:25]


TEXT_DOCUMENT_EXTS = {".docx", ".pdf", ".txt", ".md", ".csv", ".xlsx"}
ATTACHMENT_ONLY_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".svg", ".zip", ".prism", ".pzfx", ".fcs", ".rds", ".h5ad", ".fastq", ".bam"}
ALL_SUPPORTED_EXTS = TEXT_DOCUMENT_EXTS | ATTACHMENT_ONLY_EXTS


def extract_single_file_markdown(file_path: Path) -> str:
    """Extracts Markdown from a single file, or returns a clean reference note for binary files."""
    ext = file_path.suffix.lower()
    if ext in ATTACHMENT_ONLY_EXTS:
        return f"*Binary or figure asset (`{file_path.name}`) — queued in attachments.*"

    try:
        if ext == ".docx":
            raw_md = extract_docx_preserve_scripts(file_path)
        elif ext == ".pdf":
            raw_md = pymupdf4llm.to_markdown(str(file_path))
        else:
            md_converter = MarkItDown()
            result = md_converter.convert(str(file_path))
            raw_md = (result.text_content or "").strip()

        raw_md = repair_scientific_notation(raw_md.strip())
    except Exception as e:
        raw_md = f"*Extraction error on `{file_path.name}`: {e}*"

    if not raw_md:
        raw_md = f"*No selectable text layer detected in `{file_path.name}`. Original file is queued for attachment.*"
    return raw_md


def convert_file_individual(file_path: Path, parent_tag: str = "") -> dict:
    """Creates a 1-file-to-1-eLabFTW entry dictionary."""
    ext = file_path.suffix.lower()
    raw_md = extract_single_file_markdown(file_path)

    default_tags = ["legacy-import", ext.lstrip(".")]
    if parent_tag:
        default_tags.insert(0, parent_tag)

    size_kb = round(file_path.stat().st_size / 1024, 1)
    return {
        "title": file_path.stem.replace("_", " ").replace("-", " "),
        "display_label": file_path.name,
        "markdown_body": raw_md,
        "steps": extract_checklist_steps(raw_md),
        "tags": ", ".join(dict.fromkeys(default_tags)),
        "attachments": [
            {"path": str(file_path), "name": file_path.name, "size_kb": size_kb}
        ],
        "pushed_url": None
    }


def convert_files_consolidated(file_paths: list[Path], group_title: str, parent_tag: str = "") -> dict:
    """Combines multiple files into a single structured eLabFTW entry."""
    combined_sections = []
    all_steps = []
    attachments = []
    ext_tags = ["project-bundle", "legacy-import"]
    if parent_tag:
        ext_tags.insert(0, parent_tag)

    priority_order = {".md": 1, ".docx": 2, ".txt": 3, ".pdf": 4, ".xlsx": 5, ".csv": 6}
    sorted_paths = sorted(file_paths, key=lambda p: (priority_order.get(p.suffix.lower(), 99), p.name.lower()))

    for fp in sorted_paths:
        ext = fp.suffix.lower()
        size_kb = round(fp.stat().st_size / 1024, 1)
        attachments.append({"path": str(fp), "name": fp.name, "size_kb": size_kb})
        ext_tags.append(ext.lstrip("."))

        if ext in TEXT_DOCUMENT_EXTS:
            md_piece = extract_single_file_markdown(fp)
            combined_sections.append(f"## {fp.name}\n\n{md_piece}")
            for s in extract_checklist_steps(md_piece):
                if s not in all_steps and len(all_steps) < 30:
                    all_steps.append(s)

    summary_lines = [
        "## Associated Project Files",
        "| File Name | Format | Size |",
        "| :--- | :--- | :--- |"
    ]
    for att in attachments:
        f_ext = Path(att["name"]).suffix.lower()
        summary_lines.append(f"| `{att['name']}` | `{f_ext}` | {att['size_kb']} KB |")

    combined_sections.append("\n".join(summary_lines))
    full_markdown = "\n\n---\n\n".join(combined_sections)

    return {
        "title": group_title.replace("_", " ").replace("-", " "),
        "display_label": f"{group_title} ({len(attachments)} files)",
        "markdown_body": full_markdown,
        "steps": all_steps,
        "tags": ", ".join(dict.fromkeys(ext_tags)),
        "attachments": attachments,
        "pushed_url": None
    }


def push_doc_to_elabftw(doc: dict, elab_url: str, elab_key: str, target_type: str, cat_id: int, verify_ssl: bool) -> str:
    """Push entry, markdown body, checklist steps, tags, and attachments to eLabFTW."""
    j_headers = {"Authorization": elab_key, "Content-Type": "application/json"}

    create_payload = (
        {"category_id": int(cat_id), "category": int(cat_id), "content_type": 2}
        if target_type == "items"
        else {"content_type": 2}
    )

    post_r = requests.post(f"{elab_url}/{target_type}", headers=j_headers, json=create_payload, verify=verify_ssl, timeout=20)
    post_r.raise_for_status()

    loc = post_r.headers.get("Location") or post_r.headers.get("location")
    entity_url = loc if loc.startswith("http") else f"{elab_url.split('/api/v2')[0]}{loc}"

    file_names_str = ", ".join(f"`{a['name']}`" for a in doc["attachments"])
    footer = f"\n\n---\n*Source files ({len(doc['attachments'])}): {file_names_str}*"
    requests.patch(entity_url, headers=j_headers, json={
        "title": doc["title"],
        "body": doc["markdown_body"] + footer,
        "content_type": 2
    }, verify=verify_ssl, timeout=30).raise_for_status()

    for step_text in doc["steps"]:
        if step_text.strip():
            requests.post(f"{entity_url}/steps", headers=j_headers, json={"body": step_text.strip()}, verify=verify_ssl, timeout=10)

    tag_list = [t.strip() for t in doc["tags"].split(",") if t.strip()]
    for tag in tag_list:
        requests.post(f"{entity_url}/tags", headers=j_headers, json={"tag": tag}, verify=verify_ssl, timeout=10)

    for att in doc["attachments"]:
        file_path = Path(att["path"])
        if file_path.exists():
            with open(file_path, "rb") as f:
                requests.post(
                    f"{entity_url}/uploads",
                    headers={"Authorization": elab_key},
                    files={"file": (att["name"], f)},
                    data={"comment": f"Source file: {att['name']}"},
                    verify=verify_ssl,
                    timeout=120
                ).raise_for_status()

    return entity_url


# ================= MASTHEAD =================
st.markdown("""
<div class="app-masthead">
    <div>
        <h1 class="app-title">eLabFTW Ingestion Studio</h1>
        <div class="app-subtitle">Deterministic document parsing, scientific notation normalization, and direct REST API v2 synchronization.</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ================= SIDEBAR: CONFIGURATION & BATCH CONTROLS =================
with st.sidebar:
    st.markdown(
        """
        <a href="https://github.com/L-Figueiredo-Lab/elabftw-migrator" target="_blank" style="text-decoration: none;">
            <div style="background-color: #f1f5f9; padding: 10px; border-radius: 6px; text-align: center; color: #0f172a; font-size: 0.85rem; font-weight: 600; border: 1px solid #e2e8f0; margin-bottom: 15px; transition: all 0.2s ease;">
                 View Documentation on GitHub
            </div>
        </a>
        """,
        unsafe_allow_html=True
    )

with st.sidebar:
    st.markdown('<div class="sidebar-section">Server Configuration</div>', unsafe_allow_html=True)
    elab_url = st.text_input("Endpoint URL (API v2)", value="https://labbook.gimm.pt/api/v2").rstrip("/")
    elab_key = st.text_input("Authorization Token (API key)", type="password")
    st.markdown(
        "<div style='font-size: 0.75rem; color: #64748b; margin-top: -10px; margin-bottom: 10px;'>"
        "Need a token? Generate one in eLabFTW under <b>User Profile &rarr; Settings &rarr; API Keys</b>."
        "</div>", 
        unsafe_allow_html=True
    )
    verify_ssl = st.checkbox("Enforce TLS certificate verification", value=False)

    if st.button("Authenticate & Sync Schema", use_container_width=True):
        if not elab_key:
            st.warning("Provide an API token to authenticate.")
        else:
            try:
                auth_headers = {"Authorization": elab_key}
                r_info = requests.get(f"{elab_url}/experiments_templates", headers=auth_headers, verify=verify_ssl, timeout=10)
                r_info.raise_for_status()

                r_cats = requests.get(f"{elab_url}/items_types", headers=auth_headers, verify=verify_ssl, timeout=10)
                r_cats.raise_for_status()
                cats_json = r_cats.json()

                st.session_state.resource_categories = {
                    int(c.get("id") or c.get("category_id")): c.get("title", "Unnamed Category")
                    for c in cats_json
                }
                st.success(f"Authenticated. {len(st.session_state.resource_categories)} resource types indexed.")
            except Exception as e:
                st.error(f"Authentication failed: {e}")

    st.divider()
    st.markdown('<div class="sidebar-section">Target Destination</div>', unsafe_allow_html=True)

    target_type = st.selectbox(
        "Entity Endpoint",
        options=["experiments", "experiments_templates", "items"],
        format_func=lambda x: {
            "experiments": "Experiments (/experiments)",
            "experiments_templates": "Templates (/experiments_templates)",
            "items": "Resources (/items)"
        }[x]
    )

    cat_id = 1
    if target_type == "items":
        if st.session_state.resource_categories:
            cat_id = st.selectbox(
                "Resource Category",
                options=list(st.session_state.resource_categories.keys()),
                format_func=lambda cid: f"{st.session_state.resource_categories[cid]} (ID {cid})"
            )
        else:
            cat_id = st.number_input("Resource Category ID", min_value=1, value=1)

    if st.session_state.parsed_docs:
        st.divider()
        st.markdown('<div class="sidebar-section">Batch Operations</div>', unsafe_allow_html=True)

        csv_buffer = io.StringIO()
        writer = csv.DictWriter(csv_buffer, fieldnames=["title", "body", "content_type", "category_title", "tags"])
        writer.writeheader()
        for d in st.session_state.parsed_docs.values():
            pipe_tags = "|".join([t.strip() for t in d["tags"].split(",") if t.strip()])
            writer.writerow({
                "title": d["title"],
                "body": d["markdown_body"],
                "content_type": 2,
                "category_title": "Protocol",
                "tags": pipe_tags
            })
        st.download_button(
            "Export Batch CSV",
            data=csv_buffer.getvalue().encode("utf-8"),
            file_name="elabftw_batch_export.csv",
            mime="text/csv",
            use_container_width=True
        )

        if st.button("Publish All Queued Entries", type="primary", use_container_width=True):
            if not elab_key:
                st.error("API token required.")
            else:
                prog = st.progress(0)
                total = len(st.session_state.parsed_docs)
                for idx, (doc_key, doc_obj) in enumerate(st.session_state.parsed_docs.items()):
                    try:
                        url = push_doc_to_elabftw(doc_obj, elab_url, elab_key, target_type, cat_id, verify_ssl)
                        st.session_state.parsed_docs[doc_key]["pushed_url"] = url
                    except Exception as e:
                        st.error(f"Error publishing {doc_obj['title']}: {e}")
                    prog.progress((idx + 1) / total)
                st.success("Batch publication complete.")


# ================= STEP 1: INGESTION & AGGREGATION =================
st.markdown('<div class="section-label">01 / Ingestion & Aggregation Strategy</div>', unsafe_allow_html=True)

grouping_mode = st.radio(
    "Aggregation Mode",
    options=["individual", "consolidated", "by_subfolder"],
    format_func=lambda m: {
        "individual": "Individual Entries — Map each source file to a dedicated eLabFTW record",
        "consolidated": "Consolidated Record — Merge all selected documents, tables, and raw data attachments into one entry",
        "by_subfolder": "Subdirectory Mapping — Group files by immediate parent folder into separate consolidated entries"
    }[m],
    horizontal=False,
    label_visibility="collapsed"
)

tab_up, tab_dir = st.tabs(["Browser File Upload", "Workstation Directory"])
temp_dir = Path("./.st_temp_uploads")
temp_dir.mkdir(exist_ok=True)

with tab_up:
    col_u1, col_u2 = st.columns([3, 1.2])
    with col_u1:
        uploaded_files = st.file_uploader(
            "Supported formats: DOCX, PDF, XLSX, CSV, TXT, MD, PNG, JPG, TIF, ZIP, FCS, RDS",
            type=[e.lstrip(".") for e in ALL_SUPPORTED_EXTS],
            accept_multiple_files=True
        )
    with col_u2:
        bundle_title_input = st.text_input(
            "Consolidated Entry Title",
            value=f"Project Record {datetime.date.today().strftime('%Y-%m-%d')}"
        )
        process_uploads_btn = st.button("Stage Uploaded Files", type="primary", use_container_width=True)

    if process_uploads_btn and uploaded_files:
        saved_paths = []
        for uf in uploaded_files:
            tmp_path = temp_dir / uf.name
            tmp_path.write_bytes(uf.getbuffer())
            saved_paths.append(tmp_path)

        if grouping_mode == "individual":
            for sp in saved_paths:
                st.session_state.parsed_docs[f"upload::{sp.name}"] = convert_file_individual(sp)
            st.success(f"Staged {len(saved_paths)} individual entries.")
        else:
            doc_id = f"bundle::{bundle_title_input}"
            st.session_state.parsed_docs[doc_id] = convert_files_consolidated(saved_paths, bundle_title_input)
            st.success(f"Merged {len(saved_paths)} files into '{bundle_title_input}'.")

with tab_dir:
    col_path, col_browse, col_scan = st.columns([3.4, 1, 1.1])

    with col_browse:
        st.write("")
        st.write("")
        if st.button("Select Directory", use_container_width=True):
            picked = open_native_folder_dialog()
            if picked:
                st.session_state.folder_path_val = picked
                st.rerun()

    with col_path:
        folder_input = st.text_input(
            "Directory Path",
            value=st.session_state.folder_path_val,
            placeholder="/home/jaiganesh/lab_projects/experiment_01"
        )
        st.session_state.folder_path_val = folder_input

    with col_scan:
        st.write("")
        st.write("")
        scan_clicked = st.button("Index Directory", type="primary", use_container_width=True)

    if scan_clicked and folder_input:
        root_p = Path(folder_input)
        if not root_p.is_dir():
            st.error("Specified directory path does not exist.")
        else:
            found = [
                p for p in root_p.rglob("*")
                if p.is_file() and p.suffix.lower() in ALL_SUPPORTED_EXTS and not p.name.startswith("~$")
            ]
            if not found:
                st.warning("No compatible files detected in directory.")
            elif grouping_mode == "individual":
                for p in found:
                    doc_id = str(p.resolve())
                    parent_tag = p.parent.name if p.parent != root_p else root_p.name
                    st.session_state.parsed_docs[doc_id] = convert_file_individual(p, parent_tag)
                st.success(f"Indexed {len(found)} individual records from '{root_p.name}'.")

            elif grouping_mode == "consolidated":
                doc_id = f"folder_bundle::{root_p.resolve()}"
                st.session_state.parsed_docs[doc_id] = convert_files_consolidated(found, root_p.name, root_p.name)
                st.success(f"Merged {len(found)} files from '{root_p.name}' into a single record.")

            elif grouping_mode == "by_subfolder":
                subfolder_groups: dict[Path, list[Path]] = {}
                for p in found:
                    subfolder_groups.setdefault(p.parent, []).append(p)
                for folder_key, file_list in subfolder_groups.items():
                    doc_id = f"subfolder_bundle::{folder_key.resolve()}"
                    st.session_state.parsed_docs[doc_id] = convert_files_consolidated(
                        file_list, folder_key.name, folder_key.name
                    )
                st.success(f"Indexed {len(subfolder_groups)} consolidated subfolder records.")


# ================= STEP 2: WORKSPACE EDITOR & LIVE PREVIEW =================
st.divider()
st.markdown('<div class="section-label">02 / Document Workspace & Live Rendering</div>', unsafe_allow_html=True)

if not st.session_state.parsed_docs:
    st.caption("No records currently staged. Upload files or index a local directory above to inspect the output.")
else:
    doc_keys = list(st.session_state.parsed_docs.keys())
    col_sel, col_clear = st.columns([5, 1])
    with col_sel:
        selected_key = st.selectbox(
            f"Staged Records ({len(doc_keys)})",
            options=doc_keys,
            format_func=lambda k: f"[{'PUBLISHED' if st.session_state.parsed_docs[k]['pushed_url'] else 'STAGED'}]  {st.session_state.parsed_docs[k]['display_label']}"
        )
    with col_clear:
        st.write("")
        st.write("")
        if st.button("Clear Queue", use_container_width=True):
            st.session_state.parsed_docs.clear()
            st.rerun()

    current_doc = st.session_state.parsed_docs[selected_key]
    edit_col, preview_col = st.columns([1, 1.15], gap="large")

    # --- LEFT COLUMN: SOURCE EDITOR ---
    with edit_col:
        st.markdown('<div class="section-label">Source & Metadata Editor</div>', unsafe_allow_html=True)
        current_doc["title"] = st.text_input("Record Title", value=current_doc["title"])
        current_doc["tags"] = st.text_input("Metadata Tags (comma-delimited)", value=current_doc["tags"])
        current_doc["markdown_body"] = st.text_area(
            "Markdown Payload",
            value=current_doc["markdown_body"],
            height=380
        )
        steps_str = st.text_area(
            "Procedural Steps (one item per line)",
            value="\n".join(current_doc["steps"]),
            height=130
        )
        current_doc["steps"] = [s.strip() for s in steps_str.splitlines() if s.strip()]

        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button("Publish Record to eLabFTW", type="primary", use_container_width=True):
                if not elab_key:
                    st.error("Configure your API token in the sidebar before publishing.")
                else:
                    with st.spinner(f"Transmitting record and {len(current_doc['attachments'])} attachment(s)..."):
                        try:
                            entity_url = push_doc_to_elabftw(current_doc, elab_url, elab_key, target_type, cat_id, verify_ssl)
                            current_doc["pushed_url"] = entity_url
                            st.success(f"Published: {entity_url}")
                        except Exception as e:
                            st.error(f"Transmission error: {e}")
        with btn_c2:
            st.download_button(
                "Download Markdown",
                data=current_doc["markdown_body"].encode("utf-8"),
                file_name=f"{current_doc['title'].replace(' ', '_')}.md",
                mime="text/markdown",
                use_container_width=True
            )

    # --- RIGHT COLUMN: SIMULATED eLabFTW PREVIEW ---
    with preview_col:
        st.markdown('<div class="section-label">Target Rendering Preview</div>', unsafe_allow_html=True)

        tags_html = "".join(
            f'<span class="elab-tag">{t.strip()}</span>'
            for t in current_doc["tags"].split(",") if t.strip()
        )
        today_str = datetime.date.today().strftime("%Y-%m-%d")

        st.markdown(f"""
        <div class="elab-card-header">
            <div class="elab-card-title">{current_doc["title"] or "Untitled Record"}</div>
            <div class="elab-card-meta">
                <span>ENDPOINT: /{target_type}</span>
                <span>FORMAT: MARKDOWN (TYPE 2)</span>
                <span>ATTACHMENTS: {len(current_doc["attachments"])}</span>
                <span>DATE: {today_str}</span>
            </div>
            <div class="elab-tag-row">{tags_html}</div>
        </div>
        """, unsafe_allow_html=True)

        with st.container(border=True):
            st.markdown(current_doc["markdown_body"], unsafe_allow_html=True)

            st.divider()

            st.markdown('<div class="section-label">Interactive Procedural Checklist (/steps)</div>', unsafe_allow_html=True)
            if current_doc["steps"]:
                for idx, step_item in enumerate(current_doc["steps"], 1):
                    st.checkbox(f"{idx:02d}. {step_item}", value=False, key=f"prev_step_{selected_key}_{idx}")
            else:
                st.caption("No procedural checklist items defined for this record.")

            st.divider()

            st.markdown(f'<div class="section-label">Binary & Source Attachments (/uploads — {len(current_doc["attachments"])})</div>', unsafe_allow_html=True)
            for att in current_doc["attachments"]:
                st.markdown(f"""
                <div class="elab-attachment">
                    <span class="elab-attachment-name">{att["name"]}</span>
                    <span class="elab-attachment-meta">{att["size_kb"]} KB</span>
                </div>
                """, unsafe_allow_html=True)
