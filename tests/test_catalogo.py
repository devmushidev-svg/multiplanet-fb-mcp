import asyncio
import io
import json
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from catalogo import Catalogo

TZ = ZoneInfo("America/Tegucigalpa")


class CatalogoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Catalogo(Path(self.tmp.name), TZ)
        self.start = (datetime.now(TZ) + timedelta(days=1)).date().isoformat()

    def add(self, n=1, categoria="visa-americana", **kwargs):
        return [self.store.guardar(f"Publicación {i}", f"Texto completo {i}", categoria,
                                  automatica=True, **kwargs) for i in range(n)]

    def batch(self, n=1, dias=7, **kwargs):
        return self.store.preparar_lote("visa-americana", n, dias, self.start, **kwargs)

    def test_43_posts_spread_without_duplicates_and_persist(self):
        self.add(43)
        plan = self.batch(43, 15)
        rows = self.store.agenda(plan)
        self.assertEqual(len(rows), 43)
        self.assertEqual(len({p["publicacion_id"] for p in rows}), 43)
        self.assertEqual(len({p["fecha"] for p in rows}), 43)
        self.assertEqual(rows[0]["fecha_local"][:10], self.start)
        self.assertEqual(rows[-1]["fecha_local"][:10],
                         (datetime.fromisoformat(self.start) + timedelta(days=14)).date().isoformat())
        reopened = Catalogo(Path(self.tmp.name), TZ)
        self.assertEqual(len(reopened.agenda(plan)), 43)
        self.assertTrue(all(r["estado"] == "borrador" for r in rows))
        self.assertIsNone(self.store.reclamar(30))

    def test_insufficient_content_is_atomic(self):
        self.add(2)
        with self.assertRaisesRegex(ValueError, "No hay 3"):
            self.batch(3)
        self.assertEqual(self.store.agenda(), [])
        self.assertTrue(self.batch(2))

    def test_workshop_includes_both_subcategories(self):
        self.add(1, "computadoras")
        self.add(1, "impresoras")
        plan = self.store.preparar_lote("taller", 2, 2, self.start)
        self.assertEqual({r["contenido"]["categoria"] for r in self.store.agenda(plan)}, {"computadoras", "impresoras"})

    def test_floral_designs_manual_but_supplies_automatic(self):
        floral = self.add(1, "flores")[0]
        self.assertEqual(self.store.listar()[0]["automatica"], 0)
        with self.assertRaisesRegex(ValueError, "manualmente"):
            self.store.preparar_lote("flores", 1, 1, self.start)
        self.assertTrue(self.store.preparar_individual(floral, self.start + " 09:00"))
        self.add(1, "suministros-florales")
        self.assertTrue(self.store.preparar_lote("suministros-florales", 1, 1, self.start))
        child = self.store.crear_categoria("Ramos", "flores", True)
        self.assertEqual(next(c for c in self.store.categorias() if c["id"] == child)["automatica"], 0)

    def test_expiry_and_page_filter(self):
        self.add(1, vence=datetime.now(TZ).date().isoformat())
        self.add(1, pagina="floristeria")
        with self.assertRaises(ValueError):
            self.batch()
        self.assertEqual(self.store.agenda(), [])

    def test_cancel_draft_releases_content(self):
        self.add()
        plan = self.batch()
        with self.assertRaises(ValueError):
            self.batch()
        self.store.cancelar(plan)
        self.assertTrue(self.batch())
        with self.assertRaisesRegex(ValueError, "cancelado"):
            self.store.confirmar(plan)

    def test_confirm_twice_and_claim_once(self):
        self.add()
        plan = self.batch()
        self.store.confirmar(plan)
        self.store.confirmar(plan)
        self.assertEqual(len(self.store.agenda()), 1)
        self.assertIsNotNone(self.store.reclamar(30))
        self.assertIsNone(self.store.reclamar(30))

    def test_snapshots_survive_edits_and_archived_draft_cannot_confirm(self):
        pid = self.add()[0]
        plan = self.batch()
        self.store.guardar("Nuevo título", "Texto cambiado", "papeleria", publicacion_id=pid)
        self.assertEqual(self.store.agenda(plan)[0]["contenido"]["texto"], "Texto completo 0")
        self.store.guardar("Archivada", "Texto", "papeleria", publicacion_id=pid, activa=False)
        with self.assertRaisesRegex(ValueError, "archivado"):
            self.store.confirmar(plan)

    def test_far_future_waits_and_missed_slots_never_publish_now(self):
        pid = self.add()[0]
        far = datetime.now(TZ) + timedelta(days=60)
        plan = self.store.preparar_individual(pid, far.isoformat())
        self.store.confirmar(plan)
        self.assertIsNone(self.store.reclamar(30))
        with self.store.conexion(True) as db:
            db.execute("UPDATE agenda SET fecha=?", (datetime.now(TZ).timestamp() - 1,))
        self.assertIsNone(self.store.reclamar(30))
        self.assertEqual(self.store.agenda()[0]["estado"], "vencido")

    def test_recovery_requires_review_instead_of_resend(self):
        self.add()
        plan = self.batch()
        self.store.confirmar(plan)
        self.store.reclamar(30)
        reopened = Catalogo(Path(self.tmp.name), TZ)
        reopened.recuperar_interrumpidos()
        self.assertEqual(reopened.agenda()[0]["estado"], "revisar")
        self.assertIsNone(reopened.reclamar(30))
        with self.assertRaisesRegex(ValueError, "revisar"):
            reopened.cancelar(plan)

    def test_simulated_plan_never_becomes_real_automatically(self):
        self.store.simulado = True
        self.add()
        plan = self.batch()
        self.store.simulado = False
        with self.assertRaisesRegex(ValueError, "modo"):
            self.store.confirmar(plan)
        self.assertIsNone(self.store.reclamar(30))

    def test_simulated_pending_stays_isolated(self):
        self.store.simulado = True
        self.add()
        self.store.confirmar(self.batch())
        self.store.simulado = False
        self.assertIsNone(self.store.reclamar(30))

    def test_concurrent_planners_cannot_reserve_same_post(self):
        self.add()
        def prepare(_):
            try:
                return self.batch()
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            plans = list(pool.map(prepare, range(2)))
        self.assertEqual(sum(p is not None for p in plans), 1)
        self.assertEqual(len(self.store.agenda()), 1)

    def test_media_path_traversal_and_unknown_page_rejected(self):
        with self.assertRaises(ValueError):
            self.store.ruta_media("../catalogo.sqlite3")
        with self.assertRaises(ValueError):
            self.add(pagina="otra")

    def test_no_automatic_repeat_after_success_or_early_publish(self):
        self.add()
        self.store.confirmar(self.batch())
        job = self.store.reclamar(30)
        self.store.terminar(job["id"], "meta", "123_456")
        self.store.actualizar_desde_meta("123_456", estado="publicado")
        with self.assertRaises(ValueError):
            self.batch()
        self.store.actualizar_desde_meta("123_456", estado="cancelado")
        self.assertTrue(self.batch())


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = patch.dict(os.environ, {"MCP_SECRET": "secreto-aislado-pruebas-catalogo", "FB_DRY_RUN": "1",
                                           "DATA_DIR": cls.tmp.name, "PUBLIC_HOST": ""})
        cls.env.start()
        import server
        cls.server = server
        from starlette.testclient import TestClient
        cls.TestClient = TestClient
        cls.client = TestClient(server.crear_app())
        cls.root = "/api/catalogo/" + server.SECRET + "/"

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.env.stop()
        cls.tmp.cleanup()

    def setUp(self):
        self.s = self.server
        self.assertTrue(self.s.DRY_RUN, "Las pruebas no pueden llamar a Facebook real.")
        with self.s.catalogo.conexion(True) as db:
            db.execute("DELETE FROM agenda")
            db.execute("DELETE FROM planes")
            db.execute("DELETE FROM publicaciones")

    def prepare(self):
        p = self.s.catalogo.guardar("Prueba", "Texto íntegro", "visa-americana", automatica=True)
        fecha = (datetime.now(TZ) + timedelta(days=1)).isoformat()
        plan = self.s.catalogo.preparar_individual(p, fecha)
        self.s.catalogo.confirmar(plan)
        return plan

    def test_web_routes_private_assets_and_no_secret_placeholder(self):
        r = self.client.get("/catalogo/" + self.s.SECRET)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("__SECRET__", r.text)
        self.assertEqual(r.headers["referrer-policy"], "no-referrer")
        self.assertEqual(self.client.get("/catalogo/no-es-el-secreto").status_code, 404)
        self.assertEqual(self.client.get(self.root + "estado").status_code, 200)
        self.assertEqual(self.client.get("/catalogo-assets/" + self.s.SECRET + "/catalogo.js").status_code, 200)
        self.assertEqual(self.client.get("/catalogo-media/" + self.s.SECRET + "/no-existe.jpg").status_code, 404)

    def test_cross_origin_mutation_rejected(self):
        r = self.client.post(self.root + "categoria", json={"nombre": "Ataque"}, headers={"Origin": "https://otro.example"})
        self.assertEqual(r.status_code, 403)

    def test_photo_upload_retained_after_simulated_send(self):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (100, 100), "green").save(buf, "PNG")
        data = {"titulo": "Producto", "texto": "Descripción del producto", "categoria": "papeleria", "automatica": True}
        response = self.client.post(self.root + "guardar", data={"datos": json.dumps(data)},
                                    files={"fotos": ("foto.png", buf.getvalue(), "image/png")})
        self.assertEqual(response.status_code, 200, response.text)
        p = self.s.catalogo.listar()[0]
        nombre = p["imagenes"][0]
        plan = self.s.catalogo.preparar_individual(p["id"], (datetime.now(TZ) + timedelta(days=1)).isoformat())
        self.s.catalogo.confirmar(plan)
        asyncio.run(self.s.enviar_uno_catalogo())
        row = self.s.catalogo.agenda()[0]
        self.assertEqual(row["estado"], "simulado")
        self.assertTrue(self.s.catalogo.ruta_media(nombre).is_file())
        self.assertEqual(self.client.get("/catalogo-media/" + self.s.SECRET + "/" + nombre).status_code, 200)

    def test_uncertain_meta_result_is_not_retried(self):
        self.prepare()
        with patch.object(self.s, "_graph", AsyncMock(side_effect=self.s.ErrorFacebook("Timeout ambiguo"))) as graph:
            asyncio.run(self.s.enviar_uno_catalogo())
            self.assertFalse(asyncio.run(self.s.enviar_uno_catalogo()))
            self.assertEqual(graph.await_count, 1)
        self.assertEqual(self.s.catalogo.agenda()[0]["estado"], "revisar")

    def test_tools_keep_original_file_schemas(self):
        tools = {t.name: t for t in asyncio.run(self.s.mcp.list_tools())}
        for name in ("programar_post_con_imagenes", "verificar_imagenes_chat", "guardar_publicacion_catalogo_con_imagenes"):
            self.assertEqual(tools[name].meta["openai/fileParams"], ["imagenes"])
            self.assertEqual(tools[name].inputSchema["properties"]["imagenes"]["maxItems"], 10)
        self.assertIn("preparar_lote_catalogo", tools)
        self.assertTrue(tools["listar_agenda_catalogo"].annotations.readOnlyHint)

    def test_save_chat_attachment_without_publishing(self):
        from PIL import Image
        ruta = Path(self.tmp.name) / "chat.png"
        Image.new("RGB", (80, 80), "blue").save(ruta)
        with patch.object(self.s, "_recibir_archivos_chat", AsyncMock(return_value=[(ruta, ruta.stat().st_size, 80, 80)])), \
             patch.object(self.s, "_graph", AsyncMock()) as graph:
            asyncio.run(self.s.mcp.call_tool("guardar_publicacion_catalogo_con_imagenes", {
                "titulo": "Desde ChatGPT", "texto": "Texto guardado", "categoria": "papeleria",
                "imagenes": [{"download_url": "https://chatgpt.com/archivo", "file_id": "prueba"}],
            }))
            graph.assert_not_called()
        self.assertEqual(self.s.catalogo.listar()[0]["titulo"], "Desde ChatGPT")
        self.assertTrue(self.s.catalogo.ruta_media(self.s.catalogo.listar()[0]["imagenes"][0]).is_file())

    def test_z_worker_runs_with_no_mcp_client_connected(self):
        self.prepare()
        # Esta prueba detecta un lifespan atado incorrectamente a cada petición MCP.
        with self.TestClient(self.s.crear_app()) as client:
            headers = {"Accept": "application/json, text/event-stream"}
            inicial = client.post("/mcp/" + self.s.SECRET, headers=headers, json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                    "protocolVersion": "2025-03-26", "capabilities": {},
                    "clientInfo": {"name": "prueba", "version": "1"},
                },
            })
            self.assertEqual(inicial.status_code, 200, inicial.text)
            tools = client.post("/mcp/" + self.s.SECRET, headers=headers,
                                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            self.assertEqual(tools.status_code, 200, tools.text)
            self.assertIn("guardar_publicacion_catalogo_con_imagenes",
                          {t["name"] for t in tools.json()["result"]["tools"]})
            import time
            limite = time.monotonic() + 5
            while time.monotonic() < limite:
                rows = client.get(self.root + "estado").json()["agenda"]
                if rows[0]["estado"] == "simulado":
                    break
                time.sleep(.05)
            self.assertEqual(rows[0]["estado"], "simulado")


if __name__ == "__main__":
    unittest.main()
