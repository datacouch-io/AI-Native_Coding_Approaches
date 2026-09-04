"""Fixed acceptance suite for the data export module.

These tests are written by the LAB, not by a model. They are the objective gate
after each milestone: the executor runs M1 after step 1, M1+M2 after step 2, and
so on, so a later step cannot quietly break an earlier one.
"""
import json

import pytest

from exporter import ExportError, export, filter_rows, to_csv, to_json

ROWS = [
    {"id": 1, "name": "Ada",   "score": 91.5, "active": True,
     "user": {"name": "ada@example.com"}, "note": "clean"},
    {"id": 2, "name": "Grace", "score": 78.0, "active": False,
     "user": {"name": "grace@example.com"}, "note": 'say "hi", then go'},
    {"id": 3, "name": "Linus", "score": 64.25, "active": True,
     "user": {},                            "note": "line1\nline2"},
]


class TestM1ToCsv:
    def test_header_is_fields_in_order(self):
        out = to_csv(ROWS, ["name", "id"])
        assert out.splitlines()[0] == "name,id"

    def test_crlf_line_endings_and_trailing_newline(self):
        out = to_csv(ROWS[:1], ["name"])
        assert out == "name\r\nAda\r\n"

    def test_quotes_commas_and_embedded_quotes(self):
        out = to_csv([ROWS[1]], ["note"])
        assert out == 'note\r\n"say ""hi"", then go"\r\n'

    def test_quotes_embedded_newline(self):
        out = to_csv([ROWS[2]], ["note"])
        assert out == 'note\r\n"line1\nline2"\r\n'

    def test_missing_and_none_render_empty(self):
        rows = [{"a": None}]
        assert to_csv(rows, ["a", "absent"]) == "a,absent\r\n,\r\n"

    def test_dotted_path_resolves_nested(self):
        out = to_csv(ROWS, ["user.name"])
        assert out.splitlines()[1] == "ada@example.com"

    def test_dotted_path_missing_is_empty_not_error(self):
        out = to_csv([ROWS[2]], ["user.name"])
        assert out == "user.name\r\n\r\n"


class TestM2ToJson:
    def test_returns_json_array_of_objects(self):
        data = json.loads(to_json(ROWS, ["id", "name"]))
        assert isinstance(data, list) and len(data) == 3
        assert data[0] == {"id": 1, "name": "Ada"}

    def test_only_requested_fields_in_given_order(self):
        data = json.loads(to_json(ROWS[:1], ["name", "id"]))
        assert list(data[0].keys()) == ["name", "id"]

    def test_types_are_preserved(self):
        data = json.loads(to_json(ROWS[:1], ["score", "active", "id"]))
        assert data[0]["score"] == 91.5
        assert data[0]["active"] is True
        assert data[0]["id"] == 1

    def test_missing_path_is_null(self):
        data = json.loads(to_json([ROWS[2]], ["user.name"]))
        assert data[0]["user.name"] is None

    def test_dotted_path_resolves_nested(self):
        data = json.loads(to_json(ROWS[:1], ["user.name"]))
        assert data[0]["user.name"] == "ada@example.com"


class TestM3FilterRows:
    def test_bare_field_is_equality(self):
        assert [r["id"] for r in filter_rows(ROWS, {"active": True})] == [1, 3]

    def test_multiple_conditions_are_anded(self):
        got = filter_rows(ROWS, {"active": True, "name": "Ada"})
        assert [r["id"] for r in got] == [1]

    def test_gt_gte_lt_lte(self):
        assert [r["id"] for r in filter_rows(ROWS, {"score__gt": 78.0})] == [1]
        assert [r["id"] for r in filter_rows(ROWS, {"score__gte": 78.0})] == [1, 2]
        assert [r["id"] for r in filter_rows(ROWS, {"score__lt": 78.0})] == [3]
        assert [r["id"] for r in filter_rows(ROWS, {"score__lte": 78.0})] == [2, 3]

    def test_in_operator(self):
        got = filter_rows(ROWS, {"name__in": ["Ada", "Linus"]})
        assert [r["id"] for r in got] == [1, 3]

    def test_contains_is_case_sensitive(self):
        assert [r["id"] for r in filter_rows(ROWS, {"note__contains": "clean"})] == [1]
        assert filter_rows(ROWS, {"note__contains": "CLEAN"}) == []

    def test_dotted_path_in_where(self):
        got = filter_rows(ROWS, {"user.name": "grace@example.com"})
        assert [r["id"] for r in got] == [2]

    def test_unknown_operator_raises_exporterror(self):
        with pytest.raises(ExportError):
            filter_rows(ROWS, {"score__wat": 1})

    def test_incompatible_comparison_excludes_row(self):
        # comparing a str field with > against a number must not raise
        assert filter_rows(ROWS, {"name__gt": 5}) == []

    def test_empty_where_returns_all(self):
        assert len(filter_rows(ROWS, {})) == 3


class TestM4Export:
    def test_csv_roundtrip_without_path(self):
        out = export(ROWS, fmt="csv", fields=["name"])
        assert out.splitlines()[0] == "name"

    def test_json_roundtrip_without_path(self):
        data = json.loads(export(ROWS, fmt="json", fields=["id"]))
        assert [d["id"] for d in data] == [1, 2, 3]

    def test_where_is_applied_before_formatting(self):
        data = json.loads(export(ROWS, fmt="json", fields=["id"],
                                 where={"active": True}))
        assert [d["id"] for d in data] == [1, 3]

    def test_unknown_format_raises(self):
        with pytest.raises(ExportError):
            export(ROWS, fmt="xml", fields=["id"])

    def test_empty_fields_raises(self):
        with pytest.raises(ExportError):
            export(ROWS, fmt="csv", fields=[])

    def test_path_writes_utf8_and_returns_path(self, tmp_path):
        target = tmp_path / "out.csv"
        returned = export(ROWS, fmt="csv", fields=["name"], path=str(target))
        assert returned == str(target)
        assert target.read_text(encoding="utf-8").splitlines()[0] == "name"

    def test_none_where_means_no_filter(self):
        data = json.loads(export(ROWS, fmt="json", fields=["id"], where=None))
        assert len(data) == 3
