import streamlit as st
import requests
import os
import zipfile
import tempfile
from pathlib import Path
import json
from datetime import datetime
import numpy as np
from sentence_transformers import SentenceTransformer

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
    "devops_messages": [],
    "repo_memory_summary": "",
    "memory_summary": "",
    "repo_tree": {},
    "repo_tmpdir": None,
    "analysis_cache": {},
    # Nuevo estado para DevOps
    "devops_incidencias": [],
    "devops_embeddings": None,
    "devops_indexed": False,
    "embedding_model": None,
    "devops_org": "",
    "devops_project": "",
    "devops_pat": ""
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

CHUNK_SIZE = 10000  # caracteres por fragmento para archivos grandes

# ==================================================
# HELPERS ORIGINALES
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

def analizar_archivo(filepath, progress_bar=None, current_count=None, total_files=None):
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

    if len(st.session_state.repo_messages) > 10:
        st.session_state.repo_memory_summary = resumir_conversacion(st.session_state.repo_messages[-10:])
        st.session_state.repo_messages = st.session_state.repo_messages[-10:]

    if progress_bar and current_count is not None and total_files:
        progress_bar.progress(current_count / total_files)

    return analysis_full

def analizar_todo_repositorio(base_path):
    st.info("Analizando todos los archivos del repositorio... esto puede tardar")
    CODE_EXTENSIONS = (".py", ".js", ".ts", ".java", ".go", ".cs", ".rb", ".php")
    files_to_analyze = []
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith(CODE_EXTENSIONS):
                files_to_analyze.append(os.path.join(root, file))

    progress_bar = st.progress(0)
    total_files = len(files_to_analyze)
    for idx, filepath in enumerate(files_to_analyze, start=1):
        analizar_archivo(filepath, progress_bar=progress_bar, current_count=idx, total_files=total_files)
    st.success("✅ Análisis completo realizado. Ahora puedes preguntar sobre el repositorio.")

def build_repo_context():
    if st.session_state.repo_memory_summary:
        return [{"role":"system","content":st.session_state.repo_memory_summary}]
    return []

# ==================================================
# HELPERS PARA AZURE DEVOPS
# ==================================================

@st.cache_resource
def cargar_modelo_embeddings():
    """Carga el modelo de embeddings una sola vez"""
    return SentenceTransformer('all-MiniLM-L6-v2')

def obtener_incidencias_devops(organization, project, pat):
    """
    Obtiene las incidencias (bugs) de Azure DevOps
    """
    url = f"https://dev.azure.com/{organization}/{project}/_apis/wit/wiql?api-version=7.1"
    
    # Query para obtener solo bugs (Work Item Type = Bug)
    wiql = {
        "query": """
            SELECT [System.Id], [System.Title], [System.State], 
                   [System.Description], [System.Tags], 
                   [Microsoft.VSTS.Common.ResolvedReason],
                   [System.CreatedDate], [System.ChangedDate]
            FROM WorkItems 
            WHERE [System.WorkItemType] = 'Bug'
            AND [System.State] <> 'Removed'
            ORDER BY [System.ChangedDate] DESC
        """
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {pat}"
    }
    
    try:
        # Primero ejecutamos la query para obtener IDs
        response = requests.post(url, json=wiql, headers=headers)
        response.raise_for_status()
        work_item_ids = [item["id"] for item in response.json().get("workItems", [])]
        
        if not work_item_ids:
            return []
        
        # Obtenemos los detalles de cada work item
        ids_str = ",".join(map(str, work_item_ids[:200]))  # Limitamos a 200 para no saturar
        details_url = f"https://dev.azure.com/{organization}/{project}/_apis/wit/workitems?ids={ids_str}&api-version=7.1"
        
        details_response = requests.get(details_url, headers=headers)
        details_response.raise_for_status()
        
        incidencias = []
        for item in details_response.json().get("value", []):
            fields = item.get("fields", {})
            incidencias.append({
                "id": item["id"],
                "titulo": fields.get("System.Title", "Sin título"),
                "descripcion": fields.get("System.Description", "Sin descripción"),
                "estado": fields.get("System.State", ""),
                "tags": fields.get("System.Tags", ""),
                "resolucion": fields.get("Microsoft.VSTS.Common.ResolvedReason", ""),
                "fecha_creacion": fields.get("System.CreatedDate", ""),
                "fecha_cambio": fields.get("System.ChangedDate", ""),
                "url": item.get("url", "")
            })
        
        return incidencias
    
    except requests.exceptions.RequestException as e:
        st.error(f"Error al conectar con Azure DevOps: {str(e)}")
        return []

