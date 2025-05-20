import streamlit as st
import docx2txt
import subprocess
import tempfile
import requests
import pandas as pd
import os
import re
import json
from dotenv import load_dotenv
from github import Github
import openai
import google.generativeai as genai
# Load environment variables from .env file
load_dotenv()


# Load Jira credentials from environment variables
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

OLLAMA_MODEL_NAME = "deepseek-r1"  # Change to your actual model name from `ollama list`



def extract_text_from_docx(docx_path):
    return docx2txt.process(docx_path)

def prrse_tasks(text):
    lines = text.split('\n')
    return [line for line in lines if line.strip() != '']

def clean_text(text):
    return text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")

def summarize_with_gemini(text):
    prompt = f"""
Document Task Extraction for Jira Issues

Please analyze the provided document (PDF, DOCX, or TXT) and extract all tasks that should be created as Jira issues. Organize them hierarchically as follows:

1. Identify main tasks/topics that will serve as "Epics" in Jira
2. Identify secondary tasks that will be "Tasks" under their respective Epics
3. Identify detailed work items that will be "Subtasks" under their respective Tasks
4. If a sub-subtask has its own subtasks, include them as sub-subtasks
5. the description should be taken from the document
6. keep the descriptions as short as possible but meaningful and concise which match in my document.

Format the output as JSON with the following structure:
{{
  "tasks": [
    {{
      "title": "Main Task 1",
      "description": "Take description of main task 1 from document",
      "subtasks": [
        {{
          "title": "Subtask 1.1",
          "description": "Take description of subtask 1.1 from document",
          "subtasks": [
            {{
              "title": "Sub-subtask 1.1.1",
              "description": "Take description of sub-subtask 1.1.1 from document"
            }}
          ]
        }}
      ]
    }}
  ]
}}
Important Guidelines:
- use only text from the document to fill in the JSON structure
- Do not add any additional text or comments outside the JSON structure
- don't include any explanations or summaries
- don't use any extra text outside from the document
- Stricly Don't use \n or \t in the title and description
- Don't use any special characters in the title and description
Given the following document content, remove any sections related to:
- Overview Purpose Scope
- Tech stack suggestions
- Time or hour estimates
- Web design notes
- Total days or effort summaries
Document Content:
\"\"\"
{text}
\"\"\"
"""
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        raw_output = response.text.strip()

        match = re.search(r"\{[\s\S]*\}", raw_output)
        if match:
            return match.group(0)
        else:
            st.warning("No JSON block found in Gemini response.")
            return raw_output  # fallback
    except Exception as e:
        st.error(f"Gemini API error: {e}")
        return None


def count_tasks(tasks_data):
    """Count total number of tasks, subtasks, and sub-subtasks"""
    main_tasks = len(tasks_data)
    subtasks_count = 0
    sub_subtasks_count = 0
    
    for task in tasks_data:
        if "subtasks" in task:
            subtasks_count += len(task["subtasks"])
            
            for subtask in task["subtasks"]:
                if "subtasks" in subtask:
                    sub_subtasks_count += len(subtask["subtasks"])
                    
    return main_tasks, subtasks_count, sub_subtasks_count

