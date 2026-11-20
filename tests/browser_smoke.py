"""Prueba visual opcional: pip install playwright; usa Edge instalado, sin Facebook."""
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from catalogo import Catalogo

SECRET = "secreto-browser-pruebas-catalogo"
EDGE = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe"
OUT = ROOT / "test-results"
OUT.mkdir(exist_ok=True)

with tempfile.TemporaryDirectory() as tmp:
    store = Catalogo(Path(tmp), ZoneInfo("America/Tegucigalpa"), True)
    for title, category, text in [
        ("Asesoría para tu visa americana", "visa-americana", "Prepará tu trámite con acompañamiento personalizado. Consultanos por los requisitos."),
        ("Tu impresora, lista para trabajar", "impresoras", "Mantenimiento preventivo y diagnóstico para cuidar tu equipo."),
        ("Todo para tu próximo arreglo", "suministros-florales", "Encontrá los materiales para tus creaciones. Consultá disponibilidad."),
        ("Un detalle para cada ocasión", "flores", "Diseño de muestra para elegir manualmente según temporada."),
    ]:
        store.guardar(title, text, category, automatica=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "MCP_SECRET": SECRET, "FB_DRY_RUN": "1", "DATA_DIR": tmp,
           "PUBLIC_HOST": "", "HOST": "127.0.0.1", "PORT": str(port)}
    log = (OUT / "browser-server.log").open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, str(ROOT / "server.py")], cwd=ROOT, env=env, stdout=log, stderr=log)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/salud", timeout=1)
                break
            except OSError:
                if process.poll() is not None:
                    raise RuntimeError("El servidor terminó antes de iniciar.")
                time.sleep(.1)
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=str(EDGE), headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1080}, device_scale_factor=1)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            page.goto(base + "/catalogo/" + SECRET)
            page.locator(".card").nth(3).wait_for()
            assert page.locator(".card").count() == 4
            page.screenshot(path=str(OUT / "catalogo-desktop.png"), full_page=False)
            # Crear con una imagen desde el navegador, editar y conservar la foto.
            page.locator("#new-open").click()
            form = page.locator("#editor-form")
            form.locator('[name="titulo"]').fill("Documentos y trámites")
            form.locator('[name="texto"]').fill("Impresión, escaneo y apoyo secretarial en Multiplanet.")
            form.locator('[name="categoria"]').select_option("servicios-secretariales")
            form.locator('[name="automatica"]').check()
            buf = io.BytesIO()
            Image.new("RGB", (500, 400), "#0b6a53").save(buf, "PNG")
            form.locator('[name="fotos"]').set_input_files({"name": "prueba.png", "mimeType": "image/png", "buffer": buf.getvalue()})
            form.locator('button[type="submit"]').click()
            page.locator("#editor").wait_for(state="hidden")
            page.get_by_role("heading", name="Documentos y trámites").wait_for()
            card = page.locator(".card").filter(has=page.get_by_role("heading", name="Documentos y trámites"))
            card.get_by_role("button", name="Editar", exact=True).click()
            assert page.locator("#existing-images img").count() == 1
            form.locator('[name="titulo"]').fill("Servicios para tus documentos")
            form.locator('button[type="submit"]').click()
            page.locator("#editor").wait_for(state="hidden")
            # Vista previa, texto completo y confirmación; no hay envío antes de confirmar.
            page.locator("#batch-open").click()
            batch = page.locator("#batch-form")
            batch.locator('[name="categoria"]').select_option("visa-americana")
            batch.locator('[name="cantidad"]').fill("1")
            batch.locator('button[type="submit"]').click()
            page.locator("#preview[open]").wait_for()
            assert page.locator("#preview-posts").inner_text().find("Prepará tu trámite") >= 0
            page.screenshot(path=str(OUT / "catalogo-plan.png"), full_page=True)
            page.locator("#confirm-plan").click()
            page.locator("#preview").wait_for(state="hidden")
            page.locator("#agenda-rows tr").first.wait_for()
            assert "En cola local" in page.locator("#agenda-rows").inner_text()
            # El botón cancela únicamente la cola local y libera la publicación.
            page.get_by_role("button", name="Cancelar plan", exact=True).click()
            page.get_by_text("Cancelado", exact=True).wait_for()
            # Flores: la interfaz tampoco permite marcarlas como automáticas.
            page.locator("#nav-catalogo").click()
            flower = page.locator(".card").filter(has=page.get_by_role("heading", name="Un detalle para cada ocasión"))
            flower.get_by_role("button", name="Editar", exact=True).click()
            assert form.locator('[name="automatica"]').is_disabled()
            page.locator('[data-close="editor"]').click()
            # Buscar, categoría nueva y pantalla móvil sin desbordamiento.
            page.locator("#search").fill("impresora")
            assert page.locator(".card").count() == 1
            page.locator("#search").fill("")
            page.locator("#add-category").click()
            category = page.locator("#category-form")
            category.locator('[name="nombre"]').fill("Promociones de prueba")
            category.locator('button[type="submit"]').click()
            page.locator("#category-dialog").wait_for(state="hidden")
            page.locator("#toast").evaluate("el => { el.hidden = true; }")
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(OUT / "catalogo-mobile.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Desbordamiento horizontal"
            assert not errors, errors
            browser.close()
            print("OK: crear con foto, editar, preparar, revisar, confirmar, cancelar, flores manuales, categorías, búsqueda y móvil.")
    finally:
        process.terminate()
        process.wait(timeout=15)
        log.close()
