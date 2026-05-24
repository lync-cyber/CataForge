"""Concurrent regression test for md_parse._md_parser thread safety.

MarkdownIt 4.x creates a fresh StateCore per parse() call; the cached
instance itself is not mutated during parsing, making lru_cache safe.
This test exercises 4 threads parsing 200 documents concurrently.
"""

from __future__ import annotations

import concurrent.futures

from cataforge.utils.md_parse import iter_markdown_headings

_SAMPLES = [
    "# Heading 1\n\nSome paragraph text.\n",
    "## Sub-heading\n\n- item a\n- item b\n",
    "### Level 3\n\nFoo **bold** and *italic*.\n",
    "# A\n\n## B\n\n### C\n",
    "No heading here, just prose.\n",
] * 40  # 200 documents


class TestMdParseThreadSafe:
    def test_concurrent_parse_results_consistent(self) -> None:
        baseline = [iter_markdown_headings(s) for s in _SAMPLES]

        errors: list[Exception] = []

        def parse(sample: str) -> list:
            return iter_markdown_headings(sample)

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(parse, s) for s in _SAMPLES]
            results = []
            for f in futs:
                try:
                    results.append(f.result())
                except Exception as e:
                    errors.append(e)

        assert not errors, f"Concurrent parse raised exceptions: {errors}"
        assert len(results) == len(baseline)
        for i, (actual, expected) in enumerate(zip(results, baseline, strict=True)):
            assert actual == expected, f"Mismatch at index {i}"

    def test_single_instance_reuse_across_threads(self) -> None:
        from cataforge.utils.md_parse import _md_parser

        instance_ids: set[int] = set()

        def get_id(_: int) -> int:
            return id(_md_parser())

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            for iid in ex.map(get_id, range(20)):
                instance_ids.add(iid)

        assert len(instance_ids) == 1, "lru_cache should return the same instance"
