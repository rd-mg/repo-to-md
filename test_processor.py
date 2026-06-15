import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from logic.processor import RepositoryProcessor

class TestRepositoryProcessor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_file = os.path.join(self.temp_dir, "output.md")
        self.processor = RepositoryProcessor()
        self.staged_batch_files = []
        self.processor.local_processor.process = MagicMock(side_effect=self._mock_local_process)
        self.processor.git_processor.process_remote = MagicMock(return_value={"total_processed": 2})

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def _mock_local_process(self, root_dir, output_file, extra_ignores=None, include_patterns=None,
                            style="markdown", split_size=None, header_text=None):
        staged_files = sorted(
            str(path.relative_to(root_dir)).replace(os.sep, "/")
            for path in Path(root_dir).rglob("*")
            if path.is_file()
        )
        self.staged_batch_files.append(staged_files)
        return {
            "total_processed": len(staged_files),
            "total_tokens": 100 * len(staged_files),
            "total_chars": 1000 * len(staged_files),
            "total_words": 200 * len(staged_files),
            "security": "Clean",
            "top_files": [{"path": staged_files[0], "tokens": "100"}] if staged_files else [],
        }

    def test_process_repo_uses_shared_local_planning(self):
        repo_path = os.path.join(self.temp_dir, "non_git_repo")
        os.makedirs(repo_path)
        with open(os.path.join(repo_path, "README.md"), "w", encoding="utf-8") as handle:
            handle.write("# README\n")
        with open(os.path.join(repo_path, "large.py"), "w", encoding="utf-8") as handle:
            handle.write("x" * (2 * 1024 * 1024))
        with open(os.path.join(repo_path, "extra.py"), "w", encoding="utf-8") as handle:
            handle.write("y" * (2 * 1024 * 1024))

        stats = self.processor.process_repo(
            repo_path,
            self.output_file,
            include_patterns=["py", "md"],
            split_size=10,
            max_tokens=100000,
            collect_binaries=False,
        )

        self.assertEqual(self.processor.local_processor.process.call_count, 3)
        self.assertEqual(stats["planned_split_size"], 3)
        self.assertEqual(stats["largest_included_file_mb"], 2)
        self.assertEqual(stats["batch_count"], 3)
        self.assertTrue(stats["batching_applied"])
        self.assertTrue(os.path.exists(stats["index_file"]))
        self.assertEqual(self.staged_batch_files[0], ["README.md"])
        self.assertEqual(self.staged_batch_files[1], ["extra.py"])
        self.assertEqual(self.staged_batch_files[2], ["large.py"])
        self.assertEqual(stats["binary_attachments"], 0)

    def test_process_repo_planning_respects_ignore_patterns(self):
        repo_path = os.path.join(self.temp_dir, "ignore_repo")
        os.makedirs(os.path.join(repo_path, "node_modules"))
        with open(os.path.join(repo_path, "small.py"), "w", encoding="utf-8") as handle:
            handle.write("print('ok')\n")
        with open(os.path.join(repo_path, "node_modules", "ignored.py"), "w", encoding="utf-8") as handle:
            handle.write("x" * (3 * 1024 * 1024))

        planning = self.processor.plan_local_processing(
            repo_path,
            include_patterns=["py"],
            requested_split_size=5,
            max_tokens=500000,
        )

        self.assertEqual(planning["largest_file_size_mb"], 1)
        self.assertEqual(planning["largest_file_path"], "small.py")
        self.assertFalse(planning["largest_file_adjusted"])

    def test_process_repo_binary_collection_uses_shared_ignore_rules(self):
        repo_path = os.path.join(self.temp_dir, "binary_repo")
        os.makedirs(os.path.join(repo_path, "node_modules"))
        with open(os.path.join(repo_path, "image.png"), "wb") as handle:
            handle.write(b"png")
        with open(os.path.join(repo_path, "node_modules", "ignored.png"), "wb") as handle:
            handle.write(b"png")

        binary_stats = self.processor._orchestrate_binaries(repo_path, self.temp_dir, extra_ignores=None)

        self.assertEqual(binary_stats["count"], 1)
        self.assertEqual(binary_stats["files"], ["image.png"])

    def test_plan_local_processing_keeps_directory_groups_together(self):
        repo_path = os.path.join(self.temp_dir, "grouped_repo")
        os.makedirs(os.path.join(repo_path, "src", "alpha"))
        os.makedirs(os.path.join(repo_path, "src", "beta"))
        with open(os.path.join(repo_path, "README.md"), "w", encoding="utf-8") as handle:
            handle.write("# README\n")
        for name in ["one.py", "two.py"]:
            with open(os.path.join(repo_path, "src", "alpha", name), "w", encoding="utf-8") as handle:
                handle.write("a" * (1024 * 1024))
        for name in ["one.py", "two.py"]:
            with open(os.path.join(repo_path, "src", "beta", name), "w", encoding="utf-8") as handle:
                handle.write("b" * (1024 * 1024))

        planning = self.processor.plan_local_processing(
            repo_path,
            include_patterns=["py", "md"],
            requested_split_size=3,
            max_tokens=400000,
        )

        self.assertEqual(planning["batch_count"], 2)
        self.assertEqual(
            [file_info["rel_path"] for file_info in planning["batches"][0]["files"]],
            ["README.md", "src/alpha/one.py", "src/alpha/two.py"],
        )
        self.assertEqual(
            [file_info["rel_path"] for file_info in planning["batches"][1]["files"]],
            ["src/beta/one.py", "src/beta/two.py"],
        )

    def test_plan_local_processing_keeps_odoo_addon_together(self):
        repo_path = os.path.join(self.temp_dir, "odoo_repo")
        os.makedirs(os.path.join(repo_path, "addons", "sale_order_approval", "models"))
        os.makedirs(os.path.join(repo_path, "addons", "sale_order_approval", "views"))
        os.makedirs(os.path.join(repo_path, "addons", "crm_stage_guard", "models"))
        os.makedirs(os.path.join(repo_path, "addons", "crm_stage_guard", "views"))

        with open(
            os.path.join(repo_path, "addons", "sale_order_approval", "__manifest__.py"),
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write("{'name': 'Sale Order Approval'}\n")
        with open(
            os.path.join(repo_path, "addons", "sale_order_approval", "models", "sale_order.py"),
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write("a" * (1024 * 1024))
        with open(
            os.path.join(repo_path, "addons", "sale_order_approval", "views", "sale_order_views.xml"),
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write("<odoo>" + ("a" * (1024 * 1024)) + "</odoo>")

        with open(
            os.path.join(repo_path, "addons", "crm_stage_guard", "__manifest__.py"),
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write("{'name': 'CRM Stage Guard'}\n")
        with open(
            os.path.join(repo_path, "addons", "crm_stage_guard", "models", "crm_lead.py"),
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write("b" * (1024 * 1024))
        with open(
            os.path.join(repo_path, "addons", "crm_stage_guard", "views", "crm_lead_views.xml"),
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write("<odoo>" + ("b" * (1024 * 1024)) + "</odoo>")

        planning = self.processor.plan_local_processing(
            repo_path,
            include_patterns=["py", "xml"],
            requested_split_size=3,
            max_tokens=500000,
        )

        self.assertEqual(planning["batch_count"], 2)
        self.assertEqual(
            [file_info["rel_path"] for file_info in planning["batches"][0]["files"]],
            [
                "addons/crm_stage_guard/__manifest__.py",
                "addons/crm_stage_guard/models/crm_lead.py",
                "addons/crm_stage_guard/views/crm_lead_views.xml",
            ],
        )
        self.assertEqual(
            [file_info["rel_path"] for file_info in planning["batches"][1]["files"]],
            [
                "addons/sale_order_approval/__manifest__.py",
                "addons/sale_order_approval/models/sale_order.py",
                "addons/sale_order_approval/views/sale_order_views.xml",
            ],
        )

    def test_process_remote_git_applies_token_limit(self):
        stats = self.processor.process_remote_git(
            "https://github.com/example/project",
            self.output_file,
            split_size=10,
            max_tokens=100000,
        )

        self.processor.git_processor.process_remote.assert_called_once()
        call_args = self.processor.git_processor.process_remote.call_args.args

        self.assertEqual(call_args[5], 1)
        self.assertEqual(stats["total_processed"], 2)

    def test_process_repo_retries_single_pack_after_root_entry_overflow(self):
        repo_path = os.path.join(self.temp_dir, "retry_repo")
        os.makedirs(repo_path)
        with open(os.path.join(repo_path, "README.md"), "w", encoding="utf-8") as handle:
            handle.write("# README\n")

        calls = {"count": 0}

        def flaky_local_process(root_dir, output_file, extra_ignores=None, include_patterns=None,
                                style="markdown", split_size=None, header_text=None):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError(
                    "Repomix failed: ✖ Cannot split output: root entry 'content' exceeds max size. "
                    "Part size 4,295,706 bytes > limit 4,194,304 bytes."
                )
            return {
                "total_processed": 1,
                "total_tokens": 100,
                "total_chars": 1000,
                "total_words": 200,
                "security": "Clean",
                "top_files": [{"path": "README.md", "tokens": "100"}],
            }

        self.processor.local_processor.process = MagicMock(side_effect=flaky_local_process)

        stats = self.processor.process_repo(
            repo_path,
            self.output_file,
            include_patterns=["md"],
            split_size=10,
            max_tokens=500000,
            collect_binaries=False,
        )

        self.assertEqual(self.processor.local_processor.process.call_count, 2)
        first_call = self.processor.local_processor.process.call_args_list[0].args
        second_call = self.processor.local_processor.process.call_args_list[1].args
        self.assertEqual(first_call[5], 4)
        self.assertEqual(second_call[5], 6)
        self.assertEqual(stats["planned_split_size"], 6)
        self.assertEqual(stats["batch_count"], 1)

if __name__ == "__main__":
    unittest.main()
