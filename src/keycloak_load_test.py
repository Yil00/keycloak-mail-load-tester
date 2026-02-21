#!/usr/bin/env python3
"""
Test de charge Keycloak : connexions simultanées et durée.

Deux modes :
- constant (défaut) : N threads pendant D secondes (débit max).
- ramp : X utilisateurs se connectent progressivement sur ramp-up, restent (optionnel), puis
  se déconnectent progressivement sur ramp-down.

Usage :
  python keycloak_load_test.py --concurrent 20 --duration 60
  python keycloak_load_test.py --mode ramp --users 50 --ramp-up 60 --hold 30 --ramp-down 60

Variables d'environnement (ou .env) : KEYCLOAK_URL, KEYCLOAK_REALM, KEYCLOAK_ADMIN_USER, KEYCLOAK_ADMIN_PASSWORD
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

# ── Config depuis env ────────────────────────────────────────────────────────
_DEFAULT_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080").rstrip("/")
_DEFAULT_REALM = os.environ.get("KEYCLOAK_REALM", "master")
_DEFAULT_USER = os.environ.get("KEYCLOAK_ADMIN_USER", "admin")
_DEFAULT_PASS = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")
# ─────────────────────────────────────────────────────────────────────────────


def login(
    base_url: str,
    realm: str,
    username: str,
    password: str,
    timeout: float = 10.0,
) -> Tuple[bool, float, Optional[str]]:
    """
    Tente un login (obtention de token). Retourne (succès, latence_sec, message_erreur).
    """
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


def worker(
    base_url: str,
    realm: str,
    username: str,
    password: str,
    deadline: float,
    results: List[Tuple[bool, float, Optional[str]]],
    results_lock: threading.Lock,
    stop: threading.Event,
    timeout: float,
) -> None:
    """Un worker : enchaîne les logins jusqu'à deadline ou stop."""
    while not stop.is_set() and time.monotonic() < deadline:
        ok, lat, err = login(base_url, realm, username, password, timeout=timeout)
        with results_lock:
            results.append((ok, lat, err))


