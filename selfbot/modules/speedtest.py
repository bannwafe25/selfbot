import asyncio
import datetime
import html
import re

import speedtest
from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler, reply
from selfbot.module import Module

pattern = re.compile(r"^speed(?:test)?$")


class Speedtest(Module):
    name = "Speedtest"
    cmds = "speed(test)?"
    desc = {
        "?": "Optional",
        "e.g.": "speedtest",
        "Info": "Runs an internet speed test and displays the results.",
    }

    @handler(filters.regex(pattern) & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Running speedtest...</code>")
        now = datetime.datetime.now(datetime.UTC)
        try:
            results = await asyncio.to_thread(self.run_speed_test)
            if not results:
                await self.respond(
                    event, "<code>Speedtest failed: No results returned.</code>"
                )
                return

            await self.respond(
                event,
                self.fmtmsg(
                    "Speedtest Results",
                    {
                        "Provider": results.get("isp", "N/A"),
                        "Server": (
                            f"{results.get('server_name', 'N/A')} "
                            f"({results.get('server_country', 'N/A')})"
                        ),
                        "Ping": f"{results.get('ping', 0):.2f} ms",
                        "Download": f"{results.get('download', 0) / 1_000_000:.2f} Mbps",
                        "Upload": f"{results.get('upload', 0) / 1_000_000:.2f} Mbps",
                    },
                    self.fmtsec(now),
                ),
            )
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Speedtest failed: {error_msg}")
            await self.respond(
                event,
                (
                    "<b>Speedtest failed:</b>\n"
                    f"<code>{html.escape(error_msg[:200])}</code>"
                ),
            )

    def run_speed_test(self) -> dict:
        try:
            st = speedtest.Speedtest(secure=True)
            st.get_best_server()
            st.download()
            st.upload()
            return {
                "isp": st.results.client.get("isp", "N/A"),
                "server_name": st.results.server.get("name", "N/A"),
                "server_country": st.results.server.get("country", "N/A"),
                "ping": st.results.ping,
                "download": st.results.download,
                "upload": st.results.upload,
            }
        except AttributeError:
            try:
                return {
                    "isp": st.results["client"].get("isp", "N/A"),
                    "server_name": st.results["server"].get("name", "N/A"),
                    "server_country": st.results["server"].get("country", "N/A"),
                    "ping": st.results["ping"],
                    "download": st.results["download"],
                    "upload": st.results["upload"],
                }
            except Exception as e:
                raise Exception(f"Failed to extract speedtest results: {e}") from e
        except Exception as e:
            raise Exception(f"Speedtest execution failed: {e}") from e
