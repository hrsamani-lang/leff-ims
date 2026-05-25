import streamlit as st
import pandas as pd
from datetime import datetime
import os
import json

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
# FILE STORAGE
# -----------------------------
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_file_locally(file_bytes, file_name, doc_no, revision):
    doc_folder = os.path.join(UPLOAD_DIR, str(doc_no))
    os.makedirs(doc_folder, exist_ok=True)
    file_path = os.path.join(doc_folder, f"Rev{revision}_{file_name}")
    with open(file_path, "wb") as f:
        f.write(file_bytes)
    return file_path

def get_file_link(file_path):
    if os.path.exists(file_path):
        return os.path.abspath(file_path)
    return "File not found"

# -----------------------------
# INIT DATA
# -----------------------------
def init_mdr():
    if os.path.exists("mdr.json") and os.path.getsize("mdr.json") > 0:
        try:
            with open("mdr.json", "r") as f:
                data = json.load(f)
            if data:
                df = pd.DataFrame(data)
                required_cols = ["Doc No", "Title", "Discipline", "Code", "Status", "Current Step", "Revision"]
                for col in required_cols:
                    if col not in df.columns:
                        df[col] = "" if col != "Revision" else 0
                df["Doc No"] = df["Doc No"].astype(str)
                return df
        except:
            pass
    return pd.DataFrame(columns=["Doc No", "Title", "Discipline", "Code", "Status", "Current Step", "Revision"])

def init_documents():
    if os.path.exists("documents.json") and os.path.getsize("documents.json") > 0:
        try:
            with open("documents.json", "r") as f:
                data = json.load(f)
            if data:
                df = pd.DataFrame(data)
                required_cols = ["Doc No", "Revision", "Uploaded By", "Date", "Workflow Step", "Status", "File Path", "Rejection Reason", "Comments", "Source", "Email Reference"]
                for col in required_cols:
                    if col not in df.columns:
                        if col == "Comments":
                            df[col] = pd.Series([[] for _ in range(len(df))])
                        else:
                            df[col] = ""
                df["Doc No"] = df["Doc No"].astype(str)
                return df
        except:
            pass
    return pd.DataFrame(columns=["Doc No", "Revision", "Uploaded By", "Date", "Workflow Step", "Status", "File Path", "Rejection Reason", "Comments", "Source", "Email Reference"])

def init_tasks():
    if os.path.exists("tasks.json") and os.path.getsize("tasks.json") > 0:
        try:
            with open("tasks.json", "r") as f:
                data = json.load(f)
            if data:
                return pd.DataFrame(data)
        except:
            pass
    return pd.DataFrame(columns=["task_id", "doc_no", "description", "assigned_to_user", "assigned_by_user", "due_date", "status"])

if "mdr" not in st.session_state:
    st.session_state.mdr = init_mdr()
if "documents" not in st.session_state:
    st.session_state.documents = init_documents()
if "tasks" not in st.session_state:
    st.session_state.tasks = init_tasks()

# -----------------------------
# AUTH
# -----------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.full_name = None
    st.session_state.role = None

def save_data():
    with open("mdr.json", "w") as f:
        json.dump(st.session_state.mdr.to_dict(orient="records"), f, indent=2)
    docs_save = st.session_state.documents.copy()
    if "Comments" in docs_save.columns:
        docs_save["Comments"] = docs_save["Comments"].apply(lambda x: x if isinstance(x, list) else [])
    with open("documents.json", "w") as f:
        json.dump(docs_save.to_dict(orient="records"), f, indent=2)
    with open("tasks.json", "w") as f:
        json.dump(st.session_state.tasks.to_dict(orient="records"), f, indent=2)

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
                st.rerun()
            else:
                st.error("Invalid password")

