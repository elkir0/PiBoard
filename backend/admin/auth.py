"""Simple session-based auth for the admin panel."""

import hashlib
import hmac
import logging
import secrets
import time
from datetime import datetime, timedelta

from admin.config_manager import config

logger = logging.getLogger(__name__)

SESSION_COOKIE = "piboard_session"
SESSION_MAX_AGE = 86400  # 24h

_PBKDF2_ITERS = 200_000


def _hash(password: str) -> str:
    """SHA-256 brut (LEGACY). Conserve pour _DEFAULT_HASH et la compat des
    config.json deja deployes ; la migration vers PBKDF2 se fait au 1er login."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _make_hash(password: str) -> str:
    """Hash sale + itere (PBKDF2-SHA256), format 'pbkdf2_sha256$iters$salt$hash'."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERS)
    return "pbkdf2_sha256$%d$%s$%s" % (_PBKDF2_ITERS, salt.hex(), dk.hex())


def _verify_hash(password: str, stored: str) -> tuple[bool, bool]:
    """Verifie un mot de passe contre le hash stocke. Renvoie (ok, legacy) :
    legacy=True si le hash etait du SHA-256 brut (a re-hacher en PBKDF2).
    Toujours en temps constant (hmac.compare_digest) -> pas de timing attack."""
    if not stored:
        return False, False
    if "$" in stored:
        try:
            algo, iters_s, salt_hex, hash_hex = stored.split("$", 3)
            if algo != "pbkdf2_sha256":
                return False, False
            dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                     bytes.fromhex(salt_hex), int(iters_s))
            return hmac.compare_digest(dk.hex(), hash_hex), False
        except Exception:
            return False, False
    # Hash legacy SHA-256 brut.
    return hmac.compare_digest(_hash(password), stored), True


# Default credentials — stored hashed in config.json under "auth" section.
# Reste en SHA-256 brut (c'est ce que les config.json deja deployes contiennent).
_DEFAULT_HASH = _hash("piboard")

# Active sessions: token -> expiry
_sessions: dict[str, datetime] = {}

# Rate-limit login par IP : ip -> (echecs consecutifs, instant_deblocage_monotonic).
# En memoire (mono-process). Backoff exponentiel a partir du seuil.
_login_fails: dict[str, tuple[int, float]] = {}
_RL_THRESHOLD = 5
_RL_BASE_DELAY = 2.0
_RL_MAX_DELAY = 300.0


def login_blocked(ip: str) -> float:
    """Secondes de blocage restantes pour cette IP (0.0 si non bloquee)."""
    _, until = _login_fails.get(ip or "?", (0, 0.0))
    return max(0.0, until - time.monotonic())


def note_login(ip: str, ok: bool):
    """Enregistre le resultat d'une tentative (pour le rate-limit)."""
    ip = ip or "?"
    now = time.monotonic()
    # Purge des AUTRES IP dont le backoff est ecoule -> borne la taille du dict
    # (scanners a IP tournantes, sinon DoS memoire). On NE purge PAS l'IP courante :
    # une entree sous le seuil a un until==now (delai 0) et serait oubliee a chaque
    # appel -> le compteur ne s'accumulerait jamais et le rate-limit serait inoperant.
    for k, (_, u) in list(_login_fails.items()):
        if k != ip and u <= now:
            _login_fails.pop(k, None)
    if ok:
        _login_fails.pop(ip, None)
        return
    # Plafonne le compteur -> evite un OverflowError sur 2**(fails) a tres haut compteur.
    fails = min(_login_fails.get(ip, (0, 0.0))[0] + 1, _RL_THRESHOLD + 32)
    delay = 0.0
    if fails >= _RL_THRESHOLD:
        delay = min(_RL_BASE_DELAY * (2 ** (fails - _RL_THRESHOLD)), _RL_MAX_DELAY)
    _login_fails[ip] = (fails, now + delay)


def is_default_password() -> bool:
    """Vrai si le mot de passe admin est encore le defaut 'piboard' (banniere UI).
    Via _verify_hash -> reste correct que le hash stocke soit legacy SHA-256 OU
    migre en PBKDF2 (sinon faux-negatif apres la 1ere migration)."""
    return _verify_hash("piboard", config.get("auth", "password_hash", _DEFAULT_HASH))[0]


def _ensure_auth_config():
    """S'assure qu'une section auth existe. Sur une install NEUVE (aucun hash
    stocke) on GENERE un mot de passe aleatoire et on le logge une fois — plus
    de mot de passe 'piboard' livre par defaut (distribution open source). Une
    install existante (hash deja present) n'est JAMAIS modifiee -> pas de lockout."""
    stored = config.get("auth", "password_hash")
    if not stored:
        pw = secrets.token_urlsafe(9)
        config.set("auth", "password_hash", _make_hash(pw))
        config.set("auth", "username", "admin")
        logger.warning(
            "[AUTH] Aucun mot de passe admin -> genere : '%s'  "
            "(utilisateur 'admin', a changer dans l'admin web)", pw)


def verify_login(username: str, password: str) -> str | None:
    """Check credentials, return session token or None. Migre un hash legacy
    SHA-256 vers PBKDF2 au 1er login reussi (evite le lockout du owner)."""
    _ensure_auth_config()
    stored_user = config.get("auth", "username", "admin")
    stored_hash = config.get("auth", "password_hash", _DEFAULT_HASH)

    ok, legacy = _verify_hash(password, stored_hash)
    if username == stored_user and ok:
        if legacy:
            config.set("auth", "password_hash", _make_hash(password))
            logger.info("[AUTH] Hash mot de passe migre SHA-256 -> PBKDF2")
        # Purge des sessions expirees avant d'en minter une nouvelle.
        now = datetime.now()
        for t, e in list(_sessions.items()):
            if e < now:
                _sessions.pop(t, None)
        token = secrets.token_hex(32)
        _sessions[token] = now + timedelta(seconds=SESSION_MAX_AGE)
        logger.info("[AUTH] Login reussi pour %s", username)
        return token

    logger.warning("[AUTH] Login echoue pour %s", username)
    return None


def verify_session(token: str | None) -> bool:
    """Check if a session token is valid."""
    if not token:
        return False
    expiry = _sessions.get(token)
    if not expiry:
        return False
    if datetime.now() > expiry:
        _sessions.pop(token, None)
        return False
    return True


def logout(token: str | None):
    """Invalidate a session."""
    if token:
        _sessions.pop(token, None)


def change_password(current: str, new_password: str) -> bool:
    """Change the admin password. Returns True on success."""
    _ensure_auth_config()
    stored_hash = config.get("auth", "password_hash", _DEFAULT_HASH)

    ok, _ = _verify_hash(current, stored_hash)
    if not ok:
        return False

    config.set("auth", "password_hash", _make_hash(new_password))
    logger.info("[AUTH] Mot de passe modifie")
    return True


# Au chargement (= au boot) : garantit qu'un mot de passe existe et, sur une
# install neuve, logge le mot de passe genere AVANT toute tentative de login.
_ensure_auth_config()
