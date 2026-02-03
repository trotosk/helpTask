import streamlit as st
import requests
import os
import zipfile
import tempfile
from pathlib import Path

# ==================================================
# USUARIOS FIJOS
# ==================================================
USERS = {
    "antonio.alcaraz@softtek.com": "123456",
    "tester@softtek.com": "123456"
}

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_email = ""

# PANTALLA DE LOGIN
if not st.session_state.logged_in:
    st.title("🔒 Iniciar sesión")
    email = st.text_input("Correo")
    password = st.text_input("Contraseña", type="password")
    if st.button("Entrar"):
        if email in USERS and USERS[email] == password:
            st.session_state.logged_in = True
            st.session_state.user_email = email
            st.success(f"Bienvenido {email}!")
            st.rerun()
        else:
            st.error("Correo o contraseña incorrectos")
    st.stop()

# ==================================================
# IMPORTS DE TEMPLATES Y CONFIG
# ==================================================
from templates import (
    get_general_template,
    get_code_template,
    get_criterios_Aceptacion_template,
    get_criterios_epica_template,
    get_criterios_mejora_template,
    get_spike_template,
    get_historia_epica_template,
    get_resumen_reunion_template,
    get_criterios_epica_only_history_template
)

st.set_page_config(
    page_title="Softtek Prompts IA",
    page_icon="🧠",
    layout="wide"
)

API_URL = os.getenv("IA_URL")
API_RESOURCE = os.getenv("IA_RESOURCE_CONSULTA")
TOKEN = os.getenv("IA_TOKEN")

