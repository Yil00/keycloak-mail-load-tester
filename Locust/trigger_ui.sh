#!/usr/bin/env sh
# Déclenche un test Locust via l'API du conteneur qui sert l'UI.
# Les stats s'affichent en direct dans l'interface http://localhost:8089
# Usage: ./trigger_ui.sh [user_count] [spawn_rate] [run_time]
# Exemple: ./trigger_ui.sh 10 5 30   (10 users, 5/s, arrêt après 30 s)

LOCUST_HOST="${LOCUST_HOST:-http://localhost:${LOCUST_PORT:-8089}}"
USERS="${1:-10}"
SPAWN_RATE="${2:-5}"
RUN_TIME="$3"

echo "Démarrage du test dans l'UI Locust ($LOCUST_HOST) : $USERS users, spawn rate $SPAWN_RATE/s"
resp=$(curl -s -w "\n%{http_code}" -X POST "$LOCUST_HOST/swarm" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "user_count=$USERS&spawn_rate=$SPAWN_RATE")
http_code=$(echo "$resp" | tail -n1)
body=$(echo "$resp" | sed '$d')

if [ "$http_code" != "200" ]; then
  echo "Erreur API Locust (HTTP $http_code). Assure-toi que le conteneur Locust avec UI tourne : docker compose up -d locust"
  echo "$body"
  exit 1
fi

echo "Test démarré. Ouvre $LOCUST_HOST pour voir les stats en direct."

if [ -n "$RUN_TIME" ]; then
  # Supprimer un éventuel 's' pour sleep (sleep 30s est valide en sh)
  SLEEP_VAL=$(echo "$RUN_TIME" | sed 's/s$//')
  echo "Arrêt automatique dans ${SLEEP_VAL}s..."
  sleep "$SLEEP_VAL"
  # Locust n'accepte que GET sur /stop (pas POST)
  curl -s -X GET "$LOCUST_HOST/stop" > /dev/null
  echo "Test arrêté."
fi
