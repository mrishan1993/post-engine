from __future__ import annotations

import pytest

from orchestration.state_machine import RunStatus, assert_transition, can_transition


def test_happy_path_transitions() -> None:
    path = [
        RunStatus.CREATED,
        RunStatus.SCRIPT_DONE,
        RunStatus.AUDIO_DONE,
        RunStatus.VISUAL_DONE,
        RunStatus.ASSEMBLED,
        RunStatus.QA_PENDING,
        RunStatus.QA_APPROVED,
        RunStatus.PUBLISHED,
    ]
    for a, b in zip(path, path[1:]):
        assert can_transition(a, b)


def test_cannot_publish_without_approval() -> None:
    assert not can_transition(RunStatus.QA_PENDING, RunStatus.PUBLISHED)
    assert not can_transition(RunStatus.ASSEMBLED, RunStatus.PUBLISHED)
    with pytest.raises(ValueError):
        assert_transition(RunStatus.QA_PENDING, RunStatus.PUBLISHED)


def test_reject_does_not_publish() -> None:
    assert can_transition(RunStatus.QA_PENDING, RunStatus.QA_REJECTED)
    assert not can_transition(RunStatus.QA_REJECTED, RunStatus.PUBLISHED)
