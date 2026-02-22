import asyncio
import datetime
import platform
import re
import shutil

import psutil
from pyrogram import __version__ as pyrogram_version
from pyrogram import filters
from pyrogram.types import Message

from selfbot.listener import handler, reply
from selfbot.module import Module

pattern = re.compile(r"^sysinfo$")


def format_bytes(size: int) -> str:
    power = 1024
    n = 0
    power_labels = {0: "", 1: "K", 2: "M", 3: "G", 4: "T"}
    while size > power and n < len(power_labels) - 1:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}B"


class Sysinfo(Module):
    name = "Sysinfo"
    cmds = "sysinfo"
    desc = "Displays system information."

    @handler(filters.regex(pattern) & ~reply, 1)
    async def on_message_out(self, event: Message) -> None:
        await self.respond(event, "<code>Gathering information...</code>")
        now = datetime.datetime.now(datetime.UTC)
        sys_info = await self.get_system_info()
        await self.respond(event, self.fmtmsg("System Info", sys_info, self.fmtsec(now)))

    def get_os_info(self) -> str:
        system = platform.system()
        try:
            if system == "Linux":
                try:
                    return platform.freedesktop_os_release().get(
                        "PRETTY_NAME", f"{system} {platform.release()}"
                    )
                except (FileNotFoundError, AttributeError):
                    return f"{system} {platform.release()}"
            if system == "Darwin":
                return f"macOS {platform.mac_ver()[0]}"
            return f"{system} {platform.release()}"
        except Exception as e:
            self.logger.warning(f"Failed to get OS info: {e}")
            return f"{system} {platform.release()}"

    async def get_system_info(self) -> dict:
        try:
            def get_cpu_info() -> str:
                cpu_freq = psutil.cpu_freq()
                cpu_usage = psutil.cpu_percent(interval=1)
                cpu_info = (
                    f"{psutil.cpu_count(logical=False)} Cores, "
                    f"{psutil.cpu_count(logical=True)} Threads"
                )
                if cpu_freq and cpu_freq.current:
                    cpu_info += f" @ {cpu_freq.current:.2f} MHz"
                cpu_info += f" ({cpu_usage}%)"
                return cpu_info

            def get_memory_info():
                return psutil.virtual_memory()

            def get_disk_info():
                return shutil.disk_usage("/")

            def get_boot_time():
                return datetime.datetime.fromtimestamp(psutil.boot_time(), tz=datetime.UTC)

            def get_load_average():
                try:
                    return psutil.getloadavg()
                except (AttributeError, NotImplementedError):
                    return None

            cpu_info = await asyncio.to_thread(get_cpu_info)
            mem = await asyncio.to_thread(get_memory_info)
            disk = await asyncio.to_thread(get_disk_info)
            boot_time = await asyncio.to_thread(get_boot_time)
            load_avg = await asyncio.to_thread(get_load_average)

            disk_percent = (disk.used / disk.total) * 100
            uptime = datetime.datetime.now(datetime.UTC) - boot_time

            info = {
                "OS": self.get_os_info(),
                "Kernel": platform.release(),
                "CPU": cpu_info,
                "Architecture": platform.machine(),
            }

            if load_avg:
                info["Load Average"] = (
                    f"{load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}"
                )

            info["RAM"] = (
                f"{format_bytes(mem.used)} / {format_bytes(mem.total)} ({mem.percent}%)"
            )

            swap = psutil.swap_memory()
            if swap.total > 0:
                info["Swap"] = (
                    f"{format_bytes(swap.used)} / "
                    f"{format_bytes(swap.total)} ({swap.percent}%)"
                )

            info["Disk"] = (
                f"{format_bytes(disk.used)} / "
                f"{format_bytes(disk.total)} ({disk_percent:.2f}%)"
            )
            info["Python"] = platform.python_version()
            info["Pyrogram"] = pyrogram_version
            info["Uptime"] = str(uptime).split(".")[0]
            return info
        except Exception as e:
            self.logger.error(f"Failed to gather system info: {e}")
            return {"Error": f"Failed to gather system information: {e}"}