# ==================================================
# ESTADO INICIAL
# ==================================================
defaults = {
    "messages": [],
    "repo_messages": [],
    "repo_memory_summary": "",
    "memory_summary": "",
    "repo_tree": {},
    "repo_tmpdir": None,
    "analysis_cache": {}
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

CHUNK_SIZE = 10000  # caracteres por fragmento para archivos grandes

# ==================================================
# HELPERS
# ==================================================
def call_ia(payload):
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

def get_template(tipo):
    return {
        "Libre": get_general_template(),
        "PO Casos exito": get_criterios_Aceptacion_template(),
        "Programador Python": get_code_template(),
        "PO Definicion epica": get_criterios_epica_template(),
        "PO Definicion epica una historia": get_criterios_epica_only_history_template(),
        "PO Definicion mejora tecnica": get_criterios_mejora_template(),
        "PO Definicion spike": get_spike_template(),
        "PO Definicion historia": get_historia_epica_template(),
        "PO resumen reunion": get_resumen_reunion_template()
    }.get(tipo, get_general_template())

def resumir_conversacion(messages):
    resumen_prompt = [
        {"role": "system", "content": "Resume la conversación técnica manteniendo contexto y decisiones"},
        {"role": "user", "content": "\n".join(f"{m['role']}: {m['content']}" for m in messages)}
    ]
    return call_ia({"model": st.session_state.model, "messages": resumen_prompt})

def extract_zip(uploaded_zip):
    tmp = tempfile.TemporaryDirectory()
    zip_path = Path(tmp.name) / uploaded_zip.name
    with open(zip_path, "wb") as f:
        f.write(uploaded_zip.read())
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(tmp.name)
    return tmp

def build_repo_tree(base_path):
    tree = {}
    IGNORED_DIRS = [".git", "node_modules", "venv", "__pycache__", "dist", "build", ".idea", ".vscode"]
    CODE_EXTENSIONS = (".py", ".js", ".ts", ".java", ".go", ".cs", ".rb", ".php")
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

def analizar_archivo(filepath):
    """Analiza un archivo grande por chunks y actualiza cache y memoria resumida."""
    if filepath in st.session_state.analysis_cache:
        return st.session_state.analysis_cache[filepath]

    with open(filepath, encoding="utf-8", errors="ignore") as f:
        code = f.read()
    fragments = [code[i:i+CHUNK_SIZE] for i in range(0, len(code), CHUNK_SIZE)]
    analysis_full = ""
    for fragment in fragments:
        payload = {
            "model": st.session_state.model,
            "messages": [
                {"role": "system", "content": "Analiza este fragmento de código y explica responsabilidades y dependencias."},
                {"role": "user", "content": fragment}
            ]
        }
        if st.session_state.include_temp:
            payload["temperature"] = st.session_state.temperature
        if st.session_state.include_tokens:
            payload["max_tokens"] = st.session_state.max_tokens
        with st.spinner("🤖 La IA está pensando..."):
            fragment_analysis = call_ia(payload)
        analysis_full += fragment_analysis + "\n"
        st.session_state.repo_messages.append({"role": "assistant", "content": fragment_analysis})

    st.session_state.analysis_cache[filepath] = analysis_full

    # Actualizar memoria resumida cada archivo
    if len(st.session_state.repo_messages) > 10:
        st.session_state.repo_memory_summary = resumir_conversacion(st.session_state.repo_messages[-10:])
        st.session_state.repo_messages = st.session_state.repo_messages[-10:]

    return analysis_full

def analizar_todo_repositorio(base_path):
    st.info("Analizando todos los archivos del repositorio... esto puede tardar")
    CODE_EXTENSIONS = (".py", ".js", ".ts", ".java", ".go", ".cs", ".rb", ".php")
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith(CODE_EXTENSIONS):
                filepath = os.path.join(root, file)
                analizar_archivo(filepath)
    st.success("✅ Análisis completo realizado. Ahora puedes preguntar sobre el repositorio.")

def build_repo_context():
    if st.session_state.repo_memory_summary:
        return [{"role":"system","content":st.session_state.repo_memory_summary}]
    return []

# ==================================================
# SIDEBAR
# ==================================================
st.sidebar.title("⚙️ Configuración")

if st.sidebar.button("🧹 Nuevo Chat"):
    for k in defaults:
        st.session_state[k] = defaults[k]

st.session_state.model = st.sidebar.selectbox(
    "Modelo IA",
    options=[
        "Innovation-gpt4o-mini", "Innovation-gpt4o",
        "o4-mini", "o1", "o1-mini", "o3-mini",
        "o1-preview", "gpt-5-chat", "gpt-4.1",
        "gpt-4.1-mini", "gpt-5", "gpt-5-codex",
        "gpt-5-mini", "gpt-5-nano",
        "gpt-4.1-nano", "claude-3-5-sonnet",
        "claude-4-sonnet", "claude-3-7-sonnet",
        "claude-3-5-haiku", "claude-4-5-sonnet"
    ],
    index=0
)

st.session_state.include_temp = st.sidebar.checkbox("Incluir temperatura", value=True)
st.session_state.temperature = st.sidebar.slider("Temperatura", 0.0, 1.0, 0.7, 0.1)
st.session_state.include_tokens = st.sidebar.checkbox("Incluir max_tokens", value=True)
st.session_state.max_tokens = st.sidebar.slider("Max tokens", 100, 4096, 1500, 100)

template_type = st.sidebar.selectbox(
    "Tipo de prompt inicial",
    [
        "Libre", "PO Casos exito", "PO Definicion epica",
        "PO Definicion epica una historia", "PO Definicion historia",
        "PO Definicion mejora tecnica", "PO Definicion spike",
        "PO resumen reunion", "Programador Python"
    ]
)
prompt_template = st.sidebar.text_area("Contenido del template", get_template(template_type), height=220)

# ==================================================
# TABS
# ==================================================
tab_chat, tab_repo = st.tabs(["💬 Chat clásico", "📦 Copiloto repositorio"])

# ================= TAB 1: CHAT CLÁSICO =================
with tab_chat:
    st.title("💬 Chat Softtek Prompts IA")
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    if prompt := st.chat_input("Escribe tu mensaje..."):
        prompt_final = prompt_template.format(input=prompt) if not st.session_state.messages else prompt
        st.session_state.messages.append({"role": "user", "content": prompt_final})
        payload = {"model": st.session_state.model, "messages": st.session_state.messages}
        if st.session_state.include_temp:
            payload["temperature"] = st.session_state.temperature
        if st.session_state.include_tokens:
            payload["max_tokens"] = st.session_state.max_tokens
        with st.spinner("🤖 La IA está pensando..."):
            answer = call_ia(payload)
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.rerun()

# ================= TAB 2: COPILOTO REPOSITORIO =================
with tab_repo:
    st.title("📦 Copiloto de repositorios")
    uploaded_zip = st.file_uploader("Sube un repositorio (.zip)", type=["zip"])
    if uploaded_zip:
        tmp = extract_zip(uploaded_zip)
        st.session_state.repo_tmpdir = tmp
        st.session_state.repo_tree = build_repo_tree(tmp.name)

        # Analizar todo automáticamente al subir el ZIP
        analizar_todo_repositorio(tmp.name)

    col1, col2 = st.columns([1,2])

    def render_tree(tree, base, rel=""):
        for k,v in tree.items():
            if v=="FILE":
                st.text(f"📄 {rel}{k}")  # solo mostrar nombre de archivo
            else:
                with st.expander(f"📁 {rel}{k}"):
                    render_tree(v, base, rel+ k + "/")

    with col1:
        st.subheader("Repositorio")
        if st.session_state.repo_tree:
            render_tree(st.session_state.repo_tree, st.session_state.repo_tmpdir.name)
        else:
            st.info("Sube un ZIP para empezar")

    with col2:
        st.subheader("Chat técnico")
        for m in st.session_state.repo_messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
        if repo_prompt := st.chat_input("Pregunta sobre el repositorio...", key="repo_chat"):
            payload = {"model": st.session_state.model,
                       "messages": build_repo_context() + st.session_state.repo_messages + [{"role":"user","content":repo_prompt}]}
            if st.session_state.include_temp:
                payload["temperature"] = st.session_state.temperature
            if st.session_state.include_tokens:
                payload["max_tokens"] = st.session_state.max_tokens
            with st.spinner("🤖 La IA está pensando..."):
                answer = call_ia(payload)
            st.session_state.repo_messages.append({"role":"user","content":repo_prompt})
            st.session_state.repo_messages.append({"role":"assistant","content":answer})
            st.rerun()
