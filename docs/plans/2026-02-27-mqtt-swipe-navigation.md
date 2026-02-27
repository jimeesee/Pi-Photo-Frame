# MQTT Swipe Navigation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace fragile xdotool key injection with MQTT messaging so swipe-to-navigate works reliably, even during video playback.

**Architecture:** Install mosquitto broker locally on the Pi. Enable picframe's built-in MQTT support pointed at localhost. Replace `inject_keys()` in touch_daemon.py with paho-mqtt publish calls to picframe's navigation topics.

**Tech Stack:** mosquitto (MQTT broker), paho-mqtt (Python client), picframe built-in MQTT, evdev (unchanged)

**Pi Access:** `ssh pi@raspberrypi.local` (password: `RoryMoose8887`)

**Screenshot command:** `ssh pi@raspberrypi.local "WAYLAND_DISPLAY=wayland-1 XDG_RUNTIME_DIR=/run/user/1000 grim /tmp/screenshot.png" && scp pi@raspberrypi.local:/tmp/screenshot.png /tmp/pi_screenshot.png`

**MQTT Topics:**
- Next photo: `homeassistant/button/picframe_next/set` payload `ON`
- Back photo: `homeassistant/button/picframe_back/set` payload `ON`

---

### Task 1: Take baseline screenshot

**Purpose:** Verify SSH access and screenshot pipeline work. Capture current photo on screen for comparison later.

**Step 1: Screenshot the Pi display**

```bash
ssh pi@raspberrypi.local "WAYLAND_DISPLAY=wayland-1 XDG_RUNTIME_DIR=/run/user/1000 grim /tmp/screenshot.png" && scp pi@raspberrypi.local:/tmp/screenshot.png /tmp/pi_screenshot.png
```

View `/tmp/pi_screenshot.png` to confirm it shows the photo frame.

**Step 2: Check current service status**

```bash
ssh pi@raspberrypi.local "systemctl --user status picframe.service --no-pager; systemctl --user status touch_daemon.service --no-pager"
```

---

### Task 2: Install and configure mosquitto broker

**Step 1: Install mosquitto on the Pi**

```bash
ssh pi@raspberrypi.local "sudo apt-get update && sudo apt-get install -y mosquitto mosquitto-clients"
```

**Step 2: Configure mosquitto for local-only, no-auth access**

```bash
ssh pi@raspberrypi.local "sudo tee /etc/mosquitto/conf.d/local.conf > /dev/null << 'EOF'
listener 1883 localhost
allow_anonymous true
EOF"
```

**Step 3: Start and enable mosquitto**

```bash
ssh pi@raspberrypi.local "sudo systemctl enable mosquitto && sudo systemctl restart mosquitto"
```

**Step 4: Verify mosquitto is running**

```bash
ssh pi@raspberrypi.local "systemctl status mosquitto --no-pager"
```

**Step 5: Test mosquitto pub/sub round-trip**

```bash
# In one command: subscribe in background, publish, check output
ssh pi@raspberrypi.local "timeout 3 mosquitto_sub -h localhost -t test/ping &; sleep 1; mosquitto_pub -h localhost -t test/ping -m hello; wait" 2>/dev/null
```

Expected: `hello` printed to stdout.

---

### Task 3: Enable MQTT in picframe configuration

**Files:**
- Modify: `~/picframe_data/config/configuration.yaml` on the Pi (mqtt section)

**Step 1: Update picframe config to enable MQTT with localhost**

```bash
ssh pi@raspberrypi.local "cd ~/picframe_data/config && cp configuration.yaml configuration.yaml.bak"
```

Then edit the mqtt section to:
```yaml
mqtt:
  use_mqtt: True
  server: "localhost"
  port: 1883
  login: ""
  password: ""
  tls: ""
  device_id: "picframe"
```

**Step 2: Restart picframe**

```bash
ssh pi@raspberrypi.local "systemctl --user restart picframe.service"
```

**Step 3: Wait for picframe to start, then screenshot**

Wait ~10 seconds for picframe to initialize, then take a screenshot to verify it's still running.

**Step 4: Check picframe logs for MQTT connection**

```bash
ssh pi@raspberrypi.local "journalctl --user -u picframe.service --no-pager -n 30"
```

Look for MQTT connection success (no errors about MQTT).

---

### Task 4: Test MQTT navigation manually

**Purpose:** Verify picframe responds to MQTT next/back commands before touching the touch daemon.

**Step 1: Screenshot current photo (before)**

Take screenshot, note which photo is displayed.

**Step 2: Send "next" via mosquitto_pub**

```bash
ssh pi@raspberrypi.local "mosquitto_pub -h localhost -t 'homeassistant/button/picframe_next/set' -m 'ON'"
```

**Step 3: Wait for transition and screenshot (after)**

Wait ~3 seconds (fade_time is 2.0), then screenshot. Verify a different photo is now displayed.

**Step 4: Send "back" via mosquitto_pub**

```bash
ssh pi@raspberrypi.local "mosquitto_pub -h localhost -t 'homeassistant/button/picframe_back/set' -m 'ON'"
```

**Step 5: Screenshot and verify original photo returned**

Take screenshot and verify it matches the photo from Step 1.

---

### Task 5: Update touch_daemon.py to use MQTT

**Files:**
- Modify: `/home/pi/touch_daemon/touch_daemon.py` on the Pi
- Also update: `/Users/jimboslice/codex-projects/Pi_Photo_Frame/Claude Rework/touch_daemon.py` (local copy)

