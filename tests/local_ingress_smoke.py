"""Black-box checks against the disposable kind-p38o F5 controller fixture.

Requires local forwards 18080:80 / 18443:443 and a synthetic upstream returning 200.
Only loopback requests are sent. TLS verification is disabled solely for the
fixture's self-signed certificate. Never use this script as a live TLS check.
"""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import http.client
import json
import ssl
import socket
import subprocess


class LocalHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        self.sock = self._context.wrap_socket(socket.create_connection(("127.0.0.1", 18443), 10),
                                              server_hostname=self.host)


def request(host, path="/", https=False, headers=None, body=None):
    connection = (LocalHTTPSConnection(host, 18443, timeout=10,
                  context=ssl._create_unverified_context()) if https else
                  http.client.HTTPConnection("127.0.0.1", 18080, timeout=10))
    connection.request("POST" if body else "GET", path, body=body,
                       headers={"Host": host, **(headers or {})})
    response = connection.getresponse()
    result = response.status, dict(response.getheaders()), response.read().decode()
    connection.close()
    return result


def main():
    kube = ["kubectl", "--kubeconfig", "/tmp/p38o-kubeconfig"]
    assert subprocess.check_output([*kube, "config", "current-context"], text=True).strip() == "kind-p38o"
    hosts = ["modicum.cloud", "api.modicum.cloud", "app.3.111.156.216.sslip.io", "api.3.111.156.216.sslip.io"]
    for host in hosts:
        status, headers, _ = request(host, "/?q=1", headers={"X-Forwarded-Proto": "https"})
        assert status == 308 and headers["Location"] == f"https://{host}/?q=1"
        assert request(host, https=True)[0] == 200
    status, _, body = request("api.modicum.cloud", "/.well-known/acme-challenge/p38o")
    assert status == 200 and body == "synthetic-upstream"
    assert request("api.modicum.cloud", "/auth/login", https=True, body="x" * 40000)[0] == 413
    rates = {}
    for host in ("api.modicum.cloud", "api.3.111.156.216.sslip.io"):
        def attempt(n):
            return request(host, "/auth/login", https=True,
                           headers={"X-Forwarded-For": f"192.0.2.{n + 1}"})[0]
        with ThreadPoolExecutor(max_workers=20) as pool:
            counts = Counter(pool.map(attempt, range(24)))
        assert counts[200] > 0 and counts[429] > 0 and set(counts) <= {200, 429}, counts
        rates[host] = dict(counts)
    print(json.dumps({"http_redirect_hosts": len(hosts), "https_hosts": len(hosts),
                      "acme_solver_http": 200, "oversize_auth_body": 413,
                      "forged_forwarding_header_rate_results": rates}, indent=2))


if __name__ == "__main__":
    main()
