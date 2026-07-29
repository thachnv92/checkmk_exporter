# CheckMK Prometheus Exporter

Exports CheckMK dashboard view results for Prometheus scraping.

## Docker Hub Registry

- [https://hub.docker.com/r/thachnv92/checkmk_exporter](https://hub.docker.com/r/thachnv92/checkmk_exporter)
- **Image**: `thachnv92/checkmk_exporter`

## Overview

This exporter queries the CheckMK view API (`view.py`) and converts host and service metrics into Prometheus format.

## Endpoint

```text
http://$hostname/$dashboard/check_mk/view.py?view_name=allhosts&output_format=json&_username=$username&_secret=$secret
```

## Default Configuration

- **Exposed Port**: `9293`
- **Default View**: `allhosts`
- **Default Metric Name**: `checkmk_status`

## Environment Variables

| Variable | Description | Default |
| --- | --- | --- |
| `CHECKMK_HOSTNAME` | CheckMK server host / IP | |
| `CHECKMK_DASHBOARD` | CheckMK site or dashboard path | |
| `CHECKMK_USERNAME` | CheckMK API Username | |
| `CHECKMK_SECRET` | CheckMK Automation Secret / Password | |
| `CHECKMK_VIEW_NAME` | View name | `allhosts` |
| `CHECKMK_SERVER_NAME` | Bind IP | `0.0.0.0` |
| `CHECKMK_SERVER_PORT` | Bind Port | `9293` |
| `CHECKMK_METRIC_NAME` | Prometheus metric name | `checkmk_status` |

## Quickstart & Usage

### 1. Using `docker run` (CLI)

```bash
docker run -d \
  --name checkmk_exporter \
  --restart unless-stopped \
  -p 9293:9293 \
  -e CHECKMK_HOSTNAME="checkmk.example.com" \
  -e CHECKMK_DASHBOARD="site_name" \
  -e CHECKMK_USERNAME="automation_user" \
  -e CHECKMK_SECRET="your_secret_password" \
  thachnv92/checkmk_exporter:latest
```

### 2. Using Docker Compose

Create or update your `docker-compose.yml`:

```yaml
version: "2.1"

services:
  checkmk_exporter:
    image: thachnv92/checkmk_exporter:latest
    restart: unless-stopped
    ports:
      - "9293:9293"
    environment:
      CHECKMK_HOSTNAME: "checkmk.example.com"
      CHECKMK_DASHBOARD: "site_name"
      CHECKMK_USERNAME: "automation_user"
      CHECKMK_SECRET: "your_secret_password"
      CHECKMK_VIEW_NAME: "allhosts"
      CHECKMK_SERVER_PORT: "9293"
      CHECKMK_METRIC_NAME: "checkmk_status"
```

Start the container:

```bash
docker-compose up -d
```

### 3. Direct Python Execution

```bash
python files/exporter.py \
  --hostname checkmk.example.com \
  --dashboard site_name \
  --username automation_user \
  --secret your_secret_password
```

## Prometheus Scraping Configuration

Add this job block to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'checkmk_exporter'
    scrape_interval: 10s
    scrape_timeout: 5s
    static_configs:
      - targets: ['<CHECKMK_HOSTNAME>:9293']
```

## Verification

Once running, verify that metrics are exposed by fetching:

```bash
curl http://localhost:9293
```

## Example Prometheus Output

```prometheus
# HELP checkmk_status CheckMK host status
# TYPE checkmk_status gauge
checkmk_status{host_state="UP",host="Server-01",host_icons_1="themes/facelift/images/icon_host_graph.svg",host_icons_2="downtime",host_icons_3="comment",num_services_ok="4",num_services_warn="0",num_services_unknown="0",num_services_crit="0",num_services_pending="0"} 1
checkmk_status{host_state="DOWN",host="Server-02",num_services_ok="0",num_services_warn="1",num_services_unknown="0",num_services_crit="5",num_services_pending="0"} 0
```
