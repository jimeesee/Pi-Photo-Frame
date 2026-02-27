# Config Editor Web App — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A visually appealing web app on the Pi to edit picframe's configuration.yaml with curated settings + raw YAML editor.

**Architecture:** Standalone Flask app serving a single Jinja2 template. Reads/writes `~/picframe_data/config/configuration.yaml`. Runs on port 8080 as a systemd user service. Single HTML page with inline CSS/SVG for the warm & cozy aesthetic.

**Tech Stack:** Flask, PyYAML, Jinja2, vanilla JS, CSS3, SVG (all already installed on Pi)

**Pi Access:** `ssh pi@100.69.61.25`

---

### Task 1: Create Flask app with config read/write backend

**Files:**
- Create: `config_editor/app.py`
- Create: `config_editor/templates/index.html` (placeholder)

**Step 1: Write app.py**

Flask app with these routes:
- `GET /` — render the editor page, passing parsed YAML config
- `GET /api/config` — return full config as JSON
- `POST /api/config` — accept JSON, write to YAML (with backup)
- `POST /api/config/raw` — accept raw YAML string, validate and write (with backup)
- `POST /api/restart` — restart picframe systemd service

Config path: `~/picframe_data/config/configuration.yaml`
Backup: copy to `configuration.yaml.bak` before every write
Bind to `0.0.0.0:8080`

**Step 2: Write minimal placeholder template**

Just enough to verify Flask serves pages.

**Step 3: Test locally on Mac**

```bash
cd config_editor && python3 app.py
# Visit http://localhost:8080 — should see placeholder
```

**Step 4: Commit**

```bash
git add config_editor/
git commit -m "feat: config editor Flask backend with read/write API"
```

---

### Task 2: Build the curated settings frontend

**Files:**
- Modify: `config_editor/templates/index.html`

**Step 1: Build the full HTML page**

Single file containing:
- Inline CSS with warm & cozy theme (cream background, amber accents, soft shadows)
- SVG decorative corner flourishes on setting cards (picture-frame inspired)
- Setting cards organized by category:
  - **Slideshow**: time_delay (slider), fade_time (slider), shuffle (toggle), recent_n (number)
  - **Display**: blur_amount (slider 0-40), blur_edges (toggle), blur_zoom (slider), edge_alpha (slider 0-1), kenburns (toggle), fit (toggle), fps (number)
  - **Text Overlay**: show_text (multi-select checkboxes for title/caption/name/date/folder/location), show_text_sz (slider), show_text_tm (number), text_justify (dropdown L/C/R), text_opacity (slider)
  - **Mat & Framing**: mat_images (slider 0-1), outer_mat_border (number), inner_mat_border (number), outer_mat_use_texture (toggle), inner_mat_use_texture (toggle)
  - **Photos**: pic_dir (text), subdirectory (text), shuffle (already above), sort_cols (text)
- Input types: toggle switches for booleans, range sliders for numbers with min/max, text inputs for strings, dropdowns for enums
- "Save Settings" button that POSTs JSON to `/api/config`
- "Restart Picframe" button that POSTs to `/api/restart`
- Success/error toast notifications
- Tab or toggle to switch between "Settings" and "Advanced (YAML)" views

**Step 2: Build the Advanced YAML view**

- Full-width monospace textarea pre-populated with raw YAML
- "Save YAML" button that POSTs to `/api/config/raw`
- Warning text: "Edit carefully — invalid YAML will be rejected"

**Step 3: Add JavaScript**

- `loadConfig()` — fetch from `/api/config`, populate all form fields
- `saveConfig()` — gather all form values, POST to `/api/config`
- `saveRawYaml()` — POST textarea content to `/api/config/raw`
- `restartPicframe()` — POST to `/api/restart` with confirmation dialog
- `showToast(message, type)` — animated toast notification
- Toggle between curated/advanced views

**Step 4: Test in browser**

Open http://localhost:8080, verify:
- All settings render correctly from config
- Changing a toggle and saving works
- Changing a slider and saving works
- Advanced YAML view shows full config
- Restart button prompts for confirmation

**Step 5: Commit**

```bash
git add config_editor/templates/index.html
git commit -m "feat: config editor frontend with curated settings and YAML editor"
```

---

### Task 3: Deploy to Pi and create systemd service

**Files:**
- Create: `config_editor/config_editor.service`

**Step 1: Write systemd service file**

```ini
[Unit]
Description=Picframe Config Editor Web App
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/pi/config_editor
ExecStart=/usr/bin/python3 /home/pi/config_editor/app.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

**Step 2: Deploy files to Pi**

```bash
scp -r config_editor/ pi@100.69.61.25:~/config_editor/
```

**Step 3: Install and start service**

```bash
ssh pi@100.69.61.25 "cp ~/config_editor/config_editor.service ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user enable config_editor.service && systemctl --user start config_editor.service"
```

**Step 4: Verify via browser**

Visit http://100.69.61.25:8080 from Mac browser. Verify all settings load from the Pi's actual config.

**Step 5: Test save**

Change fade_time, save, verify the YAML file was updated on Pi:
```bash
ssh pi@100.69.61.25 "grep fade_time ~/picframe_data/config/configuration.yaml"
```

**Step 6: Commit**

```bash
git add config_editor/config_editor.service
git commit -m "feat: config editor systemd service for Pi deployment"
```

---

### Task 4: End-to-end testing and polish

**Step 1: Test on mobile**

Open http://100.69.61.25:8080 on phone, verify responsive layout works.

**Step 2: Test restart button**

Click "Restart Picframe", verify picframe restarts:
```bash
ssh pi@100.69.61.25 "systemctl --user status picframe.service --no-pager"
```

**Step 3: Test advanced YAML editor**

Edit raw YAML, save, verify changes persisted.

**Step 4: Test backup**

Verify configuration.yaml.bak exists after a save.

**Step 5: Screenshot for verification**

Take Pi screenshot to confirm picframe still running after config changes.

**Step 6: Commit and push**

```bash
git add -A
git commit -m "feat: config editor complete with curated settings and YAML editor"
git push
```
