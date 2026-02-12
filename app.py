import streamlit as st
import requests
import os
import zipfile
import tempfile
import base64
from pathlib import Path
import json
from datetime import datetime
import numpy as np
from sentence_transformers import SentenceTransformer
import docx
from io import BytesIO

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
    "devops_messages": [],
    "doc_messages": [],
    "wiki_messages": [],
    "memory_summary": "",
    # Estado para DevOps
    "devops_incidencias": [],
    "devops_embeddings": None,
    "devops_indexed": False,
    "embedding_model": None,
    "devops_org": "",
    "devops_project": "",
    "devops_pat": "",
    "devops_top_k": 5,
    # Estado para Documentos
    "doc_content": "",
    "doc_chunks": [],
    "doc_embeddings": None,
    "doc_indexed": False,
    "doc_filename": "",
    "doc_top_k": 3,
    "temp_attachments": [],
    "selected_attachment_url": "",
    "selected_attachment_name": "",
    # Estado para Wiki
    "wiki_paginas_contenido": [],
    "wiki_embeddings": None,
    "wiki_referencias": [],
    "wiki_chunks": [],
    "wiki_indexed": False,
    "wiki_top_k": 5,
    "selected_wiki_id": "",
    "selected_wiki_name": ""
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

# ==================================================
# HELPERS PARA AZURE DEVOPS
# ==================================================

@st.cache_resource
def cargar_modelo_embeddings():
    """Carga el modelo de embeddings una sola vez"""
    return SentenceTransformer('all-MiniLM-L6-v2')

def obtener_incidencias_devops(organization, project, pat, area_path=None, work_item_types=None, max_items=400):
    """
    Obtiene work items de Azure DevOps con filtros configurables
    """
    url = f"https://dev.azure.com/{organization}/{project}/_apis/wit/wiql?api-version=7.1"
    
    # Construir filtro de tipos
    if not work_item_types or len(work_item_types) == 0:
        work_item_types = ['Bug']
    
    if len(work_item_types) == 1:
        type_filter = f"[System.WorkItemType] = '{work_item_types[0]}'"
    else:
        types_str = "', '".join(work_item_types)
        type_filter = f"[System.WorkItemType] IN ('{types_str}')"
    
    # Construir filtro de área
    area_filter = ""
    if area_path:
        area_filter = f"AND [System.AreaPath] = '{area_path}'"
    
    wiql = {
        "query": f"""
            SELECT [System.Id], [System.Title], [System.State], 
                   [System.Description], [System.Tags], 
                   [System.WorkItemType], [System.AreaPath],
                   [Microsoft.VSTS.Common.ResolvedReason],
                   [System.CreatedDate], [System.ChangedDate]
            FROM WorkItems 
            WHERE {type_filter}
            AND [System.State] <> 'Removed'
            {area_filter}
            ORDER BY [System.ChangedDate] DESC
        """
    }
    
    # Encoding del PAT
    credentials = f":{pat}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded_credentials}"
    }
    
    try:
        # Debug
        st.info(f"🔍 Consultando: {organization}/{project}")
        st.info(f"📋 Tipos: {', '.join(work_item_types)}")
        if area_path:
            st.info(f"📁 Área: {area_path}")
        st.info(f"🔢 Límite: {max_items} items")
        
        response = requests.post(url, json=wiql, headers=headers, timeout=30)
        st.write(f"**Status Code:** {response.status_code}")
        
        if response.status_code != 200:
            st.error(f"❌ Error HTTP {response.status_code}")
            st.code(response.text[:500])
            return []
        
        response.raise_for_status()
        
        try:
            response_json = response.json()
        except json.JSONDecodeError as e:
            st.error(f"❌ Error al parsear JSON: {str(e)}")
            st.code(response.text[:500])
            return []
        
        work_item_ids = [item["id"] for item in response_json.get("workItems", [])]
        
        if not work_item_ids:
            st.warning("⚠️ La query no devolvió ningún Work Item")
            st.info("Verifica que existan items del tipo seleccionado")
            return []
        
        # Limitar al máximo configurado
        work_item_ids = work_item_ids[:max_items]
        st.success(f"✅ Se encontraron {len(work_item_ids)} work items")
        
        # Obtener detalles en lotes de 200
        all_items = []
        batch_size = 200
        
        for i in range(0, len(work_item_ids), batch_size):
            batch_ids = work_item_ids[i:i+batch_size]
            ids_str = ",".join(map(str, batch_ids))
            details_url = f"https://dev.azure.com/{organization}/{project}/_apis/wit/workitems?ids={ids_str}&api-version=7.1"
            
            details_response = requests.get(details_url, headers=headers, timeout=30)
            details_response.raise_for_status()
            
            for item in details_response.json().get("value", []):
                fields = item.get("fields", {})
                all_items.append({
                    "id": item["id"],
                    "tipo": fields.get("System.WorkItemType", ""),
                    "titulo": fields.get("System.Title", "Sin título"),
                    "descripcion": fields.get("System.Description", "Sin descripción"),
                    "estado": fields.get("System.State", ""),
                    "area": fields.get("System.AreaPath", ""),
                    "tags": fields.get("System.Tags", ""),
                    "resolucion": fields.get("Microsoft.VSTS.Common.ResolvedReason", ""),
                    "fecha_creacion": fields.get("System.CreatedDate", ""),
                    "fecha_cambio": fields.get("System.ChangedDate", ""),
                    "url": item.get("url", "")
                })
        
        return all_items
    
    except requests.exceptions.Timeout:
        st.error("❌ Timeout: Azure DevOps no respondió a tiempo")
        return []
    except requests.exceptions.RequestException as e:
        st.error(f"❌ Error de conexión: {str(e)}")
        if hasattr(e.response, 'text'):
            st.code(e.response.text[:500])
        return []

