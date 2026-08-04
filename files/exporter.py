import argparse
import csv
import http.server
import os
import sys
import requests


def _escape_string(val) -> str:
    """
    Escape string values for Prometheus exposition format.
    Backslash (\), double-quote ("), and line feed (\n) characters are escaped.
    """
    if val is None:
        return ""
    val_str = str(val)
    translate_map = str.maketrans(
        {
            "\\": "\\\\",
            '"': '\\"',
            "\n": "\\n",
        }
    )
    return val_str.translate(translate_map)


def load_servers_csv(file_path: str) -> dict:
    """
    Load servers.csv into a dictionary indexed by hostname.
    Example return:
    {
      "Server-01": {"Type": "Database", "ENV": "PROD", "Important": "YES", "Project": "Project1"},
      "server-01": ...
    }
    """
    if not file_path:
        return {}

    resolved_path = file_path
    if not os.path.isabs(resolved_path):
        candidates = [
            resolved_path,
            os.path.join(os.getcwd(), resolved_path),
            os.path.join(os.path.dirname(__file__), resolved_path),
            os.path.join(os.path.dirname(__file__), "..", resolved_path),
            "/servers.csv",
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                resolved_path = candidate
                break

    if not os.path.exists(resolved_path):
        return {}

    servers_map = {}
    try:
        with open(resolved_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            if not headers:
                return {}

            host_col_idx = 0
            for idx, h in enumerate(headers):
                if h.strip().lower() in ("hostname", "host", "host_name", "server", "name"):
                    host_col_idx = idx
                    break

            for row in reader:
                if not row or len(row) <= host_col_idx:
                    continue
                host_val = row[host_col_idx].strip()
                if not host_val:
                    continue

                meta = {}
                for idx, col_val in enumerate(row):
                    if idx == host_col_idx:
                        continue
                    if idx < len(headers):
                        col_name = headers[idx].strip()
                        meta[col_name] = col_val.strip()

                servers_map[host_val] = meta
                servers_map[host_val.lower()] = meta
    except Exception as e:
        print(f"Warning: Failed to parse CSV file '{resolved_path}': {e}", file=sys.stderr)
        return {}

    return servers_map


def fetch_checkmk_data(hostname: str, dashboard: str, username: str, secret: str, view_name: str = "allhosts") -> list:
    """
    Fetch view data from CheckMK view.py API.
    Endpoint: http://$hostname/$dashboard/check_mk/view.py?view_name=allhosts&output_format=json&_username=$username&_secret=$secret
    """
    if not (hostname.startswith("http://") or hostname.startswith("https://")):
        base_url = f"http://{hostname}"
    else:
        base_url = hostname

    base_url = base_url.rstrip("/")
    dashboard_path = dashboard.strip("/")

    if dashboard_path:
        url = f"{base_url}/{dashboard_path}/check_mk/view.py"
    else:
        url = f"{base_url}/check_mk/view.py"

    params = {
        "view_name": view_name,
        "output_format": "json",
        "_username": username,
        "_secret": secret,
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def format_prometheus(data: list, metric_name: str = "checkmk_status", servers_map: dict = None) -> str:
    """
    Convert CheckMK view JSON data to Prometheus metrics format and enrich with servers.csv metadata.
    
    Data structure example:
    [
      ["host_state", "host", ..., "host_icons", "num_services_ok", ...],
      ["UP", "UPS-Ermeson", ..., ["themes/facelift/images/icon_host_graph.svg", "downtime", "comment"], "4", ...]
    ]
    """
    if not data or not isinstance(data, list) or len(data) < 2:
        return ""

    if servers_map is None:
        servers_map = {}

    headers = data[0]
    rows = data[1:]

    host_idx = -1
    for idx, h in enumerate(headers):
        if str(h).lower() in ("host", "hostname", "host_name", "name"):
            host_idx = idx
            break

    lines = []
    lines.append(f"# HELP {metric_name} CheckMK host status")
    lines.append(f"# TYPE {metric_name} gauge")

    for row in rows:
        labels = []
        host_state = "UP"

        row_host_val = None
        if host_idx != -1 and host_idx < len(row):
            row_host_val = str(row[host_idx])

        csv_meta = {}
        if row_host_val:
            csv_meta = servers_map.get(row_host_val) or servers_map.get(row_host_val.lower()) or {}

        for i, header in enumerate(headers):
            if i >= len(row):
                continue
            val = row[i]

            if header == "host_state":
                host_state = str(val)

            if isinstance(val, (list, tuple)):
                for idx, subval in enumerate(val, 1):
                    label_key = f"{header}_{idx}"
                    label_val = _escape_string(subval)
                    labels.append(f'{label_key}="{label_val}"')
            else:
                label_key = header
                label_val = _escape_string(val)
                labels.append(f'{label_key}="{label_val}"')

                if i == host_idx and csv_meta:
                    for k, v in csv_meta.items():
                        labels.append(f'{k}="{_escape_string(v)}"')

        if host_idx == -1 and csv_meta:
            for k, v in csv_meta.items():
                labels.append(f'{k}="{_escape_string(v)}"')

        labels_str = ",".join(labels)

        # Host state logic: UP -> 1, DOWN -> 0
        if str(host_state).upper() in ("UP", "0"):
            value = 1
        else:
            value = 0

        lines.append(f"{metric_name}{{{labels_str}}} {value}")

    return "\n".join(lines) + "\n"


class ReqHandler(http.server.BaseHTTPRequestHandler):
    config = {}

    def do_GET(self):
        try:
            data = fetch_checkmk_data(
                hostname=self.config.get("hostname", ""),
                dashboard=self.config.get("dashboard", ""),
                username=self.config.get("username", ""),
                secret=self.config.get("secret", ""),
                view_name=self.config.get("view_name", "allhosts"),
            )
            servers_csv_path = self.config.get("servers_csv", "servers.csv")
            servers_map = load_servers_csv(servers_csv_path)

            metrics_output = format_prometheus(
                data=data,
                metric_name=self.config.get("metric_name", "checkmk_status"),
                servers_map=servers_map,
            )
            self.send_response(200)
            self.send_header("Content-type", "text/plain; version=0.0.4; charset=utf-8")
            self.end_headers()
            self.wfile.write(metrics_output.encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Error fetching CheckMK data: {str(e)}".encode("utf-8"))


def main():
    hostname = os.environ.get("CHECKMK_HOSTNAME")
    dashboard = os.environ.get("CHECKMK_DASHBOARD")
    username = os.environ.get("CHECKMK_USERNAME")
    secret = os.environ.get("CHECKMK_SECRET")
    view_name = os.environ.get("CHECKMK_VIEW_NAME", "allhosts")
    server_name = os.environ.get("CHECKMK_SERVER_NAME", "0.0.0.0")
    server_port = int(os.environ.get("CHECKMK_SERVER_PORT", "9293"))
    metric_name = os.environ.get("CHECKMK_METRIC_NAME", "checkmk_status")
    servers_csv = os.environ.get("SERVERS_CSV_PATH", "servers.csv")

    if not (hostname and dashboard and username and secret):
        parser = argparse.ArgumentParser(
            description="Export checkmk view results for Prometheus scraping."
        )
        parser.add_argument("--hostname", "-s", default=hostname, help="CheckMK hostname/IP")
        parser.add_argument("--dashboard", "-d", default=dashboard, help="CheckMK dashboard/site name")
        parser.add_argument("--username", "-u", default=username, help="CheckMK username")
        parser.add_argument("--secret", "-w", default=secret, help="CheckMK secret/password")
        parser.add_argument("--view_name", "-v", default=view_name, help="CheckMK view name (default: allhosts)")
        parser.add_argument("--server_name", default=server_name, help="Server address to bind to")
        parser.add_argument("--server_port", "-p", default=server_port, type=int, help="Port to bind to (default: 9293)")
        parser.add_argument("--metric_name", default=metric_name, help="Prometheus metric name (default: checkmk_status)")
        parser.add_argument("--servers_csv", "-f", default=servers_csv, help="Path to servers.csv file (default: servers.csv)")

        args = parser.parse_args()

        hostname = args.hostname or ""
        dashboard = args.dashboard or ""
        username = args.username or ""
        secret = args.secret or ""
        view_name = args.view_name
        server_name = args.server_name
        server_port = args.server_port
        metric_name = args.metric_name
        servers_csv = args.servers_csv

    ReqHandler.config = {
        "hostname": hostname,
        "dashboard": dashboard,
        "username": username,
        "secret": secret,
        "view_name": view_name,
        "metric_name": metric_name,
        "servers_csv": servers_csv,
    }

    server = http.server.HTTPServer((server_name, server_port), ReqHandler)
    print(f"Starting CheckMK Exporter on {server_name}:{server_port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
