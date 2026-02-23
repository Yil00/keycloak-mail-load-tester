# keycloak-mail-load-tester

# Keycloak + Postgres + MailHog + Grafana + Prometheus 

Setup Keycloak avec Postgres et MailHog pour tester l’envoi de mails en masse.

---

→ Notes de release : [docs/Release.md](docs/Release.md)

**Documentation monitoring** : [docs/grafana-dashboards.md](docs/grafana-dashboards.md) (dashboards, graphiques, légendes) · [docs/prometheus.md](docs/prometheus.md) (Prometheus, config, tutoriel PromQL). **Tests de charge Locust** (comptes distincts, UI + headless) : [docs/locust.md](docs/locust.md).

---

## Configuration (.env)

Les variables (ports, mots de passe, URL Keycloak) sont lues depuis **`.env`** par `docker compose` et par les scripts dans `src/`. Les scripts s’exécutent dans un conteneur Docker qui monte le projet et lit le `.env` ; l’URL Keycloak est alors `http://keycloak:8080` (conteneur keycloak-session-exporter, même réseau que Keycloak).

- **`env.dist`** : modèle avec toutes les variables. Copier vers `.env` et adapter :  
  `cp env.dist .env`
- **`.env`** : valeurs réelles (à ne pas committer si elles contiennent des secrets). Déjà fourni avec des valeurs par défaut pour le dev local.

Variables principales : `KEYCLOAK_URL`, `KEYCLOAK_ADMIN_USER`, `KEYCLOAK_ADMIN_PASSWORD`, `POSTGRES_*`, `KEYCLOAK_PORT`, `KEYCLOAK_MANAGEMENT_PORT`, `POSTGRES_PORT`, `MAILHOG_*`, `PROMETHEUS_PORT`, `GRAFANA_PORT`, `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`. Optionnel pour le script : `NB_USERS`, `MAX_WORKERS`, `BATCH_SIZE`.

---

## Commandes Make

| Commande | Description |
|----------|-------------|
| `make help` | Afficher la liste des cibles |
| `make up` | Démarrer tous les services (Postgres, Keycloak, MailHog, Prometheus, Grafana, Locust) |
| `make down` | Arrêter les conteneurs |
| `make restart` | Redémarrer tous les services |
| `make ps` | Afficher l’état des conteneurs |
| `make logs` | Suivre les logs de tous les services |
| `make logs-keycloak` | Suivre les logs Keycloak uniquement |
| `make logs-mailhog` | Suivre les logs MailHog uniquement |
| `make install` | Construire l’image Docker des scripts exécutés dans keycloak-session-exporter, make up requis |
| `make test` | Lancer le test d’envoi (100 mails, débit max) |
| `make test-nb NB=500` | Lancer le test avec un nombre personnalisé |
| `make test-rate RATE=100 NB=1000` | Test avec débit constant (ex. 100 mails/s) |
| `make test-batch NB=5000 PAUSE=30` | Test par lots + pause (ex. 5k mails puis 30 s) |
| `make load-test CONCURRENT=20 DURATION=60` | Test de charge (mode constant, un compte) |
| `make load-test-ramp` | Test de charge (ramp, un compte) |
| `make load-test-multi` | Test de charge multi-comptes (création users puis test) |
| `make load-test-multi-ramp` | Idem en mode ramp |
| `make create-locust-users` | Créer les comptes loadtest_user_1..N pour Locust (défaut 100) |
| `make locust-headless USERS=10 SPAWN_RATE=5 RUN_TIME=30s` | Test Locust sans UI (stats dans le terminal) |
| `make locust-trigger USERS=10 SPAWN_RATE=5 RUN_TIME=30` | Déclencher le test dans l'UI Locust (http://localhost:8089) |
| `make create-superadmin SUPERADMIN_USER=... SUPERADMIN_PASSWORD=...` | Créer un utilisateur superadmin |
| `make list-users` | Nombre d'utilisateurs par realm |
| `make delete-test-users` | Supprimer les users de test (loadtest_* et testuser_*) uniquement |
| `make delete-test-users DRY_RUN=1` | Idem en simulation (sans supprimer) |
| `make keycloak-allow-http` | Autoriser HTTP (realm master) si « HTTPS required » |
| `make clean` | Arrêter les conteneurs et supprimer les volumes |

