#!/usr/bin/env python3
"""
Test de charge Keycloak avec plusieurs comptes utilisateurs (simulation proche production).

Chaque thread utilise un ou plusieurs comptes différents : on sollicite les lookups user,
la base et le cache de façon plus réaliste qu'avec un seul compte (token répété).

Deux sources de comptes :
  1. Création automatique : N users créés dans le realm avec un mot de passe commun,
     puis test de charge, puis suppression (sauf --no-cleanup).
  2. Fichier externe : --accounts-file path avec une ligne "username:password" par compte.

Modes : constant (M threads × D s) ou ramp (montée/descente progressive), comme keycloak_load_test.py.

Usage :
  python keycloak_load_test_multi_user.py --create-users 50 --concurrent 20 --duration 60
  python keycloak_load_test_multi_user.py --create-users 30 --mode ramp --ramp-up 60 --hold 30 --ramp-down 60
  python keycloak_load_test_multi_user.py --accounts-file users.txt --concurrent 10 --duration 30

Variables d'environnement : KEYCLOAK_URL, KEYCLOAK_REALM, KEYCLOAK_ADMIN_USER, KEYCLOAK_ADMIN_PASSWORD.
Optionnel : LOAD_TEST_USER_PASSWORD (mot de passe des users créés, défaut "testpass").
"""

import argparse
import os
import statistics
import sys
import threading
import time
from typing import List, Optional, Tuple

import requests

try:
    from dotenv import load_dotenv
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_root, ".env"))
    load_dotenv()
except ImportError:
    pass

_DEFAULT_PORT = os.environ.get("KEYCLOAK_PORT", "8080")
_DEFAULT_URL = os.environ.get("KEYCLOAK_URL", f"http://localhost:{_DEFAULT_PORT}").rstrip("/")
_DEFAULT_REALM = os.environ.get("KEYCLOAK_REALM", "master")
_DEFAULT_ADMIN = os.environ.get("KEYCLOAK_ADMIN_USER", "admin")
_DEFAULT_ADMIN_PASS = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")
_DEFAULT_USER_PASSWORD = os.environ.get("LOAD_TEST_USER_PASSWORD", "testpass")


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
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def create_user(
    base_url: str,
    realm: str,
    token: str,
    username: str,
    email: str,
) -> Optional[str]:
    r = requests.post(
        f"{base_url}/admin/realms/{realm}/users",
        json={
            "username": username,
            "email": email,
            "enabled": True,
            "emailVerified": False,
        },
        headers=auth_headers(token),
        timeout=10,
    )
    if r.status_code != 201:
        return None
    return r.headers.get("Location", "").split("/")[-1]


def set_user_password(
    base_url: str,
    realm: str,
    token: str,
    user_id: str,
    password: str,
) -> bool:
    r = requests.put(
        f"{base_url}/admin/realms/{realm}/users/{user_id}/reset-password",
        json={"type": "password", "temporary": False, "value": password},
        headers=auth_headers(token),
        timeout=10,
    )
    return r.status_code in (200, 204)


def delete_user(base_url: str, realm: str, token: str, user_id: str) -> None:
    requests.delete(
        f"{base_url}/admin/realms/{realm}/users/{user_id}",
        headers=auth_headers(token),
        timeout=10,
    )


def login(
    base_url: str,
    realm: str,
    username: str,
    password: str,
    timeout: float = 10.0,
) -> Tuple[bool, float, Optional[str]]:
    url = f"{base_url}/realms/{realm}/protocol/openid-connect/token"
    data = {
        "client_id": "admin-cli",
        "username": username,
        "password": password,
        "grant_type": "password",
    }
    start = time.perf_counter()
    try:
        r = requests.post(url, data=data, timeout=timeout)
        elapsed = time.perf_counter() - start
        if r.status_code == 200:
            return True, elapsed, None
        return False, elapsed, f"HTTP {r.status_code}"
    except requests.exceptions.Timeout:
        elapsed = time.perf_counter() - start
        return False, elapsed, "timeout"
    except requests.exceptions.RequestException as e:
        elapsed = time.perf_counter() - start
        return False, elapsed, str(type(e).__name__)


def load_accounts_from_file(path: str) -> List[Tuple[str, str]]:
    accounts = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                u, p = line.split(":", 1)
                accounts.append((u.strip(), p.strip()))
    return accounts


