# Locust — tests de charge Keycloak (comptes distincts)

Locust est utilisé pour les tests de charge sur Keycloak avec **un compte différent par utilisateur virtuel** (password grant OIDC). Les comptes sont nommés `loadtest_user_1`, `loadtest_user_2`, … `loadtest_user_N` et doivent être créés dans Keycloak avant de lancer les tests.

**Documentation détaillée** : [locust/README.md](../locust/README.md) (variables d'environnement, UI, headless, Grafana).

---

## Commandes Make

| Commande | Description |
|----------|-------------|
| `make create-locust-users` | Créer les utilisateurs `loadtest_user_1` … `loadtest_user_N` dans le realm (défaut : 100, mot de passe `testpass`) |
| `make locust-headless` | Lancer un test Locust **sans interface** — les stats s'affichent dans le terminal uniquement |
| `make locust-trigger` | Déclencher un test dans **l'UI Locust** (stats en direct dans le navigateur). Prérequis : `make up` et ouvrir http://localhost:8089 |

### Variables utiles

- **create-locust-users** : `LOCUST_USER_COUNT=50`, `KEYCLOAK_LOAD_PASSWORD=...`, `REALM=master`
- **locust-headless** : `USERS=10`, `SPAWN_RATE=5`, `RUN_TIME=30s` (ou `RUN_TIME=2m`)
- **locust-trigger** : `USERS=10`, `SPAWN_RATE=5`, `RUN_TIME=30` (secondes, optionnel — arrêt auto après ce délai)
- **Port UI** : `LOCUST_PORT=8089` (défaut). Définissable dans `.env` (voir `env.dist`).

---

## Démarrage rapide

1. Démarrer la stack (dont le service Locust) :
   ```bash
   make up
   ```

2. Créer les comptes de test dans Keycloak (une fois, ou après un `make clean`) :
   ```bash
   make create-locust-users
   # Ou avec moins d'utilisateurs : make create-locust-users LOCUST_USER_COUNT=20
   ```

3. Lancer un test **avec interface** (recommandé pour voir les graphiques en direct) :
   - Ouvrir http://localhost:8089 dans le navigateur.
   - Puis en terminal :
     ```bash
     make locust-trigger USERS=10 SPAWN_RATE=5 RUN_TIME=30
     ```
   Le test démarre via l'API Locust et s'arrête automatiquement après 30 secondes.

4. Ou lancer un test **sans interface** (CI, scripts) :
   ```bash
   make locust-headless USERS=10 SPAWN_RATE=5 RUN_TIME=30s
   ```
   Les statistiques s'affichent uniquement dans le terminal.

---

## Comportement du scénario

- **Pendant le test** : chaque utilisateur virtuel enchaîne des **login** (password grant). Les sessions restent actives côté Keycloak, ce qui permet de voir les **comptes distincts connectés** en temps réel dans Grafana (panneaux « Comptes distincts connectés », « Sessions actives par client »).

- **À la fin du test** : lorsque le test s'arrête (bouton Stop ou `RUN_TIME`), chaque utilisateur virtuel appelle **`/logout`** pour chaque session qu'il a ouverte (`on_stop`). Les sessions se ferment côté Keycloak et la baisse est visible dans Grafana.

Les métriques Grafana (comptes distincts, sessions par client) sont fournies par le **keycloak-session-exporter** ; voir [session-exporter.md](session-exporter.md) et [grafana-dashboards.md](grafana-dashboards.md).

---

## Fichiers

- **locust/locustfile.py** : scénario Locust (password grant + logout en fin de test).
- **locust/trigger_ui.sh** : script pour déclencher le test via l'API Locust (utilisé par `make locust-trigger`).
- **docker-compose.yml** : service `locust`, port `LOCUST_PORT`, variables Keycloak pour le conteneur.

Variables d'environnement (Locust / Keycloak) : décrites dans `env.dist` (section Locust) et dans [locust/README.md](../locust/README.md).