---

## Utilisation

### 1. Démarrer l’environnement

Keycloak est construit à partir de `Dockerfile.keycloak` (feature **user-event-metrics** pour les panneaux Grafana « Logins (événements) »). **La première fois**, construire l’image puis démarrer :

```bash
docker compose build keycloak
make up
# Attendre ~30–40 s (ou 1–2 min sur Mac ARM) que Keycloak démarre
make logs-keycloak   # surveiller le démarrage
# Pour make test / load-test : si la stack est déjà up, pas d'attente ; sinon le script attend Keycloak (max 4 min).
```

Ou en une commande : `docker compose up -d --build`.

**Si la page Keycloak affiche « HTTPS required »** : exécuter une fois (après que Keycloak soit démarré) :
```bash
make keycloak-allow-http
```
Cela met le realm master en « Require SSL = None » en base puis redémarre Keycloak. Ensuite recharger http://localhost:8080.

### 2. Configurer le SMTP dans Keycloak

Aller sur **http://localhost:8080** → **Realm Settings** → **Email** :

| Champ | Valeur |
|-------|--------|
| From | `keycloak@test.local` |
| Host | `mailhog` |
| Port | `1025` |
| SSL / StartTLS / Auth | Désactivés |

Cliquer **Save** puis **Test connection** → un mail doit apparaître sur **http://localhost:8025**.

### 3. Lancer le test d’envoi de mails

```bash
make test
```

Ou avec un nombre personnalisé :

```bash
make test-nb NB=500
```

**Stratégies d’envoi** (`--strategy`) :

| Stratégie | Description | Exemple |
|-----------|-------------|---------|
| `full` (défaut) | Débit max, sans pause | `make test` |
| `batch-pause` | Lots de N mails puis pause de X s | 5k + 30 s → `--strategy batch-pause --send-batch-size 5000 --pause 30` |
| `rate` | Débit constant (mails/s), ex. 100/s = 360k/h, 3M ≈ 8h20 | `--strategy rate --rate 100` |

**Options du script** (Python du venv) :

- `--nb N` — nombre de mails (défaut : 100 avec `make test`)
- `--strategy full \| batch-pause \| rate` — stratégie d’envoi
- `--pause SEC` — avec `batch-pause` : pause en secondes entre les lots
- `--send-batch-size N` — avec `batch-pause` : taille d’un lot (défaut 5000)
- `--rate N` — avec `rate` : débit cible en mails/s
- `--skip-cleanup` — ne pas supprimer les utilisateurs après le test
- `--skip-create` — ne pas recréer les utilisateurs (réutiliser ceux existants)

Exemples :

```bash
# Débit max, 500 mails, garder les users
.venv/bin/python src/test_keycloak.py --nb 500 --skip-cleanup

# Lots de 5k mails puis 30 s de pause (20k mails au total)
.venv/bin/python src/test_keycloak.py --nb 20000 --strategy batch-pause --send-batch-size 5000 --pause 30

# Débit constant 100 mails/s (durée estimée affichée)
.venv/bin/python src/test_keycloak.py --nb 10000 --strategy rate --rate 100
```

### 4. Test de charge (connexions simultanées)

Le script **`src/keycloak_load_test.py`** mesure la charge sur le endpoint d’authentification (obtention de token) : N connexions simultanées pendant D secondes. **Locust** propose une autre approche avec **un compte distinct par utilisateur virtuel** (password grant + logout en fin de test), visible en temps réel dans Grafana ; voir [docs/locust.md](docs/locust.md) et `locust/README.md`.

```bash
make load-test
make load-test CONCURRENT=20 DURATION=60
```

→ **Explication (tokens vs comptes réels)** : [docs/load-test-tokens.md](docs/load-test-tokens.md).

**Mode ramp** (montée/descente progressive) : `make load-test-ramp` ou `make load-test-ramp RAMP_USERS=50 RAMP_UP=120 RAMP_HOLD=60 RAMP_DOWN=90`.