def create_test_users(
    base_url: str,
    realm: str,
    admin_user: str,
    admin_pass: str,
    nb: int,
    password: str,
    run_id: str,
) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Crée nb users (testuser_0_runid, ...), définit leur mot de passe. Retourne ([(username, password)], [user_id])."""
    token = get_admin_token(base_url, admin_user, admin_pass)
    accounts = []
    user_ids = []
    for i in range(nb):
        username = f"loadtest_{i}_{run_id}"
        email = f"loadtest_{i}_{run_id}@test.local"
        uid = create_user(base_url, realm, token, username, email)
        if uid and set_user_password(base_url, realm, token, uid, password):
            accounts.append((username, password))
            user_ids.append(uid)
    return accounts, user_ids


def worker_multi(
    base_url: str,
    realm: str,
    accounts: List[Tuple[str, str]],
    deadline: float,
    results: List[Tuple[bool, float, Optional[str]]],
    results_lock: threading.Lock,
    stop: threading.Event,
    timeout: float,
) -> None:
    idx = [0]

    def next_account() -> Tuple[str, str]:
        i = idx[0] % len(accounts)
        idx[0] += 1
        return accounts[i]

    while not stop.is_set() and time.monotonic() < deadline:
        user, pwd = next_account()
        ok, lat, err = login(base_url, realm, user, pwd, timeout=timeout)
        with results_lock:
            results.append((ok, lat, err))


def worker_ramp_multi(
    base_url: str,
    realm: str,
    accounts: List[Tuple[str, str]],
    results: List[Tuple[bool, float, Optional[str]]],
    results_lock: threading.Lock,
    my_stop: threading.Event,
    timeout: float,
) -> None:
    idx = [0]

    def next_account() -> Tuple[str, str]:
        i = idx[0] % len(accounts)
        idx[0] += 1
        return accounts[i]

    while not my_stop.is_set():
        user, pwd = next_account()
        ok, lat, err = login(base_url, realm, user, pwd, timeout=timeout)
        with results_lock:
            results.append((ok, lat, err))


def percentile(sorted_values: List[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * p / 100
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_values) else f
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test de charge Keycloak avec plusieurs comptes (simulation proche production)."
    )
    parser.add_argument("--url", type=str, default=_DEFAULT_URL, help="URL Keycloak")
    parser.add_argument("--realm", type=str, default=_DEFAULT_REALM, help="Realm")
    parser.add_argument("--admin-user", type=str, default=_DEFAULT_ADMIN, help="Admin pour créer/supprimer les users")
    parser.add_argument("--admin-password", type=str, default=_DEFAULT_ADMIN_PASS, help="Mot de passe admin")
    parser.add_argument(
        "--create-users",
        type=int,
        metavar="N",
        help="Créer N utilisateurs de test dans le realm (mot de passe via --user-password ou LOAD_TEST_USER_PASSWORD)",
    )
    parser.add_argument(
        "--user-password",
        type=str,
        default=_DEFAULT_USER_PASSWORD,
        help="Mot de passe des users créés (défaut: testpass)",
    )
    parser.add_argument(
        "--accounts-file",
        type=str,
        metavar="PATH",
        help="Fichier avec une ligne 'username:password' par compte (au lieu de --create-users)",
    )
    parser.add_argument("--no-cleanup", action="store_true", help="Ne pas supprimer les users créés après le test")
    parser.add_argument("--concurrent", type=int, default=10, metavar="N", help="Nombre de threads (mode constant)")
    parser.add_argument("--duration", type=float, default=30.0, metavar="SEC", help="Durée du test (mode constant)")
    parser.add_argument("--timeout", type=float, default=10.0, help="Timeout par requête")
    parser.add_argument("--warmup", type=int, default=3, help="Requêtes de warmup (exclues des stats)")
    parser.add_argument("--mode", type=str, choices=("constant", "ramp"), default="constant")
    parser.add_argument("--users", type=int, default=30, metavar="X", help="Nombre de threads (mode ramp)")
    parser.add_argument("--ramp-up", type=float, default=60.0)
    parser.add_argument("--hold", type=float, default=30.0)
    parser.add_argument("--ramp-down", type=float, default=60.0)
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    admin_pass = args.admin_password or os.environ.get("KEYCLOAK_ADMIN_PASSWORD", _DEFAULT_ADMIN_PASS)

    accounts: List[Tuple[str, str]] = []
    user_ids_to_delete: List[str] = []

    if args.accounts_file:
        if not os.path.isfile(args.accounts_file):
            print(f"Erreur: fichier introuvable: {args.accounts_file}")
            return 1
        accounts = load_accounts_from_file(args.accounts_file)
        if not accounts:
            print("Erreur: aucun compte dans le fichier (format: username:password par ligne)")
            return 1
        print(f"  Comptes chargés depuis {args.accounts_file} : {len(accounts)}")
    elif args.create_users and args.create_users > 0:
        run_id = str(int(time.time()))
        print(f"\n📋 Création de {args.create_users} utilisateurs de test (run_id={run_id})...")
        accounts, user_ids_to_delete = create_test_users(
            base_url, args.realm, args.admin_user, admin_pass,
            args.create_users, args.user_password, run_id,
        )
        if len(accounts) < args.create_users:
            print(f"  ⚠ Seulement {len(accounts)}/{args.create_users} utilisateurs créés.")
        if not accounts:
            print("  Erreur: aucun utilisateur créé.")
            return 1
        print(f"  ✅ {len(accounts)} utilisateurs créés.\n")
    else:
        print("Erreur: indiquer --create-users N ou --accounts-file PATH")
        return 1

    print("=" * 60)
    print("  🔥 Test de charge Keycloak (multi-comptes)")
    print(f"     URL        : {base_url}")
    print(f"     Realm      : {args.realm}")
    print(f"     Comptes    : {len(accounts)}")
    if args.mode == "ramp":
        print(f"     Threads    : {args.users} (ramp {args.ramp_up}s, hold {args.hold}s, ramp-down {args.ramp_down}s)")
    else:
        print(f"     Concurrent : {args.concurrent} threads, durée {args.duration}s")
    print("=" * 60)

    if args.warmup > 0:
        print(f"\n⏳ Warmup ({args.warmup} requêtes)...")
        for i in range(args.warmup):
            u, p = accounts[i % len(accounts)]
            login(base_url, args.realm, u, p, args.timeout)
        print("   OK\n")

    results: List[Tuple[bool, float, Optional[str]]] = []
    results_lock = threading.Lock()
    start_wall = time.monotonic()

    if args.mode == "ramp":
        stop_events = [threading.Event() for _ in range(args.users)]
        threads = []
        for i in range(args.users):
            t = threading.Thread(
                target=worker_ramp_multi,
                args=(base_url, args.realm, accounts, results, results_lock, stop_events[i], args.timeout),
                daemon=True,
            )
            threads.append(t)
        for i in range(args.users):
            when = start_wall + (i / max(args.users, 1)) * args.ramp_up
            if when > time.monotonic():
                time.sleep(when - time.monotonic())
            threads[i].start()
        time.sleep(args.hold)
        ramp_down_start = time.monotonic()
        for i in range(args.users):
            when = ramp_down_start + (i / max(args.users, 1)) * args.ramp_down
            if when > time.monotonic():
                time.sleep(when - time.monotonic())
            stop_events[i].set()
        for t in threads:
            t.join(timeout=args.timeout + 2)
    else:
        stop = threading.Event()
        deadline = start_wall + args.duration
        threads = []
        for _ in range(args.concurrent):
            t = threading.Thread(
                target=worker_multi,
                args=(base_url, args.realm, accounts, deadline, results, results_lock, stop, args.timeout),
                daemon=True,
            )
            t.start()
            threads.append(t)
        time.sleep(args.duration)
        stop.set()
        for t in threads:
            t.join(timeout=args.timeout + 2)

    end_wall = time.monotonic()
    elapsed_wall = end_wall - start_wall

    total = len(results)
    ok_count = sum(1 for ok, _, _ in results if ok)
    latencies = [lat for ok, lat, _ in results if ok]
    errors = {}
    for ok, _, err in results:
        if not ok and err:
            errors[err] = errors.get(err, 0) + 1

    print("  📊 Résultats")
    print("-" * 40)
    print(f"     Requêtes totales : {total}")
    print(f"     Succès           : {ok_count} ({100 * ok_count / total:.1f}%)" if total else "     (aucune requête)")
    print(f"     Durée réelle     : {elapsed_wall:.1f} s")
    if total > 0:
        print(f"     Débit (req/s)    : {total / elapsed_wall:.1f}")
    if latencies:
        lat_sorted = sorted(latencies)
        print(f"     Latence (s)      : min={min(latencies):.3f}  avg={statistics.mean(latencies):.3f}  "
              f"p50={percentile(lat_sorted, 50):.3f}  p95={percentile(lat_sorted, 95):.3f}  p99={percentile(lat_sorted, 99):.3f}")
    if errors:
        print(f"     Erreurs          : {dict(errors)}")
        if errors.get("HTTP 403"):
            print("\n  💡 HTTP 403 : activer « Direct access grants » pour admin-cli (voir docs/admin-keycloak.md)")
    print("=" * 60)

    if user_ids_to_delete and not args.no_cleanup:
        print("\n🧹 Suppression des utilisateurs de test...")
        token = get_admin_token(base_url, args.admin_user, admin_pass)
        for uid in user_ids_to_delete:
            delete_user(base_url, args.realm, token, uid)
        print(f"  ✅ {len(user_ids_to_delete)} utilisateurs supprimés.\n")

    return 0 if (total > 0 and errors.get("HTTP 401", 0) != total) else 1


if __name__ == "__main__":
    sys.exit(main())