def limpiar_html(texto):
    """Limpia tags HTML básicos del texto"""
    if not texto:
        return ""
    import re
    texto = re.sub(r'<[^>]+>', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

def generar_embeddings_incidencias(incidencias, modelo):
    """
    Genera embeddings para cada incidencia
    """
    textos = []
    for inc in incidencias:
        # Combinamos título, descripción y tags para el embedding
        texto_completo = f"{inc['titulo']} {limpiar_html(inc['descripcion'])} {inc['tags']} {inc['resolucion']}"
        textos.append(texto_completo)
    
    with st.spinner("🔄 Generando embeddings de incidencias..."):
        embeddings = modelo.encode(textos, show_progress_bar=True)
    
    return np.array(embeddings)

def buscar_incidencias_similares(query, incidencias, embeddings, modelo, top_k=5):
    """
    Busca las incidencias más similares a la query usando embeddings
    """
    query_embedding = modelo.encode([query])[0]
    
    # Calculamos similitud coseno
    similitudes = np.dot(embeddings, query_embedding) / (
        np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_embedding)
    )
    
    # Obtenemos los índices de los top_k más similares
    top_indices = np.argsort(similitudes)[-top_k:][::-1]
    
    resultados = []
    for idx in top_indices:
        resultados.append({
            "incidencia": incidencias[idx],
            "similitud": float(similitudes[idx])
        })
    
    return resultados

def construir_contexto_devops(incidencias_similares):
    """
    Construye el contexto para enviar a la IA con las incidencias encontradas
    """
    contexto = "**Incidencias similares encontradas en Azure DevOps:**\n\n"
    
    for i, resultado in enumerate(incidencias_similares, 1):
        inc = resultado["incidencia"]
        sim = resultado["similitud"]
        
        contexto += f"**Incidencia #{i}** (Similitud: {sim:.2%})\n"
        contexto += f"- **ID**: {inc['id']}\n"
        contexto += f"- **Título**: {inc['titulo']}\n"
        contexto += f"- **Estado**: {inc['estado']}\n"
        if inc['resolucion']:
            contexto += f"- **Resolución**: {inc['resolucion']}\n"
        contexto += f"- **Descripción**: {limpiar_html(inc['descripcion'])[:500]}...\n"
        contexto += f"- **Tags**: {inc['tags']}\n\n"
    
    return contexto

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
tab_chat, tab_repo, tab_devops = st.tabs([
    "💬 Chat clásico", 
    "📦 Copiloto repositorio",
    "🎯 Consulta Tareas DevOps"
])

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

        if st.button("🔄 Analizar repositorio de nuevo"):
            st.session_state.repo_messages = []
            st.session_state.repo_memory_summary = ""
            st.session_state.analysis_cache = {}
            analizar_todo_repositorio(tmp.name)
        else:
            if not st.session_state.repo_memory_summary:
                analizar_todo_repositorio(tmp.name)

    col1, col2 = st.columns([1,2])

    def render_tree(tree, base, rel=""):
        for k,v in tree.items():
            if v=="FILE":
                st.text(f"📄 {rel}{k}")
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