**Multi-comptes** (simulation proche production, chaque thread = comptes différents) : le script **`src/keycloak_load_test_multi_user.py`** crée N users dans le realm, lance le test, puis les supprime. Commandes : `make load-test-multi` (défaut : 50 users, 10 threads, 30 s) ou `make load-test-multi-ramp`. Variables : `CREATE_USERS`, `MULTI_USER_PASSWORD`, `CONCURRENT`, `DURATION`. Option fichier : `--accounts-file path` (une ligne `username:password` par compte).

En direct :

```bash
.venv/bin/python src/keycloak_load_test.py --concurrent 20 --duration 60
.venv/bin/python src/keycloak_load_test.py --mode ramp --users 30 --ramp-up 60 --hold 30 --ramp-down 60
.venv/bin/python src/keycloak_load_test_multi_user.py --create-users 50 --concurrent 20 --duration 60
```

Options : `--concurrent`, `--duration` (mode constant) ; `--mode ramp`, `--users`, `--ramp-up`, `--hold`, `--ramp-down` (mode ramp) ; `--url`, `--realm`, `--user`, `--password`, `--timeout`, `--warmup`. Les variables `KEYCLOAK_*` du `.env` sont utilisées par défaut.

**En cas de HTTP 403 (tous les logins refusés)** : le test utilise le client `admin-cli` et le grant « password ». Dans Keycloak :
1. **Realm master** → **Clients** → **admin-cli** → onglet **Paramètres** (Settings) : activer **« Direct access grants »** (Accès direct aux subventions / Direct access grants enabled), puis **Enregistrer**.
2. **Realm master** → **Sécurité** (ou **Security defenses**) → **Protection contre la force brute** : en dev/test, tu peux désactiver temporairement ou augmenter le seuil, sinon Keycloak peut bloquer après beaucoup de requêtes.

→ **Détail pas à pas** : [docs/admin-keycloak.md](docs/admin-keycloak.md). **Superadmin, nombre d’users par realm, suppression des users de test** : [docs/admin-utils.md](docs/admin-utils.md) (`make create-superadmin`, `make list-users`, `make delete-test-users`).

**Résultats affichés** : requêtes totales, taux de succès, débit (req/s), latence (min, avg, p50, p95, p99), répartition des erreurs.

**Interprétation des résultats**

| Métrique | Signification |
|----------|----------------|
| **Requêtes totales** | Nombre de logins (obtentions de token) effectués pendant le test. |
| **Succès (%)** | Part des requêtes ayant retourné un token (HTTP 200). 100 % = Keycloak tient la charge. |
| **Débit (req/s)** | Requêtes par seconde — capacité de traitement du endpoint token. Plus c’est élevé, plus Keycloak absorbe de connexions. |
| **Latence min / avg** | Temps de réponse minimum et moyen. Une moyenne basse (< 0,1 s en local) indique un bon temps de réponse. |
| **p50 / p95 / p99** | 50 %, 95 % et 99 % des requêtes ont répondu en moins que cette valeur. p99 élevée = quelques requêtes lentes sous charge. |
| **Erreurs** | Si présentes : type (timeout, HTTP 401/5xx, etc.) pour diagnostiquer saturation ou rejets. |

**Exemple de sortie** (10 threads, 30 s, Keycloak local) :

```
  📊 Résultats
----------------------------------------
     Requêtes totales : 10784
     Succès           : 10784 (100.0%)
     Durée réelle     : 30.0 s
     Débit (req/s)    : 359.3
     Latence (s)      : min=0.022  avg=0.028  p50=0.027  p95=0.035  p99=0.041
```

→ **En bref** : ~360 logins/s soutenus, 100 % de succès, latence moyenne 28 ms. Keycloak tient bien la charge pour cette configuration ; en préprod, comparer ces ordres de grandeur après avoir augmenté `CONCURRENT` et `DURATION` pour estimer la marge.

### 5. Surveiller et monitoring (Grafana)

