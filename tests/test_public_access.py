"""Public hosts must all receive the security boundaries, including legacy aliases."""
import subprocess
import unittest
from pathlib import Path

import yaml


class PublicAccessTests(unittest.TestCase):
    def test_every_api_host_has_bounded_auth_and_general_routes(self):
        rendered = subprocess.check_output(["helm", "template", "modelmatch", "charts/modelmatch"], text=True)
        docs = [d for d in yaml.safe_load_all(rendered) if d and d["kind"] == "Ingress"]
        api_hosts = {r["host"] for d in docs for r in d["spec"]["rules"] if r["host"].startswith("api.")}
        self.assertEqual(api_hosts, {"api.modicum.cloud", "api.driftplain.dev", "api.3.111.156.216.sslip.io"})
        for host in api_hosts:
            routes = {p["path"]: d for d in docs for r in d["spec"]["rules"] if r["host"] == host
                      for p in r.get("http", {}).get("paths", [])}
            self.assertEqual(set(routes), {"/", "/auth"})
            for path, ingress in routes.items():
                annotations = ingress["metadata"]["annotations"]
                self.assertEqual(annotations["nginx.org/limit-req-reject-code"], "429")
                self.assertEqual(annotations["nginx.org/limit-req-no-delay"], "true")
                self.assertEqual(annotations["nginx.org/client-max-body-size"], "32k" if path == "/auth" else "1m")

    def test_central_redirect_uses_real_scheme_and_preserves_http_challenges(self):
        app = yaml.safe_load(Path("argocd/apps/nginx-ingress.yaml").read_text())
        values = yaml.safe_load(app["spec"]["source"]["helm"]["values"])
        controller = values["controller"]
        entries = controller["config"]["entries"]
        self.assertIn('$scheme:$uri', entries["http-snippets"])
        self.assertIn('~^http:/[.]well-known/acme-challenge/ 0;', entries["http-snippets"])
        self.assertNotIn("http_x_forwarded", entries["http-snippets"])
        self.assertIn("client_body_timeout 10s;", entries["http-snippets"])
        self.assertFalse(controller.get("enableSnippets", False))


if __name__ == "__main__":
    unittest.main()
