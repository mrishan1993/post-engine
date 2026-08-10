from __future__ import annotations

from typing import Any


class ContinuityTracker:
    """Tracks character / prop / location / screen-direction state across scenes."""

    def __init__(self) -> None:
        self.characters: dict[str, dict[str, Any]] = {}
        self.props: dict[str, dict[str, Any]] = {}
        self.location: dict[str, Any] = {
            "current": None,
            "previous": None,
            "time_of_day": "night",
            "weather": "still",
            "lighting": "low",
            "environmental_state": "dark",
        }
        self.screen_direction: str = "right"
        self.flags: list[str] = []

    def set_character(
        self,
        name: str,
        *,
        location: str | None = None,
        position: str = "standing",
        emotion: str = "neutral",
        prop: str | None = None,
    ) -> dict[str, Any]:
        state = self.characters.get(name) or {
            "location": location,
            "position": position,
            "emotion": emotion,
            "clothing": "default",
            "prop": {},
            "injuries": "none",
        }
        if location:
            state["location"] = location
        state["position"] = position
        state["emotion"] = emotion
        if prop:
            state["prop"] = {**(state.get("prop") or {}), prop: True}
        self.characters[name] = state
        return dict(state)

    def move_prop(self, prop: str, holder: str | None, position: str) -> dict[str, Any]:
        state = self.props.get(prop) or {}
        state.update({"holder": holder, "position": position})
        self.props[prop] = state
        if holder and holder in self.characters:
            self.characters[holder]["prop"] = {
                **(self.characters[holder].get("prop") or {}),
                prop: position != "ground",
            }
        return dict(state)

    def enter_location(self, location: str) -> dict[str, Any]:
        prev = self.location.get("current")
        if prev and prev != location:
            self.location["previous"] = prev
        self.location["current"] = location
        return dict(self.location)

    def update_screen_direction(self, direction: str, *, looking_at: str | None = None) -> None:
        if looking_at == "opposite" and self.screen_direction in {"left", "right"}:
            expected = "left" if self.screen_direction == "right" else "right"
            if direction not in {expected, "toward", "center"}:
                self.flags.append(
                    f"screen_direction_risk: was {self.screen_direction}, now {direction}"
                )
        self.screen_direction = direction

    def snapshot(self) -> dict[str, Any]:
        return {
            "characters": {k: dict(v) for k, v in self.characters.items()},
            "props": {k: dict(v) for k, v in self.props.items()},
            "location": dict(self.location),
            "screen_direction": self.screen_direction,
            "flags": list(self.flags),
        }
