# Keycloak + Postgres + MailHog — commandes Make
# Usage : make [cible]
# Les scripts src/ s'exécutent dans le conteneur keycloak-session-exporter (même réseau que Keycloak).

COMPOSE := docker compose
# Exécuter un script Python dans keycloak-session-exporter (make up requis)
EXEC_SCRIPTS := $(COMPOSE) exec -T keycloak-session-exporter

.PHONY: help up down restart ps logs logs-keycloak logs-mailhog keycloak-allow-http install test test-nb test-rate test-batch load-test load-test-ramp load-test-multi load-test-multi-ramp create-locust-users locust-headless locust-trigger create-superadmin list-users delete-test-users clean

help:
	@echo "Keycloak — cibles disponibles :"
	@echo ""
	@echo "  Docker"
	@echo "  ──────"
	@echo "  make up              Démarrer tous les services (Postgres, Keycloak, MailHog, Prometheus, Grafana, Locust)"
	@echo "  make down            Arrêter et supprimer les conteneurs"
	@echo "  make restart         Redémarrer tous les services"
	@echo "  make ps              Afficher l’état des conteneurs"
	@echo ""
	@echo "  Logs"
	@echo "  ────"
	@echo "  make logs            Suivre les logs de tous les services"
	@echo "  make logs-keycloak   Suivre les logs Keycloak uniquement"
	@echo "  make logs-mailhog    Suivre les logs MailHog uniquement"
	@echo ""
	@echo "  Tests mails (keycloak-session-exporter)"
	@echo "  ──────────────────────────────────────"
	@echo "  make install         (info : scripts dans keycloak-session-exporter, make up requis)"
	@echo "  make test            Test d'envoi 100 mails (débit max)"
	@echo "  make test-nb NB=500  Nombre personnalisé"
	@echo "  make test-rate RATE=100 NB=1000  Débit constant"
	@echo "  make test-batch NB=5000 PAUSE=30  Lots + pause"
	@echo ""
	@echo "  Tests de charge (scripts Python)"
	@echo "  ────────────────────────────────"
	@echo "  make load-test CONCURRENT=20 DURATION=60  Constant, un compte"
	@echo "  make load-test-ramp  Ramp (montée/descente)"
	@echo "  make load-test-multi CREATE_USERS=50 CONCURRENT=20 DURATION=30  Multi-comptes"
	@echo "  make load-test-multi-ramp  Idem en ramp"
	@echo ""
	@echo "  Locust (tests de charge, comptes distincts)"
	@echo "  ────────────────────────────────────────"
	@echo "  make create-locust-users     Créer loadtest_user_1..N (défaut 100, mot de passe testpass)"
	@echo "  make locust-headless         Lancer Locust sans UI — stats dans le terminal"
	@echo "  make locust-trigger          Déclencher le test dans l'UI — stats en direct (prérequis : make up)"
	@echo "  → create-locust-users : LOCUST_USER_COUNT=50 KEYCLOAK_LOAD_PASSWORD=... REALM=master"
	@echo "  → locust-headless    : USERS=10 SPAWN_RATE=5 RUN_TIME=30s"
	@echo "  → locust-trigger     : USERS=10 SPAWN_RATE=5 RUN_TIME=30  (UI http://localhost:8089)"
	@echo "  → Voir docs/locust.md et locust/README.md"
	@echo ""
	@echo "  Admin Keycloak (utilisateurs)"
	@echo "  ─────────────────────────────"
	@echo "  make create-superadmin SUPERADMIN_USER=... SUPERADMIN_PASSWORD=..."
	@echo "  make list-users      Nombre d'utilisateurs par realm"
	@echo "  make delete-test-users  Supprimer loadtest_* et testuser_* (DRY_RUN=1 pour simuler)"
	@echo ""
	@echo "  Keycloak & nettoyage"
	@echo "  ───────────────────"
	@echo "  make keycloak-allow-http  Autoriser HTTP (realm master) si « HTTPS required »"
	@echo "  make clean           Arrêter les conteneurs et supprimer les volumes"
	@echo ""

# ── Docker Compose ───────────────────────────────────────────────────────────
up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart: down up

# Autoriser HTTP pour le realm master (enlève « HTTPS required »)
# À lancer une fois que Keycloak a démarré (make up puis attendre ~40 s)
keycloak-allow-http:
	$(COMPOSE) exec -T postgres psql -U keycloak -d keycloak -c "UPDATE realm SET ssl_required = 'NONE' WHERE name = 'master';" || true
	$(COMPOSE) restart keycloak

ps:
	$(COMPOSE) ps -a

# ── Logs ────────────────────────────────────────────────────────────────────
logs:
	$(COMPOSE) logs -f

logs-keycloak:
	$(COMPOSE) logs -f keycloak

logs-mailhog:
	$(COMPOSE) logs -f mailhog

# ── Scripts (conteneur keycloak-session-exporter) ───────────────────────────────
install:
	@echo "Les scripts s'exécutent dans keycloak-session-exporter. Lancez \"make up\" puis make test / load-test / etc."

# NB par défaut = 100
NB ?= 100
# Stratégie rate : mails/sec (ex. 100 = 360k/h)
RATE ?= 100
# Stratégie batch-pause : taille du lot et pause en secondes
SEND_BATCH_SIZE ?= 5000
PAUSE ?= 30

test:
	$(EXEC_SCRIPTS) python src/test_keycloak.py --nb $(NB)

test-nb: test

