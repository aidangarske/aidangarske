import contextlib
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from scripts import yearly_languages


class PrivateCoverageTests(unittest.TestCase):
    def collect(self):
        return yearly_languages.collect(
            Path("unused-cache"), "2025-10-16T00:00:00Z",
            "2026-10-16T00:00:00Z", include_private=True,
            previous_private=71,
        )

    @patch.dict("os.environ", {"PRIVATE_STATS_TOKEN": ""})
    @patch.object(yearly_languages, "authored_changes")
    @patch.object(yearly_languages, "repositories")
    def test_decreased_repository_count_refreshes_current_totals(self, repositories, changes):
        repositories.return_value = {"owner/repo-%s" % n: True for n in range(70)}
        # Every repository returns the same commit to also exercise deduplication.
        changes.return_value = {"sha": {
            "authored": "2026-10-15T00:00:00Z", "files": {"C": 1},
            "added": {"C": 10}, "deleted": {"C": 2},
        }}
        with contextlib.redirect_stdout(io.StringIO()) as output:
            data = self.collect()
        self.assertEqual(data["private_repositories"], 70)
        self.assertEqual(data["career_loc_added"], 10)
        self.assertEqual(changes.call_count, 70)
        self.assertIn("::warning::Private repository count decreased", output.getvalue())

    @patch.dict("os.environ", {"PRIVATE_STATS_TOKEN": ""})
    @patch.object(yearly_languages, "authored_changes")
    @patch.object(yearly_languages, "repositories", return_value={"owner/public": False})
    def test_loss_of_all_private_access_preserves_existing_totals(self, repositories, changes):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "No private repositories are accessible"):
                self.collect()
        changes.assert_not_called()

    @patch.dict("os.environ", {"PRIVATE_STATS_TOKEN": ""})
    @patch.object(yearly_languages, "repositories")
    def test_api_failure_is_not_treated_as_repository_removal(self, repositories):
        repositories.side_effect = subprocess.CalledProcessError(1, "gh")
        with self.assertRaises(subprocess.CalledProcessError):
            self.collect()


if __name__ == "__main__":
    unittest.main()
