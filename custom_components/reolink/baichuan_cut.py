"""Download a time range of an NVR recording as MP4 over Baichuan "download cut" (cmd 143).

Not part of upstream HA: added by camera-card because HA's NvrDownload path is
rejected on RLN8-410 fw v3.6.5 (home-assistant/core#179099).
"""
import asyncio
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime

from reolink_aio.baichuan import xmls

CUT, CUT_DONE = 143, 300  # the NVR ends a cut with an empty cmd-143 message carrying status 300
IDLE_TIMEOUT = 15
# One cut at a time per connection: the tap in stream_cut matches payloads on cmd_id, not mess_id.
# The NVR can't be told to stop a cut, so stream_cut reads it to the end even if its caller quits.
CUT_LOCK = asyncio.Lock()


def _tm(t: datetime) -> str:
    return "".join(f"<{k}>{getattr(t, k)}</{k}>" for k in ("year", "month", "day", "hour", "minute", "second"))


def _xml_time(block: str, tag: str) -> datetime:
    inner = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.S).group(1)
    return datetime(*(int(re.search(rf"<{k}>(\d+)</{k}>", inner).group(1)) for k in ("year", "month", "day", "hour", "minute", "second")))


async def find_file(bc, uid: str, ch: int, stream: str, start: datetime, end: datetime) -> tuple[str, str, datetime, datetime]:
    """Native recording file (name, Id, start and end clamped to the file) for [start, end]; times are NVR-local.

    The file containing start, else the first file starting inside the range.
    """
    tpl = xmls.FileInfoListOpen.replace("mainStream", f"{stream}Stream")
    times = {f"{p}_{k}": getattr(t, k) for p, t in (("start", start), ("end", end)) for k in ("year", "month", "day", "hour", "minute", "second")}
    reply = await bc.send(cmd_id=14, channel=ch, body=tpl.format(channel=ch, uid=uid, **times))
    close = xmls.FileInfoList.format(channel=ch, uid=uid, handle=re.search(r"<handle>(\d+)</handle>", reply).group(1))
    try:
        listing = await bc.send(cmd_id=15, channel=ch, body=close)
    finally:
        await bc.send(cmd_id=16, channel=ch, body=close)
    seen = []  # for the error: what the NVR did have is how a miss gets diagnosed
    later = None
    for block in re.findall(r"<FileInfo>(.*?)</FileInfo>", listing, re.S):
        file_start, file_end = _xml_time(block, "startTime"), _xml_time(block, "endTime")
        seen.append(f"{file_start:%H:%M:%S}-{file_end:%H:%M:%S}")
        found = re.search(r"<name>(.*?)</name>", block).group(1), re.search(r"<Id>(.*?)</Id>", block).group(1)
        if file_start <= start < file_end:
            # ponytail: a range crossing the hourly file boundary is cut short at it; stitch two cuts if that bites
            return *found, start, min(end, file_end)
        if later is None and start < file_start < end:
            # the NVR starts recording 1-3s after the person sensor fires, so alerts ask from before the file
            later = *found, file_start, min(end, file_end)
    if later:
        return later
    raise LookupError(f"no {stream}Stream recording on ch {ch} at {start} (files up to {end:%H:%M:%S}: {', '.join(seen) or 'none'})")


async def stream_cut(bc, uid: str, ch: int, stream: str, start: datetime, end: datetime):
    """Yield the raw BcMedia stream for [start, end] in chunks, as the NVR sends them. Hold CUT_LOCK."""
    name, file_id, start, end = await find_file(bc, uid, ch, stream, start, end)
    body = ('<?xml version="1.0" encoding="UTF-8" ?>\n<body>\n<FileInfoList version="1.1"><FileInfo>'
            f"<uid>{uid}</uid><channelId>{ch}</channelId><streamType>{stream}Stream</streamType>"
            f"<startTime>{_tm(start)}</startTime><endTime>{_tm(end)}</endTime>"
            f"<name>{name}</name><Id>{file_id}</Id></FileInfo></FileInfoList>\n</body>")
    chunks: asyncio.Queue = asyncio.Queue()  # None marks the end
    proto = bc._connection._protocol  # find_file above guarantees the connection exists
    orig = proto._push_callback

    # reolink_aio drops cmd-143 payloads (only 109/298 are collected), so tap them before it does.
    def tap(cmd_id, data, len_header, payload):
        if cmd_id != CUT:
            return orig(cmd_id, data, len_header, payload)
        if int.from_bytes(data[16:18], "little") == CUT_DONE or len(data) == len_header:
            chunks.put_nowait(None)
            return
        if m := re.search(r"<encryptLen>(\d+)</encryptLen>", bc._decrypt(data, len_header, cmd_id), re.I):
            n = int(m.group(1))
            payload = bc._aes_decrypt(payload[:n], b"", decode=False) + payload[n:]
        chunks.put_nowait(payload)

    proto._push_callback = tap  # the protocol holds its own copy, set at connect
    seen, chunk = 0, None
    try:
        await bc.send(cmd_id=CUT, channel=ch, body=body, retry=1)  # a resend after a slow ack would start a second cut
        chunk = b""  # the NVR is sending from here on: the finally must read it out
        while (chunk := await asyncio.wait_for(chunks.get(), IDLE_TIMEOUT)) is not None:
            seen += len(chunk)
            yield chunk
    except TimeoutError:
        chunk = None  # the NVR went quiet: nothing left to drain
        raise TimeoutError(f"cut stalled after {seen} bytes") from None
    finally:
        # A caller that quit early (viewer gone, ffmpeg died) still holds CUT_LOCK: swallow the rest of
        # the cut, or the next cut on this connection would receive it.
        try:
            while chunk is not None:
                chunk = await asyncio.wait_for(chunks.get(), IDLE_TIMEOUT)
        except TimeoutError:
            pass
        finally:
            proto._push_callback = orig


