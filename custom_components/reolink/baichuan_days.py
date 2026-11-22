"""Which days still have footage on the NVR, over Baichuan "day records" (cmd 142).

Not part of upstream HA: added by camera-card so the recording-list cache keeps
every day the NVR keeps, and drops a day once the NVR has overwritten it.
"""
import calendar
import datetime as dt
import re

HEAD = '<?xml version="1.0" encoding="UTF-8" ?>\n<body>\n'


def _tm(tag: str, t: dt.datetime) -> str:
    parts = zip(("year", "month", "day", "hour", "minute", "second"), (t.year, t.month, t.day, t.hour, t.minute, t.second))
    return f"<{tag}>" + "".join(f"<{k}>{v}</{k}>" for k, v in parts) + f"</{tag}>"


async def record_days(bc, ch: int, year: int, month: int) -> list[dt.date]:
    """Days in one month with footage on ch. A range spanning two months comes back empty, so ask per month."""
    last = calendar.monthrange(year, month)[1]
    body = (HEAD + '<DayRecords version="1.1">' + _tm("startTime", dt.datetime(year, month, 1))
            + _tm("endTime", dt.datetime(year, month, last, 23, 59, 59))
            + f"<DayRecordList><DayRecord><index>0</index><channelId>{ch}</channelId></DayRecord></DayRecordList></DayRecords></body>")
    reply = await bc.send(cmd_id=142, channel=ch, body=body)
    # each <index> counts days from the 1st; the request's own DayRecord echoes back with no <type>
    return [dt.date(year, month, 1 + i) for i in map(int, re.findall(r"<index>(\d+)</index>\s*<type>", reply)) if i < last]


async def days_with_footage(bc, ch: int, today: dt.date, months: int = 13) -> set[dt.date]:
    """Every day with footage on ch over the last `months` months. One query per month, one at a time.

    Asks every month rather than stopping at an empty one: a camera offline for a month leaves a gap.
    reolink_aio's request_vod_files(status_only=True) would do this in one call, but on our NVR it fails
    outright when the span reaches past the oldest footage, which is exactly what this has to find.
    """
    days, y, m = set(), today.year, today.month
    for _ in range(months):
        days.update(await record_days(bc, ch, y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return days
