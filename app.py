import streamlit as st
import pandas as pd
from datetime import datetime
import os
import json
import io
import re
import msal
import requests

# -----------------------------
# PAGE CONFIG
# -----------------------------
st.set_page_config(page_title="LEFF IMS", layout="wide")

# -----------------------------
# WORKFLOW
# -----------------------------
WORKFLOW = ["Responsible", "DCC", "Lead", "Reviewer", "Lead", "Responsible"]

# -----------------------------
# USER DATABASE (FROM JSON FILE)
# -----------------------------
USERS_FILE = "users.json"

def load_users():
    if os.path.exists(USERS_FILE) and os.path.getsize(USERS_FILE) > 0:
        try:
            with open(USERS_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    default_users = {
        "hamid_admin": {"full_name": "Hamid Samani", "role": "Admin", "password": "123"},
        "hamid_dcc": {"full_name": "Hamid Samani", "role": "DCC", "password": "123"},
        "reza": {"full_name": "Reza Janjani", "role": "Reviewer", "password": "123"},
        "ali": {"full_name": "Ali Kia", "role": "Lead", "password": "123"},
        "arshia": {"full_name": "Arshia Khafaf", "role": "Responsible", "password": "123"},
        "nima": {"full_name": "Nima Talebinia", "role": "Responsible", "password": "123"},
        "doc_controller": {"full_name": "Document Controller", "role": "DocController", "password": "doc123"},
    }
    save_users(default_users)
    return default_users

def save_users(users_dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users_dict, f, indent=2)

if "users_db" not in st.session_state:
    st.session_state.users_db = load_users()

# -----------------------------
# PROJECT MANAGEMENT
# -----------------------------
PROJECTS_FILE = "projects.json"

def load_projects():
    if os.path.exists(PROJECTS_FILE) and os.path.getsize(PROJECTS_FILE) > 0:
        try:
            with open(PROJECTS_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_projects(projects_dict):
    with open(PROJECTS_FILE, "w") as f:
        json.dump(projects_dict, f, indent=2)

if "projects" not in st.session_state:
    st.session_state.projects = load_projects()

# -----------------------------
# SHAREPOINT CONNECTION (APP-ONLY with Sites.Selected)
# -----------------------------
@st.cache_resource
def get_sharepoint_client():
    try:
        tenant_id = st.secrets["TENANT_ID"]
        client_id = st.secrets["CLIENT_ID"]
        client_secret = st.secrets["CLIENT_SECRET"]
        site_url = st.secrets["SHAREPOINT_SITE_URL"]
    except Exception:
        st.error("اطلاعات SharePoint در secrets یافت نشد. لطفاً فایل .streamlit/secrets.toml را تنظیم کنید.")
        st.stop()

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(client_id, authority=authority, client_credential=client_secret)
    token_result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in token_result:
        st.error(f"خطا در دریافت توکن: {token_result.get('error_description')}")
        st.stop()
    access_token = token_result["access_token"]

    headers = {"Authorization": f"Bearer {access_token}"}
    site_host = site_url.split('//')[-1].replace('/', ':')
    site_response = requests.get(f"https://graph.microsoft.com/v1.0/sites/{site_host}", headers=headers)
    if site_response.status_code != 200:
        st.error(f"خطا در دریافت Site ID: {site_response.text}")
        st.stop()
    site_id = site_response.json()["id"]

    return access_token, site_id

def upload_file_to_sharepoint(file_bytes, file_name, remote_folder_path):
    access_token, site_id = get_sharepoint_client()
    safe_name = re.sub(r'[\\/*?:"<>|]', '_', file_name)
    full_path = f"{remote_folder_path}/{safe_name}".strip('/')
    # استفاده از مسیر مستقیم drive/root (با مجوز Sites.Selected کار می‌کند)
    upload_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{full_path}:/content"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/octet-stream"}
    response = requests.put(upload_url, headers=headers, data=file_bytes)
    if response.status_code in [200, 201]:
        result = response.json()
        return {
            "webUrl": result.get("webUrl"),
            "id": result.get("id")
        }
    else:
        raise Exception(f"Upload failed: {response.text}")

def download_file_from_sharepoint(file_id_or_url, button_text="📥 Download File", file_name=None):
    """دریافت فایل از SharePoint با استفاده از توکن برنامه (بدون لاگین کاربر)"""
    try:
        access_token, site_id = get_sharepoint_client()
        headers = {"Authorization": f"Bearer {access_token}"}
        
        if file_id_or_url.startswith("http"):
            # اگر webUrl داریم، مستقیماً با توکن درخواست می‌زنیم
            response = requests.get(file_id_or_url, headers=headers, allow_redirects=True)
        else:
            # اگر file_id داریم (توصیه می‌شود)
            content_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/items/{file_id_or_url}/content"
            response = requests.get(content_url, headers=headers)
        
        if response.status_code == 200:
            if not file_name:
                content_disposition = response.headers.get('Content-Disposition')
                if content_disposition and 'filename=' in content_disposition:
                    file_name = content_disposition.split('filename=')[1].strip('"')
                else:
                    file_name = "downloaded_file"
            st.download_button(
                label=button_text,
                data=response.content,
                file_name=file_name,
                mime="application/octet-stream",
                key=f"download_{hash(file_id_or_url)}_{datetime.now().timestamp()}"
            )
        else:
            st.error(f"خطا در دانلود فایل: {response.status_code}")
    except Exception as e:
        st.error(f"خطا: {e}")

# -----------------------------
# FILE STORAGE (LOCAL - فقط برای کامنت‌های قدیمی، اما اصلی به SharePoint می‌رود)
BASE_UPLOAD_DIR = "uploads"
os.makedirs(BASE_UPLOAD_DIR, exist_ok=True)

# -----------------------------
# DATA INIT (PER PROJECT)
# -----------------------------
def get_mdr_file(project_name):
    return f"mdr_{project_name}.json"

def get_documents_file(project_name):
    return f"documents_{project_name}.json"

def get_tasks_file(project_name):
    return f"tasks_{project_name}.json"

def load_dataframe(file_name, required_cols, default_df, list_cols=None):
    if os.path.exists(file_name) and os.path.getsize(file_name) > 0:
        try:
            with open(file_name, "r") as f:
                data = json.load(f)
            if data:
                df = pd.DataFrame(data)
                for col in required_cols:
                    if col not in df.columns:
                        if list_cols and col in list_cols:
                            df[col] = pd.Series([[] for _ in range(len(df))])
                        else:
                            df[col] = "" if col != "Revision" else 0
                return df
        except:
            pass
    return default_df.copy()

def init_mdr(project_name):
    default = pd.DataFrame(columns=["Doc No", "Title", "Discipline", "Code", "Status", "Current Step", "Revision"])
    if not project_name:
        return default
    file_name = get_mdr_file(project_name)
    df = load_dataframe(file_name, default.columns.tolist(), default, [])
    if not df.empty and "Doc No" in df.columns:
        df["Doc No"] = df["Doc No"].astype(str)
    return df

def init_documents(project_name):
    default = pd.DataFrame(columns=["Doc No", "Revision", "Uploaded By", "Date", "Workflow Step", "Status", "File Path", "File Id", "Rejection Reason", "Comments", "Source", "Email Reference"])
    if not project_name:
        return default
    file_name = get_documents_file(project_name)
    df = load_dataframe(file_name, default.columns.tolist(), default, ["Comments"])
    if not df.empty and "Doc No" in df.columns:
        df["Doc No"] = df["Doc No"].astype(str)
    if "Comments" not in df.columns:
        df["Comments"] = pd.Series([[] for _ in range(len(df))])
    if "File Id" not in df.columns:
        df["File Id"] = ""
    return df

def init_tasks(project_name):
    default = pd.DataFrame(columns=["task_id", "doc_no", "description", "assigned_to_user", "assigned_by_user", "due_date", "status", "history"])
    if not project_name:
        return default
    file_name = get_tasks_file(project_name)
    df = load_dataframe(file_name, default.columns.tolist(), default, ["history"])
    if "history" not in df.columns:
        df["history"] = pd.Series([[] for _ in range(len(df))])
    return df

def save_project_data(project_name, mdr_df, docs_df, tasks_df):
    if not project_name:
        return
    mdr_file = get_mdr_file(project_name)
    docs_file = get_documents_file(project_name)
    tasks_file = get_tasks_file(project_name)
    with open(mdr_file, "w") as f:
        json.dump(mdr_df.to_dict(orient="records"), f, indent=2)
    docs_save = docs_df.copy()
    if "Comments" in docs_save.columns:
        docs_save["Comments"] = docs_save["Comments"].apply(lambda x: x if isinstance(x, list) else [])
    with open(docs_file, "w") as f:
        json.dump(docs_save.to_dict(orient="records"), f, indent=2)
    tasks_save = tasks_df.copy()
    if "history" in tasks_save.columns:
        tasks_save["history"] = tasks_save["history"].apply(lambda x: x if isinstance(x, list) else [])
    with open(tasks_file, "w") as f:
        json.dump(tasks_save.to_dict(orient="records"), f, indent=2)

# -----------------------------
# SESSION STATE INIT
# -----------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.full_name = None
    st.session_state.role = None
    st.session_state.current_project = None
    st.session_state.mdr = pd.DataFrame()
    st.session_state.documents = pd.DataFrame()
    st.session_state.tasks = pd.DataFrame()

def load_current_project_data():
    project = st.session_state.current_project
    st.session_state.mdr = init_mdr(project)
    st.session_state.documents = init_documents(project)
    st.session_state.tasks = init_tasks(project)

def set_current_project(project_name):
    st.session_state.current_project = project_name
    load_current_project_data()

# -----------------------------
# AUTH / LOGIN
# -----------------------------
def login():
    st.title("🔐 Login to LEFF IMS")
    if os.path.exists("company_logo.png"):
        st.image("company_logo.png", width=150)
    with st.form("login_form"):
        username_options = list(st.session_state.users_db.keys())
        username = st.selectbox("Select User", username_options)
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            if st.session_state.users_db[username]["password"] == password:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.full_name = st.session_state.users_db[username]["full_name"]
                st.session_state.role = st.session_state.users_db[username]["role"]
                if st.session_state.projects:
                    first_proj = list(st.session_state.projects.keys())[0]
                    set_current_project(first_proj)
                else:
                    st.session_state.current_project = None
                st.rerun()
            else:
                st.error("Invalid password")

def logout():
    for key in ["logged_in", "username", "full_name", "role", "current_project", "mdr", "documents", "tasks"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

def add_comment(doc_index, comment_text, attachment_file_id=None, attachment_name=None):
    if not comment_text.strip() and not attachment_file_id:
        return
    current_comments = st.session_state.documents.at[doc_index, "Comments"]
    if not isinstance(current_comments, list):
        current_comments = []
    new_comment = {
        "user": st.session_state.full_name,
        "role": st.session_state.role,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "comment": comment_text,
        "attachment_file_id": attachment_file_id,
        "attachment_name": attachment_name
    }
    current_comments.append(new_comment)
    st.session_state.documents.at[doc_index, "Comments"] = current_comments
    save_project_data(st.session_state.current_project, st.session_state.mdr, st.session_state.documents, st.session_state.tasks)

# -----------------------------
# SIDEBAR (with project selection)
# -----------------------------
def show_sidebar():
    st.sidebar.title("LEFF IMS")
    st.sidebar.markdown(f"**User:** {st.session_state.full_name}")
    st.sidebar.markdown(f"**Role:** {st.session_state.role}")

    if st.session_state.projects:
        project_list = list(st.session_state.projects.keys())
        current_proj = st.session_state.current_project if st.session_state.current_project in project_list else project_list[0]
        selected_project = st.sidebar.selectbox("Current Project", project_list, index=project_list.index(current_proj))
        if selected_project != st.session_state.current_project:
            set_current_project(selected_project)
            st.rerun()
    else:
        st.sidebar.warning("No projects defined. Please ask Admin to create a project.")

    if st.sidebar.button("🚪 Logout"):
        logout()
    st.sidebar.markdown("---")

    is_mdr_manager = st.session_state.role in ["Admin", "DCC"]
    can_do_external_intake = st.session_state.role in ["Admin", "DCC", "DocController"]
    can_assign_tasks = st.session_state.role in ["Admin", "DCC", "Lead"]
    is_admin = st.session_state.role == "Admin"
    upload_menu = ["Upload Document"] if st.session_state.role in ["Responsible", "Admin"] else []
    mdr_menu = ["Add MDR", "Import MDR from Excel", "MDR List"] if is_mdr_manager else []
    external_menu = ["External Intake"] if can_do_external_intake else []
    task_menu = ["Assign Task"] if can_assign_tasks else []
    my_tasks_menu = ["Tasks I Created"] if can_assign_tasks else []
    user_mgmt_menu = ["User Management"] if is_admin else []
    project_mgmt_menu = ["Project Management"] if is_admin else []
    full_menu = ["Dashboard"] + upload_menu + external_menu + task_menu + my_tasks_menu + user_mgmt_menu + project_mgmt_menu + mdr_menu + ["Document History", "Review Queue"]
    full_menu = list(dict.fromkeys(full_menu))
    return st.sidebar.radio("Navigation", full_menu)

# -----------------------------
# PAGE FUNCTIONS
# -----------------------------
def dashboard_page():
    st.title("Dashboard")
    st.subheader("📋 My Tasks")
    my_tasks = st.session_state.tasks[st.session_state.tasks["assigned_to_user"] == st.session_state.username]
    if len(my_tasks) == 0:
        st.info("No tasks assigned to you.")
    else:
        for idx, task in my_tasks.iterrows():
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.markdown(f"**{task['description']}**  \n*Document: {task['doc_no'] if task['doc_no'] else 'N/A'} | Due: {task['due_date']}*")
            with col2:
                st.write(f"Status: {task['status']}")
            with col3:
                if task["status"] == "Pending":
                    if st.button("✅ Mark Done", key=f"task_done_{idx}"):
                        history_entry = {
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "changed_by": st.session_state.username,
                            "old_status": "Pending",
                            "new_status": "Completed"
                        }
                        current_history = st.session_state.tasks.at[idx, "history"]
                        if not isinstance(current_history, list):
                            current_history = []
                        current_history.append(history_entry)
                        st.session_state.tasks.at[idx, "history"] = current_history
                        st.session_state.tasks.at[idx, "status"] = "Completed"
                        save_project_data(st.session_state.current_project, st.session_state.mdr, st.session_state.documents, st.session_state.tasks)
                        st.success("Task marked as completed!")
                        st.rerun()
    st.markdown("---")
    if st.session_state.role == "Admin":
        filtered_mdr = st.session_state.mdr
    else:
        filtered_mdr = st.session_state.mdr[st.session_state.mdr["Current Step"] == st.session_state.role]
    total_docs = len(filtered_mdr)
    under_review = len(filtered_mdr[filtered_mdr["Status"] == "Under Review"])
    approved = len(filtered_mdr[filtered_mdr["Status"] == "Approved"])
    col1, col2, col3 = st.columns(3)
    col1.metric("Total MDR Items (My Role)", total_docs)
    col2.metric("Under Review", under_review)
    col3.metric("Approved", approved)
    st.subheader("MDR Items Related to Your Role")
    st.dataframe(filtered_mdr, use_container_width=True)

def add_mdr_page():
    if st.session_state.role not in ["Admin", "DCC"]:
        st.error("⛔ Only Admin or DCC can add MDR items.")
        return
    st.title("Add MDR Item")
    with st.form("mdr_form"):
        doc_no = st.text_input("Document Number")
        title = st.text_input("Document Title")
        discipline = st.selectbox("Discipline", ["Structural", "Civil", "Mechanical", "Electrical"])
        code = st.text_input("Code")
        submit = st.form_submit_button("Add MDR")
        if submit:
            if doc_no == "" or title == "":
                st.error("Document Number and Title are required")
            elif doc_no in st.session_state.mdr["Doc No"].values:
                st.error("Document Number already exists")
            else:
                new_row = pd.DataFrame([{
                    "Doc No": str(doc_no),
                    "Title": title,
                    "Discipline": discipline,
                    "Code": code,
                    "Status": "Not Started",
                    "Current Step": WORKFLOW[0],
                    "Revision": 0
                }])
                st.session_state.mdr = pd.concat([st.session_state.mdr, new_row], ignore_index=True)
                save_project_data(st.session_state.current_project, st.session_state.mdr, st.session_state.documents, st.session_state.tasks)
                st.success("MDR Item Added Successfully")

def import_mdr_page():
    if st.session_state.role not in ["Admin", "DCC"]:
        st.error("⛔ Only Admin or DCC can import MDR items.")
        return
    st.title("Import MDR from Excel")
    st.markdown("Upload an Excel file with columns: **Doc No, Title, Discipline, Code** (Code is optional)")
    uploaded_excel = st.file_uploader("Choose Excel file", type=["xlsx", "xls"])
    if uploaded_excel:
        try:
            df_new = pd.read_excel(uploaded_excel, engine="openpyxl")
            required_cols = ["Doc No", "Title", "Discipline"]
            if all(col in df_new.columns for col in required_cols):
                if "Code" not in df_new.columns:
                    df_new["Code"] = ""
                df_new["Doc No"] = df_new["Doc No"].astype(str)
                existing_doc_nos = set(st.session_state.mdr["Doc No"])
                duplicates = []
                new_rows = []
                for _, row in df_new.iterrows():
                    doc_no = row["Doc No"]
                    if doc_no in existing_doc_nos:
                        duplicates.append(doc_no)
                    else:
                        new_rows.append({
                            "Doc No": doc_no,
                            "Title": row["Title"],
                            "Discipline": row["Discipline"],
                            "Code": row["Code"],
                            "Status": "Not Started",
                            "Current Step": WORKFLOW[0],
                            "Revision": 0
                        })
                if new_rows:
                    st.session_state.mdr = pd.concat([st.session_state.mdr, pd.DataFrame(new_rows)], ignore_index=True)
                    save_project_data(st.session_state.current_project, st.session_state.mdr, st.session_state.documents, st.session_state.tasks)
                    st.success(f"Imported {len(new_rows)} new MDR items.")
                else:
                    st.info("No new items to import.")
                if duplicates:
                    st.warning(f"Duplicate Doc No(s) skipped: {', '.join(duplicates)}")
            else:
                st.error(f"Missing columns. Required: {required_cols}")
        except Exception as e:
            st.error(f"Error reading file: {e}")

def mdr_list_page():
    if st.session_state.role not in ["Admin", "DCC"]:
        st.error("⛔ Only Admin or DCC can view MDR list.")
        return
    st.title("MDR List")
    st.dataframe(st.session_state.mdr, use_container_width=True)
    if st.button("Delete Selected MDR Item (experimental)"):
        doc_to_del = st.selectbox("Select Doc No to delete", st.session_state.mdr["Doc No"])
        if doc_to_del:
            st.session_state.mdr = st.session_state.mdr[st.session_state.mdr["Doc No"] != doc_to_del]
            save_project_data(st.session_state.current_project, st.session_state.mdr, st.session_state.documents, st.session_state.tasks)
            st.rerun()

def upload_document_page():
    if st.session_state.role not in ["Responsible", "Admin"]:
        st.error("⛔ Only users with role 'Responsible' or 'Admin' can upload documents.")
        return
    st.title("Upload Document")
    if len(st.session_state.mdr) == 0:
        st.warning("Please add MDR items first.")
    else:
        active_mdr = st.session_state.mdr[st.session_state.mdr["Status"] != "Approved"]
        if len(active_mdr) == 0:
            st.info("All MDR items are approved. No further uploads needed.")
        else:
            doc_options = {f"{row['Doc No']} - {row['Title']}": row['Doc No'] for _, row in active_mdr.iterrows()}
            selected_display = st.selectbox("Select MDR Document", list(doc_options.keys()))
            selected_doc = doc_options[selected_display]
            idx = st.session_state.mdr[st.session_state.mdr["Doc No"] == selected_doc].index[0]
            next_rev = st.session_state.mdr.loc[idx, "Revision"] + 1
            rev_no = st.number_input("Revision No.", min_value=1, value=next_rev, step=1)
            if rev_no != next_rev:
                existing_revs = st.session_state.documents[st.session_state.documents["Doc No"] == selected_doc]["Revision"].tolist()
                if rev_no in existing_revs:
                    st.error(f"Revision {rev_no} already exists for this document. Please use a higher number.")
                    rev_no = None
            uploader = st.text_input("Uploaded By", value=st.session_state.full_name)
            uploaded_file = st.file_uploader("Upload File (PDF, DOCX, etc.)")
            submit_upload = st.button("Submit Document")
            if submit_upload and rev_no:
                if not uploaded_file:
                    st.error("Please select a file")
                else:
                    try:
                        project_name = st.session_state.current_project
                        today = datetime.now().strftime("%Y-%m-%d")
                        remote_folder = f"IMS/{project_name}/Internal/{selected_doc}_{today}"
                        upload_result = upload_file_to_sharepoint(uploaded_file.getvalue(), uploaded_file.name, remote_folder)
                        
                        st.session_state.mdr.loc[idx, "Revision"] = rev_no
                        st.session_state.mdr.loc[idx, "Status"] = "Under Review"
                        st.session_state.mdr.loc[idx, "Current Step"] = WORKFLOW[1]
                        new_doc = pd.DataFrame([{
                            "Doc No": selected_doc,
                            "Revision": rev_no,
                            "Uploaded By": uploader,
                            "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "Workflow Step": WORKFLOW[1],
                            "Status": "In Progress",
                            "File Path": upload_result["webUrl"],
                            "File Id": upload_result["id"],
                            "Rejection Reason": "",
                            "Comments": [],
                            "Source": "Internal",
                            "Email Reference": ""
                        }])
                        st.session_state.documents = pd.concat([st.session_state.documents, new_doc], ignore_index=True)
                        save_project_data(st.session_state.current_project, st.session_state.mdr, st.session_state.documents, st.session_state.tasks)
                        st.success(f"Document uploaded as Revision {rev_no} and sent to DCC for review.")
                    except Exception as e:
                        st.error(f"Upload failed: {e}")

def external_intake_page():
    if st.session_state.role not in ["Admin", "DCC", "DocController"]:
        st.error("⛔ Only Admin, DCC or Document Controller can register external documents.")
        return
    st.title("📧 Register External Document (from Email)")
    with st.form("external_form"):
        source = st.selectbox("Source", ["Architect", "Client"])
        email_reference = st.text_area("Email Reference (subject, date, sender, etc.)")
        doc_no = st.text_input("Document Number (if available, otherwise generate a new one)")
        title = st.text_input("Document Title")
        discipline = st.selectbox("Discipline", ["Structural", "Architectural", "Civil", "Mechanical", "Electrical"])
        code = st.text_input("Code (optional)")
        custom_file_name = st.text_input("Custom file name (optional)", placeholder="e.g., Structural comments")
        uploaded_file = st.file_uploader("Attach File", type=["pdf", "docx", "xlsx", "zip", "jpg", "png"])
        submit = st.form_submit_button("Register Document")
        if submit:
            if not uploaded_file or not title:
                st.error("Please select a file and enter a title.")
            else:
                if not doc_no:
                    prefix = "EXT-ARCH" if source == "Architect" else "EXT-CLI"
                    count = len(st.session_state.mdr[st.session_state.mdr["Doc No"].str.startswith(prefix)]) + 1
                    doc_no = f"{prefix}-{count:04d}"
                if doc_no in st.session_state.mdr["Doc No"].values:
                    st.error("Document Number already exists.")
                else:
                    try:
                        project_name = st.session_state.current_project
                        today = datetime.now().strftime("%Y-%m-%d")
                        remote_folder = f"IMS/{project_name}/External/{source}/{doc_no}_{today}"
                        upload_result = upload_file_to_sharepoint(uploaded_file.getvalue(), uploaded_file.name, remote_folder)
                        
                        new_mdr_row = pd.DataFrame([{
                            "Doc No": doc_no,
                            "Title": title,
                            "Discipline": discipline,
                            "Code": code,
                            "Status": "Under Review",
                            "Current Step": WORKFLOW[1],
                            "Revision": 1
                        }])
                        st.session_state.mdr = pd.concat([st.session_state.mdr, new_mdr_row], ignore_index=True)
                        new_doc_row = pd.DataFrame([{
                            "Doc No": doc_no,
                            "Revision": 1,
                            "Uploaded By": st.session_state.full_name,
                            "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "Workflow Step": WORKFLOW[1],
                            "Status": "In Progress",
                            "File Path": upload_result["webUrl"],
                            "File Id": upload_result["id"],
                            "Rejection Reason": "",
                            "Comments": [],
                            "Source": source,
                            "Email Reference": email_reference
                        }])
                        st.session_state.documents = pd.concat([st.session_state.documents, new_doc_row], ignore_index=True)
                        save_project_data(st.session_state.current_project, st.session_state.mdr, st.session_state.documents, st.session_state.tasks)
                        st.success(f"External document from {source} registered as {doc_no} and sent to DCC.")
                    except Exception as e:
                        st.error(f"Upload failed: {e}")

def assign_task_page():
    if st.session_state.role not in ["Admin", "DCC", "Lead"]:
        st.error("⛔ Only Admin, DCC or Lead can assign tasks.")
        return
    st.title("📌 Assign Task to a User")
    with st.form("task_form"):
        doc_list = [""] + st.session_state.mdr["Doc No"].tolist()
        selected_doc = st.selectbox("Related Document (optional)", doc_list)
        task_desc = st.text_area("Task Description")
        user_list = [f"{usr} ({st.session_state.users_db[usr]['full_name']} - {st.session_state.users_db[usr]['role']})" for usr in st.session_state.users_db.keys() if usr != st.session_state.username]
        selected_user_display = st.selectbox("Assign To", user_list)
        assigned_to_username = selected_user_display.split(" ")[0]
        due_date = st.date_input("Due Date", datetime.now())
        submit_task = st.form_submit_button("Create Task")
        if submit_task:
            if not task_desc.strip():
                st.error("Please enter a task description.")
            else:
                new_task_id = len(st.session_state.tasks) + 1
                new_task = pd.DataFrame([{
                    "task_id": new_task_id,
                    "doc_no": selected_doc if selected_doc else "",
                    "description": task_desc,
                    "assigned_to_user": assigned_to_username,
                    "assigned_by_user": st.session_state.username,
                    "due_date": due_date.strftime("%Y-%m-%d"),
                    "status": "Pending",
                    "history": []
                }])
                st.session_state.tasks = pd.concat([st.session_state.tasks, new_task], ignore_index=True)
                save_project_data(st.session_state.current_project, st.session_state.mdr, st.session_state.documents, st.session_state.tasks)
                st.success(f"Task assigned to {assigned_to_username}")

def tasks_created_page():
    if st.session_state.role not in ["Admin", "DCC", "Lead"]:
        st.error("⛔ You are not authorized to view this page.")
        return
    st.title("📋 Tasks I Created")
    my_created_tasks = st.session_state.tasks[st.session_state.tasks["assigned_by_user"] == st.session_state.username]
    if len(my_created_tasks) == 0:
        st.info("You haven't created any tasks yet.")
    else:
        display_df = my_created_tasks.copy()
        display_df = display_df.drop(columns=["history"], errors="ignore")
        display_df["assigned_to_name"] = display_df["assigned_to_user"].apply(
            lambda x: st.session_state.users_db.get(x, {}).get("full_name", x)
        )
        display_df = display_df.rename(columns={
            "task_id": "Task ID",
            "doc_no": "Document No",
            "description": "Description",
            "assigned_to_name": "Assigned To",
            "due_date": "Due Date",
            "status": "Status"
        })
        st.dataframe(display_df[["Task ID", "Document No", "Description", "Assigned To", "Due Date", "Status"]], use_container_width=True)
        
        def to_excel(df):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='MyCreatedTasks')
            return output.getvalue()
        
        excel_data = to_excel(display_df[["Task ID", "Document No", "Description", "Assigned To", "Due Date", "Status"]])
        st.download_button(
            label="📥 Download Tasks as Excel",
            data=excel_data,
            file_name=f"my_tasks_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        st.markdown("---")
        st.subheader("Task History (Status Changes)")
        for idx, row in my_created_tasks.iterrows():
            with st.expander(f"Task ID {row['task_id']}: {row['description'][:50]}..."):
                st.write(f"**Assigned to:** {row['assigned_to_user']} ({st.session_state.users_db.get(row['assigned_to_user'], {}).get('full_name', 'Unknown')})")
                st.write(f"**Due Date:** {row['due_date']}")
                st.write(f"**Current Status:** {row['status']}")
                history = row.get("history", [])
                if history and len(history) > 0:
                    st.write("**History:**")
                    for h in history:
                        st.caption(f"🕒 {h['timestamp']} - {h['changed_by']} : {h['old_status']} → {h['new_status']}")
                else:
                    st.caption("No status changes recorded yet.")

def review_queue_page():
    st.title("Review Queue")
    active_docs = st.session_state.documents[
        (st.session_state.documents["Status"].isin(["In Progress", "Submitted"])) |
        (st.session_state.documents["Status"] == "Rejected")
    ]
    if st.session_state.role == "Admin":
        role_queue = active_docs
    else:
        role_queue = active_docs[active_docs["Workflow Step"] == st.session_state.role]

    if len(role_queue) == 0:
        st.info(f"No documents waiting for your role: {st.session_state.role}")
    else:
        for _, row in role_queue.iterrows():
            original_idx = row.name
            with st.expander(f"{row['Doc No']} | Rev {row['Revision']} | Step: {row['Workflow Step']}"):
                st.write(f"**Uploaded By:** {row['Uploaded By']}")
                st.write(f"**Date:** {row['Date']}")
                if row.get("Source"):
                    st.info(f"**Source:** {row['Source']}")
                if row.get("Email Reference"):
                    st.caption(f"**Email Ref:** {row['Email Reference']}")

                if row.get("File Id"):
                    download_file_from_sharepoint(row["File Id"], "📥 Download File", row.get("File Name"))
                elif row.get("File Path"):
                    download_file_from_sharepoint(row["File Path"], "📥 Download File", row.get("File Name"))
                else:
                    st.warning("File not found.")

                if row["Rejection Reason"]:
                    st.warning(f"**Previous Return Reason:** {row['Rejection Reason']}")
                if row["Comments"] and len(row["Comments"]) > 0:
                    st.markdown("**Comments History:**")
                    for c in row["Comments"]:
                        st.caption(f"_{c['timestamp']} - {c['user']} ({c['role']}):_ {c['comment']}")

                with st.form(key=f"comment_form_{original_idx}"):
                    new_comment = st.text_area("Add a comment (no workflow change)", key=f"comment_{original_idx}")
                    if st.form_submit_button("💬 Add Comment"):
                        if new_comment.strip():
                            add_comment(original_idx, new_comment)
                            st.success("Comment added")
                            st.rerun()

                if row["Status"] == "Rejected":
                    if st.button("📤 Revise & Resubmit", key=f"resubmit_{original_idx}"):
                        if st.session_state.role not in ["Responsible", "Admin"]:
                            st.error("Only Responsible or Admin can resubmit.")
                        else:
                            mdr_idx = st.session_state.mdr[st.session_state.mdr["Doc No"] == row["Doc No"]].index[0]
                            new_rev = st.session_state.mdr.loc[mdr_idx, "Revision"] + 1
                            st.session_state.mdr.loc[mdr_idx, "Revision"] = new_rev
                            st.session_state.mdr.loc[mdr_idx, "Status"] = "Under Review"
                            st.session_state.mdr.loc[mdr_idx, "Current Step"] = WORKFLOW[1]
                            new_doc = pd.DataFrame([{
                                "Doc No": row["Doc No"],
                                "Revision": new_rev,
                                "Uploaded By": st.session_state.full_name,
                                "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "Workflow Step": WORKFLOW[1],
                                "Status": "In Progress",
                                "File Path": row["File Path"],
                                "File Id": row["File Id"],
                                "Rejection Reason": "",
                                "Comments": [],
                                "Source": row.get("Source", "Internal"),
                                "Email Reference": row.get("Email Reference", "")
                            }])
                            st.session_state.documents = pd.concat([st.session_state.documents, new_doc], ignore_index=True)
                            st.session_state.documents.loc[original_idx, "Status"] = "Archived"
                            save_project_data(st.session_state.current_project, st.session_state.mdr, st.session_state.documents, st.session_state.tasks)
                            st.success("New revision created. Please upload corrected document.")
                            st.rerun()
                    continue

                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("✅ Approve", key=f"approve_{original_idx}"):
                        comment_text = st.text_area("Comment (optional)", key=f"approve_comment_{original_idx}")
                        if comment_text:
                            add_comment(original_idx, f"Approved with comment: {comment_text}")
                        current_step = row["Workflow Step"]
                        step_index = WORKFLOW.index(current_step)
                        if step_index < len(WORKFLOW)-1:
                            next_step = WORKFLOW[step_index+1]
                            st.session_state.documents.loc[original_idx, "Workflow Step"] = next_step
                            mdr_idx = st.session_state.mdr[st.session_state.mdr["Doc No"] == row["Doc No"]].index[0]
                            st.session_state.mdr.loc[mdr_idx, "Current Step"] = next_step
                            if next_step == "Responsible" and step_index+1 == len(WORKFLOW)-1:
                                st.session_state.documents.loc[original_idx, "Status"] = "Completed"
                                st.session_state.mdr.loc[mdr_idx, "Status"] = "Approved"
                                st.success("Document fully approved!")
                            else:
                                st.success(f"Moved to {next_step}")
                        else:
                            st.session_state.documents.loc[original_idx, "Status"] = "Completed"
                            mdr_idx = st.session_state.mdr[st.session_state.mdr["Doc No"] == row["Doc No"]].index[0]
                            st.session_state.mdr.loc[mdr_idx, "Status"] = "Approved"
                            st.success("Document approved.")
                        save_project_data(st.session_state.current_project, st.session_state.mdr, st.session_state.documents, st.session_state.tasks)
                        st.rerun()
                with col2:
                    if st.button("❌ Reject (Return to previous step)", key=f"reject_{original_idx}"):
                        reason = st.text_area("Return reason (required)", key=f"reason_{original_idx}")
                        comment_text = st.text_area("Additional comment", key=f"reject_comment_{original_idx}")
                        if not reason:
                            st.error("Please provide a reason.")
                        else:
                            if comment_text:
                                add_comment(original_idx, f"Returned with comment: {comment_text}")
                            current_step = row["Workflow Step"]
                            step_index = WORKFLOW.index(current_step)
                            if step_index > 0:
                                prev_step = WORKFLOW[step_index-1]
                                st.session_state.documents.loc[original_idx, "Workflow Step"] = prev_step
                                mdr_idx = st.session_state.mdr[st.session_state.mdr["Doc No"] == row["Doc No"]].index[0]
                                st.session_state.mdr.loc[mdr_idx, "Current Step"] = prev_step
                                st.session_state.documents.loc[original_idx, "Status"] = "In Progress"
                                st.session_state.documents.loc[original_idx, "Rejection Reason"] = reason
                                st.warning(f"Returned to {prev_step}.")
                            else:
                                st.warning("Already at first step.")
                            save_project_data(st.session_state.current_project, st.session_state.mdr, st.session_state.documents, st.session_state.tasks)
                            st.rerun()
                with col3:
                    if st.button("↩️ Request Changes (Return with files)", key=f"request_changes_{original_idx}"):
                        st.session_state[f"show_return_form_{original_idx}"] = True
                    if st.session_state.get(f"show_return_form_{original_idx}", False):
                        with st.form(key=f"return_form_{original_idx}"):
                            return_reason = st.text_area("Reason for changes (required)")
                            comment_text = st.text_area("Detailed comment")
                            return_file = st.file_uploader("Attach file", type=["pdf", "docx", "txt", "jpg", "png"], key=f"return_file_{original_idx}")
                            submit_return = st.form_submit_button("Submit Return Request")
                            if submit_return:
                                if not return_reason:
                                    st.error("Reason required.")
                                else:
                                    full_comment = f"Requested changes: {return_reason}"
                                    if comment_text:
                                        full_comment += f"\nComment: {comment_text}"
                                    attachment_id = None
                                    attachment_name = None
                                    if return_file:
                                        try:
                                            project_name = st.session_state.current_project
                                            doc_no = row["Doc No"]
                                            rev = row["Revision"]
                                            remote_folder = f"IMS/{project_name}/Comments/{doc_no}/rev_{rev}"
                                            upload_result = upload_file_to_sharepoint(return_file.getvalue(), return_file.name, remote_folder)
                                            attachment_id = upload_result["id"]
                                            attachment_name = return_file.name
                                            full_comment += f"\nAttached file: {return_file.name}"
                                        except Exception as e:
                                            st.error(f"خطا در آپلود فایل برگشتی: {e}")
                                            continue
                                    add_comment(original_idx, full_comment, attachment_id, attachment_name)
                                    current_step = row["Workflow Step"]
                                    step_index = WORKFLOW.index(current_step)
                                    if step_index > 0:
                                        prev_step = WORKFLOW[step_index-1]
                                        st.session_state.documents.loc[original_idx, "Workflow Step"] = prev_step
                                        mdr_idx = st.session_state.mdr[st.session_state.mdr["Doc No"] == row["Doc No"]].index[0]
                                        st.session_state.mdr.loc[mdr_idx, "Current Step"] = prev_step
                                        st.session_state.documents.loc[original_idx, "Status"] = "In Progress"
                                        st.session_state.documents.loc[original_idx, "Rejection Reason"] = return_reason
                                        st.warning(f"Returned to {prev_step} for changes.")
                                    else:
                                        st.warning("Already at first step.")
                                    save_project_data(st.session_state.current_project, st.session_state.mdr, st.session_state.documents, st.session_state.tasks)
                                    st.session_state[f"show_return_form_{original_idx}"] = False
                                    st.rerun()

def document_history_page():
    st.title("Document History")
    if len(st.session_state.mdr) == 0:
        st.warning("No MDR items available.")
    else:
        doc_title_map = dict(zip(st.session_state.mdr["Doc No"], st.session_state.mdr["Title"]))
        doc_list = st.session_state.mdr["Doc No"].unique()
        selected_doc = st.selectbox("Select Document", doc_list)
        selected_title = doc_title_map.get(selected_doc, "")
        st.markdown(f"**Document:** {selected_doc} - {selected_title}")
        doc_history = st.session_state.documents[st.session_state.documents["Doc No"] == selected_doc].sort_values("Revision")
        if len(doc_history) == 0:
            st.info("No uploads for this document.")
        else:
            for _, rev_row in doc_history.iterrows():
                with st.expander(f"Revision {rev_row['Revision']} - {rev_row['Date']} - Status: {rev_row['Status']}"):
                    st.write(f"**Uploaded By:** {rev_row['Uploaded By']}")
                    st.write(f"**Workflow Step:** {rev_row['Workflow Step']}")
                    if rev_row.get("Source"):
                        st.info(f"**Source:** {rev_row['Source']}")
                    if rev_row.get("Email Reference"):
                        st.caption(f"**Email Ref:** {rev_row['Email Reference']}")
                    if rev_row["Rejection Reason"]:
                        st.error(f"**Return Reason:** {rev_row['Rejection Reason']}")
                    if rev_row.get("File Id"):
                        download_file_from_sharepoint(rev_row["File Id"], "📥 Download File")
                    elif rev_row.get("File Path"):
                        download_file_from_sharepoint(rev_row["File Path"], "📥 Download File")
                    else:
                        st.warning("File not found.")
                    if rev_row["Comments"] and len(rev_row["Comments"]) > 0:
                        st.markdown("**Comments:**")
                        for c in rev_row["Comments"]:
                            col1, col2 = st.columns([4, 1])
                            with col1:
                                st.caption(f"_{c['timestamp']} - {c['user']} ({c['role']}):_ {c['comment']}")
                            with col2:
                                if c.get("attachment_file_id"):
                                    download_file_from_sharepoint(c["attachment_file_id"], "📎 Download Attachment", c.get("attachment_name", "attachment"))
                                elif c.get("attachment_path"):  # برای سازگاری با داده‌های قدیمی
                                    download_file_from_sharepoint(c["attachment_path"], "📎 Download Attachment")

def project_management_page():
    st.title("🏗️ Project Management")
    st.subheader("Existing Projects")
    if st.session_state.projects:
        proj_df = pd.DataFrame([
            {"Project Name": name, "Description": info.get("description", ""), "Created By": info.get("created_by", ""), "Created Date": info.get("created_date", "")}
            for name, info in st.session_state.projects.items()
        ])
        st.dataframe(proj_df, use_container_width=True)
    else:
        st.info("No projects yet.")
    st.markdown("---")
    st.subheader("Create New Project")
    with st.form("create_project_form"):
        proj_name = st.text_input("Project Name")
        proj_desc = st.text_area("Description")
        submit = st.form_submit_button("Create Project")
        if submit:
            if not proj_name.strip():
                st.error("Project name is required.")
            elif proj_name in st.session_state.projects:
                st.error("Project already exists.")
            else:
                st.session_state.projects[proj_name] = {
                    "description": proj_desc,
                    "created_by": st.session_state.username,
                    "created_date": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                save_projects(st.session_state.projects)
                st.success(f"Project '{proj_name}' created successfully.")
                st.rerun()

def user_management_page():
    st.title("👥 User Management")
    st.warning("Only Admin can access this page. Changes are saved immediately.")
    st.subheader("Existing Users")
    users_df = pd.DataFrame([
        {"Username": u, "Full Name": info["full_name"], "Role": info["role"], "Password": "••••••"}
        for u, info in st.session_state.users_db.items()
    ])
    st.dataframe(users_df, use_container_width=True)
    st.markdown("---")
    st.subheader("Change Password")
    with st.form("change_pwd_form"):
        selected_user = st.selectbox("Select User", list(st.session_state.users_db.keys()))
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        submit_pwd = st.form_submit_button("Change Password")
        if submit_pwd:
            if not new_password:
                st.error("Please enter a new password.")
            elif new_password != confirm_password:
                st.error("Passwords do not match.")
            else:
                st.session_state.users_db[selected_user]["password"] = new_password
                save_users(st.session_state.users_db)
                st.success(f"Password for {selected_user} changed successfully.")
    st.markdown("---")
    st.subheader("Add New User")
    with st.form("add_user_form"):
        new_username = st.text_input("Username")
        new_fullname = st.text_input("Full Name")
        new_role = st.selectbox("Role", ["Admin", "DCC", "Lead", "Reviewer", "Responsible", "DocController"])
        new_password = st.text_input("Password", type="password")
        submit_new = st.form_submit_button("Add User")
        if submit_new:
            if not new_username or not new_fullname or not new_password:
                st.error("All fields are required.")
            elif new_username in st.session_state.users_db:
                st.error("Username already exists.")
            else:
                st.session_state.users_db[new_username] = {
                    "full_name": new_fullname,
                    "role": new_role,
                    "password": new_password
                }
                save_users(st.session_state.users_db)
                st.success(f"User {new_username} added successfully.")
                st.rerun()
    st.markdown("---")
    st.subheader("Delete User")
    with st.form("delete_user_form"):
        del_user = st.selectbox("Select User to Delete", [u for u in st.session_state.users_db.keys() if u != st.session_state.username])
        confirm_del = st.checkbox("I understand this action is permanent.")
        submit_del = st.form_submit_button("Delete User")
        if submit_del:
            if not confirm_del:
                st.error("Please confirm deletion.")
            else:
                del st.session_state.users_db[del_user]
                save_users(st.session_state.users_db)
                st.success(f"User {del_user} deleted.")
                st.rerun()

# -----------------------------
# MAIN APP
# -----------------------------
def main_app():
    if not st.session_state.projects:
        if st.session_state.role == "Admin":
            st.warning("No projects defined. Please create your first project.")
            project_management_page()
            return
        else:
            st.error("No projects defined. Please contact Admin.")
            st.stop()
    if st.session_state.current_project is None and st.session_state.projects:
        set_current_project(list(st.session_state.projects.keys())[0])

    menu = show_sidebar()

    if menu == "Dashboard":
        dashboard_page()
    elif menu == "Add MDR":
        add_mdr_page()
    elif menu == "Import MDR from Excel":
        import_mdr_page()
    elif menu == "MDR List":
        mdr_list_page()
    elif menu == "Upload Document":
        upload_document_page()
    elif menu == "External Intake":
        external_intake_page()
    elif menu == "Assign Task":
        assign_task_page()
    elif menu == "Tasks I Created":
        tasks_created_page()
    elif menu == "Review Queue":
        review_queue_page()
    elif menu == "Document History":
        document_history_page()
    elif menu == "Project Management":
        project_management_page()
    elif menu == "User Management":
        user_management_page()

# -----------------------------
# RUN
# -----------------------------
if not st.session_state.get("logged_in", False):
    login()
else:
    main_app()
