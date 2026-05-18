"""Tests anti-regresion del orden canonico de `compute_chain_hash`.

CLAUDE.md declara explicitamente que la formula es:
    chain_hash_n = SHA-256(self_hash_n || prev_chain_hash_{n-1})
                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                  self primero, prev despues — counterintuitivo

Este modulo es un proxy de la cadena criptografica real del piloto:
los fixtures abajo son hashes verificados directamente contra la DB
ctr_store del piloto (470 events integros). Si este test falla, hay
desalineacion entre `packages/contracts` y `apps/ctr-service` —
auditores externos que usen el package OFICIAL para verificar la
cadena obtendran falsos failures.

Si necesitas regenerar los fixtures contra una DB distinta:
    docker exec platform-postgres psql -U postgres -d ctr_store \\
        -c "SELECT seq, self_hash, prev_chain_hash, chain_hash \\
            FROM events WHERE episode_id='80000000-0000-0000-0000-0000000f69b4' \\
            ORDER BY seq LIMIT 4;"
"""

from __future__ import annotations

import hashlib

from platform_contracts.ctr.hashing import GENESIS_HASH, compute_chain_hash


# Fixtures bit-exact: 4 eventos consecutivos del episodio
# 80000000-0000-0000-0000-0000000f69b4 (ctr_store del piloto, 2026-05-04).
# Cada tupla = (seq, self_hash, prev_chain_hash, chain_hash_esperado).
_REAL_CHAIN_FIXTURES = [
    (
        0,
        "dea21652b9b50e6c8e5cf223c7f53b55dda72b4b90705450d47eeee723966d28",
        "0000000000000000000000000000000000000000000000000000000000000000",
        "f948e41df15083a35f8f8eb386488d8dff9cb41b13a9fadd1f0e21cb09210250",
    ),
    (
        1,
        "2795bd871a7514b15c2134f5d3c24d03109d28e8f655cb16270ded9fbd219466",
        "f948e41df15083a35f8f8eb386488d8dff9cb41b13a9fadd1f0e21cb09210250",
        "00380026c951cd79617e1918be4aca29c899475a0d2277a7940eaecff88890a2",
    ),
    (
        2,
        "8fbee1263e82f6f6ca71858528828ec35dd2b270e6741c1b3ce1f4c9c5e1a840",
        "00380026c951cd79617e1918be4aca29c899475a0d2277a7940eaecff88890a2",
        "f3ca9c811974e59c7c97ae46aa52eca641e3cb2e034da26be2e0a0a8b796cee6",
    ),
    (
        3,
        "b94cab1766fb59a9c2b5da7a76f034b961292d3c149c8cec249c2966e9941dce",
        "f3ca9c811974e59c7c97ae46aa52eca641e3cb2e034da26be2e0a0a8b796cee6",
        "334ed4cd1b6d969b49a6e200a17fe08a78e9e933bad870f64f9702c434f50dec",
    ),
]


def test_chain_hash_matches_real_db_event_seq0() -> None:
    """El primer evento del episodio (seq=0) usa GENESIS y produce el chain_hash de la DB."""
    seq, self_hash, prev_chain_hash, expected_chain = _REAL_CHAIN_FIXTURES[0]
    assert prev_chain_hash == GENESIS_HASH, "fixture inconsistente: seq=0 debe usar genesis"
    # Pasando explicito
    assert compute_chain_hash(self_hash, prev_chain_hash) == expected_chain
    # Pasando None (deberia caer al genesis)
    assert compute_chain_hash(self_hash, None) == expected_chain


def test_chain_hash_matches_real_db_consecutive_events() -> None:
    """4 eventos consecutivos del piloto reproducen la cadena bit-a-bit.

    Si el orden de concatenacion en `compute_chain_hash` se invierte
    (prev||self en vez de self||prev), este test falla en el seq=0 ya.
    """
    for seq, self_hash, prev_chain_hash, expected_chain in _REAL_CHAIN_FIXTURES:
        actual = compute_chain_hash(self_hash, prev_chain_hash)
        assert actual == expected_chain, (
            f"chain_hash mismatch en seq={seq}: "
            f"actual={actual} expected={expected_chain}"
        )


def test_chain_hash_canonical_order_self_then_prev() -> None:
    """Defensa explicita del orden self||prev (CLAUDE.md hashing rules).

    Este test usa hashes sinteticos de un solo digito repetido para que
    sea trivial visualmente verificar que NO se invirtio el orden.
    """
    self_hash = "a" * 64
    prev_hash = "b" * 64
    # Concatenacion canonica: self primero, prev despues
    expected = hashlib.sha256(f"{self_hash}{prev_hash}".encode()).hexdigest()
    assert compute_chain_hash(self_hash, prev_hash) == expected
    # Y verificamos que el orden inverso da otro hash distinto
    inverted = hashlib.sha256(f"{prev_hash}{self_hash}".encode()).hexdigest()
    assert compute_chain_hash(self_hash, prev_hash) != inverted