def obtener_attachments_workitem(organization, project, pat, work_item_id):
    """
    Obtiene la lista de attachments de un work item
    """
    url = f"https://dev.azure.com/{organization}/{project}/_apis/wit/workitems/{work_item_id}?$expand=all&api-version=7.1"
    
    credentials = f":{pat}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded_credentials}"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        work_item = response.json()
        relations = work_item.get("relations", [])
        
        attachments = []
        for relation in relations:
            if relation.get("rel") == "AttachedFile":
                file_name = relation.get("attributes", {}).get("name", "Unknown")
                # Solo incluir archivos .docx
                if file_name.lower().endswith('.docx'):
                    attachments.append({
                        "url": relation.get("url"),
                        "name": file_name
                    })
        
        return attachments
    
    except Exception as e:
        st.error(f"Error al obtener attachments: {str(e)}")
        return []

def descargar_attachment_devops(attachment_url, pat):
    """
    Descarga un attachment desde Azure DevOps
    """
    credentials = f":{pat}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {encoded_credentials}"
    }
    
    try:
        response = requests.get(attachment_url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.content
    except Exception as e:
        st.error(f"Error al descargar attachment: {str(e)}")
        return None

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
    
    similitudes = np.dot(embeddings, query_embedding) / (
        np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_embedding)
    )
    
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
    contexto = "**Work items similares encontrados en Azure DevOps:**\n\n"
    
    for i, resultado in enumerate(incidencias_similares, 1):
        inc = resultado["incidencia"]
        sim = resultado["similitud"]
        
        contexto += f"**Work Item #{i}** (Similitud: {sim:.2%})\n"
        contexto += f"- **ID**: {inc['id']}\n"
        contexto += f"- **Tipo**: {inc['tipo']}\n"
        contexto += f"- **Título**: {inc['titulo']}\n"
        contexto += f"- **Estado**: {inc['estado']}\n"
        if inc['resolucion']:
            contexto += f"- **Resolución**: {inc['resolucion']}\n"
        contexto += f"- **Descripción**: {limpiar_html(inc['descripcion'])[:500]}...\n"
        contexto += f"- **Tags**: {inc['tags']}\n\n"
    
    return contexto

# ==================================================
# HELPERS PARA DOCUMENTOS
# ==================================================

def leer_docx_desde_bytes(file_bytes):
    """Lee un documento Word desde bytes"""
    try:
        doc = docx.Document(BytesIO(file_bytes))
        texto_completo = []
        
        for para in doc.paragraphs:
            if para.text.strip():
                texto_completo.append(para.text.strip())
        
        # También extraer texto de tablas
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        texto_completo.append(cell.text.strip())
        
        return "\n\n".join(texto_completo)
    except Exception as e:
        st.error(f"Error al leer documento: {str(e)}")
        return ""

def descargar_documento_url(url):
    """Descarga un documento desde una URL pública"""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.content
    except Exception as e:
        st.error(f"Error al descargar documento: {str(e)}")
        return None

def dividir_en_chunks(texto, chunk_size=1000):
    """Divide el texto en fragmentos para embeddings"""
    # Dividir por párrafos primero
    paragrafos = [p.strip() for p in texto.split('\n\n') if p.strip()]
    
    chunks = []
    chunk_actual = ""
    
    for para in paragrafos:
        if len(chunk_actual) + len(para) < chunk_size:
            chunk_actual += para + "\n\n"
        else:
            if chunk_actual:
                chunks.append(chunk_actual.strip())
            chunk_actual = para + "\n\n"
    
    if chunk_actual:
        chunks.append(chunk_actual.strip())
    
    return chunks

def generar_embeddings_documento(chunks, modelo):
    """Genera embeddings para los chunks del documento"""
    with st.spinner("🔄 Generando embeddings del documento..."):
        embeddings = modelo.encode(chunks, show_progress_bar=True)
    return np.array(embeddings)

def buscar_chunks_similares(query, chunks, embeddings, modelo, top_k=3):
    """Busca los chunks más relevantes del documento"""
    query_embedding = modelo.encode([query])[0]
    
    similitudes = np.dot(embeddings, query_embedding) / (
        np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_embedding)
    )
    
    top_indices = np.argsort(similitudes)[-top_k:][::-1]
    
    resultados = []
    for idx in top_indices:
        resultados.append({
            "chunk": chunks[idx],
            "similitud": float(similitudes[idx]),
            "indice": idx
        })
    
    return resultados

def construir_contexto_documento(chunks_similares):
    """Construye el contexto para enviar a Frida con los chunks relevantes"""
    contexto = "**Fragmentos relevantes del documento:**\n\n"
    
    for i, resultado in enumerate(chunks_similares, 1):
        sim = resultado["similitud"]
        chunk = resultado["chunk"]
        
        contexto += f"**Fragmento #{i}** (Relevancia: {sim:.2%})\n"
        contexto += f"{chunk}\n\n"
        contexto += "---\n\n"
    
    return contexto

# ==================================================
# HELPERS PARA AZURE DEVOPS WIKI
# ==================================================

def obtener_wikis_proyecto(organization, project, pat):
    """
    Obtiene la lista de wikis disponibles en el proyecto
    """
    url = f"https://dev.azure.com/{organization}/{project}/_apis/wiki/wikis?api-version=7.1"

    credentials = f":{pat}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded_credentials}"
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        wikis_data = response.json()
        wikis = wikis_data.get("value", [])

        return [{
            "id": wiki.get("id"),
            "name": wiki.get("name"),
            "type": wiki.get("type"),
            "url": wiki.get("url")
        } for wiki in wikis]

    except Exception as e:
        st.error(f"Error al obtener wikis: {str(e)}")
        return []

def obtener_paginas_wiki(organization, project, pat, wiki_id, recursion_level=1):
    """
    Obtiene la lista de páginas de una wiki
    recursion_level=1 muestra la estructura completa
    """
    url = f"https://dev.azure.com/{organization}/{project}/_apis/wiki/wikis/{wiki_id}/pages?recursionLevel={recursion_level}&api-version=7.1"

    credentials = f":{pat}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded_credentials}"
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Función recursiva para aplanar la estructura de páginas
        def aplanar_paginas(page, path=""):
            paginas = []
            current_path = f"{path}/{page.get('path', '')}" if path else page.get('path', '')

            # Solo añadir si tiene ID (las páginas reales tienen ID)
            if page.get('id'):
                paginas.append({
                    "id": page.get("id"),
                    "path": current_path,
                    "order": page.get("order", 0),
                    "gitItemPath": page.get("gitItemPath", ""),
                    "url": page.get("url", "")
                })

            # Procesar subpáginas
            if "subPages" in page:
                for subpage in page["subPages"]:
                    paginas.extend(aplanar_paginas(subpage, current_path))

            return paginas

        # Si hay páginas, aplanarlas
        if "id" in data:
            return aplanar_paginas(data)

        return []

    except Exception as e:
        st.error(f"Error al obtener páginas de la wiki: {str(e)}")
        return []

