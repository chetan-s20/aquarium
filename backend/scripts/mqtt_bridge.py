"""MQTT -> API bridge: devices publish readings to the broker; this stores them through POST /readings.

    python scripts/mqtt_bridge.py
    env: MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASSWORD, MQTT_TOPIC, API_URL, DEVICE_API_KEY

A message holds one reading or a list of readings, in the same JSON as POST /readings:
    {"sensor_id": "tank-a-ph", "value": 7.4, "observed_at": "2026-11-28T06:00:00Z", "sequence_no": 41}

Readings go through the API so validation, quality flags, duplicate checks and alerts stay in one place.
No reading is lost: QoS 1 + a persistent session, and paho acknowledges a QoS 1 message only after
on_message returns, which here is only once the API has stored or permanently rejected it. Redelivered
copies are harmless: the API answers 409 for a reading it already has.
"""
import json
import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger("mqtt_bridge")


def post_reading(api_url: str, key: str, reading: dict) -> int:
    """HTTP status from POST /readings. Raises OSError when the API can't be reached."""
    req = urllib.request.Request(
        f"{api_url}/readings", data=json.dumps(reading).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Device-Key": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def handle(payload: bytes, post) -> None:
    """Store every reading in one MQTT message. Blocks and retries while the API is down or failing."""
    try:
        data = json.loads(payload)
    except ValueError:
        log.error("dropped a message that is not JSON: %r", payload[:200])
        return
    for reading in data if isinstance(data, list) else [data]:
        if not isinstance(reading, dict):
            log.error("dropped an item that is not a reading object: %r", reading)
            continue
        delay = 1
        while True:
            try:
                status, problem = post(reading), None
            except OSError as e:
                status, problem = None, e
            if status is not None and status < 500:
                break
            log.warning("API is not storing readings (%s); retrying in %ss", problem or f"HTTP {status}", delay)
            time.sleep(delay)
            delay = min(delay * 2, 30)
        if status not in (200, 201, 409):  # 409 = already stored, e.g. a redelivered message
            log.error("API rejected %s with HTTP %s; reading dropped: %s", reading.get("sensor_id"), status, reading)


def main() -> None:
    import paho.mqtt.client as mqtt

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    api_url = os.environ.get("API_URL", "http://127.0.0.1:8000").rstrip("/")
    key = os.environ.get("DEVICE_API_KEY", "dev-device-key-change-me")
    topic = os.environ.get("MQTT_TOPIC", "fishut/readings/#")

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("broker refused the connection: %s", reason_code)
            return
        client.subscribe(topic, qos=1)
        log.info("listening on %s, storing to %s", topic, api_url)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="fishut-bridge", clean_session=False)
    client.username_pw_set(os.environ.get("MQTT_USER"), os.environ.get("MQTT_PASSWORD"))
    client.on_connect = on_connect
    client.on_message = lambda c, u, msg: handle(msg.payload, lambda r: post_reading(api_url, key, r))
    # connect_async: keep retrying if the broker starts after the bridge
    client.connect_async(os.environ.get("MQTT_HOST", "127.0.0.1"), int(os.environ.get("MQTT_PORT", "1883")), keepalive=60)
    client.loop_forever(retry_first_connection=True)


if __name__ == "__main__":
    main()