def logout():
    for key in ["logged_in", "username", "full_name", "role"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

def add_comment(doc_index, comment_text):
    if not comment_text.strip():
        return
    current_comments = st.session_state.documents.at[doc_index, "Comments"]
    if not isinstance(current_comments, list):
        current_comments = []
    new_comment = {
        "user": st.session_state.full_name,
        "role": st.session_state.role,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "comment": comment_text
    }
    current_comments.append(new_comment)
    st.session_state.documents.at[doc_index, "Comments"] = current_comments
    save_data()

# -----------------------------
# SIDEBAR
# -----------------------------
def show_sidebar():
    st.sidebar.title("LEFF IMS")
    st.sidebar.markdown(f"**User:** {st.session_state.full_name}")
    st.sidebar.markdown(f"**Role:** {st.session_state.role}")
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
    user_mgmt_menu = ["User Management"] if is_admin else []
    full_menu = ["Dashboard"] + upload_menu + external_menu + task_menu + user_mgmt_menu + mdr_menu + ["Document History", "Review Queue"]
    full_menu = list(dict.fromkeys(full_menu))
    return st.sidebar.radio("Navigation", full_menu)

# -----------------------------
# MAIN APP (Full Implementation)
# -----------------------------
def main_app():
    menu = show_sidebar()

    # ---------- DASHBOARD ----------
    if menu == "Dashboard":
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
                            st.session_state.tasks.at[idx, "status"] = "Completed"
                            save_data()
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

    # ---------- USER MANAGEMENT ----------
    elif menu == "User Management":
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

    # ---------- ADD MDR ----------
    elif menu == "Add MDR":
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
                    save_data()
                    st.success("MDR Item Added Successfully")

    # ---------- IMPORT MDR FROM EXCEL ----------
    elif menu == "Import MDR from Excel":
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
                        save_data()
                        st.success(f"Imported {len(new_rows)} new MDR items.")
                    else:
                        st.info("No new items to import.")
                    if duplicates:
                        st.warning(f"Duplicate Doc No(s) skipped: {', '.join(duplicates)}")
                else:
                    st.error(f"Missing columns. Required: {required_cols}")
            except Exception as e:
                st.error(f"Error reading file: {e}")

    # ---------- MDR LIST ----------
    elif menu == "MDR List":
        if st.session_state.role not in ["Admin", "DCC"]:
            st.error("⛔ Only Admin or DCC can view MDR list.")
            return
        st.title("MDR List")
        st.dataframe(st.session_state.mdr, use_container_width=True)
        if st.button("Delete Selected MDR Item (experimental)"):
            doc_to_del = st.selectbox("Select Doc No to delete", st.session_state.mdr["Doc No"])
            if doc_to_del:
                st.session_state.mdr = st.session_state.mdr[st.session_state.mdr["Doc No"] != doc_to_del]
                save_data()
                st.rerun()

    # ---------- UPLOAD DOCUMENT ----------
    elif menu == "Upload Document":
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
                            file_path = save_file_locally(uploaded_file.getvalue(), uploaded_file.name, selected_doc, rev_no)
                        except Exception as e:
                            st.error(f"File save failed: {e}")
                            st.stop()
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
                            "File Path": file_path,
                            "Rejection Reason": "",
                            "Comments": [],
                            "Source": "Internal",
                            "Email Reference": ""
                        }])
                        st.session_state.documents = pd.concat([st.session_state.documents, new_doc], ignore_index=True)
                        save_data()
                        st.success(f"Document uploaded as Revision {rev_no} and sent to DCC for review.")

    # ---------- EXTERNAL INTAKE ----------
    elif menu == "External Intake":
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
                        file_path = save_file_locally(uploaded_file.getvalue(), uploaded_file.name, doc_no, 1)
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
                            "File Path": file_path,
                            "Rejection Reason": "",
                            "Comments": [],
                            "Source": source,
                            "Email Reference": email_reference
                        }])
                        st.session_state.documents = pd.concat([st.session_state.documents, new_doc_row], ignore_index=True)
                        save_data()
                        st.success(f"External document from {source} registered as {doc_no} and sent to DCC.")

    # ---------- ASSIGN TASK ----------
    elif menu == "Assign Task":
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
                        "status": "Pending"
                    }])
                    st.session_state.tasks = pd.concat([st.session_state.tasks, new_task], ignore_index=True)
                    save_data()
                    st.success(f"Task assigned to {assigned_to_username}")

    # ---------- REVIEW QUEUE ----------
    elif menu == "Review Queue":
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
            for i, row in role_queue.iterrows():
                with st.expander(f"{row['Doc No']} | Rev {row['Revision']} | Step: {row['Workflow Step']}"):
                    st.write(f"**Uploaded By:** {row['Uploaded By']}")
                    st.write(f"**Date:** {row['Date']}")
                    if row.get("Source"):
                        st.info(f"**Source:** {row['Source']}")
                    if row.get("Email Reference"):
                        st.caption(f"**Email Ref:** {row['Email Reference']}")
                    if os.path.exists(row['File Path']):
                        st.markdown(f"**File:** [Open file]({get_file_link(row['File Path'])})")
                    if row["Rejection Reason"]:
                        st.warning(f"**Previous Return Reason:** {row['Rejection Reason']}")
                    if row["Comments"] and len(row["Comments"]) > 0:
                        st.markdown("**Comments History:**")
                        for c in row["Comments"]:
                            st.caption(f"_{c['timestamp']} - {c['user']} ({c['role']}):_ {c['comment']}")
                    with st.form(key=f"comment_form_{i}"):
                        new_comment = st.text_area("Add a comment (no workflow change)", key=f"comment_{i}")
                        if st.form_submit_button("💬 Add Comment"):
                            if new_comment.strip():
                                add_comment(i, new_comment)
                                st.success("Comment added")
                                st.rerun()
                    if row["Status"] == "Rejected":
                        if st.button("📤 Revise & Resubmit", key=f"resubmit_{i}"):
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
                                    "Rejection Reason": "",
                                    "Comments": [],
                                    "Source": row.get("Source", "Internal"),
                                    "Email Reference": row.get("Email Reference", "")
                                }])
                                st.session_state.documents = pd.concat([st.session_state.documents, new_doc], ignore_index=True)
                                st.session_state.documents.loc[i, "Status"] = "Archived"
                                save_data()
                                st.success("New revision created. Please upload corrected document.")
                                st.rerun()
                        continue
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if st.button("✅ Approve", key=f"approve_{i}"):
                            comment_text = st.text_area("Comment (optional)", key=f"approve_comment_{i}")
                            if comment_text:
                                add_comment(i, f"Approved with comment: {comment_text}")
                            current_step = row["Workflow Step"]
                            step_index = WORKFLOW.index(current_step)
                            if step_index < len(WORKFLOW)-1:
                                next_step = WORKFLOW[step_index+1]
                                st.session_state.documents.loc[i, "Workflow Step"] = next_step
                                mdr_idx = st.session_state.mdr[st.session_state.mdr["Doc No"] == row["Doc No"]].index[0]
                                st.session_state.mdr.loc[mdr_idx, "Current Step"] = next_step
                                if next_step == "Responsible" and step_index+1 == len(WORKFLOW)-1:
                                    st.session_state.documents.loc[i, "Status"] = "Completed"
                                    st.session_state.mdr.loc[mdr_idx, "Status"] = "Approved"
                                    st.success("Document fully approved!")
                                else:
                                    st.success(f"Moved to {next_step}")
                            else:
                                st.session_state.documents.loc[i, "Status"] = "Completed"
                                mdr_idx = st.session_state.mdr[st.session_state.mdr["Doc No"] == row["Doc No"]].index[0]
                                st.session_state.mdr.loc[mdr_idx, "Status"] = "Approved"
                                st.success("Document approved.")
                            save_data()
                            st.rerun()
                    with col2:
                        if st.button("❌ Reject (Return to previous step)", key=f"reject_{i}"):
                            reason = st.text_area("Return reason (required)", key=f"reason_{i}")
                            comment_text = st.text_area("Additional comment", key=f"reject_comment_{i}")
                            if not reason:
                                st.error("Please provide a reason.")
                            else:
                                if comment_text:
                                    add_comment(i, f"Returned with comment: {comment_text}")
                                current_step = row["Workflow Step"]
                                step_index = WORKFLOW.index(current_step)
                                if step_index > 0:
                                    prev_step = WORKFLOW[step_index-1]
                                    st.session_state.documents.loc[i, "Workflow Step"] = prev_step
                                    mdr_idx = st.session_state.mdr[st.session_state.mdr["Doc No"] == row["Doc No"]].index[0]
                                    st.session_state.mdr.loc[mdr_idx, "Current Step"] = prev_step
                                    st.session_state.documents.loc[i, "Status"] = "In Progress"
                                    st.session_state.documents.loc[i, "Rejection Reason"] = reason
                                    st.warning(f"Returned to {prev_step}.")
                                else:
                                    st.warning("Already at first step.")
                                save_data()
                                st.rerun()
                    with col3:
                        if st.button("↩️ Request Changes (Return with files)", key=f"request_changes_{i}"):
                            st.session_state[f"show_return_form_{i}"] = True
                        if st.session_state.get(f"show_return_form_{i}", False):
                            with st.form(key=f"return_form_{i}"):
                                return_reason = st.text_area("Reason for changes (required)")
                                comment_text = st.text_area("Detailed comment")
                                return_file = st.file_uploader("Attach file", type=["pdf", "docx", "txt", "jpg", "png"], key=f"return_file_{i}")
                                submit_return = st.form_submit_button("Submit Return Request")
                                if submit_return:
                                    if not return_reason:
                                        st.error("Reason required.")
                                    else:
                                        full_comment = f"Requested changes: {return_reason}"
                                        if comment_text:
                                            full_comment += f"\nComment: {comment_text}"
                                        add_comment(i, full_comment)
                                        if return_file:
                                            comments_dir = os.path.join(UPLOAD_DIR, "comments", row["Doc No"], f"rev_{row['Revision']}")
                                            os.makedirs(comments_dir, exist_ok=True)
                                            file_path = os.path.join(comments_dir, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{return_file.name}")
                                            with open(file_path, "wb") as f:
                                                f.write(return_file.getbuffer())
                                            add_comment(i, f"Attached file: {return_file.name}")
                                        current_step = row["Workflow Step"]
                                        step_index = WORKFLOW.index(current_step)
                                        if step_index > 0:
                                            prev_step = WORKFLOW[step_index-1]
                                            st.session_state.documents.loc[i, "Workflow Step"] = prev_step
                                            mdr_idx = st.session_state.mdr[st.session_state.mdr["Doc No"] == row["Doc No"]].index[0]
                                            st.session_state.mdr.loc[mdr_idx, "Current Step"] = prev_step
                                            st.session_state.documents.loc[i, "Status"] = "In Progress"
                                            st.session_state.documents.loc[i, "Rejection Reason"] = return_reason
                                            st.warning(f"Returned to {prev_step} for changes.")
                                        else:
                                            st.warning("Already at first step.")
                                        save_data()
                                        st.session_state[f"show_return_form_{i}"] = False
                                        st.rerun()

    # ---------- DOCUMENT HISTORY ----------
    elif menu == "Document History":
        st.title("Document History")
        if len(st.session_state.mdr) == 0:
            st.warning("No MDR items available.")
        else:
            doc_list = st.session_state.mdr["Doc No"].unique()
            selected_doc = st.selectbox("Select Document", doc_list)
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
                        if rev_row["File Path"] and os.path.exists(rev_row["File Path"]):
                            st.markdown(f"**File:** [Open file]({get_file_link(rev_row['File Path'])})")
                        if rev_row["Comments"] and len(rev_row["Comments"]) > 0:
                            st.markdown("**Comments:**")
                            for c in rev_row["Comments"]:
                                st.caption(f"_{c['timestamp']} - {c['user']} ({c['role']}):_ {c['comment']}")

# -----------------------------
# RUN
# -----------------------------
if not st.session_state.get("logged_in", False):
    login()
else:
    main_app()
