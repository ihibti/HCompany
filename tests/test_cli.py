import argparse
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from escapehatch.cli import build_parser, parse_levels
import escapehatch.cli as cli
from escapehatch.models import Audit
from escapehatch.prompts import Task, build_task_prompt
from escapehatch.scoring import score

from conftest import make_journey


@pytest.mark.asyncio
@pytest.mark.parametrize("selection,expected", [
    ([], [1, 2, 3, 4, 5]),
    (["--task", "unsubscribe"], [6, 7]),
    (["--levels", "6"], [6]),
    (["--levels", "6", "--task", "cancel_subscription"], []),
    (["--levels", "99"], []),
])
async def test_gauntlet_task_wiring(tmp_path, monkeypatch, selection, expected):
    calls = []

    async def fake_audit(**kw):
        calls.append(kw)
        leave = make_journey(["click_web"], task=kw["task"])
        enter = make_journey(["click_web"], task=Task.SUBSCRIBE) if kw["with_enter"] else None
        return Audit(id="test", created_at=datetime.now(timezone.utc),
                     site_url=kw["site_url"], task=kw["task"],
                     leave=leave, enter=enter, score=score(leave, enter, []))

    monkeypatch.setattr(cli, "run_audit", fake_audit)
    monkeypatch.setattr(cli, "KeyPool", lambda: AsyncMock())
    args = build_parser().parse_args(["gauntlet", "--store", str(tmp_path), *selection])
    result = await args.func(args)
    assert result == (0 if expected else 1)
    assert len(calls) == len(expected)
    if not expected:
        assert not list(tmp_path.rglob("*.json"))
        return
    rows = json.loads(next(tmp_path.rglob("*.json")).read_text())["levels"]
    assert [r["level"] for r in rows] == expected
    for call, row in zip(calls, rows):
        if row["level"] >= 6:
            assert call["task"] == Task.UNSUBSCRIBE
            assert call["with_enter"] is False
            assert call["enter_url"] is None
            assert row["enter_effort"] is None
            assert row["task"] == "unsubscribe"
            prompt = build_task_prompt(call["task"], call["site_url"], call["credentials"])
            assert "demo@netflux.test" in prompt
            assert "unsubscribe this email address from all marketing emails" in prompt
        else:
            assert call["task"] == Task.CANCEL_SUBSCRIPTION
            assert call["with_enter"] is True


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
        assert args.levels is None
        assert args.task is None
        assert args.base == "https://ihibti.github.io/HCompany/"

    def test_report(self):
        args = build_parser().parse_args(["report", "abc-123"])
        assert args.audit_id == "abc-123"
