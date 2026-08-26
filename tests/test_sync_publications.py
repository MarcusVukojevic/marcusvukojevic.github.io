import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.parse
from types import SimpleNamespace
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

import sync_publications  # noqa: E402


def openalex_work(identifier, title, date, work_type="preprint", doi=None):
    return {
        "id": f"https://openalex.org/{identifier}",
        "doi": doi,
        "title": title,
        "display_name": title,
        "publication_date": date,
        "type": work_type,
        "is_paratext": False,
        "authorships": [
            {
                "author": {
                    "id": sync_publications.OPENALEX_AUTHOR_URL,
                    "display_name": "Marcus Vukojevic",
                }
            }
        ],
        "primary_location": {
            "landing_page_url": doi,
            "pdf_url": None,
            "source": {"display_name": "arXiv (Cornell University)"},
        },
        "best_oa_location": {},
        "locations": [],
        "primary_topic": {"display_name": "Artificial Intelligence"},
        "abstract_inverted_index": {"OpenAlex": [0], "abstract.": [1]},
    }


OPENALEX_FIXTURE = json.dumps(
    {
        "results": [
            openalex_work(
                "W1",
                "From Layers to Submodules: Rethinking Granularity in Replacement-Based LLM Compression",
                "2026-06-01",
                doi="https://doi.org/10.48550/arxiv.2606.02559",
            ),
            openalex_work(
                "W2",
                "From Layers to Submodules: Rethinking Granularity in Replacement-Based LLM Compression",
                "2026-06-01",
            ),
            openalex_work(
                "W3",
                "Hallucination as an Anomaly: Dynamic Intervention via Probabilistic Circuits",
                "2026-05-07",
                doi="https://doi.org/10.48550/arxiv.2605.05953",
            ),
            openalex_work(
                "W4",
                "A Benchmark Dataset for Graph Regression with Homogeneous and Multi-Relational Variants",
                "2025-05-29",
                doi="https://doi.org/10.48550/arxiv.2505.23875",
            ),
            openalex_work(
                "W5",
                "Broadening the Scope of Graph Regression: Introducing a Dataset",
                "2026-02-10",
                work_type="dataset",
                doi="https://doi.org/10.5281/zenodo.18598713",
            ),
            openalex_work(
                "W6",
                "HUB Trentino Innovazione",
                "2024-01-01",
                work_type="article",
            ),
        ]
    }
).encode()


ARXIV_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2606.02559v1</id>
    <title>  From Layers to Submodules: Rethinking Granularity in Replacement-Based LLM Compression  </title>
    <updated>2026-06-01T17:52:53Z</updated>
    <summary>Line one.\n      Line two.</summary>
    <published>2026-06-01T17:52:53Z</published>
    <category term="cs.AI"/><category term="cs.CL"/>
    <arxiv:primary_category term="cs.CL"/>
    <author><name>Elia Cunegatti</name></author>
    <author><name>Marcus Vukojevic</name></author>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2605.05953v1</id>
    <title>Hallucination as an Anomaly: Dynamic Intervention via Probabilistic Circuits</title>
    <updated>2026-05-07T10:02:27Z</updated>
    <summary>Abstract.</summary>
    <published>2026-05-07T10:02:27Z</published>
    <category term="cs.CL"/>
    <arxiv:primary_category term="cs.CL"/>
    <author><name>Marcus Vukojevic</name></author>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2505.23875v1</id>
    <title>A Benchmark Dataset for Graph Regression with Homogeneous and Multi-Relational Variants</title>
    <updated>2025-05-29T12:59:36Z</updated>
    <summary>Abstract.</summary>
    <published>2025-05-29T12:59:36Z</published>
    <category term="cs.LG"/>
    <arxiv:primary_category term="cs.LG"/>
    <arxiv:journal_ref>Journal of Data-centric Machine Learning Research, 2026</arxiv:journal_ref>
    <author><name>Marcus Vukojevic</name></author>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>Similar name should not match</title>
    <updated>2024-01-01T00:00:00Z</updated>
    <summary>Abstract.</summary>
    <published>2024-01-01T00:00:00Z</published>
    <category term="cs.AI"/>
    <arxiv:primary_category term="cs.AI"/>
    <author><name>Marcus Vukojevic-Smith</name></author>
  </entry>
</feed>
"""


class PublicationSyncTests(unittest.TestCase):
    def test_normalize_replaces_em_dashes(self):
        self.assertEqual(sync_publications.normalize("hard\u2014decoded"), "hard - decoded")

    def test_remote_links_require_https_and_expected_hosts(self):
        self.assertEqual(
            sync_publications.trusted_https_url("https://openalex.org/W123", "openalex.org"),
            "https://openalex.org/W123",
        )
        self.assertEqual(sync_publications.trusted_https_url("javascript:alert(1)"), "")
        self.assertEqual(
            sync_publications.trusted_https_url("https://attacker.example/W123", "openalex.org"),
            "",
        )

    def test_reconcile_filter_deduplicate_and_render_deterministically(self):
        openalex_records = sync_publications.parse_openalex(OPENALEX_FIXTURE)
        arxiv_records = sync_publications.parse_arxiv(ARXIV_FIXTURE)
        records = sync_publications.deduplicate(openalex_records + arxiv_records)
        sync_publications.validate(records)

        self.assertEqual(len(openalex_records), 4)
        self.assertEqual(
            [record["arxiv_id"] for record in records],
            ["2606.02559", "2605.05953", "2505.23875"],
        )
        self.assertEqual(records[0]["abstract"], "Line one. Line two.")
        self.assertEqual(records[0]["categories"], ["cs.CL", "cs.AI"])
        self.assertEqual(
            records[-1]["journal_ref"],
            "Journal of Data-centric Machine Learning Research, 2026",
        )

        first_render = sync_publications.render_yaml(records)
        second_render = sync_publications.render_yaml(records)
        self.assertEqual(first_render, second_render)
        self.assertNotIn("HUB Trentino Innovazione", first_render)
        self.assertNotIn("zenodo.18598713", first_render)
        self.assertNotIn("Marcus Vukojevic-Smith", first_render)

    def test_queries_use_verified_exact_author_identifiers(self):
        openalex_query = urllib.parse.parse_qs(
            urllib.parse.urlsplit(sync_publications.openalex_query_url()).query
        )
        arxiv_query = urllib.parse.parse_qs(
            urllib.parse.urlsplit(sync_publications.arxiv_query_url()).query
        )

        self.assertEqual(openalex_query["filter"], ["author.id:A5119861930"])
        self.assertEqual(arxiv_query["search_query"], ['au:"Marcus Vukojevic"'])

    def test_degraded_sync_preserves_last_good_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "publications.yml"
            output.write_text("last-good\n", encoding="utf-8")
            arguments = SimpleNamespace(
                openalex_input=None,
                arxiv_input=None,
                output=str(output),
            )

            with mock.patch.object(sync_publications, "parse_arguments", return_value=arguments):
                with mock.patch.object(
                    sync_publications,
                    "read_source",
                    side_effect=[b"not-json", ARXIV_FIXTURE],
                ):
                    with self.assertRaisesRegex(RuntimeError, "last-good data preserved"):
                        sync_publications.main()

            self.assertEqual(output.read_text(encoding="utf-8"), "last-good\n")


if __name__ == "__main__":
    unittest.main()