def obtener_contenido_pagina_wiki(organization, project, pat, wiki_id, page_id):
    """
    Obtiene el contenido de una página específica de la wiki
    """
    # Usar el page_id directamente en la URL con includeContent=true
    url = f"https://dev.azure.com/{organization}/{project}/_apis/wiki/wikis/{wiki_id}/pages/{page_id}?includeContent=true&api-version=7.1"

    credentials = f":{pat}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded_credentials}"
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()

        return {
            "id": data.get("id"),
            "path": data.get("path"),
            "content": data.get("content", ""),
            "gitItemPath": data.get("gitItemPath", "")
        }

    except Exception as e:
        st.error(f"Error al obtener contenido de página: {str(e)}")
        return None

def limpiar_markdown(texto):
    """
    Limpia tags markdown y deja texto limpio
    """
    if not texto:
        return ""
    import re
    # Eliminar bloques de código
    texto = re.sub(r'```[\s\S]*?```', '', texto)
    # Eliminar código inline
    texto = re.sub(r'`[^`]+`', '', texto)
    # Eliminar imágenes
    texto = re.sub(r'!\[.*?\]\(.*?\)', '', texto)
    # Eliminar links pero mantener texto
    texto = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', texto)
    # Eliminar headers markdown
    texto = re.sub(r'^#+\s+', '', texto, flags=re.MULTILINE)
    # Eliminar énfasis
    texto = re.sub(r'[*_]{1,2}([^*_]+)[*_]{1,2}', r'\1', texto)
    # Limpiar espacios múltiples
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

def generar_embeddings_wiki(paginas_contenido, modelo):
    """
    Genera embeddings para las páginas de la wiki
    paginas_contenido: lista de dict con 'path', 'chunks', etc.
    """
    todos_chunks = []
    referencias = []  # Para mantener referencia de página y chunk

    for pagina in paginas_contenido:
        for idx, chunk in enumerate(pagina['chunks']):
            todos_chunks.append(chunk)
            referencias.append({
                'path': pagina['path'],
                'chunk_idx': idx,
                'page_id': pagina['id']
            })

    with st.spinner("🔄 Generando embeddings de páginas Wiki..."):
        embeddings = modelo.encode(todos_chunks, show_progress_bar=True)

    return np.array(embeddings), referencias

def buscar_chunks_wiki_similares(query, chunks, embeddings, referencias, modelo, top_k=5):
    """
    Busca los chunks más relevantes de las páginas Wiki
    """
    query_embedding = modelo.encode([query])[0]

    similitudes = np.dot(embeddings, query_embedding) / (
        np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_embedding)
    )

    top_indices = np.argsort(similitudes)[-top_k:][::-1]

    resultados = []
    for idx in top_indices:
        resultados.append({
            "chunk": chunks[idx],
            "similitud": float(similitudes[idx]),
            "path": referencias[idx]['path'],
            "page_id": referencias[idx]['page_id'],
            "chunk_idx": referencias[idx]['chunk_idx']
        })

    return resultados

