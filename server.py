from flask import Flask, render_template, request, session, send_from_directory
from main import process_question
from dotenv import load_dotenv
import os
from uuid import uuid4

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET")

MAX_CONTENT_LENGTH = 3


def get_conversation_history():
    if "conversation_history" not in session:
        session["conversation_history"] = []
    return session["conversation_history"]


def add_to_conversation_history(question, answer):
    history = get_conversation_history()
    history.append({"question": question, "answer": answer})
    if len(history) > MAX_CONTENT_LENGTH:
        history.pop(0)
    session["conversation_history"] = history


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    if "user_id" not in session:
        session["user_id"] = str(uuid4())
    if request.method == "POST":
        if request.form.get("sign_out", None):
            session.clear()
            return render_template("index.html", result=result)
        question = request.form["question"]
        conversation_history = get_conversation_history()
        result = process_question(question, conversation_history)
        add_to_conversation_history(question, result)
    return render_template(
        "index.html",
        result=result,
        gmaps_api_key=os.getenv("GPLACES_API_KEY")
    )


@app.route("/robots.txt")
def robots():
    return send_from_directory(app.static_folder, "robots.txt")


@app.route("/sitemap.xml")
def sitemap():
    return send_from_directory(app.static_folder, "sitemap.xml", mimetype="application/xml")


if __name__ == "__main__":
    app.run(debug=True)
