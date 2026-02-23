# Utilitaires Admin Keycloak (create-superadmin, list-users, delete-test-users)

Le script **`src/keycloak_admin_utils.py`** et les cibles Make associées permettent de créer un superadmin, lister le nombre d’utilisateurs par realm, et supprimer **uniquement** les utilisateurs créés pour les tests de charge.

Variables d’environnement : `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_ADMIN_USER`, `KEYCLOAK_ADMIN_PASSWORD` (ou `.env`).

---

## 1. Créer un superadmin

Crée un utilisateur dans le realm (par défaut `master`) avec les rôles **realm-management** (manage-realm, manage-users, view-realm, view-users, manage-clients, view-clients, manage-events, view-events) pour qu’il puisse utiliser la console d’administration Keycloak.

```bash
make create-superadmin SUPERADMIN_USER=monadmin SUPERADMIN_PASSWORD=MonMotDePasseSecret
```

- **SUPERADMIN_PASSWORD** est obligatoire (sinon la cible affiche l’usage et s’arrête).
- **REALM** : optionnel, défaut `master`. Ex. `make create-superadmin ... REALM=monrealm`

En direct :

```bash
.venv/bin/python src/keycloak_admin_utils.py create-superadmin --username monadmin --password secret --realm master
```

Si l’utilisateur existe déjà (409), le script indique qu’il existe déjà et ne modifie pas le mot de passe ni les rôles.

---

## 2. Lister le nombre d’utilisateurs par realm

Affiche le nombre d’utilisateurs pour **chaque** realm du serveur Keycloak.

```bash
make list-users
```

Exemple de sortie :

```
Nombre d'utilisateurs par realm :
  master: 12
  monrealm: 0
```

En direct :

```bash
.venv/bin/python src/keycloak_admin_utils.py list-users
```

---

## 3. Supprimer uniquement les utilisateurs de test

Supprime **uniquement** les utilisateurs dont le **username** commence par **`loadtest_`** (test de charge) ou **`testuser_`** (test mails, test_keycloak.py). Aucun autre utilisateur n’est supprimé.

- **Utilisateurs protégés** (jamais supprimés) : `admin`, `keycloak`, `service-account-keycloak`, `master-realm`.
- **Préfixes** : `loadtest_*` et `testuser_*`. Tout autre utilisateur est ignoré (y compris les utilisateurs créés manuellement ou par d’autres scripts).

**Exécution réelle :**

```bash
make delete-test-users
```

**Simulation (affiche qui serait supprimé, sans supprimer) :**

```bash
make delete-test-users DRY_RUN=1
```

Optionnel : **REALM** (défaut `master`). Ex. `make delete-test-users REALM=master`

En direct :

```bash
.venv/bin/python src/keycloak_admin_utils.py delete-test-users --realm master
.venv/bin/python src/keycloak_admin_utils.py delete-test-users --dry-run --realm master
```

---

## Résumé des cibles Make

| Cible | Description |
|-------|-------------|
| `make create-superadmin SUPERADMIN_USER=... SUPERADMIN_PASSWORD=...` | Créer un utilisateur superadmin (rôles realm-management). |
| `make list-users` | Afficher le nombre d’utilisateurs par realm. |
| `make delete-test-users` | Supprimer les users de test (`loadtest_*` et `testuser_*`). |
| `make delete-test-users DRY_RUN=1` | Simulation : afficher les users qui seraient supprimés. |
