import argparse
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


def format_prometheus(data: list, metric_name: str = "checkmk_status") -> str:
    """
    Convert CheckMK view JSON data to Prometheus metrics format.
    
    Data structure example:
    [
      ["host_state", "host", "host_icons", "num_services_ok", ...],
      ["UP", "UPS-Ermeson", ["themes/facelift/images/icon_host_graph.svg", "downtime", "comment"], "4", ...]
    ]
    """
    if not data or not isinstance(data, list) or len(data) < 2:
        return ""

    headers = data[0]
    rows = data[1:]

    lines = []
    lines.append(f"# HELP {metric_name} CheckMK host status")
    lines.append(f"# TYPE {metric_name} gauge")

    for row in rows:
        labels = []
        host_state = "UP"

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
            metrics_output = format_prometheus(
                data=data,
                metric_name=self.config.get("metric_name", "checkmk_status"),
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

        args = parser.parse_args()

        hostname = args.hostname or ""
        dashboard = args.dashboard or ""
        username = args.username or ""
        secret = args.secret or ""
        view_name = args.view_name
        server_name = args.server_name
        server_port = args.server_port
        metric_name = args.metric_name

    ReqHandler.config = {
        "hostname": hostname,
        "dashboard": dashboard,
        "username": username,
        "secret": secret,
        "view_name": view_name,
        "metric_name": metric_name,
    }

    server = http.server.HTTPServer((server_name, server_port), ReqHandler)
    print(f"Starting CheckMK Exporter on {server_name}:{server_port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
