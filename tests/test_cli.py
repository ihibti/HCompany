import argparse

import pytest

from escapehatch.cli import build_parser, parse_levels


class TestParseLevels:
    @pytest.mark.parametrize(
        "spec,expected",
        [
            ("1-5", [1, 2, 3, 4, 5]),
            ("2", [2]),
            ("1,3,5", [1, 3, 5]),
            ("1-3,5", [1, 2, 3, 5]),
            (" 4 ", [4]),
            ("1-2,4-5", [1, 2, 4, 5]),
        ],
    )
    def test_valid_specs(self, spec, expected):
        assert parse_levels(spec) == expected

    @pytest.mark.parametrize("spec", ["", "  ", "a", "5-1", "0", "-3", "1-0"])
    def test_invalid_specs(self, spec):
        with pytest.raises((ValueError, IndexError)):
            parse_levels(spec)

    def test_out_of_range_level_allowed_but_matches_nothing(self):
        # levels beyond the gauntlet are filtered later by load_levels
        assert parse_levels("6") == [6]


class TestParser:
    def test_audit_defaults(self):
        args = build_parser().parse_args(["audit", "https://x.test"])
        assert args.command == "audit"
        assert args.task == "refuse_cookies"
        assert args.agent == "h/web-surfer-pro"
        assert args.enter is True
        assert args.store == "runs"

    def test_audit_no_enter_and_task(self):
        args = build_parser().parse_args(
            ["audit", "https://x.test", "--task", "cancel_subscription", "--no-enter"]
        )
        assert args.enter is False
        assert args.task == "cancel_subscription"

    def test_gauntlet_defaults(self):
        args = build_parser().parse_args(["gauntlet"])
        assert args.levels == "1-5"
        assert args.base == "https://ihibti.github.io/HCompany/"

    def test_report(self):
        args = build_parser().parse_args(["report", "abc-123"])
        assert args.audit_id == "abc-123"
