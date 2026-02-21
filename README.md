# keycloak-mail-load-tester

# Keycloak + Postgres + MailHog

Setup Keycloak avec Postgres et MailHog pour tester l’envoi de mails en masse.

---

## Configuration (.env)

Les variables (ports, mots de passe, URL Keycloak) sont lues depuis **`.env`** par `docker compose` et par `test_keycloak.py` (si `python-dotenv` est installé).

- **`env.dist`** : modèle avec toutes les variables. Copier vers `.env` et adapter :  
  `cp env.dist .env`
- **`.env`** : valeurs réelles (à ne pas committer si elles contiennent des secrets). Déjà fourni avec des valeurs par défaut pour le dev local.

Variables principales : `KEYCLOAK_URL`, `KEYCLOAK_ADMIN_USER`, `KEYCLOAK_ADMIN_PASSWORD`, `POSTGRES_*`, `KEYCLOAK_PORT`, `POSTGRES_PORT`, `MAILHOG_*`. Optionnel pour le script : `NB_USERS`, `MAX_WORKERS`, `BATCH_SIZE`.

---

## Commandes Make

| Commande | Description |
|----------|-------------|
| `make help` | Afficher la liste des cibles |
| `make up` | Démarrer tous les services (Postgres, Keycloak, MailHog) |
| `make down` | Arrêter les conteneurs |
| `make restart` | Redémarrer tous les services |
| `make ps` | Afficher l’état des conteneurs |
| `make logs` | Suivre les logs de tous les services |
| `make logs-keycloak` | Suivre les logs Keycloak uniquement |
| `make logs-mailhog` | Suivre les logs MailHog uniquement |
| `make install` | Créer le venv et installer `requests` + `python-dotenv` |
| `make test` | Lancer le test d’envoi (100 mails, débit max) |
| `make test-nb NB=500` | Lancer le test avec un nombre personnalisé |
| `make test-rate RATE=100 NB=1000` | Test avec débit constant (ex. 100 mails/s) |
| `make test-batch NB=5000 PAUSE=30` | Test par lots + pause (ex. 5k mails puis 30 s) |
| `make clean` | Arrêter les conteneurs et supprimer les volumes |

---

## Utilisation

### 1. Démarrer l’environnement

```bash
make up
# Attendre ~30–40 s que Keycloak démarre
make logs-keycloak   # surveiller le démarrage
```

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
.venv/bin/python test_keycloak.py --nb 500 --skip-cleanup

# Lots de 5k mails puis 30 s de pause (20k mails au total)
.venv/bin/python test_keycloak.py --nb 20000 --strategy batch-pause --send-batch-size 5000 --pause 30

# Débit constant 100 mails/s (durée estimée affichée)
.venv/bin/python test_keycloak.py --nb 10000 --strategy rate --rate 100
```

### 4. Surveiller

| Outil | URL ou commande |
|-------|------------------|
| **MailHog** (mails) | http://localhost:8025 |
| **Keycloak** | http://localhost:8080 (admin / admin) |
| **Logs Keycloak** | `make logs-keycloak` |
| **Nombre d’utilisateurs en BDD** | `docker exec -it keycloak_postgres psql -U keycloak -c "SELECT count(*) FROM user_entity;"` |

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
   .venv/bin/python test_keycloak.py --nb 100
   ```

   Ou en surchargeant uniquement l’URL et le realm :

   ```bash
   .venv/bin/python test_keycloak.py --url https://auth-preprod.votredomaine.com --realm master --nb 100
   ```
   Le mot de passe reste lu depuis `KEYCLOAK_ADMIN_PASSWORD`.

4. **Options utiles en préprod**  
   - `--skip-cleanup` : ne pas supprimer les utilisateurs après le test (pour inspecter les mails ou les users dans l’admin).  
   - Tester d’abord avec `--nb 10` pour valider la connexion SMTP Scaleway avant un volume plus important.  
   - **Stratégie par lots ou débit constant** : pour limiter la charge SMTP, utiliser par ex.  
     `--strategy batch-pause --send-batch-size 5000 --pause 30` ou  
     `--strategy rate --rate 100` (100 mails/s = 360k/h).
