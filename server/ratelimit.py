"""Freio simples de força bruta para as rotas de login e registro.

Estado em memória do processo: reinício do servidor zera tudo, e com mais de um worker
cada um conta o seu. Serve para o uso atual (um processo local); se o app for para
produção com vários workers, isso precisa virar um armazenamento compartilhado.
"""

import threading
import time


class AttemptLimiter:
    def __init__(self, max_attempts, base_block_seconds, max_block_seconds, window_seconds):
        self.max_attempts = max_attempts
        self.base_block_seconds = base_block_seconds
        self.max_block_seconds = max_block_seconds
        self.window_seconds = window_seconds
        self._entries = {}
        self._lock = threading.Lock()

    def _prune(self, now):
        """Descarta chaves inativas para o dicionário não crescer sem limite."""
        stale = [
            key
            for key, entry in self._entries.items()
            if entry["blocked_until"] < now and entry["last_failure"] + self.window_seconds < now
        ]
        for key in stale:
            del self._entries[key]

    def retry_after(self, key) -> int:
        """Segundos que ainda faltam para a chave poder tentar de novo (0 = liberada)."""
        now = time.time()
        with self._lock:
            self._prune(now)
            entry = self._entries.get(key)
            if entry is None:
                return 0
            remaining = entry["blocked_until"] - now
            return int(remaining) + 1 if remaining > 0 else 0

    def register_failure(self, key) -> int:
        """Conta uma tentativa falha e devolve o bloqueio resultante em segundos (0 = sem)."""
        now = time.time()
        with self._lock:
            self._prune(now)
            entry = self._entries.get(key)
            if entry is None or entry["last_failure"] + self.window_seconds < now:
                entry = {"failures": 0, "blocked_until": 0.0, "last_failure": now}
                self._entries[key] = entry

            entry["failures"] += 1
            entry["last_failure"] = now

            if entry["failures"] < self.max_attempts:
                return 0

            # 5ª falha bloqueia por base_block_seconds; cada falha seguinte dobra, até o teto.
            exponent = entry["failures"] - self.max_attempts
            block = min(self.base_block_seconds * (2**exponent), self.max_block_seconds)
            entry["blocked_until"] = now + block
            return int(block)

    def reset(self, key) -> None:
        """Zera o histórico da chave — chamado quando a tentativa dá certo."""
        with self._lock:
            self._entries.pop(key, None)
