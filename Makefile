# Keycloak + Postgres + MailHog — commandes Make
# Usage : make [cible]

PYTHON  := .venv/bin/python
COMPOSE := docker compose

.PHONY: help up down restart ps logs logs-keycloak logs-mailhog keycloak-allow-http install test test-nb test-rate test-batch load-test load-test-ramp load-test-multi load-test-multi-ramp clean

help:
	@echo "Keycloak — cibles disponibles :"
	@echo ""
	@echo "  make up              Démarrer tous les services (Postgres, Keycloak, MailHog)"
	@echo "  make down            Arrêter et supprimer les conteneurs"
	@echo "  make restart         Redémarrer tous les services"
	@echo "  make ps              Afficher l’état des conteneurs"
	@echo ""
	@echo "  make logs            Suivre les logs de tous les services"
	@echo "  make logs-keycloak   Suivre les logs Keycloak uniquement"
	@echo "  make logs-mailhog    Suivre les logs MailHog uniquement"
	@echo ""
	@echo "  make install         Créer le venv et installer les dépendances (requests)"
	@echo "  make test            Lancer le test d’envoi (100 mails, débit max)"
	@echo "  make test-nb         Nombre personnalisé : make test-nb NB=500"
	@echo "  make test-rate       Débit constant : make test-rate RATE=100 NB=1000"
	@echo "  make test-batch      Lots + pause : make test-batch NB=5000 PAUSE=30"
	@echo "  make load-test       Test de charge (constant) : CONCURRENT=20 DURATION=60"
	@echo "  make load-test-ramp  Test de charge (ramp) : montée/descente progressive"
	@echo "  make load-test-multi Test multi-comptes : CREATE_USERS=50 CONCURRENT=20 DURATION=30"
	@echo "  make load-test-multi-ramp  Idem ramp : CREATE_USERS=50 RAMP_USERS=30 RAMP_UP=60 RAMP_HOLD=30 RAMP_DOWN=60"
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

# ── Test Python ──────────────────────────────────────────────────────────────
install:
	python3 -m venv .venv
	.venv/bin/pip install requests python-dotenv

# NB par défaut = 100
NB ?= 100
# Stratégie rate : mails/sec (ex. 100 = 360k/h)
RATE ?= 100
# Stratégie batch-pause : taille du lot et pause en secondes
SEND_BATCH_SIZE ?= 5000
PAUSE ?= 30

test:
	@test -d .venv || $(MAKE) install
	$(PYTHON) src/test_keycloak.py --nb $(NB)

test-nb: test

test-rate:
	@test -d .venv || $(MAKE) install
	$(PYTHON) src/test_keycloak.py --nb $(NB) --strategy rate --rate $(RATE)

test-batch:
	@test -d .venv || $(MAKE) install
	$(PYTHON) src/test_keycloak.py --nb $(NB) --strategy batch-pause --send-batch-size $(SEND_BATCH_SIZE) --pause $(PAUSE)

# Test de charge (connexions simultanées sur une durée)
CONCURRENT ?= 10
DURATION ?= 30
# Ramp : users, ramp-up (s), hold (s), ramp-down (s)
RAMP_USERS ?= 30
RAMP_UP ?= 60
RAMP_HOLD ?= 30
RAMP_DOWN ?= 60

load-test:
	@test -d .venv || $(MAKE) install
	$(PYTHON) src/keycloak_load_test.py --concurrent $(CONCURRENT) --duration $(DURATION)

load-test-ramp:
	@test -d .venv || $(MAKE) install
	$(PYTHON) src/keycloak_load_test.py --mode ramp --users $(RAMP_USERS) --ramp-up $(RAMP_UP) --hold $(RAMP_HOLD) --ramp-down $(RAMP_DOWN)

# Test de charge multi-comptes (simulation proche production)
CREATE_USERS ?= 50
MULTI_USER_PASSWORD ?= testpass

load-test-multi:
	@test -d .venv || $(MAKE) install
	$(PYTHON) src/keycloak_load_test_multi_user.py --create-users $(CREATE_USERS) --user-password $(MULTI_USER_PASSWORD) --concurrent $(CONCURRENT) --duration $(DURATION)

load-test-multi-ramp:
	@test -d .venv || $(MAKE) install
	$(PYTHON) src/keycloak_load_test_multi_user.py --create-users $(CREATE_USERS) --user-password $(MULTI_USER_PASSWORD) --mode ramp --users $(RAMP_USERS) --ramp-up $(RAMP_UP) --hold $(RAMP_HOLD) --ramp-down $(RAMP_DOWN)

# ── Nettoyage ─────────────────────────────────────────────────────────────────
clean:
	$(COMPOSE) down -v