test-rate:
	$(EXEC_SCRIPTS) python src/test_keycloak.py --nb $(NB) --strategy rate --rate $(RATE)

test-batch:
	$(EXEC_SCRIPTS) python src/test_keycloak.py --nb $(NB) --strategy batch-pause --send-batch-size $(SEND_BATCH_SIZE) --pause $(PAUSE)

# Test de charge (connexions simultanées sur une durée)
CONCURRENT ?= 10
DURATION ?= 30
# Ramp : users, ramp-up (s), hold (s), ramp-down (s)
RAMP_USERS ?= 30
RAMP_UP ?= 60
RAMP_HOLD ?= 30
RAMP_DOWN ?= 60

load-test:
	$(EXEC_SCRIPTS) python src/keycloak_load_test.py --concurrent $(CONCURRENT) --duration $(DURATION)

load-test-ramp:
	$(EXEC_SCRIPTS) python src/keycloak_load_test.py --mode ramp --users $(RAMP_USERS) --ramp-up $(RAMP_UP) --hold $(RAMP_HOLD) --ramp-down $(RAMP_DOWN)

# Test de charge multi-comptes (simulation proche production)
CREATE_USERS ?= 50
MULTI_USER_PASSWORD ?= testpass

load-test-multi:
	$(EXEC_SCRIPTS) python src/keycloak_load_test_multi_user.py --create-users $(CREATE_USERS) --user-password $(MULTI_USER_PASSWORD) --concurrent $(CONCURRENT) --duration $(DURATION)

load-test-multi-ramp:
	$(EXEC_SCRIPTS) python src/keycloak_load_test_multi_user.py --create-users $(CREATE_USERS) --user-password $(MULTI_USER_PASSWORD) --mode ramp --users $(RAMP_USERS) --ramp-up $(RAMP_UP) --hold $(RAMP_HOLD) --ramp-down $(RAMP_DOWN)

# ── Admin Keycloak (superadmin, list-users, delete-test-users) ───────────────
SUPERADMIN_USER ?= superadmin
SUPERADMIN_PASSWORD ?=
REALM ?= master

create-superadmin:
	@test -n "$(SUPERADMIN_PASSWORD)" || (echo "Usage: make create-superadmin SUPERADMIN_USER=myadmin SUPERADMIN_PASSWORD=secret"; exit 1)
	$(EXEC_SCRIPTS) -e SUPERADMIN_USER="$(SUPERADMIN_USER)" -e SUPERADMIN_PASSWORD="$(SUPERADMIN_PASSWORD)" -e REALM="$(REALM)" python src/keycloak_admin_utils.py create-superadmin --username "$(SUPERADMIN_USER)" --password "$(SUPERADMIN_PASSWORD)" --realm "$(REALM)"

list-users:
	$(EXEC_SCRIPTS) python src/keycloak_admin_utils.py list-users

delete-test-users:
	$(EXEC_SCRIPTS) -e REALM="$(REALM)" python src/keycloak_admin_utils.py delete-test-users $(if $(filter 1,$(DRY_RUN)),--dry-run) --realm "$(REALM)"

# Comptes pour Locust (loadtest_user_1, loadtest_user_2, ...)
LOCUST_USER_COUNT ?= 100
KEYCLOAK_LOAD_PASSWORD ?= testpass

create-locust-users:
	$(EXEC_SCRIPTS) python src/keycloak_admin_utils.py create-loadtest-users --count $(LOCUST_USER_COUNT) --password "$(KEYCLOAK_LOAD_PASSWORD)" --realm "$(REALM)"

# Locust en mode headless (sans interface web). Les stats s'affichent dans le terminal uniquement (pas dans l'UI 8089).
# Ex. make locust-headless USERS=10 SPAWN_RATE=5 RUN_TIME=30s  ou  make locust-headless LOCUST_HEADLESS_RUN_TIME=2m
LOCUST_HEADLESS_USERS ?= 10
LOCUST_HEADLESS_SPAWN_RATE ?= 5
LOCUST_HEADLESS_RUN_TIME ?= 1m

locust-headless:
	$(COMPOSE) run --rm locust -f /mnt/locust/locustfile.py --headless -H http://keycloak:8080 \
	  --users $(or $(USERS),$(LOCUST_HEADLESS_USERS)) \
	  --spawn-rate $(or $(SPAWN_RATE),$(LOCUST_HEADLESS_SPAWN_RATE)) \
	  --run-time $(or $(RUN_TIME),$(LOCUST_HEADLESS_RUN_TIME))

# Déclencher un test via l'API du conteneur Locust (UI). Les stats s'affichent en direct dans http://localhost:8089
# Prérequis : docker compose up -d locust  puis ouvrir http://localhost:8089
# Ex. make locust-trigger USERS=10 SPAWN_RATE=5 RUN_TIME=30  (RUN_TIME en secondes, optionnel)
LOCUST_PORT ?= 8089
locust-trigger:
	@test -x locust/trigger_ui.sh || chmod +x locust/trigger_ui.sh
	LOCUST_HOST="http://localhost:$(LOCUST_PORT)" ./locust/trigger_ui.sh \
	  "$(or $(USERS),$(LOCUST_HEADLESS_USERS))" \
	  "$(or $(SPAWN_RATE),$(LOCUST_HEADLESS_SPAWN_RATE))" \
	  "$(RUN_TIME)"

# ── Nettoyage ─────────────────────────────────────────────────────────────────
clean:
	$(COMPOSE) down -v
