"""Tiny JSON-file store. Free-tier default; swap for Supabase later without
changing agent code by reimplementing load()/save() against a real DB."""
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load(name: str) -> dict:
    path = DATA_DIR / f"{name}.json"
    with open(path, "r") as f:
        return json.load(f)


def save(name: str, data: dict) -> None:
    path = DATA_DIR / f"{name}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def load_config(name: str) -> dict:
    path = Path(__file__).resolve().parent.parent / "config" / f"{name}.json"
    with open(path, "r") as f:
        return json.load(f)


def save_config(name: str, data: dict) -> None:
    path = Path(__file__).resolve().parent.parent / "config" / f"{name}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
