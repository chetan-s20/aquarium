"""The metrics this system records. One place, used by seed, simulator and tests.

Water sensors: dissolved oxygen (primary), temperature, pH, turbidity, ammonium. TDS is not used.
Camera metrics come from ml/fish_activity.py (OpenCV), posted like any sensor.

Thresholds are (low_critical, low_warning, high_warning, high_critical).
They are general warm-water pond guidance (Boyd 1982 and ICAR pond practice), NOT
species-validated limits; confirm with the farm's fisheries officer before relying on them.
"""

METRICS: dict[str, dict] = {
    "dissolved_oxygen": {
        "unit": "mg/L", "physical": (0.0, 20.0), "source": "water",
        "thresholds": (3.0, 5.0, None, None),
        "reference": "Boyd (1982): <3 mg/L stresses warm-water fish; keep >5 mg/L",
    },
    "temperature": {
        "unit": "degC", "physical": (0.0, 45.0), "source": "water",
        "thresholds": (20.0, 24.0, 32.0, 35.0),
        "reference": "Indian major carps grow best near 25-32 degC (Boyd 1982: 28-32)",
    },
    "ph": {
        "unit": "pH", "physical": (0.0, 14.0), "source": "water",
        "thresholds": (6.0, 6.5, 8.5, 9.0),
        "reference": "Pond pH 6.5-9, optimum 7.5-8.5 (ICAR pond management guidance)",
    },
    "turbidity": {
        "unit": "NTU", "physical": (0.0, 1000.0), "source": "water",
        "thresholds": (None, None, 50.0, 100.0),
        "reference": "Placeholder: no species-specific NTU limit found; tune per pond",
    },
    "ammonium": {
        "unit": "mg/L", "physical": (0.0, 50.0), "source": "water",
        "thresholds": (None, None, 0.5, 1.0),
        "reference": "Total ammonia (ammonium ion probe). Placeholder pond guidance: look above 0.5 mg/L; "
                     "the toxic NH3 share rises with pH and temperature (Emerson 1975), so confirm per species",
    },
    "fish_activity": {
        "unit": "% motion", "physical": (0.0, 100.0), "source": "camera",
        "thresholds": None,
        "reference": "Share of frame pixels moving (OpenCV MOG2); recorded, not alerted yet",
    },
    "surface_activity": {
        "unit": "% of motion", "physical": (0.0, 100.0), "source": "camera",
        "thresholds": None,
        "reference": "Share of motion in the top 20% of frame; rises when fish gasp at the surface (hypoxia)",
    },
}
