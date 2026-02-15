# 🔄 Configuración Power Automate → GitHub Actions

Esta guía te enseña cómo configurar **Power Automate** para que detecte emails de Tilena y dispare automáticamente el workflow de GitHub Actions.

## 🏗️ Arquitectura

```
Tilena → Email Corporativo → Power Automate → GitHub API → GitHub Actions → Azure DevOps
         (Outlook)           (detecta email)   (dispara)     (procesa)      (crea Work Item)
```

**Ventajas:**
- ✅ No necesitas Gmail ni reenvíos
- ✅ Power Automate tiene acceso nativo a Outlook corporativo
- ✅ Sin problemas de autenticación básica bloqueada
- ✅ GitHub Actions procesa gratis (2000 min/mes)
- ✅ Todo queda registrado en logs

---

## 📋 Requisitos Previos

1. **Cuenta de Power Automate** (incluido con Office 365)
2. **GitHub Personal Access Token (PAT)** con permisos de Actions
3. **Secrets configurados en GitHub** (DEVOPS_ORG, DEVOPS_PROJECT, DEVOPS_PAT)

---

## 🔑 Paso 1: Crear GitHub Personal Access Token

1. **Ve a GitHub Settings:**
   ```
   https://github.com/settings/tokens
   ```

2. **Click en:** `Developer settings` → `Personal access tokens` → `Tokens (classic)`

3. **Click en:** `Generate new token` → `Generate new token (classic)`

4. **Configuración del token:**
   - **Note:** `Power Automate - Tilena Sync`
   - **Expiration:** `No expiration` (o 90 días)
   - **Scopes:** Marca las siguientes opciones:
     - ✅ `repo` (Full control of private repositories)
     - ✅ `workflow` (Update GitHub Action workflows)

5. **Click en:** `Generate token`

6. **⚠️ IMPORTANTE:** Copia el token inmediatamente (empieza con `ghp_...`)
   - **Guárdalo en un lugar seguro** (solo se muestra una vez)

---

## ⚙️ Paso 2: Crear el Flow en Power Automate

### 2.1 Crear nuevo Flow

1. **Ve a Power Automate:**
   ```
   https://make.powerautomate.com
   ```

2. **Click en:** `+ Create` → `Automated cloud flow`

3. **Nombre del flow:**
   ```
   Tilena → GitHub Actions Sync
   ```

4. **Trigger:** Busca y selecciona:
   ```
   When a new email arrives (V3) - Office 365 Outlook
   ```

5. **Click en:** `Create`

---

### 2.2 Configurar el Trigger (Email)

1. **En el paso "When a new email arrives (V3)":**

   - **Folder:** `Inbox`
   - **From:** `tilena@softtek.com` (o el email de Tilena)
   - **Include Attachments:** `No`
   - **Importance:** `Any`

   **⚙️ Opciones avanzadas (click en "Show advanced options"):**
   - **Only with Attachments:** `No`
   - **Subject Filter:** (opcional) `TILENA` o dejar vacío

2. **Click en:** `+ New step`

---

### 2.3 Agregar Acción HTTP para llamar a GitHub

1. **Busca:** `HTTP`

2. **Selecciona:** `HTTP - Premium` (o `HTTP` si no tienes premium)

3. **Configuración del HTTP Request:**

   | Campo | Valor |
   |-------|-------|
   | **Method** | `POST` |
   | **URI** | `https://api.github.com/repos/trotosk/helpTask/actions/workflows/tilena-sync.yml/dispatchs` |
   | **Headers** | Ver tabla abajo ⬇️ |
   | **Body** | Ver JSON abajo ⬇️ |

---

#### 📋 Headers

Agrega estos headers (click en "Add new item" para cada uno):

| Key | Value |
|-----|-------|
| `Accept` | `application/vnd.github+json` |
| `Authorization` | `Bearer TU_GITHUB_TOKEN_AQUI` |
| `X-GitHub-Api-Version` | `2022-11-28` |
| `Content-Type` | `application/json` |

