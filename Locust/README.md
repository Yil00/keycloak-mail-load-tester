# Locust — tests de charge Keycloak (comptes distincts)

Ce dossier contient un scénario [Locust](https://docs.locust.io/en/stable/index.html) pour charger Keycloak en utilisant **un compte différent par utilisateur virtuel**. → Doc projet : [docs/locust.md](../docs/locust.md).

Le scénario actuel utilise le **flux password grant** sur l'endpoint :

- `/realms/{realm}/protocol/openid-connect/token`

avec des comptes nommés :

- `loadtest_user_1`, `loadtest_user_2`, …, `loadtest_user_N`

## Variables d'environnement (Locust)

Les variables suivantes sont lues par `locustfile.py` :

- `KEYCLOAK_HOST` (défaut `keycloak`) : nom DNS / service Docker de Keycloak.
- `KEYCLOAK_PORT` (défaut `8080`) : port HTTP de Keycloak (dans le réseau Docker).
- `KEYCLOAK_REALM` (défaut `master`) : realm cible.
- `KEYCLOAK_CLIENT_ID` (défaut `admin-cli`) : client utilisé pour le password grant.
- `KEYCLOAK_LOAD_USER_PREFIX` (défaut `loadtest_user_`) : préfixe des logins de test.
- `KEYCLOAK_LOAD_PASSWORD` (défaut `testpass`) : mot de passe commun à tous les comptes.
- `KEYCLOAK_USER_COUNT` (défaut `100`) : nombre de comptes distincts disponibles (`loadtest_user_1`…`_N`).

Pour le port de l’UI Locust : `LOCUST_PORT` (défaut `8089`), utilisé par docker-compose et par `make locust-trigger` / `trigger_ui.sh`. Toutes ces variables peuvent être définies dans `.env` (voir `env.dist` à la racine du projet) ; docker-compose les injecte dans le conteneur Locust.

**Créer les comptes dans Keycloak avant de lancer Locust** (sinon tu auras 100 % d'échecs « Invalid user credentials ») :

```bash
make create-locust-users
```

Par défaut cela crée 100 utilisateurs `loadtest_user_1` … `loadtest_user_100` avec le mot de passe `testpass`. Tu peux changer le nombre : `make create-locust-users LOCUST_USER_COUNT=50` ou le mot de passe : `make create-locust-users KEYCLOAK_LOAD_PASSWORD=monmotdepasse`.

## Lancer Locust avec docker-compose

Un service `locust` a été ajouté dans `docker-compose.yml` (image officielle `locustio/locust`).

Depuis le dossier `Keycloak` :

```bash
docker compose up -d locust
```

Puis ouvrir l'interface web Locust sur :

- **En local** : `http://localhost:${LOCUST_PORT:-8089}`
- **Depuis le réseau (autre machine, même LAN)** : `http://<IP_DE_TA_MAC>:8089` (ex. `http://192.168.1.10:8089`). Le conteneur écoute déjà sur toutes les interfaces (`0.0.0.0`). Pense à autoriser le port 8089 dans le pare-feu si besoin.
- **Depuis internet** : exposer le port sur ta box ou utiliser un tunnel (ngrok, cloudflared, etc.) vers `localhost:8089`.

Dans l'UI Locust :

- Renseigne le **nombre d'utilisateurs** (par exemple 50 ou 100, en cohérence avec `KEYCLOAK_USER_COUNT`).
- Renseigne le **spawn rate** (taux de montée en charge).
- Laisse le host vide (il est déjà défini dans le code) ou `http://keycloak:8080`.

**Lier terminal et GUI** : tu peux aussi **déclencher le test depuis le terminal** tout en voyant les stats en direct dans l'UI. Ouvre d'abord http://localhost:8089 dans le navigateur, puis exécute :

```bash
make locust-trigger USERS=10 SPAWN_RATE=5 RUN_TIME=30
```

Le test est envoyé à l'API du conteneur Locust (celui qui sert l'UI), donc les graphiques et statistiques se mettent à jour en direct. `RUN_TIME` est optionnel (en secondes) : s'il est renseigné, le test s'arrête automatiquement après cette durée.

Chaque utilisateur virtuel utilisera un login différent dérivé de `KEYCLOAK_LOAD_USER_PREFIX` :

- user 1 → `loadtest_user_1`
- user 2 → `loadtest_user_2`
- etc. (modulo `KEYCLOAK_USER_COUNT`)

### Lancer Locust sans interface (en ligne de commande)

Pour lancer un test directement, sans ouvrir l’UI (idéal pour CI ou scripts) :

```bash
make locust-headless
```

**Important** : en mode headless, les stats s’affichent **dans le terminal uniquement**. Les graphiques de l’UI (http://localhost:8089) viennent d’un autre run (conteneur avec interface), pas du `make locust-headless`.

Par défaut : 10 users, spawn rate 5/s, durée 1 min. Tu peux surcharger (noms courts ou variables `LOCUST_HEADLESS_*`) :

```bash
make locust-headless USERS=10 SPAWN_RATE=5 RUN_TIME=30s
make locust-headless LOCUST_HEADLESS_USERS=20 LOCUST_HEADLESS_RUN_TIME=2m
```

Équivalent manuel avec Docker :

```bash
docker compose run --rm locust -f /mnt/locust/locustfile.py --headless -H http://keycloak:8080 --users 20 --spawn-rate 10 --run-time 2m
```

Tu peux ensuite adapter le scénario (`locustfile.py`) pour ajouter un flux OIDC complet (auth code) si tu veux simuler un parcours navigateur plus réaliste.

## Grafana : comptes distincts et sessions

Les panneaux Grafana **« Comptes distincts connectés »** et **« Sessions actives par client »** (et la durée par utilisateur) sont alimentés par le **keycloak-session-exporter**, qui interroge l’API Admin Keycloak toutes les 15 s (scrape Prometheus).

Pendant le test : **pas de logout** après chaque token, les sessions restent actives → les 10 comptes distincts s'affichent en temps réel dans Grafana. **À la fin du test** (arrêt Locust), chaque utilisateur virtuel appelle `/logout` une fois (`on_stop`) : les sessions se ferment en temps réel, visible côté Grafana. Vérifier que la cible `keycloak-session-exporter` est UP dans Prometheus (http://localhost:9090 → Status → Targets).