async def download_cut(bc, uid: str, ch: int, stream: str, start: datetime, end: datetime) -> bytes:
    """Raw BcMedia stream for [start, end]. Hold CUT_LOCK."""
    return b"".join([chunk async for chunk in stream_cut(bc, uid, ch, stream, start, end)])


class BcMediaReader:
    """Split a BcMedia stream into frames as bytes arrive: feed() returns (kind, codec, data, µs) tuples.

    kind is "I" (keyframe, 00dc), "P" (01dc) or "aac"; ADPCM audio and info headers are skipped.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[tuple]:
        self._buf += data
        b, j, out = self._buf, 0, []
        pad = lambda n: (8 - n % 8) % 8
        while j + 8 <= len(b):
            tag, frame = bytes(b[j:j + 4]), None
            if tag in (b"1001", b"1002"):
                n = 32 if tag == b"1001" else 40
            elif tag in (b"00dc", b"01dc"):
                if j + 24 > len(b):
                    break
                size, extra = int.from_bytes(b[j + 8:j + 12], "little"), int.from_bytes(b[j + 12:j + 16], "little")
                n = 24 + extra + size + pad(size)
                frame = ("I" if tag == b"00dc" else "P", b[j + 4:j + 8].decode(),
                         bytes(b[j + 24 + extra:j + 24 + extra + size]), int.from_bytes(b[j + 16:j + 20], "little"))
            elif tag in (b"05wb", b"01wb"):
                size = int.from_bytes(b[j + 4:j + 6], "little")
                n = 8 + size + pad(size)
                if tag == b"05wb":
                    frame = ("aac", None, bytes(b[j + 8:j + 8 + size]), None)
            else:
                raise ValueError(f"unknown BcMedia tag {tag!r}")
            if j + n > len(b):
                break
            if frame:
                out.append(frame)
            j += n
        del b[:j]
        return out


def parse_bcmedia(media: bytes) -> tuple[str, bytes, bytes, float]:
    """Split BcMedia into (codec, video elementary stream, AAC ADTS, fps from frame timestamps)."""
    video, audio, stamps, codec = bytearray(), bytearray(), [], "H264"
    reader, frames = BcMediaReader(), []
    for i in range(0, len(media), 1 << 20):  # in slices: a 120 MB clip whole would be copied 3 more times
        frames += reader.feed(media[i:i + (1 << 20)])
    for kind, c, data, us in frames:
        if kind == "aac":
            if stamps:  # NVR leads with ~8s of audio before the first frame; drop it to stay in sync
                audio += data
            continue
        codec = c
        stamps.append(us)  # microseconds; header fps byte is wrong
        video += data
    span = ((stamps[-1] - stamps[0]) % 2**32) / 1e6 if len(stamps) > 1 else 0
    fps = (len(stamps) - 1) / span if span else 10.0
    return codec, bytes(video), bytes(audio), fps


def to_mp4(media: bytes, out: str) -> None:
    codec, video, audio, fps = parse_bcmedia(media)
    # ponytail: constant frame rate from the average frame spacing; per-frame PTS would need a muxer lib
    with tempfile.TemporaryDirectory(dir=os.path.dirname(out)) as d:  # beside `out`, off the SD card
        v, a = f"{d}/v", f"{d}/a.aac"
        open(v, "wb").write(video)
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "hevc" if codec == "H265" else "h264", "-r", f"{fps:.3f}", "-i", v]
        if audio:
            open(a, "wb").write(audio)
            cmd += ["-i", a]
        subprocess.run(cmd + ["-c", "copy", "-movflags", "+faststart", out], check=True)
