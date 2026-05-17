from collections.abc import Sequence
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker
from telegram import MessageEntity

from lmbatbot.database.models import TagGroup
from lmbatbot.database.types import UpsertResult
from lmbatbot.tags import (
    TagAddArgs,
    _collect_tags_for_groups,
    _parse_tagadd_command,
    _upsert_tag_group,
    hashtag_message_handler,
    tagadd_command_handler,
    tagdel_command_handler,
    taglist_command_handler,
)
from lmbatbot.utils import CommandParsingError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_message(
    hashtags: Sequence[str] = (),
    mentions: Sequence[str] = (),
    text_mentions: Sequence[str] = (),
    from_username: str | None = "sender",
    from_name: str = "@sender",
    chat_name: str = "Test Chat",
) -> MagicMock:
    msg = MagicMock()
    msg.from_user.username = from_username
    msg.from_user.name = from_name
    msg.chat.effective_name = chat_name
    msg.reply_text = AsyncMock()
    msg.reply_html = AsyncMock()
    msg.build_reply_arguments = MagicMock(return_value={})

    entity_data = {
        MessageEntity.HASHTAG: {MagicMock(): h for h in hashtags},
        MessageEntity.MENTION: {MagicMock(): m for m in mentions},
        MessageEntity.TEXT_MENTION: {MagicMock(): t for t in text_mentions},
    }

    def _parse_entities(types: list[str]) -> dict:
        for t in types:
            if t in entity_data:
                return entity_data[t]
        return {}

    msg.parse_entities = _parse_entities
    return msg


def _make_update(
    chat_id: int = 100,
    user_id: int = 200,
    username: str = "sender",
    message: MagicMock | None = None,
) -> MagicMock:
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_chat.send_message = AsyncMock()
    update.effective_user.id = user_id
    update.effective_user.username = username
    update.effective_user.name = f"@{username}"
    update.effective_message = message or _make_message()
    return update


# ---------------------------------------------------------------------------
# _parse_tagadd_command
# ---------------------------------------------------------------------------


class TestParseTagaddCommand:
    def test_valid_single_mention(self):
        msg = _make_message(hashtags=["#team"], mentions=["@alice"])
        result = _parse_tagadd_command(msg)
        assert result.group == "#team"
        assert result.tags == ["@alice"]

    def test_valid_multiple_mentions(self):
        msg = _make_message(hashtags=["#team"], mentions=["@alice", "@bob"])
        result = _parse_tagadd_command(msg)
        assert result.group == "#team"
        assert set(result.tags) == {"@alice", "@bob"}

    def test_deduplicates_mentions_case_insensitive(self):
        msg = _make_message(hashtags=["#team"], mentions=["@Alice", "@alice", "@ALICE"])
        result = _parse_tagadd_command(msg)
        assert result.tags == ["@alice"]

    def test_normalises_group_to_lowercase(self):
        msg = _make_message(hashtags=["#TEAM"], mentions=["@alice"])
        result = _parse_tagadd_command(msg)
        assert result.group == "#team"

    def test_no_hashtag_raises(self):
        msg = _make_message(hashtags=[], mentions=["@alice"])
        with pytest.raises(CommandParsingError, match="Invalid number of tag groups"):
            _parse_tagadd_command(msg)

    def test_multiple_hashtags_raises(self):
        msg = _make_message(hashtags=["#a", "#b"], mentions=["@alice"])
        with pytest.raises(CommandParsingError, match="Invalid number of tag groups"):
            _parse_tagadd_command(msg)

    def test_no_mentions_raises(self):
        msg = _make_message(hashtags=["#team"], mentions=[])
        with pytest.raises(CommandParsingError, match="No mentions found"):
            _parse_tagadd_command(msg)

    def test_text_mention_raises(self):
        msg = _make_message(hashtags=["#team"], mentions=["@alice"], text_mentions=["Bob"])
        with pytest.raises(CommandParsingError, match="TEXT_MENTION are not supported"):
            _parse_tagadd_command(msg)


# ---------------------------------------------------------------------------
# _upsert_tag_group
# ---------------------------------------------------------------------------