def display_task_statistics(tasks_data):
    """Display task statistics in a neat layout"""
    main_tasks, subtasks_count, sub_subtasks_count = count_tasks(tasks_data)
    total_tasks = main_tasks + subtasks_count + sub_subtasks_count
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="stats-card">
            <div class="stats-number">{main_tasks}</div>
            <div class="stats-label">Main Tasks</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col2:
        st.markdown(f"""
        <div class="stats-card">
            <div class="stats-number">{subtasks_count}</div>
            <div class="stats-label">Subtasks</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col3:
        st.markdown(f"""
        <div class="stats-card">
            <div class="stats-number">{sub_subtasks_count}</div>
            <div class="stats-label">Sub-subtasks</div>
        </div>
        """, unsafe_allow_html=True)
        
    with col4:
        st.markdown(f"""
        <div class="stats-card">
            <div class="stats-number">{total_tasks}</div>
            <div class="stats-label">Total Tasks</div>
        </div>
        """, unsafe_allow_html=True)

def display_sub_subtasks(sub_subtasks):
    """Display sub-subtasks with nice formatting"""
    for sub_subtask in sub_subtasks:
        st.markdown(f"""
        <div class="sub-subtask-container">
            <div class="sub-subtask-title">{sub_subtask["title"]}</div>
            <div class="sub-subtask-description">{sub_subtask.get("description", "")}</div>
        </div>
        """, unsafe_allow_html=True)

def display_subtasks(subtasks):
    """Display subtasks with nice formatting"""
    for subtask in subtasks:
        st.markdown(f"""
        <div class="subtask-container">
            <div class="subtask-title">{subtask["title"]}</div>
            <div class="subtask-description">{subtask.get("description", "")}</div>
        </div>
        """, unsafe_allow_html=True)
        
        # Check and display sub-subtasks if they exist
        if "subtasks" in subtask and subtask["subtasks"]:
            display_sub_subtasks(subtask["subtasks"])

def display_tasks(tasks_data):
    """Display tasks with nice formatting"""
    for task in tasks_data:
        with st.expander(f"**{task['title']}**", expanded=False):
            st.markdown(f"""
            <div class="task-card">
                <div class="task-title">{task["title"]}</div>
                <div class="task-description">{task.get("description", "")}</div>
            </div>
            """, unsafe_allow_html=True)
            
            # Check and display subtasks if they exist
            if "subtasks" in task and task["subtasks"]:
                display_subtasks(task["subtasks"])

def display_task_table(tasks_data):
    """Display tasks in a table format"""
    # Prepare data for the table
    table_data = []
    
    for task_idx, task in enumerate(tasks_data):
        # Add main task
        table_data.append({
            "Level": "Main Task",
            "ID": f"T{task_idx+1}",
            "Title": task["title"],
            "Description": task.get("description", "")
        })
        
        # Add subtasks
        if "subtasks" in task:
            for subtask_idx, subtask in enumerate(task["subtasks"]):
                table_data.append({
                    "Level": "Subtask",
                    "ID": f"T{task_idx+1}.{subtask_idx+1}",
                    "Title": subtask["title"],
                    "Description": subtask.get("description", "")
                })
                
                # Add sub-subtasks
                if "subtasks" in subtask:
                    for sub_subtask_idx, sub_subtask in enumerate(subtask["subtasks"]):
                        table_data.append({
                            "Level": "Sub-subtask",
                            "ID": f"T{task_idx+1}.{subtask_idx+1}.{sub_subtask_idx+1}",
                            "Title": sub_subtask["title"],
                            "Description": sub_subtask.get("description", "")
                        })
    
    # Convert to DataFrame and display
    df = pd.DataFrame(table_data)
    st.dataframe(df, use_container_width=True, hide_index=True)

def get_valid_issue_types():
    url = f"{JIRA_BASE_URL}/rest/api/3/issuetype"
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    response = requests.get(url, auth=auth)
    if response.status_code == 200:
        return [item["name"] for item in response.json()]
    return []


def create_jira_issue(summary, description, issue_type="Epic", parent_id=None, parent_type=None):
    st.write(f"📝 Creating Jira issue: {summary}")

    url = f"{JIRA_BASE_URL}/rest/api/3/issue"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)

    valid_types = get_valid_issue_types()

    # Auto-determine issue type based on parent
    if not parent_id:
        issue_type_name = "Epic"
    elif parent_type == "Epic":
        issue_type_name = "Task"
    elif parent_type == "Task":
        issue_type_name = "Subtask"
    else:
        issue_type_name = "Task"  # Fallback default

    if issue_type_name not in valid_types:
        st.warning(f"⚠️ Issue type '{issue_type_name}' is invalid. Falling back to 'Task'.")
        issue_type_name = "Task"

    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description or ""}]
                    }
                ]
            },
            "issuetype": {"name": issue_type_name}
        }
    }

    if issue_type_name == "Subtask" and parent_id:
        payload["fields"]["parent"] = {"key": parent_id}
    elif issue_type_name == "Task" and parent_id:
        payload["fields"]["parent"] = {"key": parent_id}
    
        

    response = requests.post(url, json=payload, headers=headers, auth=auth)

    if response.status_code == 201:
        issue_key = response.json().get("key")
        st.success(f"✅ Created {issue_type_name}: {issue_key}")
        return issue_key, issue_type_name
    else:
        st.error(f"❌ Failed to create {issue_type_name}: {summary}")
        st.code(response.text)
        return None, None

def create_github_branch(branch_name, base="main"):
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(GITHUB_REPO)

    try:
        source = repo.get_branch(base)
    except Exception as e:
        st.error(f"⚠️ Could not find base branch '{base}'. Check if it exists in your GitHub repo.")
        st.stop()

    repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=source.commit.sha)

def simulate_test_case_generation(ticket, output_dir="test_cases"):
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, f"{ticket['key']}_test_cases.md")
    
    fake_test_cases = f"""# Test Cases for {ticket['key']} - {ticket['summary']}

**Test Case 1**
- Description: Basic validation of "{ticket['description']}"
- Steps: 
  1. Step one...
  2. Step two...
- Expected Result: Should function correctly
- Priority: High

**Test Case 2**
- Description: Edge case test
- Steps:
  1. Invalid input...
  2. Unexpected scenario...
- Expected Result: Should handle gracefully
- Priority: Medium
"""
    with open(file_path, "w") as f:
        f.write(fake_test_cases)
    
    # print(f"✅ Test Cases Simulated: {file_path}")

def generate_test_case_prompt(ticket):
    return f"""
You are a senior QA engineer. Based on the following task, write two detailed test cases including:
- A title
- Description
- Steps
- Expected Result
- Priority

Task:
Title: {ticket['summary']}
Description: {ticket['description']}
"""

def simulate_test_case_generation_ai(ticket, output_dir="test_cases"):
    try:
        print("in try block for test case generation")
        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"{ticket['key']}_test_cases.md")

        prompt = generate_test_case_prompt(ticket)

        response = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama3-70b-8192",
                "messages": [
                    {"role": "system", "content": "You generate QA test cases."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.5
            }
        )

        # Handle API response
        if response.status_code == 200:
            result = response.json()
            ai_output = result['choices'][0]['message']['content']
            try:
                with open(file_path, "w") as f:
                    f.write(f"# Test Cases for {ticket['key']} - {ticket['summary']}\n\n{ai_output}")
            except Exception as file_error:
                print(f"❌ Error writing test cases to file for {ticket['key']}: {file_error}")
        else:
            error_msg = f"API error {response.status_code}: {response.text}"
            print(f"❌ {error_msg}")
            with open(file_path, "w") as f:
                f.write(f"# Failed to generate test cases for {ticket['key']}\n{error_msg}")
    except Exception as e:
        print(f"❌ Unexpected error during test case generation for {ticket['key']}: {e}")
        fallback_path = os.path.join(output_dir, f"{ticket['key']}_error.log")
        with open(fallback_path, "w") as f:
            f.write(f"# Critical error while processing {ticket['key']}\nError: {str(e)}")


# Streamlit UI
st.set_page_config(page_title="Jira Task Extractor via local llama", layout="wide")
# Custom CSS for styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1E3A8A;
        text-align: center;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #CBD5E1;
    }
    
    .task-card {
        background-color: #F8FAFC;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 15px;
        border-left: 4px solid #1E3A8A;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    .task-title {
        font-size: 1.2rem;
        font-weight: 600;
        color: #1E3A8A;
        margin-bottom: 5px;
    }
    
    .task-description {
        font-size: 0.9rem;
        color: #475569;
        margin-bottom: 10px;
    }
    
    .subtask-container {
        background-color: #F1F5F9;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 12px;
        border-left: 3px solid #3B82F6;
    }
    
    .subtask-title {
        font-size: 1rem;
        font-weight: 500;
        color: #2563EB;
        margin-bottom: 3px;
    }
    
    .subtask-description {
        font-size: 0.85rem;
        color: #64748B;
        margin-bottom: 8px;
    }
    
    .sub-subtask-container {
        background-color: #EFF6FF;
        border-radius: 6px;
        padding: 10px;
        margin-bottom: 8px;
        margin-left: 15px;
        border-left: 2px solid #60A5FA;
    }
    
    .sub-subtask-title {
        font-size: 0.9rem;
        font-weight: 500;
        color: #3B82F6;
        margin-bottom: 2px;
    }
    
    .sub-subtask-description {
        font-size: 0.8rem;
        color: #64748B;
    }
    
    .stats-card {
        background-color: #F0F9FF;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 15px;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }
    
    .stats-number {
        font-size: 1.8rem;
        font-weight: 700;
        color: #0369A1;
    }
    
    .stats-label {
        font-size: 0.9rem;
        color: #475569;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: #F1F5F9;
        border-radius: 6px 6px 0px 0px;
        padding: 10px 16px;
        font-weight: 500;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #DBEAFE !important;
        color: #1E40AF !important;
    }
</style>
""", unsafe_allow_html=True)
st.title("📄📌 Jira Task Extractor using Gemini API")

