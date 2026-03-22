"""
Módulo para interactuar con la API de Tilena (GLPI)

Este módulo proporciona funciones para:
- Autenticación con User Token o Usuario/Contraseña
- Búsqueda de tickets con filtros avanzados
- Obtener detalle de tickets
- Listar opciones de búsqueda

Documentación API GLPI: https://github.com/glpi-project/glpi/blob/master/apirest.md
"""

import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import base64


class TilenaAPI:
    """Cliente para la API de Tilena/GLPI"""

    def __init__(
        self,
        base_url: str,
        user_token: Optional[str] = None,
        app_token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        Inicializa el cliente de Tilena API

        Args:
            base_url: URL base de Tilena (ej: https://tilena.fooddeliverybrands.com)
            user_token: Token de usuario para autenticación (opcional si se usa username/password)
            app_token: Token de aplicación (opcional)
            username: Nombre de usuario para autenticación (alternativa a user_token)
            password: Contraseña para autenticación (requerida si se usa username)
        """
        self.base_url = base_url.rstrip('/')
        self.user_token = user_token
        self.app_token = app_token
        self.username = username
        self.password = password
        self.session_token = None
        self.api_url = f"{self.base_url}/apirest.php"

        # Validar que se proporcione al menos un método de autenticación
        if not user_token and not (username and password):
            raise ValueError("Debes proporcionar user_token o username+password")

    def init_session(self) -> tuple[bool, str]:
        """
        Inicia sesión en la API y obtiene el session token

        Returns:
            tuple: (success: bool, error_message: str)
        """
        headers = {
            "Content-Type": "application/json"
        }

        # Autenticación por usuario/contraseña
        if self.username and self.password:
            # GLPI API acepta usuario/contraseña en base64
            auth_string = f"{self.username}:{self.password}"
            auth_bytes = auth_string.encode('utf-8')
            auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
            headers["Authorization"] = f"Basic {auth_b64}"
            print(f"[DEBUG] Usando autenticación Basic (usuario/contraseña)")
        # Autenticación por user_token
        elif self.user_token:
            headers["Authorization"] = f"user_token {self.user_token}"
            print(f"[DEBUG] Usando autenticación por user_token")

        if self.app_token:
            headers["App-Token"] = self.app_token

        url = f"{self.api_url}/initSession"

        try:
            print(f"[DEBUG] Intentando conectar a: {url}")
            headers_safe = {k: v for k, v in headers.items() if k != 'Authorization'}
            print(f"[DEBUG] Headers (sin credenciales): {headers_safe}")

            response = requests.get(
                url,
                headers=headers,
                timeout=30
            )

            print(f"[DEBUG] Status code: {response.status_code}")
            print(f"[DEBUG] Response: {response.text}")

            if response.status_code == 200:
                data = response.json()
                self.session_token = data.get('session_token')
                return True, ""
            else:
                error_msg = f"Error HTTP {response.status_code}: {response.text}"
                print(f"[ERROR] {error_msg}")
                return False, error_msg

        except requests.exceptions.Timeout:
            error_msg = f"Timeout al conectar con {url} (30s)"
            print(f"[ERROR] {error_msg}")
            return False, error_msg
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Error de conexión: No se puede conectar con {url}. Verifica la URL y tu conexión de red. Detalle: {str(e)}"
            print(f"[ERROR] {error_msg}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Error inesperado: {type(e).__name__} - {str(e)}"
            print(f"[ERROR] {error_msg}")
            import traceback
            traceback.print_exc()
            return False, error_msg

    def kill_session(self) -> bool:
        """
        Cierra la sesión actual

        Returns:
            bool: True si la sesión se cerró correctamente
        """
        if not self.session_token:
            return True

        headers = self._get_headers()

        try:
            response = requests.get(
                f"{self.api_url}/killSession",
                headers=headers,
                timeout=30
            )

            self.session_token = None
            return response.status_code == 200

        except Exception as e:
            print(f"Error al cerrar sesión: {str(e)}")
            return False

    def _get_headers(self) -> Dict[str, str]:
        """Retorna los headers necesarios para las peticiones autenticadas"""
        headers = {
            "Content-Type": "application/json",
            "Session-Token": self.session_token
        }

        if self.app_token:
            headers["App-Token"] = self.app_token

        return headers

    def get_ticket(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        """
        Obtiene el detalle completo de un ticket por su ID

        Args:
            ticket_id: ID del ticket

        Returns:
            Dict con la información del ticket o None si hay error
        """
        if not self.session_token:
            success, error_msg = self.init_session()
            if not success:
                print(f"[ERROR] No se pudo iniciar sesión: {error_msg}")
                return None

        headers = self._get_headers()

        try:
            # Obtener ticket
            response = requests.get(
                f"{self.api_url}/Ticket/{ticket_id}",
                headers=headers,
                params={"expand_dropdowns": "true", "with_logs": "true"},
                timeout=30
            )

            if response.status_code == 200:
                ticket = response.json()

                # Obtener seguimientos (followups)
                followups = self._get_ticket_followups(ticket_id)
                if followups:
                    ticket['followups'] = followups

                # Obtener tareas
                tasks = self._get_ticket_tasks(ticket_id)
                if tasks:
                    ticket['tasks'] = tasks

                # Obtener documentos adjuntos
                documents = self._get_ticket_documents(ticket_id)
                if documents:
                    ticket['documents'] = documents

                return ticket
            else:
                print(f"Error al obtener ticket: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"Error al obtener ticket: {str(e)}")
            return None

    def _get_ticket_followups(self, ticket_id: int) -> List[Dict]:
        """Obtiene los seguimientos de un ticket"""
        headers = self._get_headers()

        try:
            response = requests.get(
                f"{self.api_url}/Ticket/{ticket_id}/ITILFollowup",
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            return []
        except:
            return []

    def _get_ticket_tasks(self, ticket_id: int) -> List[Dict]:
        """Obtiene las tareas de un ticket"""
        headers = self._get_headers()

        try:
            response = requests.get(
                f"{self.api_url}/Ticket/{ticket_id}/TicketTask",
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            return []
        except:
            return []

    def _get_ticket_documents(self, ticket_id: int) -> List[Dict]:
        """Obtiene los documentos adjuntos de un ticket"""
        headers = self._get_headers()

        try:
            response = requests.get(
                f"{self.api_url}/Ticket/{ticket_id}/Document",
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            return []
        except:
            return []

    def search_tickets(
        self,
        criteria: Optional[List[Dict]] = None,
        range_start: int = 0,
        range_end: int = 50,
        sort: int = 19,  # 19 = fecha de modificación
        order: str = "DESC"
    ) -> Optional[List[Dict]]:
        """
        Busca tickets con criterios específicos

        Args:
            criteria: Lista de criterios de búsqueda. Formato:
                [
                    {"field": 1, "searchtype": "contains", "value": "texto"},
                    {"link": "AND", "field": 12, "searchtype": "equals", "value": 1}
                ]
            range_start: Inicio del rango de paginación
            range_end: Fin del rango de paginación
            sort: ID del campo por el que ordenar (19 = fecha modificación)
            order: Orden (ASC o DESC)

        Returns:
            Lista de tickets encontrados

        Field IDs comunes:
            1: Título
            12: Estado
            4: Solicitante (requester)
            5: Técnico asignado
            71: Grupo solicitante
            80: Entidad
            14: Categoría
            15: Fecha de apertura
            19: Fecha de modificación
        """
        if not self.session_token:
            success, error_msg = self.init_session()
            if not success:
                print(f"[ERROR] No se pudo iniciar sesión: {error_msg}")
                return None

        headers = self._get_headers()

        # Construir parámetros de búsqueda
        params = {
            "range": f"{range_start}-{range_end}",
            "sort": sort,
            "order": order,
            "forcedisplay[0]": 1,   # Título
            "forcedisplay[1]": 12,  # Estado
            "forcedisplay[2]": 4,   # Solicitante
            "forcedisplay[3]": 5,   # Asignado a
            "forcedisplay[4]": 15,  # Fecha apertura
            "forcedisplay[5]": 19,  # Fecha modificación
            "forcedisplay[6]": 14,  # Categoría
            "forcedisplay[7]": 80,  # Entidad
        }

        # Agregar criterios de búsqueda si se proporcionan
        if criteria:
            for idx, criterion in enumerate(criteria):
                for key, value in criterion.items():
                    params[f"criteria[{idx}][{key}]"] = value

        try:
            response = requests.get(
                f"{self.api_url}/search/Ticket",
                headers=headers,
                params=params,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                return result.get('data', [])
            else:
                print(f"Error en búsqueda: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"Error en búsqueda: {str(e)}")
            return None

    def get_search_options(self) -> Optional[Dict]:
        """
        Obtiene las opciones de búsqueda disponibles para Tickets

        Returns:
            Dict con las opciones de búsqueda y sus IDs
        """
        if not self.session_token:
            success, error_msg = self.init_session()
            if not success:
                print(f"[ERROR] No se pudo iniciar sesión: {error_msg}")
                return None

        headers = self._get_headers()

        try:
            response = requests.get(
                f"{self.api_url}/listSearchOptions/Ticket",
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error al obtener opciones: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"Error al obtener opciones: {str(e)}")
            return None


# Campos de búsqueda comunes para facilitar el uso
SEARCH_FIELDS = {
    "titulo": 1,
    "estado": 12,
    "solicitante": 4,
    "asignado": 5,
    "categoria": 14,
    "fecha_apertura": 15,
    "fecha_modificacion": 19,
    "entidad": 80,
    "grupo_solicitante": 71,
    "prioridad": 3,
    "urgencia": 10,
    "impacto": 11,
    "tipo": 14,
}

# Tipos de búsqueda disponibles
SEARCH_TYPES = {
    "contains": "contiene",
    "equals": "igual a",
    "notequals": "no igual a",
    "lessthan": "menor que",
    "morethan": "mayor que",
    "under": "bajo",
    "notunder": "no bajo",
}

# Estados de tickets comunes en GLPI
TICKET_STATUS = {
    1: "Nuevo",
    2: "En curso (asignado)",
    3: "En curso (planificado)",
    4: "En espera",
    5: "Resuelto",
    6: "Cerrado",
}


def format_ticket_for_display(ticket: Dict) -> str:
    """
    Formatea un ticket para mostrar de forma legible

    Args:
        ticket: Diccionario con datos del ticket

    Returns:
        String formateado con la información del ticket
    """
    output = []
    output.append(f"🎫 **Ticket #{ticket.get('id', 'N/A')}**")
    output.append(f"**Título:** {ticket.get('name', 'Sin título')}")

    status_id = ticket.get('status', 1)
    status_name = TICKET_STATUS.get(status_id, f"Estado {status_id}")
    output.append(f"**Estado:** {status_name}")

    output.append(f"**Fecha apertura:** {ticket.get('date', 'N/A')}")
    output.append(f"**Última modificación:** {ticket.get('date_mod', 'N/A')}")

    if ticket.get('content'):
        output.append(f"\n**Descripción:**\n{ticket.get('content')}")

    if ticket.get('followups'):
        output.append(f"\n**Seguimientos:** {len(ticket['followups'])}")

    if ticket.get('tasks'):
        output.append(f"**Tareas:** {len(ticket['tasks'])}")

    if ticket.get('documents'):
        output.append(f"**Documentos:** {len(ticket['documents'])}")

    return "\n".join(output)
