import json

import pytest

from scripts import mqtt_bridge
from scripts.mqtt_bridge import handle


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(mqtt_bridge.time, "sleep", lambda s: None)


class FakeApi:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.sent = []

    def __call__(self, reading):
        self.sent.append(reading)
        r = self.responses.pop(0) if self.responses else 201
        if isinstance(r, Exception):
            raise r
        return r


READING = {"sensor_id": "tank-a-ph", "value": 7.4, "observed_at": "2026-11-28T06:00:00Z"}


def test_posts_one_reading_or_a_batch():
    api = FakeApi()
    handle(json.dumps(READING).encode(), api)
    handle(json.dumps([READING, {**READING, "value": 7.5}]).encode(), api)
    assert [r["value"] for r in api.sent] == [7.4, 7.4, 7.5]


def test_retries_until_the_api_stores_it():
    api = FakeApi(OSError("connection refused"), 503, 201)
    handle(json.dumps(READING).encode(), api)
    assert len(api.sent) == 3


def test_duplicate_and_rejected_readings_are_not_retried():
    api = FakeApi(409, 404, 422)
    handle(json.dumps([READING, READING, READING]).encode(), api)
    assert len(api.sent) == 3


def test_bad_messages_are_dropped():
    api = FakeApi()
    handle(b"not json", api)
    handle(b"[1, 2]", api)
    assert api.sent == []
