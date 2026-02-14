# 🎫 Sincronización Automática Tilena → Azure DevOps

Este proyecto incluye una **automatización completa** que crea Work Items en Azure DevOps automáticamente cuando llegan emails de Tilena.

---

## 🎯 ¿Qué hace?

```
Email de Tilena → GitHub Actions (cada 30 min) → Work Item en Azure DevOps
```

**Proceso:**
1. ⏰ Cada 30 minutos, GitHub Actions ejecuta el script
2. 📧 El script revisa tu buzón de correo (IMAP)
3. 🔍 Busca emails NO LEÍDOS de Tilena
4. 📝 Extrae información (ID, URL, descripción)
5. ✅ Crea un Work Item tipo **Bug** en Azure DevOps
6. ✔️ Marca el email como leído (no lo procesa de nuevo)

---

## ⚙️ Configuración (Pasos Necesarios)

### **Paso 1: Configurar Secrets en GitHub**

GitHub Actions necesita 5 secrets (credenciales) para funcionar:

1. **Ve a tu repositorio en GitHub**
2. **Settings** → **Secrets and variables** → **Actions**
3. **Click en "New repository secret"**
4. **Agrega estos 5 secrets:**

| Secret Name | Valor | Descripción |
|-------------|-------|-------------|
| `EMAIL_USER` | `tu_email@softtek.com` | Tu email corporativo |
| `EMAIL_PASS` | `tu_contraseña` | Contraseña del email* |
| `DEVOPS_ORG` | `TelepizzaIT` | Organización de Azure DevOps |
| `DEVOPS_PROJECT` | `Sales` | Proyecto de Azure DevOps |
| `DEVOPS_PAT` | `tu_pat_aqui` | Personal Access Token de Azure DevOps |

**\*Importante sobre EMAIL_PASS:**

Si tu cuenta usa **autenticación de dos factores** (2FA), necesitas crear una **App Password**:

#### **Cómo crear App Password en Office 365:**

1. Ve a: https://account.microsoft.com/security
2. Click en **Advanced security options**
3. Busca **App passwords**
4. Click en **Create a new app password**
5. Copia el password generado (ejemplo: `abcd-efgh-ijkl-mnop`)
6. Úsalo como `EMAIL_PASS` en GitHub Secrets

---

### **Paso 2: Verificar Permisos del PAT**

El **Personal Access Token** (PAT) de Azure DevOps necesita estos permisos:

- ✅ **Work Items** (Read, Write, Manage)

**Cómo verificar/crear PAT:**

1. Azure DevOps → User Settings (arriba derecha) → **Personal Access Tokens**
2. Click en **New Token**
3. Name: `GitHub Actions Tilena Sync`
4. Organization: `TelepizzaIT`
5. Scopes:
   - Work Items: **Read & Write**
6. Click **Create**
7. **Copia el token** (solo se muestra una vez)
8. Pégalo en GitHub Secret `DEVOPS_PAT`

---

### **Paso 3: Push del Código (Ya hecho)**

El código ya está en el repo:

```
.github/workflows/tilena-sync.yml    # GitHub Action
scripts/tilena_sync.py               # Script Python
```

---

### **Paso 4: Activar GitHub Actions**

1. Ve a tu repositorio en GitHub
2. Pestaña **Actions**
3. Si ves un mensaje "Workflows aren't being run on this repository"
4. Click en **"I understand my workflows, go ahead and enable them"**

---

## 🧪 Probar la Integración

### **Opción A: Ejecución Manual (Recomendada para primera vez)**

1. Ve a tu repo en GitHub
2. Pestaña **Actions**
3. Click en el workflow **"🎫 Tilena → Azure DevOps Sync"**
4. Click en **"Run workflow"** (botón azul)
5. Click en **"Run workflow"** (confirmación)
6. Espera 1-2 minutos
7. Click en el job para ver los logs

**Verás algo como:**

```
[2026-02-14 10:30:00] [INFO] Conectando a buzón: tu_email@softtek.com
[2026-02-14 10:30:01] [SUCCESS] ✅ Conexión exitosa al buzón
[2026-02-14 10:30:01] [INFO] 📂 Bandeja INBOX seleccionada
[2026-02-14 10:30:02] [INFO] 🔍 Buscando emails de Tilena no leídos...
[2026-02-14 10:30:03] [INFO] 📧 Encontrados 2 email(s) nuevo(s) de Tilena
[2026-02-14 10:30:03] [INFO] [1/2] Procesando email ID 12345...
[2026-02-14 10:30:03] [INFO]    📨 Asunto: Nueva incidencia #67846
[2026-02-14 10:30:03] [INFO]    🎫 Ticket ID: 67846
[2026-02-14 10:30:03] [INFO]    🔗 URL: https://tilena.fooddeliverybrands.com/front/ticket.form.php?id=67846
[2026-02-14 10:30:04] [SUCCESS] ✅ Work Item #98765 creado: [Tilena #67846] Nueva incidencia...
[2026-02-14 10:30:04] [INFO]    ✅ Email procesado → Work Item #98765
```

### **Opción B: Esperar la Ejecución Automática**

- GitHub Actions ejecutará automáticamente **cada 30 minutos**
- Horarios: :00, :30 de cada hora (ej: 10:00, 10:30, 11:00, 11:30...)

---

## 📊 Verificar Resultados

### **En Azure DevOps:**

