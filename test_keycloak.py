"""
Script de test d'envoi de mails en masse via Keycloak.

Comportement : création d'utilisateurs → envoi de mails de vérification → suppression
des utilisateurs (idéal pour dev, préprod ou tout Keycloak avec SMTP configuré).

Stratégies d'envoi (--strategy) :
  full         Débit max, sans pause (défaut).
  batch-pause  Lots de N mails puis pause : ex. 5k mails + 30s → --strategy batch-pause --send-batch-size 5000 --pause 30
  rate         Débit constant (mails/s) : ex. 100 mails/s = 360k/h, 3M ≈ 8h20 → --strategy rate --rate 100

Usage local (défaut) :
  python test_keycloak.py [--nb N] [--skip-create] [--skip-cleanup]

Usage préprod avec débit limité :
  export KEYCLOAK_URL=https://auth-preprod.example.com
  export KEYCLOAK_ADMIN_PASSWORD=...
  python test_keycloak.py --url "$KEYCLOAK_URL" --nb 10000 --strategy rate --rate 100
"""

import argparse
import concurrent.futures
import os
import time
from typing import Optional

import requests

# Charger .env si présent (optionnel : pip install python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Valeurs par défaut (lues depuis .env / os.environ ou constantes) ─────────
def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


_DEFAULT_URL   = "http://localhost:8080"
_DEFAULT_REALM = "master"
_DEFAULT_USER  = "admin"
_DEFAULT_PASS  = "admin"
NB_USERS       = _env_int("NB_USERS", 10_000)
MAX_WORKERS    = _env_int("MAX_WORKERS", 20)   # Threads parallèles pour l'envoi
BATCH_SIZE     = _env_int("BATCH_SIZE", 500)  # Rafraîchit le token tous les X utilisateurs

# Stratégies d'envoi
STRATEGY_FULL         = "full"          # Envoi max sans pause
STRATEGY_BATCH_PAUSE  = "batch-pause"   # Lots + pause entre chaque lot
STRATEGY_RATE         = "rate"          # Débit constant (mails/sec)
# ──────────────────────────────────────────────────────────────────────────────


def _format_duration(seconds: float) -> str:
    """Ex: 30000 -> '8h 20min'."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.0f}min"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}min"


def get_token(base_url: str, admin_user: str, admin_pass: str) -> str:
    r = requests.post(
        f"{base_url}/realms/master/protocol/openid-connect/token",
        data={
            "client_id":  "admin-cli",
            "username":   admin_user,
            "password":   admin_pass,
            "grant_type": "password",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def create_user(
    base_url: str, realm: str, token: str, index: int, run_id: Optional[str] = None
) -> Optional[str]:
    suffix = f"{index}_{run_id}" if run_id else str(index)
    payload = {
        "username":      f"testuser_{suffix}",
        "email":         f"testuser_{suffix}@test.local",
        "enabled":       True,
        "emailVerified": False,
    }
    r = requests.post(
        f"{base_url}/admin/realms/{realm}/users",
        json=payload,
        headers=auth_headers(token),
        timeout=10,
    )
    if r.status_code == 201:
        return r.headers["Location"].split("/")[-1]
    return None


def send_verification_email(base_url: str, realm: str, token: str, user_id: str) -> int:
    r = requests.put(
        f"{base_url}/admin/realms/{realm}/users/{user_id}/send-verify-email",
        headers=auth_headers(token),
        timeout=10,
    )
    return r.status_code


def delete_user(base_url: str, realm: str, token: str, user_id: str) -> None:
    requests.delete(
        f"{base_url}/admin/realms/{realm}/users/{user_id}",
        headers=auth_headers(token),
        timeout=10,
    )


# ── Étape 1 : Création des utilisateurs ───────────────────────────────────────
def create_users(base_url: str, realm: str, admin_user: str, admin_pass: str, nb: int) -> list:
    run_id = str(int(time.time()))
    print(f"\n📋 Création de {nb} utilisateurs fictifs (run_id={run_id})...")
    token    = get_token(base_url, admin_user, admin_pass)
    user_ids = []
    start    = time.time()

    for i in range(nb):
        if i % BATCH_SIZE == 0 and i > 0:
            token = get_token(base_url, admin_user, admin_pass)
            elapsed = time.time() - start
            rate    = len(user_ids) / elapsed
            print(f"  ✔ {len(user_ids)}/{nb} créés  ({rate:.0f} users/s)  ETA {(nb - len(user_ids)) / rate:.0f}s" if rate > 0 else f"  ✔ {i}/{nb} en cours...")

        uid = create_user(base_url, realm, token, i, run_id)
        if uid:
            user_ids.append(uid)

    elapsed = time.time() - start
    rate_final = len(user_ids) / elapsed if elapsed > 0 else 0
    print(f"  ✅ {len(user_ids)} utilisateurs créés en {elapsed:.1f}s ({rate_final:.0f} users/s)\n")
    return user_ids


# ── Étape 2 : Envoi des mails ──────────────────────────────────────────────────
def _send_chunk(
    base_url: str,
    realm: str,
    token: str,
    executor: concurrent.futures.ThreadPoolExecutor,
    user_ids_chunk: list,
) -> tuple:
    """Envoie un lot d'emails, retourne (sent, errors)."""
    sent, errors = 0, 0
    futures = [
        executor.submit(send_verification_email, base_url, realm, token, uid)
        for uid in user_ids_chunk
    ]
    for future in concurrent.futures.as_completed(futures):
        status = future.result()
        if status in (200, 204):
            sent += 1
        else:
            errors += 1
    return sent, errors


