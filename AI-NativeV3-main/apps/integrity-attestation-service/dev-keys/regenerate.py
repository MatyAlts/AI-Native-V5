"""Regenera las dev keys Ed25519 de manera DETERMINISTA desde un seed fijo.

ADR-021 — clave DEV ONLY commiteada al repo.

Por que determinista? Permite que:
1. Tests reproduzcan firmas bit-exact (golden tests).
2. Cualquiera que clone el repo y borre las claves obtenga EXACTAMENTE las
   mismas regenerando — sin que la firma de un test cambie aleatoriamente.
3. La pubkey id (SHA-256[:12] de la pubkey) sea estable y discriminable.

ADVERTENCIA: estas claves NO son secretas. Estan commiteadas al repo. Cualquier
deploy que las use en `environment=production` debe FALLAR FAST en startup.
La proteccion vive en `services/signing.py::load_keypair`.

Uso:
    cd apps/integrity-attestation-service
    uv run python dev-keys/regenerate.py
"""

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

# Seed determinista de 32 bytes derivado de un literal humano + padding cero.
# Si en algun momento se rota la dev key (raro), bumpea la version del seed.
_SEED = b"AI-NativeV3-DEV-ATTESTATION-KEY1"  # exactamente 32 bytes
_REQUIRED_SEED_LEN = 32


def _seed_32_bytes() -> bytes:
    if len(_SEED) != _REQUIRED_SEED_LEN:
        raise ValueError(f"Seed must be {_REQUIRED_SEED_LEN} bytes, got {len(_SEED)}")
    return _SEED


def regenerate(target_dir: Path) -> tuple[Path, Path]:
    """Regenera y escribe el keypair. Devuelve (priv_path, pub_path)."""
    target_dir.mkdir(parents=True, exist_ok=True)

    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(_seed_32_bytes())
    public_key = private_key.public_key()

    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    priv_path = target_dir / "dev-private.pem"
    pub_path = target_dir / "dev-public.pem"
    priv_path.write_bytes(priv_pem)
    pub_path.write_bytes(pub_pem)

    return priv_path, pub_path


if __name__ == "__main__":
    target = Path(__file__).resolve().parent
    priv, pub = regenerate(target)
    print("[OK] Dev keypair regenerated:")
    print(f"     {priv}")
    print(f"     {pub}")
    print("     WARNING: dev-only, do NOT use in production.")
