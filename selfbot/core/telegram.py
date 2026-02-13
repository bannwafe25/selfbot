import abc
import asyncio
import contextlib
import functools
import signal

from pyrogram import Client
from pyrogram import filters as flt
from pyrogram.enums import ChatAction, ClientPlatform, ParseMode
from pyrogram.errors import (
    FloodWait,
    MessageDeleteForbidden,
    PeerIdInvalid,
    RPCError,
    UserIsBlocked,
)
from pyrogram.handlers import (
    CallbackQueryHandler,
    ChosenInlineResultHandler,
    InlineQueryHandler,
    MessageHandler,
)
from pyrogram.raw.types import (
    UpdateBotInlineQuery,
    UpdateBotInlineSend,
    UpdateInlineBotCallbackQuery,
    UpdateNewChannelMessage,
    UpdateNewMessage,
)
from pyrogram.types import (
    ChatPrivileges,
    KeyboardButton,
    KeyboardButtonRequestChat,
    KeyboardButtonRequestUsers,
    LinkPreviewOptions,
    ReplyKeyboardMarkup,
    Update,
)

from selfbot import __version__
from selfbot.storage import PostgreStorage


class Telegram(abc.ABC):
    def __init__(self, **kwargs) -> None:
        self.app = None
        self.bot = None
        self.handlers = {}
        self.__idle__ = None
        super().__init__(**kwargs)

    async def run(self) -> None:
        if self.__idle__ and not self.__idle__.is_set():
            raise RuntimeError(f"{self.__class__.__name__} Running")

        await self.initdb()
        rows = await self.db.fetch(
            "SELECT name, chat_id, message_id FROM restart.msgs;"
        )
        self.logger.info(f"Starting {self.__class__.__name__}...")
        try:
            await self.start()
            for row in rows:
                name, chat_id, message_id = (
                    row["name"],
                    row["chat_id"],
                    row["message_id"],
                )
                if name == "app":
                    await self.app.delete_messages(chat_id, message_id)
                elif name == "bot":
                    with contextlib.suppress(MessageDeleteForbidden):
                        await self.bot.delete_messages(chat_id, message_id)

                await self.db.execute("DELETE FROM restart.msgs WHERE name = $1;", name)

            rkm = ReplyKeyboardMarkup(
                [
                    [
                        KeyboardButton(
                            "Owned Groups",
                            request_chat=KeyboardButtonRequestChat(
                                10, chat_is_channel=False, chat_is_created=True
                            ),
                        ),
                        KeyboardButton(
                            "Owned Channels",
                            request_chat=KeyboardButtonRequestChat(
                                11, chat_is_channel=True, chat_is_created=True
                            ),
                        ),
                    ],
                    [
                        KeyboardButton(
                            "Admin Groups",
                            request_chat=KeyboardButtonRequestChat(
                                20,
                                chat_is_channel=False,
                                chat_is_created=False,
                                user_administrator_rights=ChatPrivileges(),
                            ),
                        ),
                        KeyboardButton(
                            "Admin Channels",
                            request_chat=KeyboardButtonRequestChat(
                                21,
                                chat_is_channel=True,
                                chat_is_created=False,
                                user_administrator_rights=ChatPrivileges(),
                            ),
                        ),
                    ],
                    [
                        KeyboardButton(
                            "Peer Groups",
                            request_chat=KeyboardButtonRequestChat(
                                30, chat_is_channel=False
                            ),
                        ),
                        KeyboardButton(
                            "Peer Channels",
                            request_chat=KeyboardButtonRequestChat(
                                31, chat_is_channel=True
                            ),
                        ),
                    ],
                    [
                        KeyboardButton(
                            "Peer Users & Peer Bots",
                            request_users=KeyboardButtonRequestUsers(40),
                        )
                    ],
                ],
                is_persistent=True,
                resize_keyboard=True,
                input_field_placeholder=f"Selfbot {__version__}",
            )
            new = await self.bot.send_sticker(
                self.app.me.id,
                self.config["STICKER_FILE_ID"],
                disable_notification=True,
                reply_markup=rkm,
            )
            await self.db.execute(
                """
                INSERT INTO restart.msgs AS r (
                    name,
                    chat_id,
                    message_id
                )
                VALUES ($1, $2, $3)
                ON CONFLICT (name)
                DO UPDATE SET
                    chat_id     = EXCLUDED.chat_id,
                    message_id  = EXCLUDED.message_id
                WHERE
                    r.chat_id       IS DISTINCT FROM EXCLUDED.chat_id
                OR  r.message_id    IS DISTINCT FROM EXCLUDED.message_id;
                """,
                "bot",
                new.chat.id,
                new.id,
            )
        except Exception as e:
            self.logger.error(f"{e.__class__.__name__}: {e}")
            raise

        self.logger.info(f"{self.__class__.__name__} Started")
        await self.idle()

    async def start(self) -> None:
        if self.__idle__ and not self.__idle__.is_set():
            raise RuntimeError(f"{self.__class__.__name__} Started")

        self.app = self.build(
            "app", updates=(UpdateNewChannelMessage, UpdateNewMessage)
        )
        try:
            await self.app.start()
        except RPCError as e:
            if isinstance(e, FloodWait):
                self.logger.warning(f"{e.__class__.__name__}: {e}")
            else:
                self.logger.error(f"{e.__class__.__name__}: {e}")
                await self.app.storage.delete()

            raise

        self.bot = self.build(
            "bot",
            updates=(
                UpdateBotInlineQuery,
                UpdateBotInlineSend,
                UpdateInlineBotCallbackQuery,
                UpdateNewMessage,
            ),
            bot_token=self.config.get("BOT_TOKEN"),
        )
        try:
            await self.bot.start()
        except RPCError as e:
            if isinstance(e, FloodWait):
                self.logger.warning(f"{e.__class__.__name__}: {e}")
            else:
                self.logger.error(f"{e.__class__.__name__}: {e}")
                await self.bot.storage.delete()

            raise

        self.config.pop("BOT_TOKEN", None)
        await asyncio.gather(
            self.app.resolve_peer(self.bot.me.username), asyncio.to_thread(self.loads)
        )
        try:
            await self.bot.send_chat_action(self.app.me.id, ChatAction.TYPING)
        except PeerIdInvalid:
            msg = await self.app.send_message(self.bot.me.id, "/start")
            await msg.delete()
        except UserIsBlocked:
            await self.app.unblock_user(self.bot.me.id)

        await self.dispatch("starting")
        asyncio.create_task(self.dispatch("started"))

    async def idle(self) -> None:
        if self.__idle__ and not self.__idle__.is_set():
            raise RuntimeError(f"{self.__class__.__name__} Idling")

        signames = (signal.SIGINT, signal.SIGTERM, signal.SIGABRT)

        def sighandler(signum: int) -> None:
            if self.__idle__:
                self.__idle__.set()

        for signame in signames:
            self.loop.add_signal_handler(
                signame, functools.partial(sighandler, signame)
            )

        self.__idle__ = asyncio.Event()
        try:
            await self.__idle__.wait()
        finally:
            for signame in signames:
                with contextlib.suppress(Exception):
                    self.loop.remove_signal_handler(signame)

    def updates(self) -> None:
        fltapp = flt.user(self.app.me.id)
        events = {
            self.app.name: (self.app, MessageHandler, flt.incoming, -1),
            "message_in": (
                self.app,
                MessageHandler,
                (flt.mentioned | (flt.incoming & flt.private))
                & (~flt.me & ~flt.bot & ~flt.via_bot & ~flt.service),
                -1,
            ),
            "message_out": (
                self.app,
                MessageHandler,
                (flt.me & (flt.text | flt.caption)) & ~flt.via_bot,
                -1,
            ),
            self.bot.name: (self.bot, MessageHandler, flt.incoming, -1),
            "message_bot": (self.bot, MessageHandler, fltapp, -1),
            "inline_query": (self.bot, InlineQueryHandler, fltapp, -1),
            "inline_result": (self.bot, ChosenInlineResultHandler, fltapp, -1),
            "inline_callback": (self.bot, CallbackQueryHandler, fltapp, -1),
        }
        for name, (client, handler, filters, group) in events.items():
            if name in self.handlers:
                client.remove_handler(*self.handlers.pop(name))

            if name in self.listeners and self.listeners[name]:

                async def callback(_, event: Update, bound=name) -> None:
                    asyncio.create_task(self.dispatch(bound, event))

                dispatcher = (handler(callback, filters), group)
                try:
                    client.add_handler(*dispatcher)
                finally:
                    self.handlers[name] = dispatcher

    def build(self, name: str, updates: tuple = (), *args, **kwargs) -> Client:
        client = Client(
            name=name,
            api_id=2496,
            api_hash="8da85b0d5bfe62527e5b244c209159c3",
            app_version="2.2 K",
            device_model="Chrome 143",
            workdir="./selfbot/",
            parse_mode=ParseMode.HTML,
            sleep_threshold=25,
            max_concurrent_transmissions=5,
            max_message_cache_size=0,
            max_business_user_connection_cache_size=0,
            no_joined_notifications=True,
            client_platform=ClientPlatform.ANDROID,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
            storage_engine=PostgreStorage(name, self.db),
            *args,
            **kwargs,
        )
        if updates:
            client.dispatcher.update_parsers = {
                k: v
                for k, v in client.dispatcher.update_parsers.items()
                if k in updates
            }
            client.workers = len(client.dispatcher.update_parsers)

        return client
