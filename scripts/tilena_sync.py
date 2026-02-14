#!/usr/bin/env python3
"""
Script para sincronizar emails de Tilena con Azure DevOps Work Items

Este script:
1. Se conecta al buzón de correo (IMAP)
2. Busca emails no leídos de Tilena
3. Extrae información del ticket (ID, URL, descripción)
4. Crea un Work Item tipo Bug en Azure DevOps
5. Marca el email como leído para no procesarlo de nuevo

Autor: Claude Code
Fecha: 2026-02-14
"""

import imaplib
import email
import re
import requests
import base64
import os
import sys
from email.header import decode_header
from datetime import datetime


def log(message, level="INFO"):
    """Logger simple con timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")


def connect_email():
    """
    Conecta al buzón de correo usando IMAP

    Returns:
        imaplib.IMAP4_SSL: Conexión al servidor IMAP
    """
    try:
        # Obtener credenciales desde variables de entorno
        email_user = os.getenv('EMAIL_USER')
        email_pass = os.getenv('EMAIL_PASS')

        if not email_user or not email_pass:
            log("ERROR: EMAIL_USER o EMAIL_PASS no están configurados", "ERROR")
            sys.exit(1)

        log(f"Conectando a buzón: {email_user}")

        # Conectar usando IMAP SSL
        mail = imaplib.IMAP4_SSL('outlook.office365.com', 993)
        mail.login(email_user, email_pass)

        log("✅ Conexión exitosa al buzón", "SUCCESS")
        return mail

    except imaplib.IMAP4.error as e:
        log(f"Error de autenticación IMAP: {str(e)}", "ERROR")
        log("Verifica que EMAIL_USER y EMAIL_PASS sean correctos", "ERROR")
        log("Si usas autenticación de dos factores, necesitas una App Password", "ERROR")
        sys.exit(1)
    except Exception as e:
        log(f"Error inesperado al conectar: {str(e)}", "ERROR")
        sys.exit(1)


def extract_ticket_info(email_body, subject):
    """
    Extrae información del ticket de Tilena desde el email

    Args:
        email_body (str): Cuerpo del email
        subject (str): Asunto del email

    Returns:
        dict: Información extraída (id, url, title)
    """
    # Buscar ID del ticket en el email
    # Patrones comunes: "id=12345", "ID: 12345", "#12345"
    ticket_id_match = re.search(r'(?:id[=:\s]+|#)(\d{4,})', email_body, re.IGNORECASE)

    if not ticket_id_match:
        # Buscar en el subject
        ticket_id_match = re.search(r'(?:id[=:\s]+|#)(\d{4,})', subject, re.IGNORECASE)

    ticket_id = ticket_id_match.group(1) if ticket_id_match else "Unknown"

    # Buscar URL completa en el email
    url_match = re.search(
        r'https?://tilena\.fooddeliverybrands\.com[^\s<>"\)]+',
        email_body
    )

    if url_match:
        ticket_url = url_match.group(0)
    else:
        # Construir URL si no se encuentra
        ticket_url = f"https://tilena.fooddeliverybrands.com/front/ticket.form.php?id={ticket_id}"

    # Limpiar subject para el título
    title = subject.replace('[TILENA]', '').replace('TILENA', '').strip()
    if not title:
        title = "Incidencia desde Tilena"

    return {
        'id': ticket_id,
        'url': ticket_url,
        'title': title
    }


def get_email_body(email_message):
    """
    Obtiene el cuerpo del email (texto plano o HTML)

    Args:
        email_message: Objeto email.message.Message

    Returns:
        str: Contenido del email
    """
    body = ""

    try:
        if email_message.is_multipart():
            # Email multipart (tiene partes HTML y texto)
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                # Ignorar adjuntos
                if "attachment" in content_disposition:
                    continue

                # Preferir texto plano
                if content_type == "text/plain":
                    body = part.get_payload(decode=True).decode(errors='ignore')
                    break
                elif content_type == "text/html" and not body:
                    body = part.get_payload(decode=True).decode(errors='ignore')
        else:
            # Email simple
            body = email_message.get_payload(decode=True).decode(errors='ignore')

    except Exception as e:
        log(f"Error al extraer cuerpo del email: {str(e)}", "WARNING")
        body = "[No se pudo extraer el contenido del email]"

    return body


def decode_subject(subject):
    """
    Decodifica el subject del email si está encoded

    Args:
        subject (str): Subject raw del email

    Returns:
        str: Subject decodificado
    """
    try:
        decoded_parts = []
        for part, encoding in decode_header(subject):
            if isinstance(part, bytes):
                decoded_parts.append(part.decode(encoding or 'utf-8', errors='ignore'))
            else:
                decoded_parts.append(str(part))
        return ''.join(decoded_parts)
    except Exception as e:
        log(f"Error al decodificar subject: {str(e)}", "WARNING")
        return subject


def create_devops_workitem(title, description, ticket_url, ticket_id):
    """
    Crea un Work Item tipo Bug en Azure DevOps

    Args:
        title (str): Título del Work Item
        description (str): Descripción del Work Item
        ticket_url (str): URL del ticket en Tilena
        ticket_id (str): ID del ticket

    Returns:
        int|None: ID del Work Item creado o None si falla
    """
    try:
        # Obtener credenciales de Azure DevOps
        org = os.getenv('DEVOPS_ORG')
        project = os.getenv('DEVOPS_PROJECT')
        pat = os.getenv('DEVOPS_PAT')

        if not org or not project or not pat:
            log("ERROR: Variables de Azure DevOps no configuradas", "ERROR")
            return None

        # Construir URL de la API
        url = f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems/$Bug?api-version=7.1"

        # Preparar autenticación
        credentials = f":{pat}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Content-Type": "application/json-patch+json",
            "Authorization": f"Basic {encoded_credentials}"
        }

        # Formatear descripción HTML con link a Tilena
        formatted_description = f"""<div>
        <h3>🎫 Incidencia desde Tilena</h3>
        <p><strong>ID Tilena:</strong> #{ticket_id}</p>
        <p><strong>URL:</strong> <a href="{ticket_url}" target="_blank">{ticket_url}</a></p>
        <hr/>
        <h4>Descripción original:</h4>
        <div style="background: #f5f5f5; padding: 10px; border-left: 3px solid #0078d4;">
        <pre>{description[:2000]}</pre>
        </div>
        </div>"""

        # Preparar payload para crear Work Item
        body = [
            {
                "op": "add",
                "path": "/fields/System.Title",
                "value": title[:255]  # Azure DevOps limita títulos a 255 chars
            },
            {
                "op": "add",
                "path": "/fields/System.Description",
                "value": formatted_description
            },
            {
                "op": "add",
                "path": "/fields/System.Tags",
                "value": "Tilena;AutoCreated;FromEmail"
            },
            {
                "op": "add",
                "path": "/fields/System.AreaPath",
                "value": project
            }
        ]

        # Hacer request
        response = requests.post(url, json=body, headers=headers, timeout=30)

        if response.status_code in [200, 201]:
            work_item = response.json()
            work_item_id = work_item['id']
            log(f"✅ Work Item #{work_item_id} creado: {title[:50]}...", "SUCCESS")
            return work_item_id
        else:
            log(f"❌ Error al crear Work Item: HTTP {response.status_code}", "ERROR")
            log(f"Response: {response.text[:200]}", "ERROR")
            return None

    except Exception as e:
        log(f"❌ Error inesperado al crear Work Item: {str(e)}", "ERROR")
        return None


def main():
    """Función principal"""
    log("=" * 60)
    log("🚀 Iniciando sincronización Tilena → Azure DevOps")
    log("=" * 60)

    # Conectar al buzón
    mail = connect_email()

    try:
        # Seleccionar bandeja de entrada
        mail.select('INBOX')
        log("📂 Bandeja INBOX seleccionada")

        # Buscar emails de Tilena no leídos
        log("🔍 Buscando emails de Tilena no leídos...")
        status, messages = mail.search(None, '(FROM "tilena" UNSEEN)')

        if status != 'OK':
            log("❌ Error al buscar emails", "ERROR")
            return

        email_ids = messages[0].split()

        if not email_ids:
            log("ℹ️  No hay emails nuevos de Tilena")
            log("=" * 60)
            return

        log(f"📧 Encontrados {len(email_ids)} email(s) nuevo(s) de Tilena")
        log("-" * 60)

        processed_count = 0
        error_count = 0

        # Procesar cada email
        for i, email_id in enumerate(email_ids, 1):
            try:
                log(f"\n[{i}/{len(email_ids)}] Procesando email ID {email_id.decode()}...")

                # Obtener email
                status, msg_data = mail.fetch(email_id, '(RFC822)')

                if status != 'OK':
                    log(f"⚠️  No se pudo obtener el email {email_id}", "WARNING")
                    error_count += 1
                    continue

                # Parsear email
                email_message = email.message_from_bytes(msg_data[0][1])

                # Extraer y decodificar subject
                subject_raw = email_message['Subject']
                subject = decode_subject(subject_raw) if subject_raw else "Sin asunto"

                log(f"   📨 Asunto: {subject[:60]}...")

                # Extraer body
                body = get_email_body(email_message)

                # Extraer info del ticket
                ticket_info = extract_ticket_info(body, subject)

                log(f"   🎫 Ticket ID: {ticket_info['id']}")
                log(f"   🔗 URL: {ticket_info['url']}")

                # Crear título para Azure DevOps
                title = f"[Tilena #{ticket_info['id']}] {ticket_info['title']}"

                # Crear Work Item
                work_item_id = create_devops_workitem(
                    title=title,
                    description=body,
                    ticket_url=ticket_info['url'],
                    ticket_id=ticket_info['id']
                )

                if work_item_id:
                    # Marcar email como leído para no procesarlo de nuevo
                    mail.store(email_id, '+FLAGS', '\\Seen')
                    processed_count += 1
                    log(f"   ✅ Email procesado → Work Item #{work_item_id}")
                else:
                    error_count += 1
                    log(f"   ❌ No se pudo crear Work Item", "ERROR")

            except Exception as e:
                error_count += 1
                log(f"   ❌ Error procesando email: {str(e)}", "ERROR")

        # Resumen final
        log("-" * 60)
        log(f"✅ Sincronización completada")
        log(f"   📊 Procesados: {processed_count}")
        log(f"   ❌ Errores: {error_count}")
        log("=" * 60)

    finally:
        # Cerrar conexión
        try:
            mail.close()
            mail.logout()
            log("🔌 Conexión cerrada")
        except:
            pass


if __name__ == "__main__":
    main()
