#!/usr/bin/env python3
"""Picframe Config Editor — a warm little web app for tweaking your photo frame."""

import copy
import os
import shutil
import subprocess
from pathlib import Path

import yaml
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

CONFIG_PATH = Path(os.environ.get(
    "PICFRAME_CONFIG",
    os.path.expanduser("~/picframe_data/config/configuration.yaml"),
))

# Settings metadata: defines what shows up in the curated editor.
# Each entry: (yaml_key, label, input_type, extra)
# input_type: "toggle", "slider", "number", "text", "select", "checkboxes"
# extra: dict with min, max, step, options, etc.
SETTINGS_SCHEMA = {
    "Slideshow": {
        "section": "model",
        "icon": "slideshow",
        "fields": [
            ("time_delay", "Time Between Photos (s)", "slider", {"min": 5, "max": 600, "step": 5}),
            ("fade_time", "Crossfade Duration (s)", "slider", {"min": 0.5, "max": 30, "step": 0.5}),
            ("shuffle", "Shuffle Photos", "toggle", {}),
            ("recent_n", "Prioritize Recent (days)", "number", {"min": 0, "max": 365}),
        ],
    },
    "Display": {
        "section": "viewer",
        "icon": "display",
        "fields": [
            ("blur_amount", "Background Blur", "slider", {"min": 0, "max": 40, "step": 1}),
            ("blur_zoom", "Blur Zoom", "slider", {"min": 1.0, "max": 3.0, "step": 0.1}),
            ("blur_edges", "Blur Edges", "toggle", {}),
            ("edge_alpha", "Edge Reflection", "slider", {"min": 0, "max": 1, "step": 0.05}),
            ("fit", "Fit (show full image)", "toggle", {}),
            ("kenburns", "Ken Burns Effect", "toggle", {}),
            ("fps", "Frame Rate", "number", {"min": 5, "max": 60}),
        ],
    },
    "Text Overlay": {
        "section": "viewer",
        "icon": "text",
        "fields": [
            ("show_text", "Show Text Fields", "text", {}),
            ("show_text_sz", "Text Size", "slider", {"min": 10, "max": 100, "step": 2}),
            ("show_text_tm", "Text Display Time (s)", "number", {"min": 0, "max": 60}),
            ("show_text_fm", "Date Format", "text", {}),
            ("text_justify", "Text Alignment", "select", {"options": ["L", "C", "R"]}),
            ("text_opacity", "Text Opacity", "slider", {"min": 0, "max": 1, "step": 0.05}),
        ],
    },
    "Mat & Framing": {
        "section": "viewer",
        "icon": "frame",
        "fields": [
            ("mat_images", "Auto-Mat Threshold", "slider", {"min": 0, "max": 1, "step": 0.01}),
            ("outer_mat_border", "Outer Mat Border (px)", "number", {"min": 0, "max": 200}),
            ("inner_mat_border", "Inner Mat Border (px)", "number", {"min": 0, "max": 200}),
            ("outer_mat_use_texture", "Outer Mat Texture", "toggle", {}),
            ("inner_mat_use_texture", "Inner Mat Texture", "toggle", {}),
        ],
    },
    "Photos": {
        "section": "model",
        "icon": "photos",
        "fields": [
            ("pic_dir", "Photos Directory", "text", {}),
            ("subdirectory", "Subdirectory Filter", "text", {}),
            ("sort_cols", "Sort Order", "text", {}),
            ("location_filter", "Location Filter", "text", {}),
            ("tags_filter", "Tags Filter", "text", {}),
        ],
    },
    "Clock": {
        "section": "viewer",
        "icon": "clock",
        "fields": [
            ("show_clock", "Show Clock", "toggle", {}),
            ("clock_format", "Clock Format", "text", {}),
            ("clock_text_sz", "Clock Size", "slider", {"min": 20, "max": 300, "step": 10}),
            ("clock_justify", "Clock Position", "select", {"options": ["L", "C", "R"]}),
            ("clock_opacity", "Clock Opacity", "slider", {"min": 0, "max": 1, "step": 0.05}),
            ("clock_top_bottom", "Clock Placement", "select", {"options": ["T", "B"]}),
        ],
    },
}


