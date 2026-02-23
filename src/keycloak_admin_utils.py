#!/usr/bin/env python3
"""
Utilitaires Admin Keycloak : créer un superadmin, lister le nombre d'utilisateurs par realm,
supprimer uniquement les utilisateurs créés pour les tests (préfixes loadtest_ et testuser_).

Usage :
  python keycloak_admin_utils.py create-superadmin --username superadmin --password secret
  python keycloak_admin_utils.py list-users
  python keycloak_admin_utils.py delete-test-users [--dry-run] [--realm master]

Variables d'environnement : KEYCLOAK_URL, KEYCLOAK_REALM, KEYCLOAK_ADMIN_USER, KEYCLOAK_ADMIN_PASSWORD.
"""

import argparse
import os
import sys
from typing import List, Optional, Tuple

try:
    from dotenv import load_dotenv
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_root, ".env"))
    load_dotenv()
except ImportError:
    pass

import requests

_DEFAULT_PORT = os.environ.get("KEYCLOAK_PORT", "8080")
DEFAULT_URL = os.environ.get("KEYCLOAK_URL", f"http://localhost:{_DEFAULT_PORT}").rstrip("/")
DEFAULT_REALM = os.environ.get("KEYCLOAK_REALM", "master")
DEFAULT_ADMIN = os.environ.get("KEYCLOAK_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASS = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")

# Préfixes des utilisateurs créés par les scripts de test (ne jamais supprimer les autres)
# loadtest_ = keycloak_load_test_multi_user.py ; testuser_ = test_keycloak.py (mails)
TEST_USERNAME_PREFIXES = ("loadtest_", "testuser_")

# Utilisateurs à ne jamais supprimer (bootstrap admin, etc.)
PROTECTED_USERNAMES = frozenset({"admin", "keycloak", "service-account-keycloak", "master-realm"})


