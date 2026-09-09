"""Prove an existing-database sync cannot invoke seeds or mutate database resources."""
import copy
import pathlib
import subprocess
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]


def render(*values):
    cmd = ["helm", "template", "modelmatch-postgres", "charts/modelmatch-postgres"]
    for value in values:
        cmd.extend(["--set", value])
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=True)
    return {(obj["kind"], obj["metadata"]["name"]): obj
            for obj in yaml.safe_load_all(result.stdout) if obj}


class MigrationOnlyTests(unittest.TestCase):
    def test_default_renders_only_migration_and_no_seed_credentials(self):
        docs = render()
        jobs = [obj for (kind, _), obj in docs.items() if kind == "Job"]
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["metadata"]["annotations"]["argocd.argoproj.io/hook"], "PostSync")
        container = job["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["command"], ["alembic", "upgrade", "head"])
        self.assertNotIn("DEMO_SEED_PASSWORD", str(docs))

    def test_migration_image_bump_changes_only_job_images(self):
        before = render()
        after = render("migrate.image.tag=1.0.21")
        expected = copy.deepcopy(before)
        pod = expected["Job", "modelmatch-postgres-migrate"]["spec"]["template"]["spec"]
        for container in pod["containers"] + pod["initContainers"]:
            container["image"] = "957261948820.dkr.ecr.ap-south-1.amazonaws.com/modelmatch-backend:1.0.21"
        self.assertEqual(after, expected)

    def test_fresh_bootstrap_can_explicitly_enable_ordered_seeds(self):
        default = render()
        bootstrap = render("seed.catalog=true", "seed.demo=true")
        self.assertEqual({k: v for k, v in default.items() if k[0] != "Job"},
                         {k: v for k, v in bootstrap.items() if k[0] != "Job"})
        for name, wave, module in [("catalog", "10", "app.catalog.seed"), ("demo", "20", "app.demo.seed")]:
            job = bootstrap["Job", "modelmatch-postgres-seed-" + name]
            self.assertEqual(job["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"], wave)
            self.assertEqual(job["spec"]["template"]["spec"]["containers"][0]["command"],
                             ["python", "-m", module])


if __name__ == "__main__":
    unittest.main()