Keycloak expose des **métriques** (débit, latence, requêtes actives) sur le port **9000**. **Prometheus** les scrape et **Grafana** les affiche en temps réel.

| Outil | URL ou commande |
|-------|------------------|
| **Grafana** (graphiques) | http://localhost:3000 (admin / admin) |
| **Prometheus** | http://localhost:9090 |
| **MailHog** (mails) | http://localhost:8025 |
| **Keycloak** | http://localhost:8080 (admin / admin) |
| **Logs Keycloak** | `make logs-keycloak` |
| **Nombre d’utilisateurs en BDD** | `docker exec -it keycloak_postgres psql -U keycloak -c "SELECT count(*) FROM user_entity;"` |

**Dashboards Grafana** (menu **Keycloak**) : **Keycloak — Vue d'ensemble** (débit req/s, latence, 2xx/4xx/5xx, comptes distincts, sessions par client, logins) ; **Keycloak — Sessions et utilisateurs** (comptes distincts, sessions par client, durée de session par user, tableau des dernières connexions id/username/email, évolution des comptes distincts). Lancer `make load-test` ou `make load-test-multi-ramp` tout en regardant Grafana pour voir la charge en direct. Variables optionnelles : `GRAFANA_PORT`, `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`, `PROMETHEUS_PORT`, `KEYCLOAK_MANAGEMENT_PORT`.

Les panneaux **Logins (événements)** utilisent l’image Keycloak construite avec `Dockerfile.keycloak`. Si tout reste à 0, lancer `docker compose build keycloak` puis redémarrer. Voir [docs/grafana-metrics.md](docs/grafana-metrics.md) (activation de la feature `user-event-metrics`, vérification des métriques). Le **nombre de comptes distincts connectés** et les **sessions actives par client** sont fournis par le service **keycloak-session-exporter** (script `src/keycloak_session_exporter.py`), qui interroge l’API Admin Keycloak et expose des métriques Prometheus ; voir [docs/session-exporter.md](docs/session-exporter.md). Liste des dashboards et légendes : [docs/grafana-dashboards.md](docs/grafana-dashboards.md). Prometheus (config, tutoriel) : [docs/prometheus.md](docs/prometheus.md).

Conseil : commencer avec `make test` (100 mails) pour valider la config, puis par exemple `make test-nb NB=10000`.

---

## Utilisation en préprod (Keycloak + SMTP Scaleway)

Le même script peut servir en préprod : **création d’utilisateurs → envoi des mails de vérification (via le SMTP configuré, ex. Scaleway) → suppression des utilisateurs**. Aucune donnée de test ne reste dans le realm.

1. **Configurer l’email dans Keycloak** (Realm Settings → Email) avec les paramètres SMTP Scaleway (host, port, SSL/TLS, identifiants).

2. **Définir les variables d’environnement** (évite de mettre le mot de passe en clair dans l’historique) :

   ```bash
   export KEYCLOAK_URL=https://auth-preprod.votredomaine.com
   export KEYCLOAK_REALM=master
   export KEYCLOAK_ADMIN_USER=admin
   export KEYCLOAK_ADMIN_PASSWORD=votre_mot_de_passe_admin
   ```

3. **Lancer le test** (par ex. 100 mails) :

   ```bash
   .venv/bin/python src/test_keycloak.py --nb 100
   ```

   Ou en surchargeant uniquement l’URL et le realm :

   ```bash
   .venv/bin/python src/test_keycloak.py --url https://auth-preprod.votredomaine.com --realm master --nb 100
   ```
   Le mot de passe reste lu depuis `KEYCLOAK_ADMIN_PASSWORD`.

4. **Options utiles en préprod**  
   - `--skip-cleanup` : ne pas supprimer les utilisateurs après le test (pour inspecter les mails ou les users dans l’admin).  
   - Tester d’abord avec `--nb 10` pour valider la connexion SMTP Scaleway avant un volume plus important.  
   - **Stratégie par lots ou débit constant** : pour limiter la charge SMTP, utiliser par ex.  
     `--strategy batch-pause --send-batch-size 5000 --pause 30` ou  
     `--strategy rate --rate 100` (100 mails/s = 360k/h).
