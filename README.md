# MCP de Facebook — Multiplanet

Servidor MCP propio para publicar y programar posts en la página de Facebook de
Multiplanet Tocoa desde **ChatGPT** (o cualquier cliente MCP remoto). Usa la Graph API
oficial de Meta: sin límite de posts al mes y sin pagar herramientas de terceros.

## Herramientas

Dos páginas: `tocoa` (por defecto) y `floristeria`. Las herramientas de publicar y listar aceptan `pagina`; el modelo elige `floristeria` si el usuario lo pide o el contenido es floral. Reprogramar/borrar deducen la página por el ID del post. Solo publica cuando el usuario lo pide de forma explícita.

| Herramienta | Para qué |
|---|---|
| `programar_post_con_imagenes` | Publica o programa un post con 1–10 imágenes **adjuntas en el chat de ChatGPT** (`openai/fileParams`). Sin `fecha` publica ya |
| `verificar_imagenes_chat` | Comprueba que llegaron las imágenes del chat (formato, tamaño). No publica nada |
| `listar_imagenes` / `ver_imagen` | Fotos subidas a la bandeja desde la página web |
| `programar_post` / `publicar_ahora` | Post con texto, fotos de la bandeja o un link |
| `listar_programados` / `reprogramar` / `publicar_programado_ya` / `borrar_post` | Administrar la cola |
| `posts_recientes` / `info_pagina` | Consultas |

Páginas web del servidor: `/subir/<MCP_SECRET>` (subir fotos a la bandeja), `/privacidad`
(la exige Meta para el modo Live) y `/salud`.

### Catálogo y programación por tipo

Abrí `https://TU_DOMINIO/catalogo/<MCP_SECRET>` desde la computadora o el celular.
Guardá publicaciones completas (texto y hasta 10 fotos, o un enlace), editá su contenido
y marcá **Aprobar para programación por lotes** cuando esté listo. Guardar no publica.
Las fotos se copian al catálogo: siguen disponibles después de programarlas y no se
mueven a la carpeta de fotos usadas. Se pueden archivar publicaciones sin borrarlas.

Tipos incluidos: visa americana; reparación de taller con subcategorías computadoras
e impresoras; útiles de oficina; útiles escolares; suministros de arreglos florales;
papelería; servicios secretariales; diseños de flores. Podés agregar categorías y
subcategorías. **Diseños de flores es siempre manual**; suministros florales sí permite
lotes. La página de Facebook se elige por publicación, independientemente del tipo.

Ejemplo de pedido en ChatGPT:

> Preparame 43 publicaciones de visa americana para los próximos 15 días,
> empezando mañana, entre las 9:00 y las 18:00, para Multiplanet Tocoa.

El MCP prepara un **borrador persistente** con publicaciones distintas y horarios
distribuidos en el período. Mostrá y revisá los textos, las fotos y las fechas antes
de confirmar. Si no hay suficientes publicaciones aprobadas, vigentes y sin usar,
o faltan horarios libres, devuelve un error sin crear un plan parcial ni repetir
contenido. Seleccionar taller incluye sus subcategorías. La vigencia opcional impide
elegir promociones que vencen antes de la fecha de publicación.

Al confirmar, la cola local envía cada post a Meta cuando entra en la ventana de
programación configurada. El catálogo permite planificar hasta 365 días adelante;
**la VM debe permanecer encendida para hacer los envíos**. Una vez entregado a Meta,
Facebook se encarga de la fecha programada. No se necesita mantener ChatGPT abierto.
El consumidor revisa la cola cada 30 segundos, con un único proceso del servidor.

Estados visibles en Agenda:

| Estado | Significado |
|---|---|
| Borrador | Reservado para revisión; no se envía hasta confirmar |
| En cola local | Confirmado y pendiente de entregar a Meta |
| Enviando | Solicitud en curso |
| En Meta | Meta devolvió un ID; la publicación efectiva no se verifica automáticamente |
| Simulado | Se probó el envío sin llamar a Facebook |
| Requiere revisión | Falló o se interrumpió el envío; comprobar en Facebook antes de reintentar |
| Horario vencido | El servidor no logró enviarlo con anticipación; nunca se publica inmediatamente como reemplazo |
| Cancelado | Cancelado antes de enviar, o borrado mediante el MCP |

Los borradores reservan contenido hasta descartarlos desde Agenda. Confirmar dos veces
no duplica la cola. Cambiar el catálogo no cambia la copia de texto/fotos de un plan ya
preparado. Cancelar un plan local no borra publicaciones de Facebook: si ya hubo envíos,
consultá sus IDs y usá las herramientas originales `borrar_post` o `reprogramar`.
Esas herramientas también actualizan los registros locales que les corresponden.
Los cambios hechos directamente en Facebook no se sincronizan automáticamente.

Los planes simulados y reales permanecen separados: desactivar `FB_DRY_RUN` no envía
planes de prueba. Un timeout puede suceder después de que Meta creó el post; por eso
los envíos dudosos y los interrumpidos durante un reinicio quedan para revisión y
**no se reintentan automáticamente**.

