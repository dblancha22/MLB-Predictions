"""Shared MLB Stats API transport with run-scoped response caching."""

from __future__ import annotations

import json
import logging
import time
from datetime import date
from typing import Any, Dict, Mapping, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .common import IngestionError


MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_BOXSCORE_URL = "https://statsapi.mlb.com/api/v1/game/{game_id}/boxscore"
MLB_VENUE_URL = "https://statsapi.mlb.com/api/v1/venues/{venue_id}"
MLB_PERSON_URL = "https://statsapi.mlb.com/api/v1/people/{person_id}"
LOGGER = logging.getLogger("ingestion.mlb")


def request_json(
    url: str,
    params: Mapping[str, Any],
    timeout: float,
    retries: int,
    logger: logging.Logger = LOGGER,
) -> Dict[str, Any]:
    """Request one MLB JSON object with bounded exponential-backoff retries."""
    request_url = f"{url}?{urlencode(params)}" if params else url
    request = Request(
        request_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "MLB-Predictions-ingestion/1.0",
        },
    )
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                if not 200 <= response.status < 300:
                    raise IngestionError(
                        f"MLB Stats API returned HTTP {response.status} for {request_url}"
                    )
                payload = json.load(response)
                if not isinstance(payload, dict):
                    raise IngestionError("MLB Stats API response was not a JSON object")
                return payload
        except HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code < 600
            if not retryable or attempt >= retries:
                raise IngestionError(
                    f"MLB Stats API returned HTTP {exc.code} for {request_url}"
                ) from exc
        except (URLError, TimeoutError) as exc:
            if attempt >= retries:
                raise IngestionError(
                    f"MLB Stats API request failed for {request_url}: {exc}"
                ) from exc
        delay = 2**attempt
        logger.warning("MLB request failed; retrying in %s second(s)", delay)
        time.sleep(delay)
    raise AssertionError("retry loop exited unexpectedly")


class MLBStatsClient:
    """MLB client whose successful responses are cached for one command run."""

    def __init__(self, timeout: float = 30.0, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries
        self._cache: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], Dict[str, Any]] = {}
        self._failures: Dict[
            Tuple[str, Tuple[Tuple[str, str], ...]], Exception
        ] = {}
        self.requests_made = 0
        self.cache_hits = 0

    @staticmethod
    def _key(
        url: str, params: Mapping[str, Any]
    ) -> Tuple[str, Tuple[Tuple[str, str], ...]]:
        return url, tuple(sorted((str(key), str(value)) for key, value in params.items()))

    def get(self, url: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        key = self._key(url, params)
        if key in self._cache:
            self.cache_hits += 1
            return self._cache[key]
        if key in self._failures:
            self.cache_hits += 1
            raise self._failures[key]
        self.requests_made += 1
        try:
            payload = request_json(url, params, self.timeout, self.retries)
        except Exception as exc:
            self._failures[key] = exc
            raise
        self._cache[key] = payload
        return payload

    def fetch_schedule_range(
        self,
        start_date: date,
        end_date: date,
        game_type: str = "R",
        hydrate: str = "venue,team",
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "sportId": 1,
            "gameType": game_type,
            "hydrate": hydrate,
        }
        if start_date == end_date:
            params["date"] = start_date.isoformat()
        else:
            params["startDate"] = start_date.isoformat()
            params["endDate"] = end_date.isoformat()
        return self.get(MLB_SCHEDULE_URL, params)

    def fetch_boxscore(self, game_id: int, *_unused: Any) -> Dict[str, Any]:
        return self.get(MLB_BOXSCORE_URL.format(game_id=game_id), {})

    def fetch_venue(self, venue_id: int, *_unused: Any) -> Mapping[str, Any]:
        payload = self.get(
            MLB_VENUE_URL.format(venue_id=venue_id), {"hydrate": "location"}
        )
        venues = payload.get("venues")
        if not isinstance(venues, list) or not venues:
            raise IngestionError(
                f"MLB venue endpoint returned no venue for venue_id={venue_id}"
            )
        venue = venues[0]
        if not isinstance(venue, Mapping) or venue.get("id") is None:
            raise IngestionError(
                f"MLB venue endpoint returned an invalid venue for venue_id={venue_id}"
            )
        if int(venue["id"]) != venue_id:
            raise IngestionError(
                f"MLB venue endpoint returned venue_id={venue['id']} "
                f"for requested venue_id={venue_id}"
            )
        return venue

    def fetch_person(self, person_id: int, *_unused: Any) -> Dict[str, Any]:
        return self.get(MLB_PERSON_URL.format(person_id=person_id), {})


def schedule_payloads_by_date(
    payload: Mapping[str, Any], requested_dates: Tuple[date, ...]
) -> Dict[date, Dict[str, Any]]:
    """Split a range schedule response without losing MLB source-date grouping."""
    by_date: Dict[date, Dict[str, Any]] = {
        requested: {"dates": []} for requested in requested_dates
    }
    for entry in payload.get("dates", []):
        if not isinstance(entry, Mapping):
            continue
        raw_date = entry.get("date")
        if raw_date is None:
            continue
        try:
            source_date = date.fromisoformat(str(raw_date))
        except ValueError as exc:
            raise IngestionError(f"invalid MLB schedule date {raw_date!r}") from exc
        if source_date in by_date:
            by_date[source_date]["dates"].append(dict(entry))
    return by_date