def construir_contexto_wiki(chunks_similares):
    """
    Construye el contexto para enviar a Frida con los chunks relevantes de la Wiki
    """
    contexto = "**Fragmentos relevantes de la Wiki de Azure DevOps:**\n\n"

    for i, resultado in enumerate(chunks_similares, 1):
        sim = resultado["similitud"]
        chunk = resultado["chunk"]
        path = resultado["path"]

        contexto += f"**Página: {path}** - Fragmento #{i} (Relevancia: {sim:.2%})\n"
        contexto += f"{chunk}\n\n"
        contexto += "---\n\n"

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
st.session_state.max_tokens = st.sidebar.slider("Max tokens", 100, 4096, 3000, 100)

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
tab_chat, tab_devops, tab_doc = st.tabs([
    "💬 Chat clásico",
    "🎯 Consulta Tareas DevOps",
    "📄 Análisis Documentos"
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

# ================= TAB 2: CONSULTA TAREAS DEVOPS =================
with tab_devops:
    st.title("🎯 Azure DevOps")
    st.markdown("Consulta work items y documentación Wiki de Azure DevOps usando IA")

    # Configuración de Azure DevOps (compartida entre subtabs)
    with st.expander("⚙️ Configuración Azure DevOps", expanded=(not st.session_state.devops_indexed and not st.session_state.wiki_indexed)):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 🔗 Conexión")
            org_input = st.text_input(
                "Organización", 
                value=st.session_state.devops_org if st.session_state.devops_org else "TelepizzaIT",
                placeholder="ej: TelepizzaIT"
            )
            project_input = st.text_input(
                "Proyecto", 
                value=st.session_state.devops_project if st.session_state.devops_project else "Sales",
                placeholder="ej: Sales"
            )
            pat_input = st.text_input(
                "Personal Access Token (PAT)", 
                value=st.session_state.devops_pat,
                type="password",
                help="PAT con permisos de lectura en Work Items"
            )
        
        with col2:
            st.markdown("#### 🎛️ Filtros")
            work_item_types = st.multiselect(
                "Tipos de Work Items",
                options=["Bug", "User Story", "Task", "Feature", "Epic", "Issue", "Test Case"],
                default=["Bug"],
                help="Selecciona uno o más tipos"
            )
            
            area_path_input = st.text_input(
                "Área (opcional)",
                value="",
                placeholder="ej: Sales\\MySaga POC",
                help="Deja vacío para todas las áreas"
            )
            
            max_items = st.slider(
                "Límite de items a traer",
                min_value=50,
                max_value=1000,
                value=200,
                step=50,
                help="Máximo de work items a sincronizar"
            )
            
            top_k_similar = st.slider(
                "Items similares a mostrar",
                min_value=3,
                max_value=10,
                value=5,
                step=1,
                help="Número de items similares para enviar a Frida"
            )
        
        st.markdown("---")
        
        col_btn1, col_btn2 = st.columns([3, 1])
        with col_btn1:
            if st.button("🔄 Sincronizar e Indexar Work Items", use_container_width=True):
                if not org_input or not project_input or not pat_input:
                    st.error("❌ Completa organización, proyecto y PAT")
                elif not work_item_types or len(work_item_types) == 0:
                    st.error("❌ Selecciona al menos un tipo de work item")
                else:
                    st.session_state.devops_org = org_input
                    st.session_state.devops_project = project_input
                    st.session_state.devops_pat = pat_input
                    
                    with st.spinner("📥 Obteniendo work items de Azure DevOps..."):
                        incidencias = obtener_incidencias_devops(
                            org_input, 
                            project_input, 
                            pat_input,
                            area_path=area_path_input if area_path_input else None,
                            work_item_types=work_item_types,
                            max_items=max_items
                        )
                    
                    if incidencias:
                        st.success(f"✅ Se encontraron {len(incidencias)} work items")
                        
                        tipos_count = {}
                        for inc in incidencias:
                            tipo = inc['tipo']
                            tipos_count[tipo] = tipos_count.get(tipo, 0) + 1
                        
                        st.info(f"📊 Distribución: " + ", ".join([f"{t}: {c}" for t, c in tipos_count.items()]))
                        
                        st.session_state.devops_incidencias = incidencias
                        
                        if st.session_state.embedding_model is None:
                            st.session_state.embedding_model = cargar_modelo_embeddings()
                        
                        embeddings = generar_embeddings_incidencias(
                            incidencias, 
                            st.session_state.embedding_model
                        )
                        st.session_state.devops_embeddings = embeddings
                        st.session_state.devops_indexed = True
                        st.session_state.devops_top_k = top_k_similar
                        
                        st.success("✅ Indexación completada. Ahora puedes hacer consultas.")
                        st.rerun()
                    else:
                        st.warning("⚠️ No se encontraron work items o hubo un error")
        
        with col_btn2:
            if st.button("🗑️ Limpiar", use_container_width=True, key="limpiar_devops"):
                st.session_state.devops_incidencias = []
                st.session_state.devops_embeddings = None
                st.session_state.devops_indexed = False
                st.session_state.devops_messages = []
                st.success("✅ Cache limpiado")
                st.rerun()

    st.markdown("---")

    # Crear subtabs
    subtab_workitems, subtab_wiki = st.tabs(["📋 Consulta Work Items", "📚 Consulta Wiki"])

    # ================= SUBTAB 1: CONSULTA WORK ITEMS =================
    with subtab_workitems:
        # Estado de indexación
        if st.session_state.devops_indexed:
            tipos_en_cache = {}
            for inc in st.session_state.devops_incidencias:
                tipo = inc['tipo']
                tipos_en_cache[tipo] = tipos_en_cache.get(tipo, 0) + 1

            tipos_str = ", ".join([f"{t} ({c})" for t, c in tipos_en_cache.items()])
            st.info(f"📊 **{len(st.session_state.devops_incidencias)} work items indexados**: {tipos_str}")
            st.info(f"🎯 **Top-K configurado**: {st.session_state.get('devops_top_k', 5)} items similares por consulta")

        # Chat de consultas
        st.markdown("---")

        col_chat, col_stats = st.columns([2, 1])

        with col_stats:
            st.subheader("📈 Estadísticas")
            if st.session_state.devops_incidencias:
                st.markdown("**Por tipo:**")
                tipos = {}
                for inc in st.session_state.devops_incidencias:
                    tipo = inc['tipo']
                    tipos[tipo] = tipos.get(tipo, 0) + 1
                for tipo, count in sorted(tipos.items()):
                    st.metric(tipo, count)

                st.markdown("---")

                st.markdown("**Por estado:**")
                estados = {}
                for inc in st.session_state.devops_incidencias:
                    estado = inc['estado']
                    estados[estado] = estados.get(estado, 0) + 1
                for estado, count in sorted(estados.items(), key=lambda x: x[1], reverse=True)[:5]:
                    st.text(f"{estado}: {count}")
            else:
                st.info("Sincroniza primero los work items")

        with col_chat:
            st.subheader("💬 Chat de consultas")

            for m in st.session_state.devops_messages:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])

            if devops_query := st.chat_input(
                "Pregunta sobre work items... ej: '¿Cómo se implementó X?'",
                key="devops_chat",
                disabled=not st.session_state.devops_indexed
            ):
                if not st.session_state.devops_indexed:
                    st.warning("⚠️ Primero debes sincronizar e indexar los work items")
                else:
                    st.session_state.devops_messages.append({"role": "user", "content": devops_query})

                    top_k = st.session_state.get('devops_top_k', 5)

                    with st.spinner(f"🔍 Buscando los {top_k} work items más similares..."):
                        resultados = buscar_incidencias_similares(
                            devops_query,
                            st.session_state.devops_incidencias,
                            st.session_state.devops_embeddings,
                            st.session_state.embedding_model,
                            top_k=top_k
                        )

                    contexto = construir_contexto_devops(resultados)

                    system_prompt = """Eres un asistente técnico experto en analizar work items de software.

Cuando respondas:
1. Analiza los work items similares (pueden ser Bugs, User Stories, Tasks, etc.)
2. Si hay coincidencia exacta o similar, explica cómo se resolvió o implementó
3. Si no hay coincidencia exacta, propón soluciones basadas en casos similares
4. Sé específico y técnico
5. Menciona el ID y tipo de los work items relevantes
6. Si encuentras patrones comunes, menciónalo"""

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

                    with st.spinner("🤖 Frida está analizando los work items..."):
                        respuesta = call_ia(payload)

                    st.session_state.devops_messages.append({"role": "assistant", "content": respuesta})

                    with st.expander(f"📋 Ver los {top_k} work items más similares"):
                        for i, resultado in enumerate(resultados, 1):
                            inc = resultado["incidencia"]
                            sim = resultado["similitud"]

                            st.markdown(f"### Work Item {i} - [{inc['tipo']}] ID: {inc['id']} (Similitud: {sim:.1%})")
                            st.markdown(f"**Título:** {inc['titulo']}")
                            st.markdown(f"**Estado:** {inc['estado']}")
                            st.markdown(f"**Área:** {inc['area']}")
                            if inc['resolucion']:
                                st.markdown(f"**Resolución:** {inc['resolucion']}")
                            st.markdown(f"**Descripción:** {limpiar_html(inc['descripcion'])[:300]}...")
                            if inc['tags']:
                                st.markdown(f"**Tags:** {inc['tags']}")
                            st.markdown("---")

                    st.rerun()

    # ================= SUBTAB 2: CONSULTA WIKI =================
    with subtab_wiki:
        st.subheader("📚 Consulta Wiki de Azure DevOps")
        st.markdown("Indexa páginas de la Wiki y haz consultas sobre su contenido")

        # Verificar configuración de Azure DevOps
        if not st.session_state.devops_pat or not st.session_state.devops_org or not st.session_state.devops_project:
            st.warning("⚠️ Primero configura la conexión a Azure DevOps en la sección de Configuración arriba")
            st.stop()

        # Sección de carga de Wiki
        with st.expander("📥 Seleccionar Páginas de Wiki", expanded=not st.session_state.wiki_indexed):
            col1, col2 = st.columns([2, 1])

            with col1:
                # Listar wikis disponibles
                if st.button("🔍 Listar Wikis del Proyecto"):
                    with st.spinner("Obteniendo wikis..."):
                        wikis = obtener_wikis_proyecto(
                            st.session_state.devops_org,
                            st.session_state.devops_project,
                            st.session_state.devops_pat
                        )

                    if wikis:
                        st.session_state.available_wikis = wikis
                        st.success(f"✅ {len(wikis)} wiki(s) encontrada(s)")
                    else:
                        st.error("❌ No se encontraron wikis o hubo un error")

                # Selector de wiki
                if 'available_wikis' in st.session_state and st.session_state.available_wikis:
                    selected_wiki_idx = st.selectbox(
                        "Selecciona una Wiki",
                        options=range(len(st.session_state.available_wikis)),
                        format_func=lambda i: f"{st.session_state.available_wikis[i]['name']} ({st.session_state.available_wikis[i]['type']})",
                        key="wiki_selector"
                    )

                    selected_wiki = st.session_state.available_wikis[selected_wiki_idx]
                    st.session_state.selected_wiki_id = selected_wiki['id']
                    st.session_state.selected_wiki_name = selected_wiki['name']

                    st.info(f"📖 Wiki seleccionada: **{selected_wiki['name']}**")

                    # Botón para listar páginas
                    if st.button("📄 Listar Páginas de esta Wiki"):
                        with st.spinner("Obteniendo páginas..."):
                            paginas = obtener_paginas_wiki(
                                st.session_state.devops_org,
                                st.session_state.devops_project,
                                st.session_state.devops_pat,
                                st.session_state.selected_wiki_id
                            )

                        if paginas:
                            st.session_state.available_wiki_pages = paginas
                            st.success(f"✅ {len(paginas)} página(s) encontrada(s)")
                        else:
                            st.warning("⚠️ No se encontraron páginas en esta wiki")

                    # Selector de páginas (individual + batch)
                    if 'available_wiki_pages' in st.session_state and st.session_state.available_wiki_pages:
                        st.markdown("#### Seleccionar páginas para indexar:")

                        # Opción: Seleccionar todas
                        select_all = st.checkbox("Seleccionar todas las páginas", value=False)

                        # Lista de checkboxes para páginas
                        selected_pages = []

                        if select_all:
                            selected_pages = st.session_state.available_wiki_pages.copy()
                            st.info(f"📑 Todas las páginas seleccionadas ({len(selected_pages)})")
                        else:
                            st.markdown("**Selecciona páginas individualmente:**")
                            for idx, page in enumerate(st.session_state.available_wiki_pages):
                                if st.checkbox(
                                    f"{page['path']}",
                                    value=False,
                                    key=f"wiki_page_{idx}"
                                ):
                                    selected_pages.append(page)

                        st.session_state.selected_wiki_pages = selected_pages

                        if selected_pages:
                            st.success(f"✅ {len(selected_pages)} página(s) seleccionada(s)")

            with col2:
                st.markdown("#### ⚙️ Configuración")
                wiki_chunk_size = st.slider(
                    "Tamaño de fragmentos",
                    min_value=500,
                    max_value=4000,
                    value=1000,
                    step=100,
                    help="Tamaño de cada fragmento de las páginas Wiki"
                )

                wiki_top_k = st.slider(
                    "Fragmentos relevantes",
                    min_value=3,
                    max_value=10,
                    value=5,
                    step=1,
                    help="Número de fragmentos a usar como contexto"
                )

            st.markdown("---")

            # Botones de acción
            col_btn1, col_btn2 = st.columns([3, 1])

            with col_btn1:
                if st.button("🔄 Procesar e Indexar Páginas", use_container_width=True, key="procesar_wiki_btn"):
                    if not hasattr(st.session_state, 'selected_wiki_pages') or len(st.session_state.selected_wiki_pages) == 0:
                        st.error("❌ Debes seleccionar al menos una página de la wiki")
                    else:
                        # Procesar cada página seleccionada
                        paginas_contenido = []
                        progress_bar = st.progress(0)
                        total_pages = len(st.session_state.selected_wiki_pages)

                        for idx, page in enumerate(st.session_state.selected_wiki_pages):
                            progress_bar.progress((idx + 1) / total_pages)

                            with st.spinner(f"Descargando {page['path']}..."):
                                contenido_page = obtener_contenido_pagina_wiki(
                                    st.session_state.devops_org,
                                    st.session_state.devops_project,
                                    st.session_state.devops_pat,
                                    st.session_state.selected_wiki_id,
                                    page['id']
                                )

                            if contenido_page and contenido_page['content']:
                                # Limpiar markdown
                                texto_limpio = limpiar_markdown(contenido_page['content'])

                                # Dividir en chunks
                                chunks = dividir_en_chunks(texto_limpio, chunk_size=wiki_chunk_size)

                                paginas_contenido.append({
                                    'id': page['id'],
                                    'path': page['path'],
                                    'chunks': chunks
                                })

                        if paginas_contenido:
                            st.success(f"✅ {len(paginas_contenido)} página(s) procesada(s)")

                            # Cargar modelo si no está cargado
                            if st.session_state.embedding_model is None:
                                st.session_state.embedding_model = cargar_modelo_embeddings()

                            # Generar embeddings
                            embeddings, referencias = generar_embeddings_wiki(
                                paginas_contenido,
                                st.session_state.embedding_model
                            )

                            # Extraer lista plana de chunks para búsqueda
                            todos_chunks = []
                            for pagina in paginas_contenido:
                                todos_chunks.extend(pagina['chunks'])

                            # Guardar en session_state
                            st.session_state.wiki_paginas_contenido = paginas_contenido
                            st.session_state.wiki_embeddings = embeddings
                            st.session_state.wiki_referencias = referencias
                            st.session_state.wiki_chunks = todos_chunks
                            st.session_state.wiki_indexed = True
                            st.session_state.wiki_top_k = wiki_top_k

                            total_chunks = sum(len(p['chunks']) for p in paginas_contenido)
                            st.success(f"✅ Wiki indexada: {len(paginas_contenido)} páginas, {total_chunks} fragmentos")
                            st.rerun()
                        else:
                            st.error("❌ No se pudo procesar ninguna página")

            with col_btn2:
                if st.button("🗑️ Limpiar", use_container_width=True, key="limpiar_wiki"):
                    st.session_state.wiki_paginas_contenido = []
                    st.session_state.wiki_embeddings = None
                    st.session_state.wiki_referencias = []
                    st.session_state.wiki_chunks = []
                    st.session_state.wiki_indexed = False
                    st.session_state.wiki_messages = []
                    if 'available_wikis' in st.session_state:
                        del st.session_state.available_wikis
                    if 'available_wiki_pages' in st.session_state:
                        del st.session_state.available_wiki_pages
                    if 'selected_wiki_pages' in st.session_state:
                        del st.session_state.selected_wiki_pages
                    st.success("✅ Wiki limpiada")
                    st.rerun()

        # Estado de indexación
        if st.session_state.wiki_indexed:
            total_chunks = len(st.session_state.wiki_chunks)
            total_pages = len(st.session_state.wiki_paginas_contenido)
            st.info(f"📚 **Wiki indexada**: {st.session_state.selected_wiki_name} - {total_pages} páginas, {total_chunks} fragmentos")
            st.info(f"🎯 **Top-K configurado**: {st.session_state.get('wiki_top_k', 5)} fragmentos por consulta")

        st.markdown("---")

        # Chat de consultas Wiki
        st.subheader("💬 Consultas sobre la Wiki")

        for m in st.session_state.wiki_messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

        if wiki_query := st.chat_input(
            "Pregunta sobre la Wiki... ej: '¿Cómo configurar X?'",
            key="wiki_chat",
            disabled=not st.session_state.wiki_indexed
        ):
            if not st.session_state.wiki_indexed:
                st.warning("⚠️ Primero debes seleccionar e indexar páginas de la Wiki")
            else:
                st.session_state.wiki_messages.append({"role": "user", "content": wiki_query})

                top_k = st.session_state.get('wiki_top_k', 5)

                # Buscar chunks relevantes
                with st.spinner(f"🔍 Buscando fragmentos relevantes en la Wiki..."):
                    resultados = buscar_chunks_wiki_similares(
                        wiki_query,
                        st.session_state.wiki_chunks,
                        st.session_state.wiki_embeddings,
                        st.session_state.wiki_referencias,
                        st.session_state.embedding_model,
                        top_k=top_k
                    )

                # Construir contexto
                contexto = construir_contexto_wiki(resultados)

                # Llamar a Frida
                system_prompt = """Eres un asistente experto en analizar documentación técnica de wikis.

Cuando respondas:
1. Basa tu respuesta en la información de los fragmentos de la Wiki proporcionados
2. Si la información no está en los fragmentos, indícalo claramente
3. Menciona las páginas específicas de la Wiki cuando sea relevante
4. Proporciona respuestas claras y estructuradas
5. Si encuentras procedimientos o pasos, enuméralos claramente"""

                payload = {
                    "model": st.session_state.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"{contexto}\n\n**Consulta:** {wiki_query}"}
                    ]
                }

                if st.session_state.include_temp:
                    payload["temperature"] = st.session_state.temperature
                if st.session_state.include_tokens:
                    payload["max_tokens"] = st.session_state.max_tokens

                with st.spinner("🤖 Frida está analizando la Wiki..."):
                    respuesta = call_ia(payload)

                st.session_state.wiki_messages.append({"role": "assistant", "content": respuesta})

                # Mostrar fragmentos usados
                with st.expander(f"📋 Ver fragmentos de Wiki utilizados"):
                    for i, resultado in enumerate(resultados, 1):
                        sim = resultado["similitud"]
                        chunk = resultado["chunk"]
                        path = resultado["path"]

                        st.markdown(f"### Fragmento {i} - Página: {path}")
                        st.markdown(f"**Relevancia:** {sim:.1%}")
                        st.text(chunk[:500] + ("..." if len(chunk) > 500 else ""))
                        st.markdown("---")

                st.rerun()