| Herramienta del catálogo | Uso |
|---|---|
| `listar_categorias_catalogo` / `crear_categoria_catalogo` | Tipos y subcategorías |
| `guardar_publicacion_catalogo` | Guardar texto y copias de fotos de la bandeja, sin publicar |
| `guardar_publicacion_catalogo_con_imagenes` | Guardar fotos adjuntas de ChatGPT con su texto, sin publicar |
| `actualizar_publicacion_catalogo` | Editar, aprobar o archivar contenido guardado |
| `listar_catalogo` / `ver_imagen_catalogo` | Revisar contenido y fotos |
| `preparar_lote_catalogo` | Borrador por tipo, cantidad, días, inicio, horas y página |
| `preparar_publicacion_catalogo` | Borrador individual; también permite flores |
| `confirmar_plan_catalogo` | Activar un plan que el usuario ya aprobó |
| `listar_agenda_catalogo` / `cancelar_plan_catalogo` | Revisar y cancelar planes locales |

Los datos quedan en `DATA_DIR/catalogo.sqlite3` y `DATA_DIR/catalogo-media/`, dentro del
volumen persistente existente. Conservá ambos al respaldar o cambiar de servidor;
detené el servicio al copiar SQLite o usá su API de backup para incluir cambios del WAL.
La URL del catálogo contiene el mismo secreto que el MCP; no la compartas. Las fotos
y los endpoints del catálogo también requieren ese secreto.

Límites de Meta: programar entre 10 minutos y 30 días adelante; Reels y Stories no se
pueden programar por la API.

## Despliegue actual

- VM de Azure `vcbot` (grupo `VCBOT-RG`, Ubuntu 24.04), junto al bot de Discord.
- Código en `/opt/fbmcp`, servicio systemd `fbmcp`, Caddy hace HTTPS y proxy a `127.0.0.1:8000`.
- Configuración en `/opt/fbmcp/.env` (**nunca** en el repo): `MCP_SECRET`, `FB_PAGE_ID`,
  `FB_PAGE_TOKEN`, `FB_PAGE_ID_FLORISTERIA`, `FB_PAGE_TOKEN_FLORISTERIA` (opcionales), `FB_GRAPH_VERSION`, `PUBLIC_HOST`, `HOST`, `PORT`, `DATA_DIR`, `ZONA_HORARIA`.

### Actualizar la VM después de un push

Desde Azure Cloud Shell:

```bash
az vm run-command invoke -g VCBOT-RG -n vcbot --command-id RunShellScript \
  --scripts "curl -fsSL https://raw.githubusercontent.com/devmushidev-svg/multiplanet-fb-mcp/main/deploy/actualizar.sh | sh" \
  --query "value[0].message" -o tsv
```

`deploy/actualizar.sh` baja los módulos Python y los recursos `web/` desde `main`, los
prueba en modo simulado con el venv real y datos aislados, guarda un respaldo de los
archivos, reinicia solo `fbmcp` y restaura el código anterior si no arranca. No cambia
`.env`, las fotos existentes ni los datos del catálogo. Docker también incluye la web.

### Instalar en una VM nueva

```bash
sudo DOMINIO=tu-dominio.cloudapp.azure.com sh deploy/instalar-vm.sh
```

Abrí los puertos 80 y 443 y ponele una etiqueta DNS a la IP pública. También hay
`Dockerfile` + `docker-compose.yml` + `Caddyfile` si preferís Docker.

## Token de Meta

1. App en developers.facebook.com con el caso de uso **"Administrar todos los aspectos de tu página"**
   y los permisos `pages_show_list`, `pages_read_engagement`, `pages_manage_posts` y
   `business_management` (necesario si la página pertenece a un portfolio comercial).
2. URL de privacidad: `https://TU_DOMINIO/privacidad`. **Pasar la app a Live**: en modo
   desarrollo los posts solo los ven quienes tienen rol en la app.
3. `python obtener_token.py` convierte el token corto del Graph API Explorer en un token de
   página que no vence (Meta igual pide reautorizar el acceso a datos cada ~90 días).

## Conectar en ChatGPT

Complementos → Agregar → **Agregar servidor MCP personalizado** → URL
`https://TU_DOMINIO/mcp/<MCP_SECRET>`, autenticación **Sin autenticación**.

**La URL lleva el secreto: quien la tenga puede publicar en la página. No la compartas.**
Si se filtra, cambiá `MCP_SECRET` en `.env` y reiniciá `fbmcp`.

## Probar sin Facebook

```bash
pip install -r requirements.txt
MCP_SECRET=una_clave_larga_de_al_menos_24_chars FB_DRY_RUN=1 python server.py
```

En PowerShell:

```powershell
$env:MCP_SECRET='una_clave_larga_de_al_menos_24_chars'
$env:FB_DRY_RUN='1'
python server.py
```

Abrí `http://localhost:8000/catalogo/una_clave_larga_de_al_menos_24_chars`.
Para ejecutar las pruebas aisladas, sin credenciales ni llamadas a Facebook:

```bash
python -m unittest discover -s tests -v
node --check web/catalogo.js
```

Prueba opcional del navegador en Windows con Edge instalado:

```powershell
pip install playwright
python tests/browser_smoke.py
```

Comprueba creación con foto, edición, revisión, confirmación y cancelación del plan,
flores manuales, búsqueda y la vista móvil. Usa datos temporales en modo simulado y
guarda capturas en `test-results/`; no agrega contenido a tu catálogo real.
