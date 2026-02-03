import streamlit as st
import requests
import os
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

# =========================
# CONFIGURACIÓN DE PÁGINA
# =========================
st.set_page_config(page_title="Softtek Prompts IA", page_icon="🔗", layout="wide")

# =========================
# ESTADO INICIAL
# =========================
if "messages" not in st.session_state:
    st.session_state.messages = []

if "uploaded_files_content" not in st.session_state:
    st.session_state.uploaded_files_content = ""

# =========================
# SIDEBAR
# =========================
st.sidebar.title("Configuración")

if st.sidebar.button("🧹 Nuevo Chat"):
    st.session_state.messages = []
    st.session_state.uploaded_files_content = ""

bearer_token = os.getenv("IA_TOKEN")
resource_api_ask = os.getenv("IA_RESOURCE_CONSULTA")
api_url = os.getenv("IA_URL")

model = st.sidebar.selectbox(
    "🤖 Modelo IA",
    options=[
        "Innovation-gpt4o-mini", "Innovation-gpt4o", "o4-mini", "o1",
        "o1-mini", "o3-mini", "o1-preview", "gpt-5-chat", "gpt-4.1",
        "gpt-4.1-mini", "gpt-5", "gpt-5-codex", "gpt-5-mini",
        "gpt-5-nano", "gpt-4.1-nano",
        "claude-3-5-sonnet", "claude-4-sonnet",
        "claude-3-7-sonnet", "claude-3-5-haiku", "claude-4-5-sonnet"
    ],
    index=0
)

include_temp = st.sidebar.checkbox("Incluir temperatura", value=True)
temperatura = st.sidebar.slider("Temperatura", 0.0, 1.0, 0.7, 0.1)

include_tokens = st.sidebar.checkbox("Incluir max_tokens", value=True)
max_tokens = st.sidebar.slider("Max tokens", 100, 4096, 1500, 100)

template_seleccionado = st.sidebar.selectbox(
    "Tipo de prompt inicial",
    options=[
        "Libre", "PO Casos exito", "PO Definicion epica",
        "PO Definicion epica una historia", "PO Definicion historia",
        "PO Definicion mejora tecnica", "PO Definicion spike",
        "PO resumen reunion", "Programador Python"
    ],
    index=0
)

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

template_preview = get_template(template_seleccionado)
prompt_template = st.sidebar.text_area(
    "Contenido del template:",
    template_preview,
    height=220
)

# =========================
# SUBIDA DE FICHEROS
# =========================
st.sidebar.markdown("### 📎 Adjuntar ficheros")
uploaded_files = st.sidebar.file_uploader(
    "Puedes subir txt, md, json, csv",
    type=["txt", "md", "json", "csv"],
    accept_multiple_files=True
)

if uploaded_files:
    contents = []
    for file in uploaded_files:
        try:
            content = file.read().decode("utf-8")
            contents.append(f"### Archivo: {file.name}\n{content}")
        except Exception:
            contents.append(f"### Archivo: {file.name}\n(No se pudo leer el contenido)")
    st.session_state.uploaded_files_content = "\n\n".join(contents)

# =========================
# UI PRINCIPAL
# =========================
st.title("💬 Chat Softtek Prompts IA")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content_final"])

# =========================
# INPUT DE CHAT
# =========================
if prompt := st.chat_input("Escribe tu mensaje..."):

    if not st.session_state.messages:
        prompt_final = prompt_template.format(input=prompt)
    else:
        prompt_final = prompt

    # Adjuntar ficheros si existen
    if st.session_state.uploaded_files_content:
        prompt_final += (
            "\n\n---\n"
            "Contexto adicional proporcionado en archivos:\n"
            f"{st.session_state.uploaded_files_content}"
        )

    st.session_state.messages.append({
        "role": "user",
        "content": prompt,
        "content_final": prompt_final
    })

    with st.chat_message("user"):
        st.markdown(prompt)

    if not api_url or not bearer_token or not resource_api_ask:
        st.error("⚠️ Faltan variables de entorno IA_URL, IA_TOKEN o IA_RESOURCE_CONSULTA")
    else:
        try:
            with st.spinner("La IA está pensando..."):
                payload = {
                    "model": model,
                    "messages": [
                        {"role": m["role"], "content": m["content_final"]}
                        for m in st.session_state.messages
                    ],
                    "stream": False
                }

                if include_temp:
                    payload["temperature"] = temperatura
                if include_tokens:
                    payload["max_tokens"] = max_tokens

                headers = {
                    "Authorization": f"Bearer {bearer_token}",
                    "Content-Type": "application/json"
                }

                response = requests.post(
                    api_url + resource_api_ask,
                    json=payload,
                    headers=headers,
                    timeout=60
                )

                response.raise_for_status()
                data = response.json()

                answer = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "No se recibió respuesta.")
                )

            with st.chat_message("assistant"):
                st.markdown(answer)

            st.session_state.messages.append({
                "role": "assistant",
                "content": answer,
                "content_final": answer
            })

        except requests.exceptions.RequestException as e:
            st.error("❌ Error de comunicación con la IA")
            st.exception(e)