def send_emails(
    base_url: str,
    realm: str,
    admin_user: str,
    admin_pass: str,
    user_ids: list,
    strategy: str = STRATEGY_FULL,
    pause_sec: float = 0,
    send_batch_size: int = 5000,
    rate_per_sec: Optional[float] = None,
    rate_batch: int = 100,
) -> None:
    total = len(user_ids)
    if strategy == STRATEGY_FULL:
        strategy_desc = "débit max (sans pause)"
    elif strategy == STRATEGY_BATCH_PAUSE:
        strategy_desc = f"lots de {send_batch_size} + pause {pause_sec}s"
    elif strategy == STRATEGY_RATE and rate_per_sec is not None:
        strategy_desc = f"débit constant {rate_per_sec:.0f} mails/s"
    else:
        strategy_desc = strategy
    print(f"📨 Envoi de {total} mails (stratégie: {strategy_desc}, threads={MAX_WORKERS})...")
    if strategy == STRATEGY_RATE and rate_per_sec:
        eta_approx = total / rate_per_sec
        print(f"    ⏱  Durée estimée : {_format_duration(eta_approx)} ({total / rate_per_sec:.0f}s)")

    token = get_token(base_url, admin_user, admin_pass)
    start = time.time()
    sent, errors = 0, 0
    completed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        if strategy == STRATEGY_FULL:
            # Envoi max : tout en parallèle
            future_to_uid = {
                executor.submit(send_verification_email, base_url, realm, token, uid): uid
                for uid in user_ids
            }
            for i, future in enumerate(concurrent.futures.as_completed(future_to_uid)):
                status = future.result()
                if status in (200, 204):
                    sent += 1
                else:
                    errors += 1
                completed = i + 1
                if completed % BATCH_SIZE == 0 or completed == total:
                    elapsed = time.time() - start
                    r = completed / elapsed if elapsed > 0 else 0
                    eta = (total - completed) / r if r > 0 else 0
                    print(f"  ✔ {completed}/{total} mails  ({r:.1f} mails/s)  ETA {eta:.0f}s")

        elif strategy == STRATEGY_BATCH_PAUSE:
            # Lots de send_batch_size, puis pause
            for chunk_start in range(0, total, send_batch_size):
                chunk = user_ids[chunk_start : chunk_start + send_batch_size]
                if not chunk:
                    break
                s, e = _send_chunk(base_url, realm, token, executor, chunk)
                sent += s
                errors += e
                completed += len(chunk)
                if completed % BATCH_SIZE == 0 or completed >= total:
                    token = get_token(base_url, admin_user, admin_pass)
                elapsed = time.time() - start
                r = completed / elapsed if elapsed > 0 else 0
                print(f"  ✔ {completed}/{total} mails  ({r:.1f} mails/s)  lot terminé")
                if completed < total and pause_sec > 0:
                    time.sleep(pause_sec)

        elif strategy == STRATEGY_RATE and rate_per_sec and rate_per_sec > 0:
            # Débit constant : après chaque micro-lot, sleep pour respecter rate
            for chunk_start in range(0, total, rate_batch):
                chunk = user_ids[chunk_start : chunk_start + rate_batch]
                if not chunk:
                    break
                batch_start = time.time()
                s, e = _send_chunk(base_url, realm, token, executor, chunk)
                sent += s
                errors += e
                completed += len(chunk)
                if completed % BATCH_SIZE == 0 or completed >= total:
                    token = get_token(base_url, admin_user, admin_pass)
                # Throttle : pour avoir (completed) mails en (completed/rate) secondes
                target_elapsed = completed / rate_per_sec
                actual_elapsed = time.time() - start
                sleep_time = target_elapsed - actual_elapsed
                if sleep_time > 0.01:  # évite des sleep minuscules
                    time.sleep(sleep_time)
                if completed % (rate_batch * 10) == 0 or completed == total:
                    elapsed = time.time() - start
                    r = completed / elapsed if elapsed > 0 else 0
                    eta = (total - completed) / rate_per_sec if rate_per_sec > 0 else 0
                    print(f"  ✔ {completed}/{total} mails  ({r:.1f} mails/s)  ETA {_format_duration(eta)}")

        else:
            raise ValueError(f"Stratégie inconnue ou paramètres manquants: {strategy}")

    elapsed = time.time() - start
    rate = (sent + errors) / elapsed if elapsed > 0 else 0
    print(f"\n  ✅ Résultats :")
    print(f"     • Mails envoyés : {sent}")
    print(f"     • Erreurs       : {errors}")
    print(f"     • Durée totale  : {_format_duration(elapsed)} ({elapsed:.1f}s)")
    print(f"     • Débit moyen   : {rate:.1f} mails/s")


