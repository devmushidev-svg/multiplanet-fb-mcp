#!/bin/sh
# Si FB_PAGE_TOKEN_FLORISTERIA es un token de USUARIO, lo cambia por el token de la PÁGINA
# (no vence si el de usuario es de larga duración). Nunca imprime tokens.
set -u
ENV=/opt/fbmcp/.env
V=v27.0
G=https://graph.facebook.com/$V
leer() { grep "^$1=" "$ENV" | tail -1 | cut -d= -f2-; }
campo() { python3 -c "import sys,json
try: d=json.load(sys.stdin)
except Exception: d={}
print(d.get('$1','') if '$1'!='error' else d.get('error',{}).get('message',''))"; }

PID=$(leer FB_PAGE_ID_FLORISTERIA)
TOK=$(leer FB_PAGE_TOKEN_FLORISTERIA)
if [ -z "$PID" ] || [ -z "$TOK" ]; then echo "Faltan FB_PAGE_ID_FLORISTERIA o FB_PAGE_TOKEN_FLORISTERIA"; exit 1; fi

YO=$(curl -s "$G/me?fields=id" -H "Authorization: Bearer $TOK" | campo id)
if [ "$YO" = "$PID" ]; then
  echo "El token ya es de la pagina."
else
  NUEVO=$(curl -s "$G/$PID?fields=access_token" -H "Authorization: Bearer $TOK" | campo access_token)
  if [ -z "$NUEVO" ]; then echo "No pude obtener el token de la pagina."; exit 1; fi
  TMP=$(mktemp)
  grep -v '^FB_PAGE_TOKEN_FLORISTERIA=' "$ENV" > "$TMP"
  echo "FB_PAGE_TOKEN_FLORISTERIA=$NUEVO" >> "$TMP"
  cat "$TMP" > "$ENV"
  rm -f "$TMP"
  TOK=$NUEVO
  echo "Token de usuario cambiado por token de pagina."
fi

R=$(curl -s "$G/$PID/posts?limit=1&fields=id" -H "Authorization: Bearer $TOK")
ERR=$(echo "$R" | campo error)
if [ -z "$ERR" ]; then echo "Lectura de posts: OK"; else echo "Lectura de posts: ERROR $ERR"; fi
echo "lineas_floristeria=$(grep -c FLORISTERIA "$ENV")"
systemctl restart fbmcp
sleep 3
systemctl is-active fbmcp
