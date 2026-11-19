#!/bin/sh
set -eu

base=/opt/fbmcp
repo_raw="${FBMCP_RAW:-https://raw.githubusercontent.com/devmushidev-svg/multiplanet-fb-mcp/main}"
target="$base/server.py"
python="$base/venv/bin/python"
candidate=$(mktemp "$base/.server.py.XXXXXX")
sandbox=$(mktemp -d)
trap 'rm -f "$candidate"; rmdir "$sandbox/bandeja" "$sandbox/usadas" "$sandbox" 2>/dev/null || true' EXIT

curl -fsSL --max-time 60 "$repo_raw/server.py" -o "$candidate"
[ -s "$candidate" ] || { echo "No pude descargar server.py desde GitHub." >&2; exit 1; }

# Validar el candidato con el venv real y un entorno de prueba separado.
if ! env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
    FB_DRY_RUN=1 MCP_SECRET=secreto-local-para-preflight \
    DATA_DIR="$sandbox" "$python" - "$candidate" <<'PY'
import asyncio
import importlib.metadata
import importlib.machinery
import importlib.util
import sys

print("SDK MCP", importlib.metadata.version("mcp"))
loader = importlib.machinery.SourceFileLoader("fbmcp_candidate", sys.argv[1])
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = module
loader.exec_module(module)
tools = {tool.name: tool for tool in asyncio.run(module.mcp.list_tools())}
for name in ("programar_post_con_imagenes", "verificar_imagenes_chat"):
    tool = tools[name]
    assert tool.meta["openai/fileParams"] == ["imagenes"]
    assert tool.inputSchema["properties"]["imagenes"]["maxItems"] == 10
assert tools["verificar_imagenes_chat"].annotations.readOnlyHint
PY
then
    echo "Falló la comprobación con el venv de fbmcp. No se reemplazó server.py." >&2
    exit 1
fi

backup=$(mktemp "$base/server.py.bak.XXXXXX")
cp -p "$target" "$backup"
chown --reference="$target" "$candidate"
chmod --reference="$target" "$candidate"
mv -f "$candidate" "$target"

salud() {
    for intento in 1 2 3 4 5 6 7 8 9 10; do
        if systemctl is-active --quiet fbmcp &&
           curl --max-time 2 -fsS -H 'Host: multiplanet-mcp.northcentralus.cloudapp.azure.com' \
                http://127.0.0.1:8000/salud; then
            printf '\n'
            return 0
        fi
        sleep 1
    done
    return 1
}

if systemctl restart fbmcp && salud; then
    echo "fbmcp activo. Respaldo: $backup"
else
    echo "Falló el arranque. Restaurando server.py desde $backup." >&2
    cp -p "$backup" "$candidate"
    mv -f "$candidate" "$target"
    systemctl restart fbmcp
    salud
    exit 1
fi

