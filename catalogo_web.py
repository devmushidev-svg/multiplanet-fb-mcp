"""Adaptador web/MCP del catálogo. Comparte credenciales y Graph API con server.py."""
from __future__ import annotations

import asyncio
import io
import json
import logging
import secrets
from urllib.parse import quote
from pathlib import Path
from tempfile import TemporaryDirectory

from mcp.server.fastmcp import Image
from mcp.types import ToolAnnotations
from PIL import Image as PILImage, ImageOps
from starlette.responses import HTMLResponse, JSONResponse, FileResponse

from catalogo import Catalogo

WEB = Path(__file__).parent / "web"
HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
           "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY"}
LECTURA = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
ESCRITURA = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)


def instalar(mcp, s):
    catalogo = Catalogo(s.DATA_DIR, s.TZ, s.DRY_RUN)

    def guardar_imagen(datos: bytes):
        if len(datos) > s.MAX_BYTES_CHAT:
            raise ValueError("Cada imagen admite hasta 25 MiB.")
        try:
            with PILImage.open(io.BytesIO(datos)) as im:
                if im.width * im.height > s.MAX_PIXELES_CHAT:
                    raise ValueError("La imagen admite hasta 12 millones de píxeles.")
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((2048, 2048))
                nombre = secrets.token_hex(16) + ".jpg"
                im.save(catalogo.media / nombre, "JPEG", quality=93, optimize=True)
                return nombre
        except (OSError, PILImage.DecompressionBombError):
            raise ValueError("El archivo no es una imagen válida.") from None

    @mcp.tool(annotations=LECTURA)
    def listar_categorias_catalogo() -> list[dict]:
        """Tipos del catálogo y subcategorías. 'flores' requiere programación individual;
        'suministros-florales' sí permite lotes. Taller incluye computadoras e impresoras.
        """
        return catalogo.categorias()

    @mcp.tool(annotations=ESCRITURA)
    def crear_categoria_catalogo(nombre: str, padre: str | None = None, automatica: bool = True) -> dict:
        """Crea un tipo o subcategoría de contenido. No publica ni programa en Facebook."""
        return {"id": catalogo.crear_categoria(nombre, padre, automatica)}

    @mcp.tool(annotations=LECTURA)
    def listar_catalogo(categoria: str | None = None, pagina: str | None = None) -> list[dict]:
        """Publicaciones completas guardadas, con texto, fotos, tipo, página y vigencia.
        Las fotos se conservan aunque se programe el contenido. No llama a Facebook.
        """
        return [p for p in catalogo.listar() if (not categoria or p["categoria"] == categoria)
                and (not pagina or p["pagina"] == pagina)]

    @mcp.tool(annotations=LECTURA)
    def ver_imagen_catalogo(nombre: str) -> Image:
        """Muestra una foto guardada del catálogo; usá los nombres de listar_catalogo."""
        with PILImage.open(catalogo.ruta_media(nombre)) as im:
            im.thumbnail((768, 768))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=80)
        return Image(data=buf.getvalue(), format="jpeg")

    @mcp.tool(annotations=ESCRITURA)
    def guardar_publicacion_catalogo(titulo: str, texto: str, categoria: str, pagina: str = "tocoa",
                                    imagenes: list[str] | None = None, link: str | None = None,
                                    automatica: bool = False, vence: str | None = None) -> dict:
        """Guarda texto y copias de fotos de la bandeja para usar después. NO publica.
        automatica=True solo para contenido aprobado para lotes. Flores siempre manual.
        vence: último día válido AAAA-MM-DD (promociones, temporada o disponibilidad).
        """
        nuevas = []
        try:
            if len(imagenes or []) > 10:
                raise ValueError("Máximo 10 fotos.")
            for nombre in imagenes or []:
                nuevas.append(guardar_imagen(s._ruta_bandeja(nombre).read_bytes()))
            pid = catalogo.guardar(titulo, texto, categoria, pagina, nuevas, link, automatica, vence)
        except BaseException:
            for nombre in nuevas:
                (catalogo.media / nombre).unlink(missing_ok=True)
            raise
        return {"id": pid, "estado": "guardado", "publicado": False}

    @mcp.tool(annotations=ESCRITURA)
    def actualizar_publicacion_catalogo(publicacion_id: str, cambios: dict) -> dict:
        """Edita una publicación guardada. Campos: titulo, texto, categoria, pagina, imagenes
        (nombres ya guardados), link, automatica, activa, vence. No modifica planes preparados.
        Para archivar usá activa=False. Para quitar vigencia usá vence=null.
        """
        permitidos = {"titulo", "texto", "categoria", "pagina", "imagenes", "link", "automatica", "activa", "vence"}
        if set(cambios) - permitidos:
            raise ValueError("Campos desconocidos en cambios.")
        p = next((p for p in catalogo.listar() if p["id"] == publicacion_id), None)
        if not p:
            raise ValueError("La publicación no existe.")
        datos = {k: p[k] for k in permitidos}
        datos.update(cambios)
        catalogo.guardar(**datos, publicacion_id=publicacion_id)
        return {"id": publicacion_id, "estado": "guardado", "planes_modificados": False}

    async def guardar_publicacion_catalogo_con_imagenes(titulo: str, texto: str, categoria: str,
                                                       imagenes, pagina: str = "tocoa",
                                                       automatica: bool = False, vence: str | None = None) -> dict:
        """Guarda una publicación y copias de 1–10 imágenes adjuntas del chat. NO publica.
        Pasá los archivos adjuntos mismos en imagenes, nunca rutas /mnt/data o sandbox:.
        automatica=True solo si el usuario aprobó ese contenido para lotes.
        """
        nuevas = []
        try:
            async with s._archivos_chat_en_curso:
                with TemporaryDirectory(prefix=".catalogo-chat-", dir=s.DATA_DIR) as carpeta:
                    recibidas = await s._recibir_archivos_chat(imagenes, Path(carpeta))
                    for ruta, _, _, _ in recibidas:
                        nuevas.append(guardar_imagen(ruta.read_bytes()))
                pid = catalogo.guardar(titulo, texto, categoria, pagina, nuevas,
                                       automatica=automatica, vence=vence)
        except BaseException:
            for nombre in nuevas:
                (catalogo.media / nombre).unlink(missing_ok=True)
            raise
        return {"id": pid, "estado": "guardado", "publicado": False}

    guardar_publicacion_catalogo_con_imagenes.__annotations__["imagenes"] = s.EntradaArchivosChat
    mcp.add_tool(guardar_publicacion_catalogo_con_imagenes, meta=s.META_ARCHIVOS_CHAT, annotations=ESCRITURA)
    s._anunciar_esquema("guardar_publicacion_catalogo_con_imagenes", {
        "titulo": {"type": "string"}, "texto": {"type": "string"}, "categoria": {"type": "string"},
        "imagenes": s._IMAGENES, "pagina": s._PAGINA, "automatica": {"type": "boolean"},
        "vence": {"type": "string", "description": "Último día válido, AAAA-MM-DD. Opcional."},
    }, ["titulo", "texto", "categoria", "imagenes"])

    @mcp.tool(annotations=ESCRITURA)
    def preparar_lote_catalogo(categoria: str, cantidad: int, dias: int, inicio: str,
                              horas: list[str] | None = None, pagina: str = "tocoa") -> dict:
        """Prepara una vista previa sin enviar a Meta: X posts de un tipo en X días.
        inicio AAAA-MM-DD, horas HH:MM, zona Honduras. No repite contenido ni horarios.
        Taller incluye sus subcategorías. Flores excluidas. Requiere contenido aprobado.
        MOSTRÁ textos y fechas al usuario antes de llamar confirmar_plan_catalogo.
        Los borradores reservan contenido; cancelalos si el usuario los descarta.
        """
        plan = catalogo.preparar_lote(categoria, cantidad, dias, inicio, horas, pagina)
        return {"plan_id": plan, "estado": "borrador", "publicaciones": catalogo.agenda(plan)}

    @mcp.tool(annotations=ESCRITURA)
    def preparar_publicacion_catalogo(publicacion_id: str, fecha: str) -> dict:
        """Prepara UNA publicación guardada para revisar, incluidas flores.
        No envía a Facebook. Mostrá el contenido y confirmá con confirmar_plan_catalogo.
        """
        plan = catalogo.preparar_individual(publicacion_id, fecha)
        return {"plan_id": plan, "estado": "borrador", "publicaciones": catalogo.agenda(plan)}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                        idempotentHint=True, openWorldHint=True))
    def confirmar_plan_catalogo(plan_id: str) -> dict:
        """Activa el envío automático de un plan revisado. SOLO si el usuario aprobó
        expresamente los textos y horarios. La cola persiste sin el chat abierto.
        El servidor debe estar encendido para entregar a Meta; fechas lejanas esperan
        en cola local hasta entrar en la ventana configurada de Meta. No duplica al confirmar dos veces.
        """
        for p in catalogo.agenda(plan_id):
            s._pagina(p["pagina"])  # Detectar credenciales ausentes antes de activar.
        catalogo.confirmar(plan_id)
        return {"plan_id": plan_id, "estado": "confirmado", "simulado": s.DRY_RUN}

    @mcp.tool(annotations=LECTURA)
    def listar_agenda_catalogo(plan_id: str | None = None) -> list[dict]:
        """Agenda local: borradores, pendientes, enviados a Meta, simulados y errores.
        'meta' significa entregado a Meta para la fecha indicada, no publicación verificada.
        'revisar' requiere comprobar Facebook por posible envío ambiguo antes de reintentar.
        """
        return catalogo.agenda(plan_id)

    @mcp.tool(annotations=ESCRITURA)
    def cancelar_plan_catalogo(plan_id: str) -> dict:
        """Cancela un plan local sin enviar. No borra posts enviados a Facebook.
        Para esos posts usá borrar_post con el ID devuelto por listar_agenda_catalogo.
        """
        catalogo.cancelar(plan_id)
        return {"plan_id": plan_id, "estado": "cancelado"}

    async def enviar_uno():
        p = catalogo.reclamar(s.MAX_ANTICIPACION.days)
        if not p:
            return False
        try:
            contenido = p["contenido"]
            fecha = s.datetime.fromtimestamp(p["fecha"], s.TZ)
            ts = s._validar_programacion(fecha)
            page_id, token, _ = s._pagina(p["pagina"])
            data = {"message": contenido["texto"], "published": "false", "scheduled_publish_time": str(ts)}
            if contenido["link"]:
                data["link"] = contenido["link"]
            for i, nombre in enumerate(contenido["imagenes"]):
                datos, mime = s._preparar_imagen(catalogo.ruta_media(nombre))
                foto = await s._graph("POST", f"{page_id}/photos",
                                      data={"published": "false", "temporary": "true"},
                                      files={"source": (nombre, datos, mime)}, token=token)
                data[f"attached_media[{i}]"] = json.dumps({"media_fbid": foto["id"]})
            res = await s._graph("POST", f"{page_id}/feed", data=data, token=token)
            if not res.get("id"):
                raise ValueError("Meta no devolvió un ID. Comprobá la página antes de volver a enviar.")
            catalogo.terminar(p["id"], "simulado" if s.DRY_RUN else "meta", res["id"])
        except Exception as exc:
            # No reintentar: un timeout puede ocurrir DESPUÉS de que Meta haya creado el post.
            mensaje = str(exc)
            for token in s.TOKENS:
                mensaje = mensaje.replace(token, "[oculto]")
            catalogo.terminar(p["id"], "revisar", error=mensaje[:500])
        return True

    async def ciclo():
        while True:
            try:
                # Ceder entre envíos y mantener la web disponible durante un lote grande.
                while await enviar_uno():
                    await asyncio.sleep(0.2)
            except Exception:
                logging.getLogger(__name__).error("La cola del catálogo no pudo completar su revisión.")
            await asyncio.sleep(30)

    def respuesta(valor, estado=200):
        return JSONResponse(valor, status_code=estado, headers=HEADERS)

    @mcp.custom_route(f"/catalogo/{s.SECRET}", methods=["GET"], include_in_schema=False)
    async def pagina_catalogo(request):
        return HTMLResponse((WEB / "catalogo.html").read_text(encoding="utf-8").replace(
            "__SECRET__", quote(s.SECRET, safe="")), headers={
            **HEADERS, "Content-Security-Policy": "default-src 'self'; img-src 'self' blob: data:; "
            "script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"})

    @mcp.custom_route(f"/catalogo-assets/{s.SECRET}/{{nombre}}", methods=["GET"], include_in_schema=False)
    async def asset(request):
        nombre = request.path_params["nombre"]
        if nombre not in ("catalogo.css", "catalogo.js"):
            return respuesta({"error": "No existe."}, 404)
        return FileResponse(WEB / nombre, headers=HEADERS)

    @mcp.custom_route(f"/catalogo-media/{s.SECRET}/{{nombre}}", methods=["GET"], include_in_schema=False)
    async def media(request):
        try:
            return FileResponse(catalogo.ruta_media(request.path_params["nombre"]), headers=HEADERS)
        except ValueError:
            return respuesta({"error": "No existe."}, 404)

    @mcp.custom_route(f"/api/catalogo/{s.SECRET}/{{accion}}", methods=["GET", "POST"], include_in_schema=False)
    async def api(request):
        accion = request.path_params["accion"]
        if request.method == "GET":
            if accion != "estado":
                return respuesta({"error": "No existe."}, 404)
            return respuesta({"publicaciones": catalogo.listar(), "categorias": catalogo.categorias(),
                              "agenda": catalogo.agenda(), "simulado": s.DRY_RUN, "zona": str(s.TZ),
                              "paginas": [{"id": p, "nombre": s.NOMBRES_PAGINA[p]} for p in s.NOMBRES_PAGINA
                                          if p in s.PAGINAS or s.DRY_RUN]})
        # Formularios/API privados: no aceptar POST desde otras páginas.
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return respuesta({"error": "Origen no permitido."}, 403)
        nuevas = []
        try:
            if accion == "guardar":
                async with request.form(max_files=10, max_fields=3, max_part_size=26*1024*1024) as form:
                    datos = json.loads(form["datos"])
                    imagenes = datos.pop("imagenes", [])
                    if not isinstance(imagenes, list) or len(imagenes) > 10:
                        raise ValueError("Máximo 10 fotos.")
                    for f in form.getlist("fotos"):
                        if not getattr(f, "filename", None):
                            continue
                        nuevas.append(guardar_imagen(await f.read(s.MAX_BYTES_CHAT + 1)))
                    pid = catalogo.guardar(**datos, imagenes=imagenes + nuevas)
                return respuesta({"id": pid})
            if "application/json" not in request.headers.get("content-type", ""):
                return respuesta({"error": "Usá application/json."}, 415)
            datos = await request.json()
            if accion == "categoria":
                return respuesta({"id": catalogo.crear_categoria(**datos)})
            if accion == "preparar":
                plan = catalogo.preparar_lote(**datos)
                return respuesta({"plan_id": plan, "publicaciones": catalogo.agenda(plan)})
            if accion == "individual":
                plan = catalogo.preparar_individual(**datos)
                return respuesta({"plan_id": plan, "publicaciones": catalogo.agenda(plan)})
            if accion == "confirmar":
                return respuesta(confirmar_plan_catalogo(datos["plan_id"]))
            if accion == "cancelar":
                return respuesta(cancelar_plan_catalogo(datos["plan_id"]))
            return respuesta({"error": "Acción desconocida."}, 404)
        except (ValueError, TypeError, KeyError) as exc:
            for nombre in nuevas:
                (catalogo.media / nombre).unlink(missing_ok=True)
            return respuesta({"error": str(exc)}, 400)

    return catalogo, ciclo, enviar_uno