class TestUpsertTagGroup:
    def test_insert_new_group(self, session_factory: sessionmaker):
        with patch("lmbatbot.tags.Session", session_factory):
            args = TagAddArgs(group="#team", tags=["@alice"])
            result = _upsert_tag_group(chat_id=1, tag_group=args)
        assert result == UpsertResult.INSERTED

    def test_update_existing_group(self, session_factory: sessionmaker):
        with patch("lmbatbot.tags.Session", session_factory):
            args = TagAddArgs(group="#team", tags=["@alice"])
            _upsert_tag_group(chat_id=1, tag_group=args)

            args_updated = TagAddArgs(group="#team", tags=["@alice", "@bob"])
            result = _upsert_tag_group(chat_id=1, tag_group=args_updated)
        assert result == UpsertResult.UPDATED

    def test_groups_are_isolated_per_chat(self, session_factory: sessionmaker):
        with patch("lmbatbot.tags.Session", session_factory):
            args = TagAddArgs(group="#team", tags=["@alice"])
            r1 = _upsert_tag_group(chat_id=1, tag_group=args)
            r2 = _upsert_tag_group(chat_id=2, tag_group=args)
        assert r1 == UpsertResult.INSERTED
        assert r2 == UpsertResult.INSERTED


# ---------------------------------------------------------------------------
# _collect_tags_for_groups
# ---------------------------------------------------------------------------


class TestCollectTagsForGroups:
    def _seed(self, session_factory: sessionmaker, chat_id: int, groups: dict[str, list[str]]) -> None:
        with session_factory.begin() as s:
            for group_name, tags in groups.items():
                s.add(TagGroup(chat_id=chat_id, group_name=group_name, tags=tags))

    def test_returns_union_of_matching_groups(self, session_factory: sessionmaker):
        self._seed(session_factory, 1, {"#a": ["@x", "@y"], "#b": ["@y", "@z"]})
        with patch("lmbatbot.tags.Session", session_factory):
            result = _collect_tags_for_groups(1, ["#a", "#b"])
        assert result == {"@x", "@y", "@z"}

    def test_returns_empty_when_no_match(self, session_factory: sessionmaker):
        self._seed(session_factory, 1, {"#a": ["@x"]})
        with patch("lmbatbot.tags.Session", session_factory):
            result = _collect_tags_for_groups(1, ["#missing"])
        assert result == set()

    def test_isolated_per_chat(self, session_factory: sessionmaker):
        self._seed(session_factory, 1, {"#team": ["@alice"]})
        self._seed(session_factory, 2, {"#team": ["@bob"]})
        with patch("lmbatbot.tags.Session", session_factory):
            result = _collect_tags_for_groups(2, ["#team"])
        assert result == {"@bob"}


# ---------------------------------------------------------------------------
# taglist_command_handler
# ---------------------------------------------------------------------------


class TestTaglistCommandHandler:
    async def test_empty_list(self, session_factory: sessionmaker):
        update = _make_update()
        with patch("lmbatbot.tags.Session", session_factory):
            await taglist_command_handler(update, MagicMock())
        update.effective_chat.send_message.assert_awaited_once()
        sent = update.effective_chat.send_message.call_args[0][0]
        assert "no configured groups" in sent.lower() or "there are no" in sent.lower()

    async def test_lists_groups(self, session_factory: sessionmaker):
        with session_factory.begin() as s:
            s.add(TagGroup(chat_id=100, group_name="#team", tags=["@alice", "@bob"]))
        update = _make_update(chat_id=100)
        with patch("lmbatbot.tags.Session", session_factory):
            await taglist_command_handler(update, MagicMock())
        sent = update.effective_chat.send_message.call_args[0][0]
        assert "#team" in sent
        assert "alice" in sent
        assert "bob" in sent


# ---------------------------------------------------------------------------
# tagadd_command_handler
# ---------------------------------------------------------------------------


class TestTagaddCommandHandler:
    async def test_adds_new_group(self, session_factory: sessionmaker):
        msg = _make_message(hashtags=["#team"], mentions=["@alice"])
        update = _make_update(chat_id=100, message=msg)
        with patch("lmbatbot.tags.Session", session_factory):
            await tagadd_command_handler(update, MagicMock())
        update.effective_chat.send_message.assert_awaited_once()
        sent = update.effective_chat.send_message.call_args[0][0]
        assert "added" in sent.lower()

    async def test_updates_existing_group(self, session_factory: sessionmaker):
        with session_factory.begin() as s:
            s.add(TagGroup(chat_id=100, group_name="#team", tags=["@alice"]))
        msg = _make_message(hashtags=["#team"], mentions=["@bob"])
        update = _make_update(chat_id=100, message=msg)
        with patch("lmbatbot.tags.Session", session_factory):
            await tagadd_command_handler(update, MagicMock())
        sent = update.effective_chat.send_message.call_args[0][0]
        assert "updated" in sent.lower()

    async def test_invalid_format_replies_with_error(self, session_factory: sessionmaker):
        msg = _make_message(hashtags=[], mentions=["@alice"])
        update = _make_update(message=msg)
        with patch("lmbatbot.tags.Session", session_factory):
            await tagadd_command_handler(update, MagicMock())
        update.effective_message.reply_text.assert_awaited_once()
        update.effective_chat.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# tagdel_command_handler
