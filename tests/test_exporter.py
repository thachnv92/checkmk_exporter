import os
import sys

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from files.exporter import _escape_string, format_prometheus, fetch_checkmk_data
from unittest.mock import patch, MagicMock


def test_escape_string():
    assert _escape_string('hello "world"') == 'hello \\"world\\"'
    assert _escape_string('line1\nline2') == 'line1\\nline2'
    assert _escape_string('path\\to\\file') == 'path\\\\to\\\\file'
    assert _escape_string(None) == ""


def test_format_prometheus():
    data = [
        [
            "host_state",
            "host",
            "host_icons",
            "num_services_ok",
            "num_services_warn",
            "num_services_unknown",
            "num_services_crit",
            "num_services_pending",
        ],
        [
            "UP",
            "Server-01",
            [
                "themes/facelift/images/icon_host_graph.svg",
                "downtime",
                "comment",
            ],
            "4",
            "0",
            "0",
            "0",
            "0",
        ],
        [
            "DOWN",
            "Server-02",
            [],
            "0",
            "1",
            "0",
            "5",
            "0",
        ],
    ]

    output = format_prometheus(data, metric_name="checkmk_status")

    assert '# HELP checkmk_status CheckMK host status' in output
    assert '# TYPE checkmk_status gauge' in output

    # Row 1 (UP) -> 1
    assert (
        'checkmk_status{host_state="UP",host="Server-01",'
        'host_icons_1="themes/facelift/images/icon_host_graph.svg",host_icons_2="downtime",host_icons_3="comment",'
        'num_services_ok="4",num_services_warn="0",num_services_unknown="0",num_services_crit="0",num_services_pending="0"} 1'
        in output
    )

    # Row 2 (DOWN) -> 0
    assert (
        'checkmk_status{host_state="DOWN",host="Server-02",'
        'num_services_ok="0",num_services_warn="1",num_services_unknown="0",num_services_crit="5",num_services_pending="0"} 0'
        in output
    )


@patch("requests.get")
def test_fetch_checkmk_data(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = [
        ["host_state", "host"],
        ["UP", "host1"],
    ]
    mock_get.return_value = mock_response

    res = fetch_checkmk_data(
        hostname="checkmk.local",
        dashboard="site1",
        username="admin",
        secret="secret123",
        view_name="allhosts",
    )

    assert res == [["host_state", "host"], ["UP", "host1"]]
    mock_get.assert_called_once_with(
        "http://checkmk.local/site1/check_mk/view.py",
        params={
            "view_name": "allhosts",
            "output_format": "json",
            "_username": "admin",
            "_secret": "secret123",
        },
        timeout=30,
    )