# ================= TAB 3: CONSULTA TAREAS DEVOPS =================
with tab_devops:
    st.title("🎯 Consulta de Tareas Azure DevOps")
    st.markdown("Pregunta sobre incidencias anteriores y encuentra soluciones similares usando IA")
    
    # Configuración de Azure DevOps
    with st.expander("⚙️ Configuración Azure DevOps", expanded=not st.session_state.devops_indexed):
        col1, col2 = st.columns(2)
        
        with col1:
            org_input = st.text_input(
                "Organización", 
                value=st.session_state.devops_org,
                placeholder="ej: softtek"
            )
            project_input = st.text_input(
                "Proyecto", 
                value=st.session_state.devops_project,
                placeholder="ej: MiProyecto"
            )
        
        with col2:
            pat_input = st.text_input(
                "Personal Access Token (PAT)", 
                value=st.session_state.devops_pat,
                type="password",
                help="Crea un PAT en Azure DevOps con permisos de lectura en Work Items"
            )
            
            st.markdown("---")
            if st.button("🔄 Sincronizar e Indexar Incidencias", use_container_width=True):
                if not org_input or not project_input or not pat_input:
                    st.error("❌ Completa todos los campos de configuración")
                else:
                    st.session_state.devops_org = org_input
                    st.session_state.devops_project = project_input
                    st.session_state.devops_pat = pat_input
                    
                    # Obtener incidencias
                    with st.spinner("📥 Obteniendo incidencias de Azure DevOps..."):
                        incidencias = obtener_incidencias_devops(org_input, project_input, pat_input)
                    
                    if incidencias:
                        st.success(f"✅ Se encontraron {len(incidencias)} incidencias")
                        st.session_state.devops_incidencias = incidencias
                        
                        # Cargar modelo de embeddings
                        if st.session_state.embedding_model is None:
                            st.session_state.embedding_model = cargar_modelo_embeddings()
                        
                        # Generar embeddings
                        embeddings = generar_embeddings_incidencias(
                            incidencias, 
                            st.session_state.embedding_model
                        )
                        st.session_state.devops_embeddings = embeddings
                        st.session_state.devops_indexed = True
                        
                        st.success("✅ Indexación completada. Ahora puedes hacer consultas.")
                        st.rerun()
                    else:
                        st.warning("⚠️ No se encontraron incidencias o hubo un error")
    
    # Mostrar estado de la indexación
    if st.session_state.devops_indexed:
        st.info(f"📊 **{len(st.session_state.devops_incidencias)} incidencias indexadas** y listas para consulta")
    
    # Chat de consultas
    st.markdown("---")
    
    col_chat, col_stats = st.columns([2, 1])
    
    with col_stats:
        st.subheader("📈 Estadísticas")
        if st.session_state.devops_incidencias:
            estados = {}
            for inc in st.session_state.devops_incidencias:
                estado = inc['estado']
                estados[estado] = estados.get(estado, 0) + 1
            
            st.markdown("**Estados de incidencias:**")
            for estado, count in estados.items():
                st.metric(estado, count)
        else:
            st.info("Sincroniza primero las incidencias")
    
    with col_chat:
        st.subheader("💬 Chat de consultas")
        
        # Mostrar mensajes anteriores
        for m in st.session_state.devops_messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
        
        # Input de consulta
        if devops_query := st.chat_input(
            "Pregunta sobre incidencias... ej: '¿Cómo se solucionó el error de login?'", 
            key="devops_chat",
            disabled=not st.session_state.devops_indexed
        ):
            if not st.session_state.devops_indexed:
                st.warning("⚠️ Primero debes sincronizar e indexar las incidencias")
            else:
                # Añadir pregunta del usuario
                st.session_state.devops_messages.append({"role": "user", "content": devops_query})
                
                # Buscar incidencias similares
                with st.spinner("🔍 Buscando incidencias similares..."):
                    resultados = buscar_incidencias_similares(
                        devops_query,
                        st.session_state.devops_incidencias,
                        st.session_state.devops_embeddings,
                        st.session_state.embedding_model,
                        top_k=5
                    )
                
                # Construir contexto para la IA
                contexto = construir_contexto_devops(resultados)
                
                # Preparar prompt para Frida
                system_prompt = """Eres un asistente técnico experto en analizar incidencias de software. 
Tu tarea es ayudar a encontrar soluciones basándote en incidencias anteriores similares.

Cuando respondas:
1. Analiza las incidencias similares que se te proporcionan
2. Si hay una coincidencia exacta o muy similar, explica cómo se resolvió
3. Si no hay coincidencia exacta, propón soluciones basadas en los casos similares
4. Sé específico y técnico en tus recomendaciones
5. Menciona el ID de las incidencias relevantes para que el usuario pueda consultarlas"""

                prompt_completo = f"{system_prompt}\n\n{contexto}\n\n**Consulta del usuario:** {devops_query}"
                
                # Llamar a Frida
                payload = {
                    "model": st.session_state.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"{contexto}\n\n**Consulta:** {devops_query}"}
                    ]
                }
                
                if st.session_state.include_temp:
                    payload["temperature"] = st.session_state.temperature
                if st.session_state.include_tokens:
                    payload["max_tokens"] = st.session_state.max_tokens
                
                with st.spinner("🤖 Frida está analizando las incidencias..."):
                    respuesta = call_ia(payload)
                
                # Añadir respuesta de la IA
                st.session_state.devops_messages.append({"role": "assistant", "content": respuesta})
                
                # Mostrar las incidencias encontradas como referencia
                with st.expander("📋 Ver incidencias similares encontradas"):
                    for i, resultado in enumerate(resultados, 1):
                        inc = resultado["incidencia"]
                        sim = resultado["similitud"]
                        
                        st.markdown(f"### Incidencia {i} - ID: {inc['id']} (Similitud: {sim:.1%})")
                        st.markdown(f"**Título:** {inc['titulo']}")
                        st.markdown(f"**Estado:** {inc['estado']}")
                        if inc['resolucion']:
                            st.markdown(f"**Resolución:** {inc['resolucion']}")
                        st.markdown(f"**Descripción:** {limpiar_html(inc['descripcion'])[:300]}...")
                        st.markdown("---")
                
                st.rerun()
