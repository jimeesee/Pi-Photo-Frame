# Config Editor Web App — Design

**Goal:** A visually appealing web app to edit picframe's configuration.yaml, accessible from any device on the network.

**Architecture:** Standalone Flask app on the Pi, reads/writes configuration.yaml directly. Single HTML page with curated settings view + advanced raw YAML editor.

**Tech Stack:** Flask (Python), vanilla JS, CSS3 with SVG decorations, PyYAML

## Main View: Curated Settings

Organized into visual cards by category:
- **Slideshow** — time_delay, fade_time, shuffle, recent_n
- **Display** — blur_amount, blur_edges, kenburns, fit, fps, background color
- **Text Overlay** — show_text options, font size, format, opacity
- **Mat & Framing** — mat_images, mat_type, border sizes, textures
- **Photos** — pic_dir, subdirectory, sort order

Each card has a warm frame-like border with SVG decorative corners. Toggles for booleans, sliders for numeric ranges, dropdowns for enums.

## Advanced View: Raw YAML

Syntax-highlighted YAML editor (textarea with monospace font) for full config. Save button writes directly to the file.

## Key Behaviors

- Save backs up current config, writes new YAML, shows success toast
- Restart Picframe button — restarts systemd service to apply changes
- Accessible from any device on the network (phone, laptop)
- Runs on port 8080
- Responsive — works on phone

## Visual Style: Warm & Cozy

- Warm cream background with subtle paper texture (CSS)
- Cards with decorative SVG corner flourishes (picture-frame inspired)
- Amber/brown accent colors, soft rounded corners
- Soft shadows, living room aesthetic