def read_config() -> dict:
    """Read and parse the YAML config file."""
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def write_config(config: dict) -> None:
    """Back up existing config and write new one."""
    backup = CONFIG_PATH.with_suffix(".yaml.bak")
    if CONFIG_PATH.exists():
        shutil.copy2(CONFIG_PATH, backup)
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def read_config_raw() -> str:
    """Read config file as raw text."""
    with open(CONFIG_PATH) as f:
        return f.read()


def write_config_raw(raw_yaml: str) -> None:
    """Validate and write raw YAML config."""
    # Validate it parses
    yaml.safe_load(raw_yaml)
    # Back up
    backup = CONFIG_PATH.with_suffix(".yaml.bak")
    if CONFIG_PATH.exists():
        shutil.copy2(CONFIG_PATH, backup)
    with open(CONFIG_PATH, "w") as f:
        f.write(raw_yaml)


@app.route("/")
def index():
    config = read_config()
    raw_yaml = read_config_raw()
    current_transform = get_current_transform()
    return render_template(
        "index.html",
        config=config,
        raw_yaml=raw_yaml,
        schema=SETTINGS_SCHEMA,
        current_transform=current_transform,
    )


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(read_config())


@app.route("/api/config", methods=["POST"])
def save_config():
    """Save curated settings — merges incoming JSON into existing config."""
    try:
        incoming = request.get_json()
        config = read_config()
        # incoming is structured as {section: {key: value}}
        for section, values in incoming.items():
            if section in config and isinstance(values, dict):
                for key, val in values.items():
                    config[section][key] = val
        write_config(config)
        return jsonify({"status": "ok", "message": "Settings saved"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/config/raw", methods=["POST"])
def save_raw_config():
    """Save raw YAML config."""
    try:
        raw = request.get_json().get("yaml", "")
        write_config_raw(raw)
        return jsonify({"status": "ok", "message": "YAML saved"})
    except yaml.YAMLError as e:
        return jsonify({"status": "error", "message": f"Invalid YAML: {e}"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


WLR_RANDR_ENV = {
    "WAYLAND_DISPLAY": "wayland-0",
    "XDG_RUNTIME_DIR": "/run/user/1000",
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
}


def get_current_transform() -> str:
    """Get the current display transform via wlr-randr."""
    try:
        result = subprocess.run(
            ["wlr-randr"],
            capture_output=True, text=True, timeout=5,
            env={**os.environ, **WLR_RANDR_ENV},
        )
        for line in result.stdout.splitlines():
            if "Transform:" in line:
                return line.split("Transform:")[1].strip()
    except Exception:
        pass
    return "normal"


@app.route("/api/rotation", methods=["GET"])
def get_rotation():
    return jsonify({"transform": get_current_transform()})


@app.route("/api/rotation", methods=["POST"])
def set_rotation():
    """Set display rotation via wlr-randr."""
    try:
        transform = request.get_json().get("transform", "normal")
        valid = {"normal", "90", "180", "270", "flipped", "flipped-90", "flipped-180", "flipped-270"}
        if transform not in valid:
            return jsonify({"status": "error", "message": f"Invalid transform: {transform}"}), 400
        result = subprocess.run(
            ["wlr-randr", "--output", "HDMI-A-1", "--transform", transform],
            capture_output=True, text=True, timeout=5,
            env={**os.environ, **WLR_RANDR_ENV},
        )
        if result.returncode == 0:
            return jsonify({"status": "ok", "message": f"Rotated to {transform}"})
        return jsonify({"status": "error", "message": result.stderr}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/restart", methods=["POST"])
def restart_picframe():
    """Restart the picframe systemd service."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "restart", "picframe.service"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return jsonify({"status": "ok", "message": "Picframe restarting..."})
        return jsonify({"status": "error", "message": result.stderr}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
