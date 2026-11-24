"""Discover broker symbols, filter Forex instruments and map canonical pairs to broker names."""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from pydantic import ValidationError

from app.core.errors import BrokerDataError, SymbolAmbiguousError, SymbolNotFoundError
from app.mt5_connector.connector import MT5Connector
from app.symbol_manager.models import (
    FIAT_CURRENCIES,
    FOREX_CALC_MODES,
    MappingStatus,
    SymbolMapping,
    SymbolSpec,
)

logger = logging.getLogger(__name__)

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9._#+\-]{3,32}$")


def is_forex_record(raw: Mapping[str, Any]) -> bool:
    """True for fiat-vs-fiat instruments with a Forex calculation mode."""
    base = str(raw.get("currency_base") or "").upper()
    quote = str(raw.get("currency_profit") or "").upper()
    return (
        raw.get("trade_calc_mode") in FOREX_CALC_MODES
        and base in FIAT_CURRENCIES
        and quote in FIAT_CURRENCIES
        and base != quote
    )


def spec_from_record(raw: Mapping[str, Any]) -> SymbolSpec:
    """Validate a raw broker record. Raises ``ValidationError`` / ``ValueError`` if malformed."""
    tick_value = raw.get("trade_tick_value")
    base = str(raw["currency_base"]).upper()
    quote = str(raw["currency_profit"]).upper()
    return SymbolSpec(
        name=str(raw["name"]),
        canonical=f"{base}{quote}",
        description=str(raw.get("description") or ""),
        path=str(raw.get("path") or ""),
        currency_base=base,
        currency_profit=quote,
        currency_margin=str(raw.get("currency_margin") or base).upper(),
        calc_mode=int(raw["trade_calc_mode"]),
        trade_mode=int(raw["trade_mode"]),
        digits=int(raw["digits"]),
        point=float(raw["point"]),
        tick_size=float(raw["trade_tick_size"]),
        tick_value=float(tick_value) if tick_value not in (None, 0, 0.0) else None,
        contract_size=float(raw["trade_contract_size"]),
        volume_min=float(raw["volume_min"]),
        volume_max=float(raw["volume_max"]),
        volume_step=float(raw["volume_step"]),
        stops_level_points=int(raw.get("trade_stops_level") or 0),
        freeze_level_points=int(raw.get("trade_freeze_level") or 0),
        spread_points=int(raw["spread"]) if raw.get("spread") is not None else None,
        visible=bool(raw.get("visible")),
    )


def build_mapping(
    universe: Iterable[str], specs: Iterable[SymbolSpec], overrides: Mapping[str, str]
) -> dict[str, SymbolMapping]:
    """Map each canonical pair in ``universe`` to exactly one broker symbol, or flag it."""
    by_name = {s.name: s for s in specs}
    by_canonical: dict[str, list[str]] = {}
    for spec in by_name.values():
        by_canonical.setdefault(spec.canonical, []).append(spec.name)

    result: dict[str, SymbolMapping] = {}
    for pair in universe:
        candidates = sorted(by_canonical.get(pair, []))
        override = overrides.get(pair)
        if override is not None:
            if override in by_name and by_name[override].canonical == pair:
                result[pair] = SymbolMapping(
                    canonical=pair,
                    broker_symbol=override,
                    status=MappingStatus.MAPPED,
                    source="override",
                    candidates=candidates,
                )
            else:
                logger.warning("Override %s -> %s does not match a discovered %s symbol", pair, override, pair)
                result[pair] = SymbolMapping(
                    canonical=pair,
                    broker_symbol=None,
                    status=MappingStatus.MISSING,
                    source="override",
                    candidates=candidates,
                )
        elif pair in candidates:
            result[pair] = SymbolMapping(
                canonical=pair, broker_symbol=pair, status=MappingStatus.MAPPED, source="exact", candidates=candidates
            )
        elif len(candidates) == 1:
            result[pair] = SymbolMapping(
                canonical=pair,
                broker_symbol=candidates[0],
                status=MappingStatus.MAPPED,
                source="unique_candidate",
                candidates=candidates,
            )
        elif candidates:
            result[pair] = SymbolMapping(
                canonical=pair, broker_symbol=None, status=MappingStatus.AMBIGUOUS, source="none", candidates=candidates
            )
        else:
            result[pair] = SymbolMapping(
                canonical=pair, broker_symbol=None, status=MappingStatus.MISSING, source="none"
            )
    return result


