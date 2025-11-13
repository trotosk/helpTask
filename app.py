import streamlit as st
import anthropic
import os
from templates import get_general_template, get_code_template, get_criterios_Aceptacion_template, get_criterios_epica_template, get_criterios_mejora_template, get_spike_template, get_historia_epica_template, get_resumen_reunion_template, get_criterios_epica_only_history_template

# Configurar la página
st.set_page_config(page_title="Softtek Prompts IA", page_icon="🔗")

# Sidebar para la clave API y selección de modelo
st.sidebar.title("Configuración")
#api_key = st.sidebar.text_input("🔑 Clave API de Anthropic", type="password")
api_user = os.getenv("IA_User")
api_pass = os.getenv("IA_Pass")
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
temperatura = st.sidebar.slider("Temperatura", min_value=0.0, max_value=1.0, value=0.7, step=0.1)
max_tokens = st.sidebar.slider("Maximo de tokens", min_value=100, max_value=4096, value=2000, step=100)

# Selecci贸n de template
template_seleccionado = st.sidebar.selectbox(
    "Tipo de prompts",
    options=["Libre", "PO Casos exito", "PO Definicion epica", "PO Definicion epica una historia", "PO Definicion historia", "PO Definicion mejora tecnica", "PO Definicion spike", "PO resumen reunion", "Programador Python"],
    index=0  # por defecto: General
)


# Inicializar historial de mensajes si no existe
if "messages" not in st.session_state:
    st.session_state.messages = []

st.title("💬 Chat Softtek Prompts IA")

# Mostrar historial de chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Entrada del usuario
if prompt := st.chat_input("Escribe tu mensaje..."):
    # Formatear el prompt seg煤n el template seleccionado
    prompt_template = generate_response(template_seleccionado)
    
    # Reemplazar variables en el template
    prompt_final = prompt_template.format(input=prompt)
    # Mostrar mensaje del usuario
    st.session_state.messages.append({"role": "user", "content": prompt, "content_final": prompt_final})
    with st.chat_message("user"):
        st.markdown(prompt)

    if not api_url:
        st.error("⚠️ URL incorrecta. Debes ingresar tu URL API.")
    else:
        try:
            client = anthropic.Anthropic(api_key=api_key)

            # Enviar conversación completa
            with st.spinner("Claude está pensando..."):
                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperatura,
                    messages=[
                        {"role": m["role"], "content": m["content_final"]} for m in st.session_state.messages
                    ]
                )

            # Obtener respuesta
            answer = response.content[0].text

            # Mostrar respuesta
            with st.chat_message("assistant"):
                st.markdown(answer)

            # Guardar en historial
            st.session_state.messages.append({"role": "assistant", "content": answer, "content_final": prompt_final})

        except Exception as e:
            st.error(f"❌ Error al llamar a la API: {e}")