1. Ve a tu proyecto: `https://dev.azure.com/TelepizzaIT/Sales`
2. Click en **Boards** → **Work Items**
3. Filtrar por:
   - Type: **Bug**
   - Tags: **Tilena**

Verás Work Items con este formato:

```
Title: [Tilena #67846] Error al procesar pedidos
Type: Bug
Tags: Tilena, AutoCreated, FromEmail
Description:
  🎫 Incidencia desde Tilena
  ID Tilena: #67846
  URL: https://tilena.fooddeliverybrands.com/front/ticket.form.php?id=67846

  Descripción original:
  [Contenido del email...]
```

### **En tu Email:**

- Los emails procesados se marcarán como **leídos** ✅
- NO se borrarán (solo se marcan como leídos)
- NO se moverán de carpeta (quedan en INBOX)

---

## 🔧 Personalización

### **Cambiar Frecuencia de Ejecución**

Edita `.github/workflows/tilena-sync.yml`:

```yaml
schedule:
  - cron: '*/15 * * * *'  # Cada 15 minutos
  - cron: '*/60 * * * *'  # Cada hora
  - cron: '0 9-18 * * 1-5'  # Cada hora de 9-18h, Lun-Vie
```

### **Cambiar Tipo de Work Item**

Edita `scripts/tilena_sync.py` línea ~220:

```python
# Cambiar de Bug a User Story, Task, etc.
url = f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems/$UserStory?api-version=7.1"
```

### **Agregar Campos Personalizados**

Edita `scripts/tilena_sync.py` en la función `create_devops_workitem`:

```python
body = [
    # ... campos existentes ...
    {
        "op": "add",
        "path": "/fields/System.Priority",
        "value": 2  # Prioridad Alta
    },
    {
        "op": "add",
        "path": "/fields/System.AssignedTo",
        "value": "usuario@softtek.com"
    }
]
```

---

## 🐛 Troubleshooting

### **Error: "Authentication failed"**

**Causa:** Credenciales de email incorrectas

**Solución:**
1. Verifica que `EMAIL_USER` y `EMAIL_PASS` sean correctos
2. Si usas 2FA, crea una **App Password** (ver arriba)
3. Vuelve a configurar el secret en GitHub

### **Error: "No module named 'imapclient'"**

**Causa:** Dependencias no instaladas

**Solución:** Ya está resuelto en el workflow (se instalan automáticamente)

### **Error: "Work Item creation failed: 401"**

**Causa:** PAT de Azure DevOps inválido o sin permisos

**Solución:**
1. Verifica que `DEVOPS_PAT` sea correcto
2. Verifica que el PAT tenga permisos de **Work Items (Write)**
3. Verifica que el PAT no haya expirado

### **No se procesan emails**

**Posibles causas:**

1. **No hay emails nuevos de Tilena**
   - El script solo procesa emails **NO LEÍDOS**
   - Marca un email de Tilena como no leído y vuelve a ejecutar

2. **El filtro de búsqueda no coincide**
   - Edita `scripts/tilena_sync.py` línea ~280:
   ```python
   # Cambiar filtro de búsqueda
   status, messages = mail.search(None, '(FROM "tilena.fooddeliverybrands.com" UNSEEN)')
   ```

3. **Emails en otra carpeta**
   - El script busca en `INBOX`
   - Si están en otra carpeta, edita línea ~275:
   ```python
   mail.select('nombre_de_carpeta')
   ```

---

## 📈 Monitoreo

### **Ver Logs en GitHub Actions:**

1. GitHub → Actions → Click en la ejecución
2. Click en el job `sync-tilena-emails`
3. Verás logs detallados en tiempo real

### **Descargar Logs:**

Los logs se guardan como **artifacts** por 7 días:

1. GitHub → Actions → Click en la ejecución
2. Scroll down → **Artifacts**
3. Download `tilena-sync-logs`

---

## 💰 Costos

**GitHub Actions:**
- ✅ **GRATIS** hasta 2000 minutos/mes (repos públicos ilimitado)
- Este workflow usa ~2 minutos/día = **60 min/mes**
- Estás muy por debajo del límite gratuito

**Outlook/Office 365:**
- ✅ **GRATIS** (ya incluido en tu cuenta Softtek)

**Azure DevOps:**
- ✅ **GRATIS** (API incluida en tu suscripción)

**Total: $0/mes** 🎉

---

## 🔒 Seguridad

- ✅ Secrets encriptados en GitHub (nadie puede verlos)
- ✅ Conexión IMAP usa SSL/TLS
- ✅ Azure DevOps API usa HTTPS
- ✅ El script **SOLO LEE** emails (no envía ni borra)
- ✅ Los emails se marcan como leídos (no se borran)
- ✅ PAT con permisos mínimos necesarios

---

## 📞 Soporte

Si tienes problemas:

1. **Verifica los logs** en GitHub Actions
2. **Revisa los secrets** (EMAIL_USER, EMAIL_PASS, DEVOPS_PAT)
3. **Ejecuta manualmente** para ver errores en tiempo real
4. **Revisa este README** para troubleshooting

---

## 🎉 ¡Listo!

Una vez configurado, el sistema funcionará **100% automáticamente**:

```
✅ Email de Tilena → ✅ Work Item en Azure DevOps
   (cada 30 minutos, sin intervención manual)
```

**¡Disfruta de la automatización!** 🚀