# ================= TAB 3: ANÁLISIS DOCUMENTOS =================
with tab_doc:
    st.title("📄 Análisis de Documentos")
    st.markdown("Carga un documento Word y haz preguntas sobre su contenido o genera work items automáticamente")
    
    # Configuración del documento
    with st.expander("📥 Cargar Documento", expanded=not st.session_state.doc_indexed):
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("#### Opción 1: Subir archivo local")
            uploaded_doc = st.file_uploader(
                "Sube un documento Word (.docx)", 
                type=["docx"],
                help="Archivo .docx desde tu ordenador",
                key="upload_doc_file"
            )
            
            st.markdown("#### Opción 2: Desde Azure DevOps Work Item")
            col_az1, col_az2 = st.columns(2)
            
            with col_az1:
                workitem_id_input = st.number_input(
                    "ID de Work Item",
                    min_value=0,
                    value=0,
                    step=1,
                    help="ID del work item que contiene el documento adjunto"
                )
            
            with col_az2:
                if st.button("📋 Ver documentos adjuntos", disabled=(workitem_id_input == 0)):
                    if not st.session_state.devops_pat:
                        st.error("❌ Primero configura Azure DevOps en la pestaña 'Consulta Tareas'")
                    else:
                        with st.spinner("Obteniendo adjuntos..."):
                            attachments = obtener_attachments_workitem(
                                st.session_state.devops_org or "TelepizzaIT",
                                st.session_state.devops_project or "Sales",
                                st.session_state.devops_pat,
                                int(workitem_id_input)
                            )
                        
                        if attachments:
                            st.session_state.temp_attachments = attachments
                            st.success(f"✅ {len(attachments)} documento(s) .docx encontrado(s)")
                        else:
                            st.warning("⚠️ No se encontraron documentos .docx en este work item")
            
            # Mostrar lista de attachments si existen
            if st.session_state.temp_attachments:
                st.markdown("**Documentos Word encontrados:**")
                selected_attachment = st.selectbox(
                    "Selecciona un documento",
                    options=range(len(st.session_state.temp_attachments)),
                    format_func=lambda i: st.session_state.temp_attachments[i]["name"],
                    key="selected_attachment_idx"
                )
                
                st.session_state.selected_attachment_url = st.session_state.temp_attachments[selected_attachment]["url"]
                st.session_state.selected_attachment_name = st.session_state.temp_attachments[selected_attachment]["name"]
            
            st.markdown("#### Opción 3: URL pública")
            doc_url = st.text_input(
                "URL del documento",
                placeholder="https://ejemplo.com/documento.docx",
                help="URL de acceso público a un archivo .docx"
            )
        
        with col2:
            st.markdown("#### ⚙️ Configuración")
            chunk_size = st.slider(
                "Tamaño de fragmentos",
                min_value=500,
                max_value=4000,
                value=1000,
                step=100,
                help="Tamaño de cada fragmento del documento"
            )
            
            doc_top_k = st.slider(
                "Fragmentos relevantes",
                min_value=2,
                max_value=5,
                value=3,
                step=1,
                help="Número de fragmentos a usar como contexto"
            )
        
        st.markdown("---")
        
        col_btn1, col_btn2 = st.columns([3, 1])
        
        with col_btn1:
            if st.button("🔄 Procesar Documento", use_container_width=True, key="procesar_doc_btn"):
                doc_bytes = None
                filename = ""
                
                # Opción 1: Archivo local
                if uploaded_doc is not None:
                    doc_bytes = uploaded_doc.read()
                    filename = uploaded_doc.name
                    st.info(f"📄 Procesando: {filename}")
                
                # Opción 2: Desde Azure DevOps
                elif st.session_state.selected_attachment_url:
                    if not st.session_state.devops_pat:
                        st.error("❌ Configura Azure DevOps primero")
                    else:
                        with st.spinner("📥 Descargando desde Azure DevOps..."):
                            doc_bytes = descargar_attachment_devops(
                                st.session_state.selected_attachment_url,
                                st.session_state.devops_pat
                            )
                        filename = st.session_state.selected_attachment_name
                        if doc_bytes:
                            st.info(f"📄 Procesando: {filename}")
                
                # Opción 3: URL pública
                elif doc_url:
                    with st.spinner("📥 Descargando documento desde URL..."):
                        doc_bytes = descargar_documento_url(doc_url)
                    filename = doc_url.split("/")[-1]
                
                else:
                    st.error("❌ Debes subir un archivo, seleccionar uno de Azure DevOps o proporcionar una URL")
                
                if doc_bytes:
                    # Leer contenido
                    with st.spinner("📖 Leyendo contenido del documento..."):
                        contenido = leer_docx_desde_bytes(doc_bytes)
                    
                    if contenido:
                        st.success(f"✅ Documento leído: {len(contenido)} caracteres")
                        
                        # Dividir en chunks
                        chunks = dividir_en_chunks(contenido, chunk_size=chunk_size)
                        st.info(f"📑 Dividido en {len(chunks)} fragmentos")
                        
                        # Cargar modelo si no está cargado
                        if st.session_state.embedding_model is None:
                            st.session_state.embedding_model = cargar_modelo_embeddings()
                        
                        # Generar embeddings
                        embeddings = generar_embeddings_documento(
                            chunks,
                            st.session_state.embedding_model
                        )
                        
                        # Guardar en session_state
                        st.session_state.doc_content = contenido
                        st.session_state.doc_chunks = chunks
                        st.session_state.doc_embeddings = embeddings
                        st.session_state.doc_indexed = True
                        st.session_state.doc_filename = filename
                        st.session_state.doc_top_k = doc_top_k
                        
                        # Limpiar attachments temporales
                        st.session_state.temp_attachments = []
                        st.session_state.selected_attachment_url = ""
                        st.session_state.selected_attachment_name = ""
                        
                        st.success("✅ Documento indexado. Ya puedes hacer consultas o generar work items.")
                        st.rerun()
                    else:
                        st.error("❌ No se pudo leer el contenido del documento")
        
        with col_btn2:
            if st.button("🗑️ Limpiar", use_container_width=True, key="limpiar_doc"):
                st.session_state.doc_content = ""
                st.session_state.doc_chunks = []
                st.session_state.doc_embeddings = None
                st.session_state.doc_indexed = False
                st.session_state.doc_messages = []
                st.session_state.doc_filename = ""
                st.session_state.temp_attachments = []
                st.session_state.selected_attachment_url = ""
                st.session_state.selected_attachment_name = ""
                st.success("✅ Documento eliminado")
                st.rerun()
    
    # Estado del documento
    if st.session_state.doc_indexed:
        st.info(f"📄 **Documento cargado**: {st.session_state.doc_filename} ({len(st.session_state.doc_chunks)} fragmentos)")
        st.info(f"🎯 **Fragmentos por consulta**: {st.session_state.get('doc_top_k', 3)}")
    
    st.markdown("---")
    
    # Pestañas de funcionalidad
    subtab_chat, subtab_generate = st.tabs(["💬 Consultas", "🔧 Generar Work Items"])
    
    # SUBTAB: Consultas sobre el documento
    with subtab_chat:
        st.subheader("💬 Haz preguntas sobre el documento")
        
        for m in st.session_state.doc_messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
        
        if doc_query := st.chat_input(
            "Pregunta sobre el documento... ej: '¿Cuáles son los requisitos principales?'",
            key="doc_chat",
            disabled=not st.session_state.doc_indexed
        ):
            if not st.session_state.doc_indexed:
                st.warning("⚠️ Primero debes cargar y procesar un documento")
            else:
                st.session_state.doc_messages.append({"role": "user", "content": doc_query})
                
                top_k = st.session_state.get('doc_top_k', 3)
                
                # Buscar fragmentos relevantes
                with st.spinner(f"🔍 Buscando fragmentos relevantes..."):
                    resultados = buscar_chunks_similares(
                        doc_query,
                        st.session_state.doc_chunks,
                        st.session_state.doc_embeddings,
                        st.session_state.embedding_model,
                        top_k=top_k
                    )
                
                # Construir contexto
                contexto = construir_contexto_documento(resultados)
                
                # Llamar a Frida
                system_prompt = """Eres un asistente experto en analizar documentos técnicos y de negocio.

Cuando respondas:
1. Basa tu respuesta SOLO en la información de los fragmentos proporcionados
2. Si la información no está en los fragmentos, di que no está disponible en el documento
3. Sé preciso y cita partes específicas cuando sea relevante
4. Estructura tu respuesta de forma clara y concisa"""

                payload = {
                    "model": st.session_state.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"{contexto}\n\n**Pregunta:** {doc_query}"}
                    ]
                }
                
                if st.session_state.include_temp:
                    payload["temperature"] = st.session_state.temperature
                if st.session_state.include_tokens:
                    payload["max_tokens"] = st.session_state.max_tokens
                
                with st.spinner("🤖 Frida está analizando el documento..."):
                    respuesta = call_ia(payload)
                
                st.session_state.doc_messages.append({"role": "assistant", "content": respuesta})
                
                # Mostrar fragmentos usados
                with st.expander(f"📋 Ver fragmentos utilizados"):
                    for i, resultado in enumerate(resultados, 1):
                        sim = resultado["similitud"]
                        chunk = resultado["chunk"]
                        
                        st.markdown(f"### Fragmento {i} (Relevancia: {sim:.1%})")
                        st.text(chunk[:500] + ("..." if len(chunk) > 500 else ""))
                        st.markdown("---")
                
                st.rerun()
    
    # SUBTAB: Generar work items
    with subtab_generate:
        st.subheader("🔧 Generar Work Items desde el Documento")
        
        if not st.session_state.doc_indexed:
            st.warning("⚠️ Primero debes cargar y procesar un documento")
        else:
            col_gen1, col_gen2 = st.columns([2, 1])
            
            with col_gen1:
                instruccion_generacion = st.text_area(
                    "Instrucciones de generación",
                    placeholder="Ej: Genera una épica principal con 3 historias de usuario basándote en los requisitos del documento",
                    height=100
                )
            
            with col_gen2:
                template_generacion = st.selectbox(
                    "Template a usar",
                    [
                        "PO Definicion epica",
                        "PO Definicion epica una historia",
                        "PO Definicion historia",
                        "PO Casos exito",
                        "PO Definicion mejora tecnica",
                        "PO Definicion spike"
                    ]
                )
                
                usar_todo_doc = st.checkbox(
                    "Usar documento completo",
                    value=False,
                    help="Si está marcado, usa todo el documento. Si no, solo fragmentos relevantes"
                )
            
            if st.button("✨ Generar Work Items", use_container_width=True):
                if not instruccion_generacion:
                    st.error("❌ Debes proporcionar instrucciones de generación")
                else:
                    # Decidir contexto
                    if usar_todo_doc:
                        contexto_doc = f"**Documento completo:**\n\n{st.session_state.doc_content[:10000]}"
                        if len(st.session_state.doc_content) > 10000:
                            contexto_doc += "\n\n[Documento truncado por longitud]"
                    else:
                        # Buscar fragmentos relevantes según instrucción
                        with st.spinner("🔍 Buscando fragmentos relevantes..."):
                            resultados = buscar_chunks_similares(
                                instruccion_generacion,
                                st.session_state.doc_chunks,
                                st.session_state.doc_embeddings,
                                st.session_state.embedding_model,
                                top_k=st.session_state.get('doc_top_k', 3)
                            )
                        contexto_doc = construir_contexto_documento(resultados)
                    
                    # Obtener template
                    template_content = get_template(template_generacion)
                    
                    # Preparar prompt combinado
                    prompt_final = f"""Contexto del documento:
{contexto_doc}

Instrucciones:
{instruccion_generacion}

Plantilla a seguir:
{template_content}

Genera el/los work item(s) solicitados siguiendo la plantilla proporcionada y basándote en el contenido del documento."""
                    
                    payload = {
                        "model": st.session_state.model,
                        "messages": [
                            {"role": "user", "content": prompt_final}
                        ]
                    }
                    
                    if st.session_state.include_temp:
                        payload["temperature"] = st.session_state.temperature
                    if st.session_state.include_tokens:
                        payload["max_tokens"] = st.session_state.max_tokens
                    
                    with st.spinner("🤖 Frida está generando los work items..."):
                        resultado_generacion = call_ia(payload)
                    
                    # Mostrar resultado
                    st.success("✅ Work items generados")
                    st.markdown("### Resultado:")
                    st.markdown(resultado_generacion)
                    
                    # Botón para copiar
                    st.text_area(
                        "Copiar resultado",
                        value=resultado_generacion,
                        height=300
                    )
