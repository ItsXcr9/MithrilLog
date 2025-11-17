from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass, field
from typing import Iterable


def _hashes(value: bytes, num_hashes: int) -> Iterable[int]:
    digest = hashlib.sha256(value).digest()
    for i in range(num_hashes):
        start = i * 4
        chunk = digest[start : start + 4]
        if len(chunk) < 4:
            chunk = (chunk + hashlib.sha1(chunk).digest())[:4]
        yield int.from_bytes(chunk, "little", signed=False)


@dataclass
class BloomDeduper:
    """
    Tiny bloom filter for minute buckets.
    """

    capacity: int = 1_000_000
    error_rate: float = 1e-4
    seed: int = field(default_factory=lambda: int.from_bytes(os.urandom(4), "little"))

    def __post_init__(self) -> None:
        m = -self.capacity * math.log(self.error_rate) / (math.log(2) ** 2)
        self.num_bits = max(8, int(m))
        self.num_hashes = max(2, int(self.num_bits / self.capacity * math.log(2)))
        self.bitset = bytearray(math.ceil(self.num_bits / 8))

    def _positions(self, payload: bytes) -> list[int]:
        salted = self.seed.to_bytes(4, "little") + payload
        return [pos % self.num_bits for pos in _hashes(salted, self.num_hashes)]

    def seen(self, payload: bytes) -> bool:
        positions = self._positions(payload)
        present = all(self.bitset[p // 8] & (1 << (p % 8)) for p in positions)
        if not present:
            for p in positions:
                self.bitset[p // 8] |= 1 << (p % 8)
        return present

    def reset(self) -> None:
        for idx in range(len(self.bitset)):
            self.bitset[idx] = 0


@dataclass
class ReservoirSampler:
    """
    Per-key reservoir sampler keeping representative examples.
    """

    size: int = 200

    def __post_init__(self) -> None:
        self._reservoir: dict[str, list[dict]] = {}
        self._counts: dict[str, int] = {}
        self._pattern_counts: dict[str, int] = {}

    def add(self, key: str, pattern: str, event: dict) -> None:
        count = self._counts.get(key, 0) + 1
        self._counts[key] = count
        self._pattern_counts[pattern] = self._pattern_counts.get(pattern, 0) + 1
        reservoir = self._reservoir.setdefault(key, [])
        if len(reservoir) < self.size:
            reservoir.append(event)
            return
        import random

        index = random.randint(0, count - 1)
        if index < self.size:
            reservoir[index] = event

    def register_duplicate(self, pattern: str) -> None:
        self._pattern_counts[pattern] = self._pattern_counts.get(pattern, 0) + 1

    def snapshot(self) -> dict[str, list[dict]]:
        return {key: values.copy() for key, values in self._reservoir.items()}

    def totals(self) -> dict[str, int]:
        return self._pattern_counts.copy()

    def reset(self) -> None:
        self._reservoir.clear()
        self._counts.clear()
        self._pattern_counts.clear()

