"""
Convierte el token corto del Graph API Explorer en un token de PÁGINA que no vence.

Uso (solo necesita Python, sin librerías extra):
    python obtener_token.py

Te pide:
  - App ID y App Secret (developers.facebook.com → tu app → Configuración → Básica)
  - El token de usuario corto que generaste en el Graph API Explorer con los permisos
    pages_show_list, pages_read_engagement, pages_manage_posts
"""

import getpass
import json
import urllib.parse
import urllib.request

VERSION = "v27.0"
BASE = f"https://graph.facebook.com/{VERSION}"


def get(ruta: str, **params) -> dict:
    url = f"{BASE}/{ruta}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        cuerpo = json.load(e)
        raise SystemExit(f"\nError de Meta: {cuerpo.get('error', {}).get('message', cuerpo)}")


def main() -> None:
    app_id = input("App ID: ").strip()
    app_secret = getpass.getpass("App Secret (no se muestra): ").strip()
    corto = getpass.getpass("Token corto del Graph API Explorer (no se muestra): ").strip()

    largo = get("oauth/access_token", grant_type="fb_exchange_token", client_id=app_id,
                client_secret=app_secret, fb_exchange_token=corto)["access_token"]
    print("\n✓ Token de usuario de larga duración obtenido.")

    paginas = get("me/accounts", access_token=largo, fields="id,name,access_token,tasks").get("data", [])
    if not paginas:
        raise SystemExit("No se encontraron páginas. ¿Marcaste pages_show_list y sos admin de la página?")

    for i, p in enumerate(paginas):
        print(f"  [{i}] {p['name']}  (id {p['id']})  permisos: {', '.join(p.get('tasks', []))}")
    idx = int(input("\n¿Cuál página? Número: ") or 0) if len(paginas) > 1 else 0
    pagina = paginas[idx]

    info = get("debug_token", input_token=pagina["access_token"],
               access_token=f"{app_id}|{app_secret}")["data"]
    vence = "nunca" if info.get("expires_at", 0) == 0 else f"timestamp {info['expires_at']}"
    print(f"\n✓ Token de página para '{pagina['name']}' — vence: {vence}")
    print(f"  Permisos: {', '.join(info.get('scopes', []))}")
    if "pages_manage_posts" not in info.get("scopes", []):
        print("  ⚠ Falta pages_manage_posts: no vas a poder publicar. Regenerá el token corto con ese permiso.")

    print("\nCopiá esto en tu archivo .env del servidor:\n")
    print(f"FB_PAGE_ID={pagina['id']}")
    print(f"FB_PAGE_TOKEN={pagina['access_token']}")


if __name__ == "__main__":
    main()