**Step 1: Install paho-mqtt in touch daemon venv**

```bash
ssh pi@raspberrypi.local "~/touch_daemon_venv/bin/pip install paho-mqtt"
```

**Step 2: Rewrite touch_daemon.py**

Replace `inject_keys()` (xdotool subprocess calls) with MQTT publish. Remove xdotool dependency entirely.

Key changes:
- Remove `import subprocess` (no longer needed for key injection)
- Add `import paho.mqtt.publish as mqtt_publish`
- Replace `inject_keys()` with `publish_navigation()` that publishes to the appropriate MQTT topic
- Remove xdotool version check from `run()`
- Add `--mqtt-host` and `--mqtt-port` CLI args (default localhost:1883)
- Swipe left (direction=-1) = next photo = publish to `homeassistant/button/picframe_next/set`
- Swipe right (direction=+1) = back photo = publish to `homeassistant/button/picframe_back/set`
- For key_count > 1 (velocity-scaled), publish multiple times with interval

New `publish_navigation()`:
```python
def publish_navigation(direction: int, count: int, interval: float,
                       mqtt_host: str, mqtt_port: int) -> None:
    topic = (f"homeassistant/button/picframe_{'next' if direction == -1 else 'back'}/set")
    for i in range(count):
        mqtt_publish.single(topic, payload="ON",
                            hostname=mqtt_host, port=mqtt_port)
        if i < count - 1:
            time.sleep(interval)
```

Note: direction mapping — swipe left on screen (direction=-1, negative delta) = "next", swipe right (direction=+1) = "back". This matches the existing behavior where the user swipes in the direction they want photos to "come from".

**Step 3: Deploy to Pi**

```bash
scp "/Users/jimboslice/codex-projects/Pi_Photo_Frame/Claude Rework/touch_daemon.py" pi@raspberrypi.local:~/touch_daemon/touch_daemon.py
```

**Step 4: Restart touch daemon**

```bash
ssh pi@raspberrypi.local "systemctl --user restart touch_daemon.service"
```

**Step 5: Verify touch daemon started without errors**

```bash
ssh pi@raspberrypi.local "systemctl --user status touch_daemon.service --no-pager; journalctl --user -u touch_daemon.service --no-pager -n 20"
```

---

### Task 6: Update touch_daemon.service (remove DISPLAY dependency)

**Files:**
- Modify: `~/.config/systemd/user/touch_daemon.service` on the Pi

**Step 1: Remove X11 environment from service file**

The `Environment=DISPLAY=:0` line is no longer needed since we're not using xdotool. Remove it. Also remove `ExecStartPre=/bin/sleep 5` — we no longer need to wait for Xwayland.

Replace service with:
```ini
[Unit]
Description=Touch Swipe Daemon for Pi Photo Frame
After=network.target

[Service]
Type=simple
ExecStart=/home/pi/touch_daemon_venv/bin/python3 /home/pi/touch_daemon/touch_daemon.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

**Step 2: Reload and restart**

```bash
ssh pi@raspberrypi.local "systemctl --user daemon-reload && systemctl --user restart touch_daemon.service"
```

**Step 3: Verify it's running**

```bash
ssh pi@raspberrypi.local "systemctl --user status touch_daemon.service --no-pager"
```

---

### Task 7: End-to-end verification via simulated MQTT (no physical touch needed)

**Step 1: Screenshot before**

Take screenshot of current photo.

**Step 2: Simulate what touch daemon does — publish MQTT next**

```bash
ssh pi@raspberrypi.local "mosquitto_pub -h localhost -t 'homeassistant/button/picframe_next/set' -m 'ON'"
```

**Step 3: Screenshot after and verify photo changed**

**Step 4: Publish back**

```bash
ssh pi@raspberrypi.local "mosquitto_pub -h localhost -t 'homeassistant/button/picframe_back/set' -m 'ON'"
```

**Step 5: Screenshot and verify original photo**

**Step 6: Check touch daemon logs for any errors**

```bash
ssh pi@raspberrypi.local "journalctl --user -u touch_daemon.service --no-pager -n 30"
```

---

### Task 8: Video playback edge case test

**Purpose:** Verify MQTT navigation works even during/after video playback (the whole reason for this migration).

**Step 1: Check if there are any videos in the photo collection**

```bash
ssh pi@raspberrypi.local "find ~/Pictures -type f \( -name '*.mp4' -o -name '*.mov' -o -name '*.avi' \) | head -5"
```

If videos exist, wait for one to play (or rapidly advance with `mosquitto_pub` until a video appears), then try navigating during playback.

**Step 2: Send next during video playback**

```bash
ssh pi@raspberrypi.local "mosquitto_pub -h localhost -t 'homeassistant/button/picframe_next/set' -m 'ON'"
```

**Step 3: Screenshot and verify it advanced past the video**

This should work because MQTT bypasses X11 focus entirely.

---

### Task 9: Cleanup and commit

**Step 1: Update local copies to match deployed versions**

Ensure the local `Claude Rework/` files match what's on the Pi.

**Step 2: Update memory files**

Update `swipe-navigation.md` to reflect MQTT approach is now working.

**Step 3: Commit**

```bash
cd /Users/jimboslice/codex-projects/Pi_Photo_Frame
git add "Claude Rework/touch_daemon.py" "Claude Rework/touch_daemon.service"
git commit -m "feat: replace xdotool with MQTT for reliable swipe navigation"
```
