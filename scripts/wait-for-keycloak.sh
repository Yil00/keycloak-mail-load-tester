#!/bin/sh
# Attend que Keycloak réponde avant d'exécuter la commande (évite Connection refused au run).
# Au premier run, Keycloak peut mettre 1 à 3 min à démarrer (surtout sur Mac ARM).
set -e
echo "Attente de Keycloak (${KEYCLOAK_URL:-http://keycloak:${KEYCLOAK_PORT:-8080}})..." >&2
python -c "
import os, sys, time, urllib.request
port = os.environ.get('KEYCLOAK_PORT', '8080')
url = os.environ.get('KEYCLOAK_URL', f'http://keycloak:{port}').rstrip('/')
# 120 x 2s = 4 min max (Keycloak peut être lent au premier démarrage)
for i in range(120):
    try:
        urllib.request.urlopen(url + '/', timeout=3)
        print('Keycloak prêt.', file=sys.stderr)
        break
    except Exception as e:
        if i == 0:
            print('Connexion refusée, nouvel essai toutes les 2s (max 4 min)...', file=sys.stderr)
        if (i + 1) % 15 == 0 and i > 0:
            print('  ... toujours en attente ({0}s)'.format((i + 1) * 2), file=sys.stderr)
        time.sleep(2)
else:
    print('Keycloak injoignable après 4 min. Conseil : lancez \"make up\", attendez 1 min, puis relancez la commande.', file=sys.stderr)
    sys.exit(1)
"
exec "$@"