**⚠️ IMPORTANTE:** Reemplaza `TU_GITHUB_TOKEN_AQUI` con el token que creaste en el Paso 1 (empieza con `ghp_...`)

---

#### 📋 Body (JSON)

**Click en el campo Body y pega esto:**

```json
{
  "ref": "main",
  "inputs": {
    "trigger_mode": "powerautomate",
    "email_subject": "@{triggerOutputs()?['body/subject']}",
    "email_body": "@{triggerOutputs()?['body/body']}",
    "email_from": "@{triggerOutputs()?['body/from']}",
    "email_date": "@{triggerOutputs()?['body/receivedDateTime']}"
  }
}
```

**⚠️ NOTA:** Los valores `@{...}` son **expresiones de Power Automate** que extraen datos dinámicos del email.

---

#### 🎯 ¿Cómo agregar las expresiones dinámicas?

Si Power Automate no reconoce las expresiones `@{...}`, hazlo manualmente:

1. **Click en el campo** `email_subject`
2. **Click en el icono del rayo** ⚡ (Dynamic content)
3. **Busca y selecciona:** `Subject`
4. Repite para los demás campos:
   - `email_body` → `Body`
   - `email_from` → `From`
   - `email_date` → `Received Time`

---

### 2.4 Guardar el Flow

1. **Click en:** `Save` (arriba derecha)

2. **El flow se activará automáticamente**

---

## ✅ Paso 3: Probar el Flow

### 3.1 Enviar email de prueba

**Opción A: Reenviar un email de Tilena existente** a tu buzón corporativo

**Opción B: Crear un email de prueba:**
1. Envíate un email a ti mismo
2. **From:** Cambia temporalmente el filtro en Power Automate para aceptar tu email
3. **Subject:** `[TILENA] Prueba #12345`
4. **Body:**
   ```
   Ticket ID: 12345
   URL: https://tilena.fooddeliverybrands.com/front/ticket.form.php?id=12345

   Esta es una prueba de integración.
   ```

---

### 3.2 Ver ejecución en Power Automate

1. **Ve a:** `https://make.powerautomate.com`
2. **Click en:** `My flows`
3. **Click en:** `Tilena → GitHub Actions Sync`
4. **Ver historial de ejecuciones:** Deberías ver una ejecución reciente
5. **Click en la ejecución** para ver detalles

**Si funciona:** Verás ✅ en todos los pasos

**Si falla:** Click en el paso fallido para ver el error

---

### 3.3 Ver ejecución en GitHub Actions

1. **Ve a:** `https://github.com/trotosk/helpTask/actions`
2. **Click en:** `🎫 Tilena → Azure DevOps Sync`
3. **Deberías ver una ejecución nueva** disparada por Power Automate
4. **Click en la ejecución** para ver logs

**Logs esperados:**
```
[2026-02-14 10:30:00] [INFO] 🚀 Iniciando sincronización Tilena → Azure DevOps
[2026-02-14 10:30:00] [INFO] 📥 Modo: Power Automate (webhook)
[2026-02-14 10:30:00] [INFO] 📧 Email recibido desde Power Automate
[2026-02-14 10:30:00] [INFO]    De: tilena@softtek.com
[2026-02-14 10:30:00] [INFO]    Asunto: [TILENA] Nueva incidencia #12345
[2026-02-14 10:30:01] [INFO] 🎫 Ticket ID: 12345
[2026-02-14 10:30:01] [INFO] 🔗 URL: https://tilena.fooddeliverybrands.com/...
[2026-02-14 10:30:02] [SUCCESS] ✅ Work Item #98765 creado exitosamente
```

---

### 3.4 Ver Work Item en Azure DevOps

1. **Ve a tu proyecto en Azure DevOps**
2. **Boards → Work Items**
3. **Deberías ver un nuevo Bug:** `[Tilena #12345] ...`
4. **Abre el Work Item** para verificar:
   - ✅ Título correcto
   - ✅ Descripción con link a Tilena
   - ✅ Tags: `Tilena`, `AutoCreated`, `FromEmail`

