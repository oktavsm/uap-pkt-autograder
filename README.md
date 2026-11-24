# UAP Packet Tracer Autograder

Offline semantic autograder for Cisco Packet Tracer (`.pkt` / `.pka`) networking exams, built for fast batch evaluation of hundreds of student submissions via CLI or a lightweight web workbench.

## Features

- **Offline `.pkt` / `.pka` decoding** (Packet Tracer 5.3 through 9.0.1) without launching Packet Tracer GUI.
- **Semantic IOS verification** instead of brittle raw `show run` text diffs:
  - Topology device & 5-link cable verification (`PC1`, `PC2`, `S1`, `R1`, `R2`, `Server1`).
  - Switch `S1`: VLAN 10 & 20 creation, `Fa0/1` access VLAN 10, `Fa0/2` access VLAN 20, `Gi0/1` trunk & allowed VLANs.
  - Router `R1`: base IP & subinterface integrity, DHCP excluded addresses (`.1-.10`), DHCP pools for VLAN 10 & 20 (arbitrary pool names accepted), static route to LAN B (`192.168.30.0/24`).
  - Router `R2` & `Server1`: base IP integrity and static routes to VLAN 10 & VLAN 20.
  - Runtime end-device verification: confirms `PC1` and `PC2` enabled DHCP and obtained valid leases (`192.168.10.11-254` and `192.168.20.11-254`).
  - Configuration persistence check (`write memory` / `startup-config`).
- **Batch CLI**: accepts single files, multiple files, folders, and `.zip` archives; prints a summary table and exports CSV (Excel-ready UTF-8 BOM) and JSON.
- **Web Workbench**: drag-and-drop `.zip` and/or multi-file upload, editable rubric weights, instant search and status filtering, per-student diagnostic inspector with `show running-config` viewer, and one-click CSV/JSON download.

## Quickstart (CLI)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Grade a folder or ZIP of student submissions and export CSV
pkt-grade submissions.zip --csv nilai_uap.csv

# Grade multiple files with verbose error output
pkt-grade UAP_245150600111001_Budi.pkt UAP_245150600111002_Siti.pkt --csv hasil.csv -v

# Use a custom rubric file
pkt-grade ./submissions --rubric rubric.default.json --csv hasil.csv --json hasil.json
```

## Quickstart (Web Workbench - Local)

```bash
# 1. Build frontend
cd web
npm install
npm run build
cd ..

# 2. Start server (serves both API and UI on port 8000)
pkt-grade-web
# Open http://localhost:8000
```

For frontend hot-reload development:

```bash
# Terminal 1: API
uvicorn pkt_grader.server:app --reload --port 8000

# Terminal 2: Vite dev server (proxies /api -> localhost:8000)
cd web && npm run dev
```

## Deploy on a VM (Docker)

```bash
docker compose up -d --build
# Accessible at http://<vm-ip>:8000
```

## Running Tests

```bash
pip install -e ".[dev]"
pytest -v
```
