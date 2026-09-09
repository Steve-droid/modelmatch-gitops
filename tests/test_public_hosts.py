"""Offline rendering contracts for the staged DNS/TLS cutover. Requires Helm + PyYAML."""
import pathlib
import subprocess
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEGACY_APP = "app.3.111.156.216.sslip.io"
LEGACY_API = "api.3.111.156.216.sslip.io"


def render(*values):
    command = ["helm", "template", "modelmatch", "charts/modelmatch", "--namespace", "app"]
    for value in values:
        command.extend(["--set", value])
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True)


def render_custom(*values):
    return render("global.appHost=modicum.cloud", "global.apiHost=api.modicum.cloud",
                  "global.useCustomHosts=false", *values)

def objects(result):
    assert result.returncode == 0, result.stderr
    return {(obj["kind"], obj["metadata"]["name"]): obj
            for obj in yaml.safe_load_all(result.stdout) if obj}


class PublicHostTests(unittest.TestCase):
    def assert_urls(self, docs, api, origins):
        backend = docs["ConfigMap", "modelmatch-backend-config"]["data"]
        frontend = docs["ConfigMap", "modelmatch-frontend-config"]["data"]
        self.assertEqual(backend["PUBLIC_BASE_URL"], "https://" + api)
        self.assertEqual(frontend["API_BASE_URL"], "https://" + api)
        self.assertEqual(set(backend["CORS_ALLOW_ORIGINS"].split(",")),
                         {"https://" + host for host in origins})

    def test_no_custom_hosts_preserves_original_routes_and_urls(self):
        docs = objects(render("global.appHost=", "global.apiHost=", "global.useCustomHosts=false"))
        self.assertEqual(sum(kind == "Ingress" for kind, _ in docs), 5)
        self.assert_urls(docs, LEGACY_API, [LEGACY_APP])

    def test_committed_values_use_branded_api_and_retain_legacy_hosts(self):
        docs = objects(render())
        self.assertEqual(sum(kind == "Ingress" for kind, _ in docs), 10)
        self.assert_urls(docs, "api.modicum.cloud", [LEGACY_APP, "modicum.cloud"])

    def test_stage_certificates_keeps_runtime_on_original_api(self):
        docs = objects(render_custom())
        self.assertEqual(sum(kind == "Ingress" for kind, _ in docs), 10)
        self.assert_urls(docs, LEGACY_API, [LEGACY_APP, "modicum.cloud"])
        secrets = []
        for role, host in [("app", LEGACY_APP), ("api", LEGACY_API),
                           ("app-branded", "modicum.cloud"), ("api-branded", "api.modicum.cloud")]:
            master = docs["Ingress", "modelmatch-" + role]
            minion = docs["Ingress", "modelmatch-" + role + "-routes"]
            self.assertEqual(master["spec"]["rules"], [{"host": host}])
            self.assertEqual(master["spec"]["tls"][0]["hosts"], [host])
            secrets.append(master["spec"]["tls"][0]["secretName"])
            self.assertEqual(master["metadata"]["annotations"]["nginx.org/mergeable-ingress-type"], "master")
            self.assertEqual(minion["metadata"]["annotations"]["nginx.org/mergeable-ingress-type"], "minion")
            self.assertEqual(master["metadata"]["annotations"]["nginx.org/ssl-redirect"], "false")
            self.assertEqual(minion["spec"]["rules"][0]["host"], host)
        self.assertEqual(len(set(secrets)), 4)

    def test_switch_keeps_legacy_ingress_and_both_origins(self):
        staged = objects(render_custom())
        active = objects(render_custom("global.useCustomHosts=true"))
        self.assert_urls(active, "api.modicum.cloud", [LEGACY_APP, "modicum.cloud"])
        self.assertEqual({key: val for key, val in staged.items() if key[0] == "Ingress"},
                         {key: val for key, val in active.items() if key[0] == "Ingress"})
        for name in ["modelmatch-frontend", "modelmatch-backend"]:
            before = staged["Deployment", name]["spec"]["template"]
            after = active["Deployment", name]["spec"]["template"]
            self.assertNotEqual(before["metadata"]["annotations"]["checksum/config"],
                                after["metadata"]["annotations"]["checksum/config"])

    def test_retire_legacy_only_after_cutover(self):
        docs = objects(render_custom("global.useCustomHosts=true", "global.retainSslipHosts=false"))
        self.assertEqual(sum(kind == "Ingress" for kind, _ in docs), 5)
        self.assert_urls(docs, "api.modicum.cloud", ["modicum.cloud"])
        self.assertNotIn(("Ingress", "modelmatch-api"), docs)

    def test_invalid_cutovers_fail_closed(self):
        for values in [("global.apiHost=",), ("global.appHost=https://modicum.cloud",),
                       ("global.retainSslipHosts=false",),
                       ("global.appHost=api.modicum.cloud",),
                       ("global.appHost=" + LEGACY_API,)]:
            with self.subTest(values=values):
                self.assertNotEqual(render_custom(*values).returncode, 0)


if __name__ == "__main__":
    unittest.main()
