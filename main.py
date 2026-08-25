from dotenv import load_dotenv
import os
import re
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_openai import ChatOpenAI
from prefix import SQL_PREFIX
from boilerplate import directions_sql_boilerplate, map_boilerplate, stop_marker_boilerplate, directions_map_boilerplate
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent
from tools import setup_tools
from markupsafe import Markup
import markdown
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

load_dotenv()

connection_string = os.getenv("DATABASE_URL") or (
    "postgresql://{user}:{password}@{host}:{port}/{db}".format(
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST", "localhost"),
        port=os.getenv("PG_PORT", "5432"),
        db=os.getenv("TRANSIT_PG_DB", "transit_gpt"),
    )
)

db = SQLDatabase.from_uri(connection_string)
llm = ChatOpenAI(model="gpt-4o-mini")
prefix = SQL_PREFIX.format(
    table_names=db.get_usable_table_names(),
    map_boilerplate=map_boilerplate,
    stop_marker_boilerplate=stop_marker_boilerplate,
    directions_sql_boilerplate=directions_sql_boilerplate,
    directions_map_boilerplate=directions_map_boilerplate,
)

system_message = SystemMessage(content=prefix)
tools = setup_tools(db, llm)
agent_executor = create_react_agent(llm, tools, prompt=system_message)


def extract_and_remove_html(text):
    html_pattern = r"```html\s*([\s\S]*?)\s*```"

    python_pattern = r'<pre\s+class="codehilite"><code\s+class="language-python">(.*?)</code></pre>'
    md_pattern = r"```python(.*?)```"
    python_match = re.search(python_pattern, text, re.DOTALL | re.IGNORECASE)
    md_match = re.search(md_pattern, text, re.DOTALL)
    code_match = python_match or md_match
    if code_match:
        code = code_match.group(1)
        code = code.replace("&quot;", '"').replace("&amp;", "&")
        code = code.replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
        return None, "PDF Generated!", code

    match = re.search(html_pattern, text, re.IGNORECASE)
    if match:
        html_code = match.group(1).strip()
        text_without_html = re.sub(html_pattern, "", text, flags=re.IGNORECASE).strip()
        return Markup(html_code), text_without_html, False

    return None, text, False


def detect_malicious_code(code):
    malicious_patterns = [
        r"import\s+(sys|subprocess|shlex|socket|ctypes|signal|multiprocessing)",
        r"os\.(system|popen|remove|rmdir|rename|chmod|chown|kill|fork)",
        r"subprocess\.(Popen|run|call|check_output)",
        r"eval\(", r"exec\(", r"compile\(",
        r"shutil\.(copy|move|rmtree)",
        r"socket\.", r"requests\.", r"urllib\.",
        r"getattr\(", r"setattr\(",
        r"globals\(", r"locals\(",
        r"importlib\.", r"input\(",
        r"os\.exec", r"ast\.(literal_eval)",
    ]
    for pattern in malicious_patterns:
        if re.search(pattern, code):
            return True
    return False


def process_markdown(text):
    html = markdown.markdown(text, extensions=["extra", "codehilite"])
    return Markup(html)


def process_question(prompted_question, conversation_history):
    context = "\n".join(
        f"Q: {entry['question']}\nA: {entry['answer']}"
        for entry in conversation_history
    )
    consolidated_prompt = f"""
Previous conversation:
{context}
New question: {prompted_question}
Please answer the new question, taking into account the context from the previous conversation."""

    prompt = consolidated_prompt if conversation_history else prompted_question
    content = []

    for s in agent_executor.stream({"messages": [HumanMessage(content=prompt)]}):
        for msg in s.get("agent", {}).get("messages", []):
            for call in msg.tool_calls:
                if sql := call.get("args", {}).get("query", None):
                    print(f"\nSQL: {sql}\n")
            print(msg.content)
            html, stripped_text, code = extract_and_remove_html(msg.content)
            content.append(process_markdown(stripped_text))
            if code and not detect_malicious_code(code):
                code = code.replace(
                    "from reportlab.lib.pages import canvas",
                    "from reportlab.pdfgen import canvas"
                )
                exec(code)
            if html:
                content.append(html)

    return content