def get_admin_token(base_url: str, admin_user: str, admin_pass: str) -> str:
    r = requests.post(
        f"{base_url}/realms/master/protocol/openid-connect/token",
        data={
            "client_id": "admin-cli",
            "username": admin_user,
            "password": admin_pass,
            "grant_type": "password",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}


def get_realms(base_url: str, token: str) -> List[dict]:
    r = requests.get(
        f"{base_url}/admin/realms",
        headers=auth_headers(token),
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def count_users_in_realm(base_url: str, realm: str, token: str) -> int:
    total = 0
    first = 0
    page_size = 500
    while True:
        r = requests.get(
            f"{base_url}/admin/realms/{realm}/users",
            params={"first": first, "max": page_size},
            headers=auth_headers(token),
            timeout=15,
        )
        r.raise_for_status()
        users = r.json()
        total += len(users)
        if len(users) < page_size:
            break
        first += page_size
    return total


def list_user_count_per_realm(base_url: str, token: str) -> List[Tuple[str, int]]:
    realms = get_realms(base_url, token)
    result = []
    for realm_info in realms:
        realm = realm_info.get("realm") or realm_info.get("id")
        if not realm:
            continue
        try:
            n = count_users_in_realm(base_url, realm, token)
            result.append((realm, n))
        except Exception as e:
            result.append((realm, -1))
            print(f"  ⚠ {realm}: erreur ({e})", file=sys.stderr)
    return result


def get_realm_management_client_id(base_url: str, realm: str, token: str) -> Optional[str]:
    r = requests.get(
        f"{base_url}/admin/realms/{realm}/clients",
        params={"clientId": "realm-management"},
        headers=auth_headers(token),
        timeout=15,
    )
    r.raise_for_status()
    clients = r.json()
    for c in clients:
        if c.get("clientId") == "realm-management":
            return c.get("id")
    return None


def get_client_roles(base_url: str, realm: str, token: str, client_uuid: str) -> List[dict]:
    r = requests.get(
        f"{base_url}/admin/realms/{realm}/clients/{client_uuid}/roles",
        headers=auth_headers(token),
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def create_superadmin(
    base_url: str,
    realm: str,
    token: str,
    username: str,
    password: str,
) -> bool:
    """Crée un utilisateur avec les rôles realm-management (manage-realm, manage-users, etc.) pour admin console."""
    # Créer l'utilisateur
    r = requests.post(
        f"{base_url}/admin/realms/{realm}/users",
        json={
            "username": username,
            "enabled": True,
            "emailVerified": True,
        },
        headers=auth_headers(token),
        timeout=10,
    )
    if r.status_code == 409:
        print(f"L'utilisateur '{username}' existe déjà.", file=sys.stderr)
        return False
    if r.status_code != 201:
        print(f"Échec création utilisateur: {r.status_code} {r.text[:200]}", file=sys.stderr)
        return False

    user_id = r.headers.get("Location", "").rstrip("/").split("/")[-1]
    # Récupérer l'id si Location absente
    if not user_id:
        r2 = requests.get(
            f"{base_url}/admin/realms/{realm}/users",
            params={"username": username},
            headers=auth_headers(token),
            timeout=10,
        )
        r2.raise_for_status()
        users = r2.json()
        if not users:
            return False
        user_id = users[0].get("id")

    # Mot de passe
    rp = requests.put(
        f"{base_url}/admin/realms/{realm}/users/{user_id}/reset-password",
        json={"type": "password", "temporary": False, "value": password},
        headers=auth_headers(token),
        timeout=10,
    )
    if rp.status_code not in (200, 204):
        print(f"Échec définition mot de passe: {rp.status_code}", file=sys.stderr)
        return False

    # Rôles realm-management (admin console)
    client_uuid = get_realm_management_client_id(base_url, realm, token)
    if not client_uuid:
        print("Client realm-management introuvable.", file=sys.stderr)
        return False
    roles = get_client_roles(base_url, realm, token, client_uuid)
    # Rôles utiles pour un superadmin (gestion complète du realm)
    role_names = {"manage-realm", "manage-users", "view-realm", "view-users", "manage-clients", "view-clients", "manage-events", "view-events"}
    to_assign = [{"id": r["id"], "name": r["name"], "containerId": r.get("containerId"), "clientRole": True} for r in roles if r.get("name") in role_names]
    if to_assign:
        ra = requests.post(
            f"{base_url}/admin/realms/{realm}/users/{user_id}/role-mappings/clients/{client_uuid}",
            json=to_assign,
            headers=auth_headers(token),
            timeout=10,
        )
        if ra.status_code not in (200, 204):
            print(f"Assignation rôles: {ra.status_code} {ra.text[:150]}", file=sys.stderr)
    print(f"Superadmin '{username}' créé dans le realm '{realm}' (rôles realm-management assignés).")
    return True


def get_users_in_realm(base_url: str, realm: str, token: str) -> List[dict]:
    out = []
    first = 0
    page_size = 500
    while True:
        r = requests.get(
            f"{base_url}/admin/realms/{realm}/users",
            params={"first": first, "max": page_size},
            headers=auth_headers(token),
            timeout=15,
        )
        r.raise_for_status()
        users = r.json()
        out.extend(users)
        if len(users) < page_size:
            break
        first += page_size
    return out


def delete_test_users(
    base_url: str,
    realm: str,
    token: str,
    dry_run: bool = True,
) -> Tuple[int, int]:
    """
    Supprime uniquement les utilisateurs dont le username commence par TEST_USERNAME_PREFIX.
    Ne touche jamais aux utilisateurs protégés (admin, etc.).
    Retourne (nombre supprimés, nombre ignorés/protégés).
    """
    users = get_users_in_realm(base_url, realm, token)
    deleted = 0
    skipped = 0
    for u in users:
        username = (u.get("username") or "").strip()
        if not username:
            skipped += 1
            continue
        if username in PROTECTED_USERNAMES:
            skipped += 1
            continue
        if not any(username.startswith(p) for p in TEST_USERNAME_PREFIXES):
            skipped += 1
            continue
        user_id = u.get("id")
        if not user_id:
            continue
        if dry_run:
            print(f"  [dry-run] serait supprimé : {username} ({user_id})")
            deleted += 1
        else:
            try:
                rd = requests.delete(
                    f"{base_url}/admin/realms/{realm}/users/{user_id}",
                    headers=auth_headers(token),
                    timeout=10,
                )
                if rd.status_code in (200, 204):
                    print(f"  Supprimé : {username}")
                    deleted += 1
                else:
                    print(f"  ⚠ Échec suppression {username}: {rd.status_code}", file=sys.stderr)
                    skipped += 1
            except Exception as e:
                print(f"  ⚠ Erreur suppression {username}: {e}", file=sys.stderr)
                skipped += 1
    return deleted, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Utilitaires Admin Keycloak (superadmin, list-users, delete-test-users)")
    sub = parser.add_subparsers(dest="command", required=True)

    # create-superadmin
    p_create = sub.add_parser("create-superadmin", help="Créer un utilisateur superadmin (rôles realm-management)")
    p_create.add_argument("--username", required=True, help="Nom d'utilisateur")
    p_create.add_argument("--password", required=True, help="Mot de passe")
    p_create.add_argument("--realm", default=DEFAULT_REALM, help="Realm (défaut: master)")
    p_create.add_argument("--url", default=DEFAULT_URL, help="URL Keycloak")

    # list-users
    p_list = sub.add_parser("list-users", help="Afficher le nombre d'utilisateurs par realm")
    p_list.add_argument("--url", default=DEFAULT_URL, help="URL Keycloak")

    # delete-test-users
    p_del = sub.add_parser("delete-test-users", help="Supprimer les utilisateurs de test (loadtest_* et testuser_*)")
    p_del.add_argument("--dry-run", action="store_true", help="Afficher les utilisateurs qui seraient supprimés sans supprimer")
    p_del.add_argument("--realm", default=DEFAULT_REALM, help="Realm à traiter (défaut: master)")
    p_del.add_argument("--url", default=DEFAULT_URL, help="URL Keycloak")

    args = parser.parse_args()
    base_url = getattr(args, "url", DEFAULT_URL).rstrip("/")
    admin_user = os.environ.get("KEYCLOAK_ADMIN_USER", DEFAULT_ADMIN)
    admin_pass = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", DEFAULT_ADMIN_PASS)

    try:
        token = get_admin_token(base_url, admin_user, admin_pass)
    except Exception as e:
        print(f"Erreur authentification: {e}", file=sys.stderr)
        return 1

    if args.command == "create-superadmin":
        ok = create_superadmin(base_url, getattr(args, "realm", DEFAULT_REALM), token, args.username, args.password)
        return 0 if ok else 1

    if args.command == "list-users":
        counts = list_user_count_per_realm(base_url, token)
        print("Nombre d'utilisateurs par realm :")
        for realm, n in sorted(counts, key=lambda x: x[0]):
            print(f"  {realm}: {n}" if n >= 0 else f"  {realm}: erreur")
        return 0

    if args.command == "delete-test-users":
        realm = getattr(args, "realm", DEFAULT_REALM)
        dry_run = getattr(args, "dry_run", False)
        if dry_run:
            print(f"Mode dry-run (realm={realm}) — aucun utilisateur ne sera supprimé :")
        else:
            print(f"Suppression des utilisateurs de test (username commençant par {list(TEST_USERNAME_PREFIXES)}) dans le realm '{realm}' :")
        deleted, skipped = delete_test_users(base_url, realm, token, dry_run=dry_run)
        print(f"Résultat : {deleted} utilisateur(s) {'à supprimer' if dry_run else 'supprimé(s)'}, {skipped} ignoré(s)/protégé(s).")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
