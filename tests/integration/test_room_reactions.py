"""Live Socket.IO coverage for ephemeral Player → Host room reactions."""

from __future__ import annotations

import asyncio

import pytest

from .helpers import Tracker
from .test_question_feedback import MC
from .test_question_types import LiveGame


@pytest.fixture
def t(docker_stack, base_url, admin_token):
    tracker = Tracker(base_url, admin_token)
    yield tracker
    tracker.cleanup()


def test_host_controls_reactions_and_player_sends_to_host(t, base_url):
    async def run():
        async with LiveGame(t, base_url, [MC], players=1) as game:
            host, player = game.host, game.players[0]
            # LiveGame.join consumed sync_state; rejoin exercises persisted sync.
            await host.emit("rejoin_room", {"room_code": game.room})
            assert (await host.wait_for("sync_state"))["reactionsEnabled"] is True

            await player.emit("host_set_reactions", {"enabled": False})
            assert (
                "Only the Host" in (await player.wait_for("reaction_error"))["message"]
            )

            await host.emit("host_set_reactions", {"enabled": False})
            assert (await host.wait_for("reactions_enabled"))["enabled"] is False
            assert (await player.wait_for("reactions_enabled"))["enabled"] is False
            await player.emit("rejoin_room", {"room_code": game.room})
            assert (await player.wait_for("sync_state"))["reactionsEnabled"] is False

            await player.emit("player_reaction", {"kind": "text", "value": "Hello"})
            assert "turned off" in (await player.wait_for("reaction_error"))["message"]
            with pytest.raises(asyncio.TimeoutError):
                await host.wait_for("reaction_bubble", 0.4)

            await host.emit("host_set_reactions", {"enabled": True})
            assert (await host.wait_for("reactions_enabled"))["enabled"] is True
            assert (await player.wait_for("reactions_enabled"))["enabled"] is True

            await host.emit("player_reaction", {"kind": "emoji", "value": "👏"})
            assert "Only players" in (await host.wait_for("reaction_error"))["message"]
            for invalid in (
                {"kind": "emoji", "value": "🚫"},
                {"kind": "text", "value": " "},
                {"kind": "text", "value": "x" * 81},
            ):
                await player.emit("player_reaction", invalid)
                await player.wait_for("reaction_error")

            await player.emit(
                "player_reaction", {"kind": "text", "value": "  Nice   one!  "}
            )
            bubble = await host.wait_for("reaction_bubble")
            assert bubble["kind"] == "text" and bubble["value"] == "Nice one!"
            assert bubble["displayName"] and bubble["id"]
            with pytest.raises(asyncio.TimeoutError):
                await player.wait_for("reaction_bubble", 0.4)

            await player.emit("player_reaction", {"kind": "emoji", "value": "👏"})
            assert "Wait" in (await player.wait_for("reaction_error"))["message"]

            await game.next_question()
            await host.emit("host_set_reactions", {"enabled": False})
            assert (
                "before the game starts"
                in (await host.wait_for("reaction_error"))["message"]
            )
            await asyncio.sleep(5.1)
            await player.emit("player_reaction", {"kind": "emoji", "value": "👏"})
            assert (await host.wait_for("reaction_bubble"))["value"] == "👏"
            await game.results()
            await game.finish()
            await player.emit("player_reaction", {"kind": "emoji", "value": "👏"})
            assert (
                "no longer active"
                in (await player.wait_for("reaction_error"))["message"]
            )

    asyncio.run(run())


def test_reaction_only_reaches_its_own_host(t, base_url):
    async def run():
        async with LiveGame(t, base_url, [MC], players=1) as first:
            async with LiveGame(t, base_url, [MC], players=1) as second:
                await first.players[0].emit(
                    "player_reaction", {"kind": "emoji", "value": "🎉"}
                )
                assert (await first.host.wait_for("reaction_bubble"))["value"] == "🎉"
                with pytest.raises(asyncio.TimeoutError):
                    await second.host.wait_for("reaction_bubble", 0.5)

    asyncio.run(run())
