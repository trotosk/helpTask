import streamlit as st
import requests
import os
import zipfile
import tempfile
from pathlib import Path

# =====================
# CONFIG
# =====================
st.set_page_config(
    page_title="Softtek IA – Repo Copilot",
    page_icon="🧠",
    layout="wide"
)

API_URL = os.getenv("IA_URL")
API_RESOURCE = os.getenv("IA_RESOURCE_CONSULTA")
TOKEN = os.getenv("IA_TOKEN")

MODEL_DEFAULT = "gpt-5"
MAX_MESSAGES = 12

IGNORED_DIRS = [
    ".git", "node_modules", "venv", "__pycache__",
    "dist", "build", ".idea", ".vscode"
]

CODE_EXTENSIONS = (".py", ".js", ".ts", ".java", ".go", ".cs")

# =====================
# STATE
# =====================
for key, default in {
    "messages": [],
    "memory_summary": "",
    "repo_tree": {},
    "repo_path": None,
    "analysis_cache": {}
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# =====================
# HELPERS IA
# =====================
def call_ia(messages, temperature=0.2):
    payload = {
        "model": MODEL_DEFAULT,
        "messages": messages,
        "temperature": temperature
    }
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    r = requests.post(
        API_URL + API_RESOURCE,
        json=payload,
        headers=headers,
        timeout=120
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

# =====================
# MEMORIA RESUMIDA (REAL)
# =====================
def resumir_conversacion(messages):
    prompt = [
        {
            "role": "system",
            "content": (
                "Resume la conversación técnica manteniendo:\n"
                "- Objetivo del usuario\n"
                "- Decisiones técnicas\n"
                "- Qué partes del repositorio se han analizado\n"
                "- Qué queda pendiente\n"
                "Resumen conciso y técnico."
            )
        },
        {
            "role": "user",
            "content": "\n".join(
                f"{m['role']}: {m['content']}"
                for m in messages
            )
        }
    ]
    return call_ia(prompt)

# =====================
# ZIP + INDEXADO
# =====================
def build_repo_tree(base_path):
    tree = {}

    for root, dirs, files in os.walk(base_path):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]

        rel = os.path.relpath(root, base_path)
        node = tree
        if rel != ".":
            for part in rel.split(os.sep):
                node = node.setdefault(part, {})

        for f in files:
            if f.endswith(CODE_EXTENSIONS):
                node[f] = "FILE"

    return tree

def extract_zip(uploaded_zip):
    tmp = tempfile.TemporaryDirectory()
    zip_path = Path(tmp.name) / uploaded_zip.name

    with open(zip_path, "wb") as f:
        f.write(uploaded_zip.read())

    with zipfile.ZipFile(zip_path) as z:
        z.extractall(tmp.name)

    return tmp

# =====================
# UI SIDEBAR
# =====================
st.sidebar.title("🧠 Configuración")

if st.sidebar.button("🧹 Nuevo Chat"):
    for k in st.session_state.keys():
        st.session_state[k] = [] if isinstance(st.session_state[k], list) else {}

model = st.sidebar.selectbox(
    "Modelo IA",
    ["gpt-5", "gpt-5-mini", "claude-4-sonnet"],
    index=0
)
MODEL_DEFAULT = model

uploaded_zip = st.sidebar.file_uploader(
    "📦 Subir repositorio (.zip)",
    type=["zip"]
)

if uploaded_zip:
    with st.spinner("Procesando repositorio..."):
        tmp = extract_zip(uploaded_zip)
        st.session_state.repo_path = tmp
        st.session_state.repo_tree = build_repo_tree(tmp.name)
    st.sidebar.success("Repositorio listo")

# =====================
# UX EXPLORADOR
# =====================
st.title("🧠 IA Copilot sobre Repositorio")

col1, col2 = st.columns([1, 2])

def render_tree(tree, path=""):
    for k, v in tree.items():
        if v == "FILE":
            if st.button(f"📄 {path}{k}", key=path+k):
                analizar_archivo(os.path.join(st.session_state.repo_path.name, path, k))
        else:
            with st.expander(f"📁 {path}{k}"):
                render_tree(v, path + k + "/")

def analizar_archivo(filepath):
    if filepath in st.session_state.analysis_cache:
        st.info("Usando análisis en caché")
        st.session_state.messages.append({
            "role": "assistant",
            "content": st.session_state.analysis_cache[filepath]
        })
        return

    with open(filepath, encoding="utf-8", errors="ignore") as f:
        code = f.read()

    prompt = [
        {
            "role": "system",
            "content": "Analiza este archivo de código. Explica responsabilidades y dependencias."
        },
        {
            "role": "user",
            "content": code[:12000]
        }
    ]

    analysis = call_ia(prompt)
    st.session_state.analysis_cache[filepath] = analysis

    st.session_state.messages.append({
        "role": "assistant",
        "content": analysis
    })

with col1:
    st.subheader("📂 Repositorio")
    if st.session_state.repo_tree:
        render_tree(st.session_state.repo_tree)
    else:
        st.info("Sube un ZIP para empezar")

with col2:
    st.subheader("💬 Chat técnico")

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if prompt := st.chat_input("Pregunta sobre el repositorio..."):

        if len(st.session_state.messages) > MAX_MESSAGES:
            st.session_state.memory_summary = resumir_conversacion(
                st.session_state.messages[:-4]
            )
            st.session_state.messages = st.session_state.messages[-4:]

        context = ""
        if st.session_state.memory_summary:
            context += f"MEMORIA:\n{st.session_state.memory_summary}\n\n"

        prompt_final = context + prompt

        st.session_state.messages.append({
            "role": "user",
            "content": prompt
        })

        response = call_ia([
            {"role": "system", "content": prompt_final}
        ])

        st.session_state.messages.append({
            "role": "assistant",
            "content": response
        })