# ── Étape 3 : Nettoyage ────────────────────────────────────────────────────────
def cleanup(base_url: str, realm: str, admin_user: str, admin_pass: str, user_ids: list) -> None:
    print(f"\n🧹 Suppression de {len(user_ids)} utilisateurs de test...")
    token = get_token(base_url, admin_user, admin_pass)
    start = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(delete_user, base_url, realm, token, uid)
            for uid in user_ids
        ]
        for i, _ in enumerate(concurrent.futures.as_completed(futures)):
            if i % BATCH_SIZE == 0 and i > 0:
                print(f"  ✔ {i}/{len(user_ids)} supprimés...")

    print(f"  ✅ Nettoyage terminé en {time.time() - start:.1f}s")


# ── Main ───────────────────────────────────────────────────────────────────────
def _config_from_env_and_args() -> tuple:
    """URL, realm, admin_user, admin_pass : env puis args puis défaut."""
    url = os.environ.get("KEYCLOAK_URL", _DEFAULT_URL).rstrip("/")
    realm = os.environ.get("KEYCLOAK_REALM", _DEFAULT_REALM)
    user = os.environ.get("KEYCLOAK_ADMIN_USER", _DEFAULT_USER)
    password = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", _DEFAULT_PASS)
    return url, realm, user, password


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test envoi mails Keycloak (création → envoi → suppression). "
                    "Utilisable en local ou préprod (SMTP Scaleway, etc.)."
    )
    parser.add_argument("--url",     type=str, default=None, help="URL Keycloak (sinon KEYCLOAK_URL ou localhost:8080)")
    parser.add_argument("--realm",   type=str, default=None, help="Realm cible (sinon KEYCLOAK_REALM ou master)")
    parser.add_argument("--user",    type=str, default=None, help="Admin username (sinon KEYCLOAK_ADMIN_USER ou admin)")
    parser.add_argument("--nb",      type=int, default=NB_USERS, help="Nombre de mails à envoyer")
    # Stratégie d'envoi
    parser.add_argument(
        "--strategy",
        type=str,
        choices=[STRATEGY_FULL, STRATEGY_BATCH_PAUSE, STRATEGY_RATE],
        default=STRATEGY_FULL,
        help="Stratégie: full (débit max), batch-pause (lots + pause), rate (débit constant mails/s)",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0,
        metavar="SEC",
        help="Avec --strategy batch-pause: pause en secondes entre chaque lot (ex: 30)",
    )
    parser.add_argument(
        "--send-batch-size",
        type=int,
        default=5000,
        metavar="N",
        help="Avec --strategy batch-pause: taille d’un lot avant pause (ex: 5000)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=None,
        metavar="N",
        help="Avec --strategy rate: débit cible en mails/s (ex: 100 → 360k/h, 3M ≈ 8h20)",
    )
    parser.add_argument(
        "--rate-batch",
        type=int,
        default=100,
        metavar="N",
        help="Avec --strategy rate: taille du micro-lot pour le throttling (défaut: 100)",
    )
    parser.add_argument("--skip-create",  action="store_true", help="Ne pas recréer les utilisateurs")
    parser.add_argument("--skip-cleanup", action="store_true", help="Ne pas supprimer les utilisateurs après")
    args = parser.parse_args()

    base_url, realm, admin_user, admin_pass = _config_from_env_and_args()
    if args.url is not None:
        base_url = args.url.rstrip("/")
    if args.realm is not None:
        realm = args.realm
    if args.user is not None:
        admin_user = args.user
    if not admin_pass or admin_pass == _DEFAULT_PASS:
        admin_pass = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", _DEFAULT_PASS)

    if args.strategy == STRATEGY_RATE and (args.rate is None or args.rate <= 0):
        parser.error("--strategy rate requiert --rate N (mails/sec, ex: --rate 100)")

    strategy_line = f"Stratégie : {args.strategy}"
    if args.strategy == STRATEGY_BATCH_PAUSE:
        strategy_line += f" (lot={args.send_batch_size}, pause={args.pause}s)"
    elif args.strategy == STRATEGY_RATE:
        strategy_line += f" ({args.rate:.0f} mails/s)"

    print("=" * 55)
    print("  🚀 Test envoi mails Keycloak")
    print(f"     URL      : {base_url}")
    print(f"     Realm    : {realm}")
    print(f"     User     : {admin_user}")
    print(f"     Nb mails : {args.nb}")
    print(f"     {strategy_line}")
    print(f"     Threads  : {MAX_WORKERS}")
    print("=" * 55)

    total_start = time.time()

    user_ids = create_users(base_url, realm, admin_user, admin_pass, args.nb)
    send_emails(
        base_url,
        realm,
        admin_user,
        admin_pass,
        user_ids,
        strategy=args.strategy,
        pause_sec=args.pause,
        send_batch_size=args.send_batch_size,
        rate_per_sec=args.rate,
        rate_batch=args.rate_batch,
    )

    if not args.skip_cleanup:
        cleanup(base_url, realm, admin_user, admin_pass, user_ids)

    print(f"\n⏱  Durée totale du test : {time.time() - total_start:.1f}s")