class SymbolManager:
    def __init__(
        self,
        connector: MT5Connector,
        universe: list[str],
        overrides: Mapping[str, str] | None = None,
        cache_seconds: float = 300.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._connector = connector
        self._universe = list(universe)
        self._overrides = dict(overrides or {})
        self._cache_seconds = cache_seconds
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._cached_at: float | None = None
        self._specs: dict[str, SymbolSpec] = {}
        self._mapping: dict[str, SymbolMapping] = {}
        self.rejected_count = 0

    @property
    def universe(self) -> list[str]:
        return list(self._universe)

    def refresh(self, force: bool = False) -> None:
        with self._lock:
            fresh = self._cached_at is not None and self._monotonic() - self._cached_at < self._cache_seconds
            if fresh and not force:
                return
            raw = self._connector.run(lambda a: a.symbols_get())
            if raw is None:
                code, msg = self._connector.last_error()
                raise BrokerDataError(f"symbols_get returned no data: [{code}] {msg}")
            specs: dict[str, SymbolSpec] = {}
            rejected = 0
            for rec in raw:
                if not is_forex_record(rec):
                    continue
                try:
                    spec = spec_from_record(rec)
                except (KeyError, TypeError, ValueError, ValidationError) as exc:
                    rejected += 1
                    logger.warning("Rejected malformed symbol record %r: %s", rec.get("name"), exc)
                    continue
                specs[spec.name] = spec
            self._specs = specs
            self._mapping = build_mapping(self._universe, specs.values(), self._overrides)
            self.rejected_count = rejected
            self._cached_at = self._monotonic()
            logger.info(
                "Discovered %d Forex symbols (%d rejected); universe mapped %d/%d",
                len(specs),
                rejected,
                sum(m.status is MappingStatus.MAPPED for m in self._mapping.values()),
                len(self._universe),
            )

    def forex_symbols(self) -> list[SymbolSpec]:
        self.refresh()
        return sorted(self._specs.values(), key=lambda s: s.name)

    def mapping(self) -> dict[str, SymbolMapping]:
        self.refresh()
        return dict(self._mapping)

    def resolve(self, symbol: str) -> SymbolSpec:
        """Accept a canonical pair (``EURUSD``) or an exact broker name (``EURUSD.r``)."""
        if not _SYMBOL_RE.match(symbol):
            raise SymbolNotFoundError(f"Invalid symbol format: {symbol!r}")
        self.refresh()
        if symbol in self._specs:
            return self._specs[symbol]
        key = symbol.upper()
        mapping = self._mapping.get(key)
        if mapping is None:
            # Not in the configured universe: allow an unambiguous canonical match anyway.
            mapping = build_mapping([key], self._specs.values(), self._overrides)[key]
        if mapping.status is MappingStatus.AMBIGUOUS:
            raise SymbolAmbiguousError(
                f"{key} matches several broker symbols {mapping.candidates}; set SYMBOL_MAP_OVERRIDES"
            )
        if mapping.status is MappingStatus.MISSING or mapping.broker_symbol is None:
            raise SymbolNotFoundError(f"No Forex symbol for {symbol!r} at this broker")
        return self._specs[mapping.broker_symbol]

    def ensure_selected(self, spec: SymbolSpec) -> None:
        """Make sure the symbol is in Market Watch so the terminal serves its data."""
        info = self._connector.run(lambda a: a.symbol_info(spec.name))
        if info is None:
            raise SymbolNotFoundError(f"Broker no longer reports symbol {spec.name!r}")
        if info.get("visible"):
            return
        if not self._connector.run(lambda a: a.symbol_select(spec.name, True)):
            code, msg = self._connector.last_error()
            raise BrokerDataError(f"Could not select {spec.name} in Market Watch: [{code}] {msg}")
