# Keycloak + Postgres + MailHog — commandes Make
# Usage : make [cible]

PYTHON  := .venv/bin/python
COMPOSE := docker compose

.PHONY: help up down restart ps logs logs-keycloak logs-mailhog install test test-nb test-rate test-batch clean

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
	@echo "  make clean           Arrêter les conteneurs et supprimer les volumes"
	@echo ""

# ── Docker Compose ───────────────────────────────────────────────────────────
up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart: down up

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
	$(PYTHON) test_keycloak.py --nb $(NB)

test-nb: test

test-rate:
	@test -d .venv || $(MAKE) install
	$(PYTHON) test_keycloak.py --nb $(NB) --strategy rate --rate $(RATE)

test-batch:
	@test -d .venv || $(MAKE) install
	$(PYTHON) test_keycloak.py --nb $(NB) --strategy batch-pause --send-batch-size $(SEND_BATCH_SIZE) --pause $(PAUSE)

# ── Nettoyage ─────────────────────────────────────────────────────────────────
clean:
	$(COMPOSE) down -v
