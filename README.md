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

`deploy/actualizar.sh` baja `server.py` desde `main`, lo prueba en modo simulado con el
venv real, guarda un respaldo, reinicia solo `fbmcp` y vuelve atrás solo si no arranca.

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