# ---------------------------------------------------------------------------


class TestTagdelCommandHandler:
    async def test_deletes_existing_group(self, session_factory: sessionmaker):
        with session_factory.begin() as s:
            s.add(TagGroup(chat_id=100, group_name="#team", tags=["@alice"]))
        msg = _make_message(hashtags=["#team"])
        update = _make_update(chat_id=100, message=msg)
        with patch("lmbatbot.tags.Session", session_factory):
            await tagdel_command_handler(update, MagicMock())
        sent = update.effective_chat.send_message.call_args[0][0]
        assert "#team" in sent

        with session_factory() as s:
            remaining = s.query(TagGroup).filter_by(chat_id=100, group_name="#team").first()
        assert remaining is None

    async def test_missing_hashtag_replies_with_error(self):
        msg = _make_message(hashtags=[])
        update = _make_update(message=msg)
        await tagdel_command_handler(update, MagicMock())
        update.effective_message.reply_text.assert_awaited_once()
        update.effective_chat.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# hashtag_message_handler
# ---------------------------------------------------------------------------


class TestHashtagMessageHandler:
    async def test_sends_mentions_for_matching_group(self, session_factory: sessionmaker):
        with session_factory.begin() as s:
            s.add(TagGroup(chat_id=100, group_name="#team", tags=["@alice", "@bob"]))
        msg = _make_message(hashtags=["#team"], from_username="carol")
        update = _make_update(chat_id=100, username="carol", message=msg)
        with patch("lmbatbot.tags.Session", session_factory), patch("lmbatbot.tags.settings") as mock_settings:
            mock_settings.GLOBAL_PVT_NOTIFICATION_USERS = []
            await hashtag_message_handler(update, MagicMock())
        msg.reply_html.assert_awaited_once()
        reply_text = msg.reply_html.call_args[0][0]
        assert "@alice" in reply_text or "@bob" in reply_text

    async def test_no_reply_for_unknown_hashtag(self, session_factory: sessionmaker):
        msg = _make_message(hashtags=["#unknown"])
        update = _make_update(chat_id=100, message=msg)
        with patch("lmbatbot.tags.Session", session_factory):
            await hashtag_message_handler(update, MagicMock())
        msg.reply_html.assert_not_awaited()

    async def test_sender_excluded_from_mentions(self, session_factory: sessionmaker):
        with session_factory.begin() as s:
            s.add(TagGroup(chat_id=100, group_name="#team", tags=["@alice", "@sender"]))
        msg = _make_message(hashtags=["#team"], from_username="sender")
        update = _make_update(chat_id=100, username="sender", message=msg)
        with patch("lmbatbot.tags.Session", session_factory), patch("lmbatbot.tags.settings") as mock_settings:
            mock_settings.GLOBAL_PVT_NOTIFICATION_USERS = []
            await hashtag_message_handler(update, MagicMock())
        reply_text = msg.reply_html.call_args[0][0]
        assert "@sender" not in reply_text
        assert "@alice" in reply_text

    async def test_no_reply_when_only_sender_in_group(self, session_factory: sessionmaker):
        with session_factory.begin() as s:
            s.add(TagGroup(chat_id=100, group_name="#solo", tags=["@sender"]))
        msg = _make_message(hashtags=["#solo"], from_username="sender")
        update = _make_update(chat_id=100, username="sender", message=msg)
        with patch("lmbatbot.tags.Session", session_factory), patch("lmbatbot.tags.settings") as mock_settings:
            mock_settings.GLOBAL_PVT_NOTIFICATION_USERS = []
            await hashtag_message_handler(update, MagicMock())
        msg.reply_html.assert_not_awaited()