uploaded_file = st.file_uploader("Upload a project document", type=["docx", "pdf", "txt"])

if uploaded_file is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_file:
        tmp_file.write(uploaded_file.read())
        temp_docx_path = tmp_file.name

    st.success("File uploaded successfully!")

    text = extract_text_from_docx(temp_docx_path)
    cleaned_text = clean_text(text)
    tasks = prrse_tasks(text)

  

    st.subheader("🧠 Generating Summary with LLaMA...")
    if st.button("genrate response"):
        summary = summarize_with_gemini(cleaned_text)
        st.write("### Summary:")
        if summary:
            # create the view to store llama response
            with open("geminisummary.json", "w", encoding="utf-8") as f:
              f.write(summary)
            st.subheader("📦 JSON Task Summary")
            st.text_area("JSON Response", summary, height=300)
            # st.code(summary, language="text")
            # download btn for json download
            # st.download_button(
            #     label="📥 Download Summary as JSON",
            #     data=summary,
            #     file_name="jira_task_summary.json",
            #     mime="application/json"
            # )
        else:
            st.error("Failed to generate summary from the document.")

    # Clean up temp file
    os.unlink(temp_docx_path)


use_saved = st.button("🔁 View the extracted tasks ")
if use_saved:
    try:
        with open("geminisummary.json", "r", encoding="utf-8") as f:
            summary = f.read()
        st.success("Loaded Tasks from saved file.")
        try:
            data = json.loads(summary)
            if "tasks" not in data:
                st.error("Invalid JSON structure: 'tasks' key missing.")
            else:
                tasks_data = data["tasks"]
                display_task_statistics(tasks_data)
                tab1, tab2 = st.tabs(["📋 Task Hierarchy", "📊 Task Table"])

                with tab1:
                    display_tasks(tasks_data)
                with tab2:
                    display_task_table(tasks_data)

            st.success("Task hierarchy visualized successfully!")
            #  jira tickets creation button
            if st.button("🚀 Create Tickets on Jira"):
                try:
                    for t in tasks_data:
                        epic_key, epic_type = create_jira_issue(t["title"], t.get("description", ""))
                        for stask in t.get("subtasks", []):
                            task_key, task_type = create_jira_issue(
                                stask["title"], stask.get("description", ""),
                                parent_id=epic_key, parent_type=epic_type
                            )
                            for sstask in stask.get("subtasks", []):
                                create_jira_issue(
                                    sstask["title"], sstask.get("description", ""),
                                    parent_id=task_key, parent_type=task_type
                                )
                    st.success("🎉 All issues created!")
                except Exception as e:
                    st.error(f"❌ Jira issue creation failed: {e}")
            #  github brnaches creation button
            if st.button("🚀 Create Github Branches "):
                for t in tasks_data:
                    branch_name = f"{t['title'].replace(' ', '_').replace('.', '_')}".lower()
                    try:
                        create_github_branch(branch_name)
                        # st.success(f"Created branch: {branch_name}")
                    except Exception as e:
                        st.error(f"Failed to create branch {branch_name}: {e}")
                    for stask in t.get("subtasks", []):
                        sub_branch_name = f"{t['title'].replace(' ', '_').replace('.', '_')}".lower()
                        try:
                            create_github_branch(sub_branch_name)
                            # st.success(f"Created branch: {sub_branch_name}")
                        except Exception as e:
                            st.error(f"Failed to create branch {sub_branch_name}: {e}")
                        for sstask in stask.get("subtasks", []):
                            sub_sub_branch_name = f"{t['title'].replace(' ', '_').replace('.', '_')}".lower()
                            try:
                                create_github_branch(sub_sub_branch_name)
                                # st.success(f"Created branch: {sub_sub_branch_name}")
                            except Exception as e:
                                st.error(f"Failed to create branch {sub_sub_branch_name}: {e}")
                # st.success("All branches created!")
            
            if st.button("🚀 Create test cases is comming soon "):
                # Simulate test case generation for each task, subtask, and sub-subtask
                def walk_tasks_for_test_cases(tasks, parent_key="T"):
                    for idx, task in enumerate(tasks):
                        task_key = f"{parent_key}{idx+1}"
                        ticket = {
                            "key": task_key,
                            "summary": task.get("title", ""),
                            "description": task.get("description", "")
                        }
                        # replace with this Simulate_test_case_generation_ai for gerating test cases through AI 
                        simulate_test_case_generation_ai(ticket)
                        # Subtasks
                        if "subtasks" in task and task["subtasks"]:
                            walk_tasks_for_test_cases(task["subtasks"], parent_key=f"{task_key}.")
                walk_tasks_for_test_cases(tasks_data)
                st.success("✅  test cases generated for all tasks!")
                # st.write("Creating test is coming soon")

        except json.JSONDecodeError:
            st.error("Could not parse  JSON from file .")
    except FileNotFoundError:
        st.error("json file not found.")

    
    
    