---

## 🐛 Troubleshooting

### ❌ Error 401 Unauthorized en Power Automate

**Causa:** Token de GitHub inválido o sin permisos

**Solución:**
1. Verifica que el token tenga los scopes `repo` y `workflow`
2. Copia el token completo (empieza con `ghp_`)
3. En Power Automate, edita el header `Authorization`:
   ```
   Bearer ghp_TuTokenCompleto
   ```

---

### ❌ Error 404 Not Found

**Causa:** URL del workflow incorrecta

**Solución:**
Verifica que la URL sea exactamente:
```
https://api.github.com/repos/trotosk/helpTask/actions/workflows/tilena-sync.yml/dispatches
```

**⚠️ IMPORTANTE:** Debe terminar en `/dispatches` (no `dispatchs`)

---

### ❌ GitHub Actions se dispara pero falla

**Causa:** Secrets de Azure DevOps no configurados

**Solución:**
1. Ve a: `https://github.com/trotosk/helpTask/settings/secrets/actions`
2. Verifica que existan estos 3 secrets:
   - `DEVOPS_ORG`
   - `DEVOPS_PROJECT`
   - `DEVOPS_PAT`
3. Si faltan, agrégalos (ver documentación principal)

---

### ❌ Power Automate no se dispara

**Causa:** Filtro de email muy restrictivo

**Solución:**
1. Edita el Flow
2. En el trigger "When a new email arrives"
3. **Quita temporalmente** el filtro `From`
4. Guarda y prueba con cualquier email
5. Si funciona, vuelve a agregar el filtro correcto

---

## 🔧 Personalización Avanzada

### Filtrar solo emails con palabras clave

**En el trigger, agrega una condición:**

1. **Después del trigger, click en:** `+ New step`
2. **Busca:** `Condition`
3. **Configuración:**
   - **Value:** `Subject` (dynamic content)
   - **Operator:** `contains`
   - **Value:** `incidencia` (o palabra clave)

4. **Mueve el paso HTTP** dentro de la rama `If yes`

---

### Enviar notificación cuando falla

**Después del paso HTTP:**

1. **Click en los 3 puntos** `...` del paso HTTP
2. **Configure run after**
3. **Marca:** `has failed` ✅
4. **Agrega nuevo paso:** `Send an email (V2)`
5. **Configuración:**
   - **To:** `tu_email@softtek.com`
   - **Subject:** `❌ Error sincronizando Tilena`
   - **Body:** `El workflow falló. Revisa GitHub Actions.`

---

## 📊 Monitoreo

### Ver estadísticas del Flow

1. **My flows** → **Tilena → GitHub Actions Sync**
2. **Analytics** (pestaña superior)
3. Verás:
   - Total de ejecuciones
   - Tasa de éxito/fallo
   - Gráfica de ejecuciones por día

### Ver estadísticas de GitHub Actions

1. **Repo → Insights → Actions**
2. Verás:
   - Uso de minutos (de los 2000 gratis)
   - Ejecuciones por workflow
   - Tiempo promedio de ejecución

---

## 🎉 ¡Listo!

Ahora tienes una integración **completamente automatizada**:

```
Tilena envía email
    ↓ (segundos)
Power Automate detecta
    ↓ (1-2 segundos)
GitHub Actions procesa
    ↓ (10-15 segundos)
Work Item creado en Azure DevOps ✅
```

**Tiempo total:** ~30 segundos desde que llega el email hasta que se crea el Work Item

**Sin intervención manual** 🚀

---

## 📚 Recursos Adicionales

- [GitHub Actions API Documentation](https://docs.github.com/en/rest/actions/workflows)
- [Power Automate Documentation](https://learn.microsoft.com/en-us/power-automate/)
- [Azure DevOps REST API](https://learn.microsoft.com/en-us/rest/api/azure/devops/)

---

**¿Preguntas?** Abre un issue en el repositorio.
