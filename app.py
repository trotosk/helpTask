import streamlit as st
import requests
import os
from templates import get_general_template, get_code_template, get_criterios_Aceptacion_template, get_criterios_epica_template, get_criterios_mejora_template, get_spike_template, get_historia_epica_template, get_resumen_reunion_template, get_criterios_epica_only_history_template

#Botón en sidebar
if st.sidebar.button("🧹 Nuevo Chat"):
    st.session_state.messages = []
    
# Configurar la página
st.set_page_config(page_title="Softtek Prompts IA", page_icon="🔗")


# Sidebar para la clave API y selección de modelo
st.sidebar.title("Configuración")
bearer_token = os.getenv("IA_TOKEN")
resource_api_ask = os.getenv("IA_RESOURCE_CONSULTA")
api_url = os.getenv("IA_URL")

def generate_response(template_type="PO Casos exito"):
# Definir templates para diferentes casos de uso
# Seleccion de template
    if template_seleccionado == "Libre":
        template = get_general_template()
    elif template_seleccionado == "PO Casos exito":
        template = get_criterios_Aceptacion_template()
    elif template_seleccionado == "Programador Python":
        template = get_code_template()
    elif template_seleccionado == "PO Definicion epica":
        template = get_criterios_epica_template()
    elif template_seleccionado == "PO Definicion epica una historia":
        template = get_criterios_epica_only_history_template()
    elif template_seleccionado == "PO Definicion mejora tecnica":
        template = get_criterios_mejora_template()
    elif template_seleccionado == "PO Definicion spike":
        template = get_spike_template()
    elif template_seleccionado == "PO Definicion historia":
        template = get_historia_epica_template()
    elif template_seleccionado == "PO resumen reunion":
        template = get_resumen_reunion_template()

    return template


model = st.sidebar.selectbox(
    "🤖 Modelo IA",
    options=["Innovation-gpt4o-mini", "Innovation-gpt4o", "o4-mini", "o1", "o1-mini", "o3-mini", "o1-preview", "gpt-5-chat", "gpt-4.1", "gpt-4.1-mini", "gpt-5", "gpt-5-codex", "gpt-5-mini", "gpt-5-nano", "gpt-4.1-nano", "claude-3-5-sonnet", "claude-4-sonnet", "claude-3-7-sonnet", "claude-3-5-haiku", "claude-4-5-sonnet"],
    index=0  # por defecto: el primero
)

  # Perimetros de generacion
include_temp = st.sidebar.checkbox("Incluir temperatura", value=True)
temperatura = st.sidebar.slider("Temperatura", min_value=0.0, max_value=1.0, value=0.7, step=0.1)
include_tokens = st.sidebar.checkbox("Incluir max_tokens", value=True)
max_tokens = st.sidebar.slider("Maximo de tokens", min_value=100, max_value=4096, value=1500, step=100)

# Selecci贸n de template
template_seleccionado = st.sidebar.selectbox(
    "Tipo de prompts inicio",
    options=["Libre", "PO Casos exito", "PO Definicion epica", "PO Definicion epica una historia", "PO Definicion historia", "PO Definicion mejora tecnica", "PO Definicion spike", "PO resumen reunion", "Programador Python"],
    index=0  # por defecto: General
)

# Mostrar contenido del template seleccionado en caja no editable
template_preview = generate_response(template_seleccionado)
#st.sidebar.text_area("Contenido del template", template_preview, height=200, disabled=False)
prompt_template = st.sidebar.text_area("Contenido del template:", template_preview, height=200)

# Inicializar historial de mensajes si no existe
if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("💬 Chat Softtek Prompts IA")

# Mostrar historial de chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content_final"])



# Entrada del usuario
if prompt := st.chat_input("Escribe tu mensaje..."):

    if len(st.session_state.messages) == 0:
        # Reemplazar variables en el template
        prompt_final = prompt_template.format(input=prompt)
    else:
        # No hay que reemplazar nada y se asigna directamente tal cual.
        prompt_final = prompt

    # Mostrar mensaje del usuario
    st.session_state.messages.append({"role": "user", "content": prompt, "content_final": prompt_final})
    with st.chat_message("user"):
        st.markdown(prompt)

    if not api_url or not bearer_token or not resource_api_ask:
        st.error("⚠️ Configura IA_URL y IA_TOKEN en tu entorno.")
    else:
        try:
            # Enviar conversación completa
            with st.spinner("La IA está pensando..."):
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {bearer_token}"
                }
                payload = {
                    "model": model,
                    "messages": [{"role": m["role"], "content": m["content_final"]} for m in st.session_state.messages],
                    "stream": False,
                    "user": "user_id"
                }

                # Añadir parámetros opcionales
                if include_temp:
                    payload["temperature"] = temperatura
                if include_tokens:
                    payload["max_tokens"] = max_tokens

                # Logs en consola
                print("=== Payload listo para envio ===")
                print(payload)

                api_url_final = api_url + resource_api_ask
                response = requests.post(api_url_final, json=payload, headers=headers)

                print("=== Status Code ===", response.status_code)
                print("=== Respuesta completa ===", response.text)

                response.raise_for_status()
                data = response.json()

                # Extraer respuesta del JSON
                answer = data.get("choices", [{}])[0].get("message", {}).get("content", "No se recibió respuesta.")

            # Mostrar respuesta
            with st.chat_message("assistant"):
                st.markdown(answer)

            # Guardar en historial
            st.session_state.messages.append({"role": "assistant", "content": data.get("choices", [{}])[0], "content_final": answer})

        except Exception as e:
            st.error(f"❌ Error al llamar a la API: {e}")
            print("=== Error ===", e)