def worker_ramp(
    base_url: str,
    realm: str,
    username: str,
    password: str,
    results: List[Tuple[bool, float, Optional[str]]],
    results_lock: threading.Lock,
    my_stop: threading.Event,
    timeout: float,
) -> None:
    """Un worker pour le mode ramp : enchaîne les logins jusqu'à ce que my_stop soit posé."""
    while not my_stop.is_set():
        ok, lat, err = login(base_url, realm, username, password, timeout=timeout)
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
        description="Test de charge Keycloak : connexions simultanées sur une durée."
    )
    parser.add_argument("--url", type=str, default=_DEFAULT_URL, help="URL Keycloak")
    parser.add_argument("--realm", type=str, default=_DEFAULT_REALM, help="Realm")
    parser.add_argument("--user", type=str, default=_DEFAULT_USER, help="Username pour le login")
    parser.add_argument("--password", type=str, default=_DEFAULT_PASS, help="Password (ou KEYCLOAK_ADMIN_PASSWORD)")
    parser.add_argument(
        "--concurrent",
        type=int,
        default=10,
        metavar="N",
        help="Nombre de connexions simultanées (threads)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
        metavar="SEC",
        help="Durée du test en secondes",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        metavar="SEC",
        help="Timeout par requête (secondes)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=3,
        metavar="N",
        help="Nombre de requêtes de warmup (exclues des stats)",
    )
    # Mode ramp : montée / descente progressive
    parser.add_argument(
        "--mode",
        type=str,
        choices=("constant", "ramp"),
        default="constant",
        help="constant = N threads pendant D s ; ramp = X users montée/descente progressive",
    )
    parser.add_argument(
        "--users",
        type=int,
        default=30,
        metavar="X",
        help="Nombre d'utilisateurs simulés (mode ramp uniquement)",
    )
    parser.add_argument(
        "--ramp-up",
        type=float,
        default=60.0,
        metavar="SEC",
        help="Durée de montée : 0 → X users (mode ramp)",
    )
    parser.add_argument(
        "--hold",
        type=float,
        default=30.0,
        metavar="SEC",
        help="Durée au pic (X users actifs) avant descente (mode ramp)",
    )
    parser.add_argument(
        "--ramp-down",
        type=float,
        default=60.0,
        metavar="SEC",
        help="Durée de descente : X → 0 users (mode ramp)",
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    password = args.password or os.environ.get("KEYCLOAK_ADMIN_PASSWORD", _DEFAULT_PASS)

    print("=" * 60)
    if args.mode == "ramp":
        print("  🔥 Test de charge Keycloak (ramp : montée / descente progressive)")
        print(f"     URL        : {base_url}")
        print(f"     Realm      : {args.realm}")
        print(f"     User       : {args.user}")
        print(f"     Users      : {args.users} (montée {args.ramp_up}s, hold {args.hold}s, descente {args.ramp_down}s)")
    else:
        print("  🔥 Test de charge Keycloak (connexions simultanées)")
        print(f"     URL        : {base_url}")
        print(f"     Realm      : {args.realm}")
        print(f"     User       : {args.user}")
        print(f"     Concurrent : {args.concurrent} threads")
        print(f"     Durée      : {args.duration} s")
    print("=" * 60)

    # Warmup
    if args.warmup > 0:
        print(f"\n⏳ Warmup ({args.warmup} requêtes)...")
        for _ in range(args.warmup):
            login(base_url, args.realm, args.user, password, args.timeout)
        print("   OK\n")

    results: List[Tuple[bool, float, Optional[str]]] = []
    results_lock = threading.Lock()
    start_wall = time.monotonic()

    if args.mode == "ramp":
        # Mode ramp : un stop Event par thread
        stop_events = [threading.Event() for _ in range(args.users)]
        threads: List[threading.Thread] = []
        for i in range(args.users):
            t = threading.Thread(
                target=worker_ramp,
                args=(base_url, args.realm, args.user, password, results, results_lock, stop_events[i], args.timeout),
                daemon=True,
            )
            threads.append(t)

        # Montée : démarrer les threads progressivement
        ramp_up_end = start_wall + args.ramp_up
        for i in range(args.users):
            when = start_wall + (i / max(args.users, 1)) * args.ramp_up
            now = time.monotonic()
            if when > now:
                time.sleep(when - now)
            threads[i].start()

        # Hold au pic
        time.sleep(args.hold)

        # Descente : arrêter les threads progressivement
        ramp_down_start = time.monotonic()
        for i in range(args.users):
            when = ramp_down_start + (i / max(args.users, 1)) * args.ramp_down
            now = time.monotonic()
            if when > now:
                time.sleep(when - now)
            stop_events[i].set()

        for t in threads:
            t.join(timeout=args.timeout + 2)
    else:
        # Mode constant (comportement d'origine)
        stop = threading.Event()
        deadline = start_wall + args.duration
        threads = []
        for _ in range(args.concurrent):
            t = threading.Thread(
                target=worker,
                args=(base_url, args.realm, args.user, password, deadline, results, results_lock, stop, args.timeout),
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

    # Stats
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
        rps = total / elapsed_wall
        print(f"     Débit (req/s)    : {rps:.1f}")
    if latencies:
        lat_sorted = sorted(latencies)
        print(f"     Latence (s)      : min={min(latencies):.3f}  avg={statistics.mean(latencies):.3f}  "
              f"p50={percentile(lat_sorted, 50):.3f}  p95={percentile(lat_sorted, 95):.3f}  p99={percentile(lat_sorted, 99):.3f}")
    if errors:
        print(f"     Erreurs          : {dict(errors)}")
        if errors.get("HTTP 403"):
            print("\n  💡 HTTP 403 : activer « Direct access grants » pour le client admin-cli")
            print("     (Realm master → Clients → admin-cli → Paramètres) et vérifier la protection brute force.")
    print("=" * 60)
    return 0 if (total > 0 and errors.get("HTTP 401", 0) != total) else 1


if __name__ == "__main__":
    sys.exit(main())
