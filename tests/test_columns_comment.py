"""The `# itqan:columns` block above a manifest entry for a multi-column asset."""

import pytest

from itqan_cli.columns_comment import PackageColumn, PackageStructure, render_block, replace_block
from itqan_cli.exceptions import ManifestError
from itqan_cli.manifest import parse_manifest_content

QA = PackageStructure(
    template="ayah",
    header=("surah", "ayah", "question", "answer"),
    columns=(PackageColumn("question", "Question", "السؤال"), PackageColumn("answer", "Answer", "الجواب")),
)
QA_LINES = [
    "  # itqan:columns CSV, one row per ayah: surah, ayah, question, answer",
    "  # itqan:columns   question: Question / السؤال",
    "  # itqan:columns   answer: Answer / الجواب",
]
MANIFEST = 'schema_version: 1\n\nassets:\n  qa:\n    version: "^1.0.0"\n'


def test_render_block_where_two_columns_should_match_the_backend_format():
    assert render_block(QA, "  ") == QA_LINES


def test_render_block_where_single_column_should_be_empty():
    single = PackageStructure("ayah", ("surah", "ayah", "text"), (PackageColumn("text"),))

    assert render_block(single, "  ") == []


def test_render_block_where_column_has_no_or_one_label_should_skip_or_show_it():
    structure = PackageStructure(
        "word",
        ("word_id", "sura", "aya", "word", "gloss", "note"),
        (PackageColumn("gloss", "", "المعنى"), PackageColumn("note")),
    )

    assert render_block(structure, "  ") == [
        "  # itqan:columns CSV, one row per word: word_id, sura, aya, word, gloss, note",
        "  # itqan:columns   gloss: المعنى",
    ]


def test_replace_block_where_no_block_should_insert_above_the_entry():
    updated = replace_block(MANIFEST, "qa", QA_LINES)

    assert updated == "schema_version: 1\n\nassets:\n" + "\n".join(QA_LINES) + '\n  qa:\n    version: "^1.0.0"\n'
    assert parse_manifest_content(updated.encode("utf-8")).assets["qa"].version == "^1.0.0"


def test_replace_block_where_old_block_and_user_comment_should_replace_only_the_block():
    content = (
        "schema_version: 1\n\nassets:\n"
        "  # pinned for the quiz screen\n"
        "  # itqan:columns CSV, one row per ayah: surah, ayah, question\n"
        '  qa:\n    version: "^1.0.0"\n'
    )

    updated = replace_block(content, "qa", QA_LINES)

    assert updated == (
        "schema_version: 1\n\nassets:\n  # pinned for the quiz screen\n"
        + "\n".join(QA_LINES)
        + '\n  qa:\n    version: "^1.0.0"\n'
    )


def test_replace_block_where_lines_empty_should_remove_the_block():
    content = "schema_version: 1\n\nassets:\n" + "\n".join(QA_LINES) + '\n  qa:\n    version: "^1.0.0"\n'

    assert replace_block(content, "qa", []) == MANIFEST


def test_replace_block_where_entry_is_flow_style_should_leave_content_unchanged():
    content = 'schema_version: 1\n\nassets:\n  qa: {version: "^1.0.0"}\n'

    assert replace_block(content, "qa", QA_LINES) == content


def test_replace_block_where_key_is_quoted_should_find_the_entry():
    content = 'schema_version: 1\n\nassets:\n  "qa":\n    version: "^1.0.0"\n'

    updated = replace_block(content, "qa", QA_LINES)

    assert updated.endswith("\n".join(QA_LINES) + '\n  "qa":\n    version: "^1.0.0"\n')


def test_replace_block_where_entry_missing_should_leave_content_unchanged():
    assert replace_block(MANIFEST, "nope", QA_LINES) == MANIFEST


def test_replace_block_where_other_entry_has_a_block_should_not_touch_it():
    content = (
        "schema_version: 1\n\nassets:\n"
        "  # itqan:columns CSV, one row per ayah: surah, ayah, a, b\n"
        '  other:\n    version: "^1.0.0"\n'
        '  qa:\n    version: "^1.0.0"\n'
    )

    updated = replace_block(content, "qa", QA_LINES)

    assert "  # itqan:columns CSV, one row per ayah: surah, ayah, a, b\n  other:" in updated
    assert updated.endswith("\n".join(QA_LINES) + '\n  qa:\n    version: "^1.0.0"\n')


def test_replace_block_where_result_is_not_a_valid_manifest_should_raise():
    with pytest.raises(ManifestError):
        replace_block(MANIFEST, "qa", ["  not: [a valid comment"])
