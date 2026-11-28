"""Stand-in for the ESP32 water probe: publishes SIMULATED readings over MQTT, like the real gateway will.

    python scripts/fake_esp32.py --tank tank-a --every 60 [--count 5]
    env: MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASSWORD

Each round sends one batch (a JSON list) to fishut/readings/<tank>-water with one reading per water
sensor. Values come from the same model as the dashboard simulator; raw_payload marks them simulated.
"""
import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.catalog import METRICS  # noqa: E402
from app.services.simulator import _values  # noqa: E402

WATER = [m for m, spec in METRICS.items() if spec["source"] == "water"]


def batch(tank: str, rng: random.Random, seq: int) -> list[dict]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    values = _values(now, rng, day_offset=0.0, turbidity=25 + rng.gauss(0, 2))
    return [
        {"sensor_id": f"{tank}-{m}", "value": values[m], "observed_at": now.isoformat(), "sequence_no": seq,
         "raw_payload": {"simulated": True, "device": "fake_esp32"}}
        for m in WATER
    ]


def main() -> None:
    import paho.mqtt.client as mqtt

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tank", default="tank-a")
    ap.add_argument("--every", type=float, default=60, help="seconds between batches")
    ap.add_argument("--count", type=int, default=0, help="stop after this many batches (0 = run forever)")
    args = ap.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"fake-esp32-{args.tank}")
    client.username_pw_set(os.environ.get("MQTT_USER"), os.environ.get("MQTT_PASSWORD"))
    client.connect(os.environ.get("MQTT_HOST", "127.0.0.1"), int(os.environ.get("MQTT_PORT", "1883")))
    client.loop_start()
    rng, seq, sent = random.Random(), int(time.time()), 0
    topic = f"fishut/readings/{args.tank}-water"
    try:
        while True:
            msg = client.publish(topic, json.dumps(batch(args.tank, rng, seq)), qos=1)
            msg.wait_for_publish(timeout=10)
            print(f"sent {len(WATER)} readings to {topic} (seq {seq})", flush=True)
            seq, sent = seq + 1, sent + 1
            if sent == args.count:
                break
            time.sleep(args.every)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
