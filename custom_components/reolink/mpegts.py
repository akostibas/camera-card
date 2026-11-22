"""Wrap the NVR's picture and sound in one MPEG-TS stream stamped with the NVR's own clock.

ffmpeg given picture and sound as two raw inputs has no timing for either: it put a clip's sound in its
last segments, or stalled waiting on one input while we were blocked writing the other.
"""
PMT, VIDEO, AUDIO = 0x1000, 0x100, 0x101
_RATES = (96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350)
_RESYNC = 45000  # 0.5s: sound counted further than this from its picture lost packets, so re-pin it


def _crc(data: bytes) -> bytes:  # CRC-32/MPEG-2; zlib's is the bit-reflected one
    c = 0xFFFFFFFF
    for x in data:
        c ^= x << 24
        for _ in range(8):
            c = (c << 1 ^ 0x04C11DB7 if c & 0x80000000 else c << 1) & 0xFFFFFFFF
    return c.to_bytes(4, "big")


def _table(pid: int, section: bytes) -> bytes:
    body = b"\x00" + section + _crc(section)  # leading 0: the section starts right here
    return bytes((0x47, 0x40 | pid >> 8, pid & 0xFF, 0x10)) + body.ljust(184, b"\xff")


def _stamp(pts: int) -> bytes:
    return bytes((0x21 | pts >> 29 & 0x0E, pts >> 22 & 0xFF, 0x01 | pts >> 14 & 0xFE, pts >> 7 & 0xFF, 0x01 | pts << 1 & 0xFE))


class TsMux:
    def __init__(self, hevc: bool, audio: bool) -> None:
        self._cc = {VIDEO: 0, AUDIO: 0}
        self._us = self._last = None  # the NVR's 32-bit microsecond clock, as last seen
        self._v = 0  # picture time in 90 kHz ticks since the first frame
        self._a = None  # sound time: counted in samples, as the NVR doesn't stamp sound
        streams = [(0x24 if hevc else 0x1B, VIDEO)] + ([(0x0F, AUDIO)] if audio else [])
        es = b"".join(bytes((t, 0xE0 | p >> 8, p & 0xFF, 0xF0, 0)) for t, p in streams)
        self.header = (
            _table(0, b"\x00\xb0\x0d\x00\x01\xc1\x00\x00\x00\x01" + bytes((0xE0 | PMT >> 8, PMT & 0xFF)))
            + _table(PMT, bytes((2, 0xB0, 13 + len(es))) + b"\x00\x01\xc1\x00\x00" + bytes((0xE0 | VIDEO >> 8, VIDEO & 0xFF, 0xF0, 0)) + es))

    def _pes(self, pid: int, stream_id: int, pts: int, data: bytes) -> bytes:
        n = 0 if pid == VIDEO else len(data) + 8  # 0: unbounded, allowed for video only
        pes = b"\x00\x00\x01" + bytes((stream_id, n >> 8, n & 0xFF, 0x80, 0x80, 5)) + _stamp(pts) + data
        out, cc = bytearray(), self._cc[pid]
        for i in range(0, len(pes), 184):
            chunk = pes[i:i + 184]
            out += bytes((0x47, (0x40 if i == 0 else 0) | pid >> 8, pid & 0xFF, (0x10 if len(chunk) == 184 else 0x30) | cc))
            if len(chunk) < 184:  # the last packet is padded in its adaptation field
                pad = 183 - len(chunk)
                out += bytes((pad,)) + (b"\x00" + b"\xff" * (pad - 1) if pad else b"")
            out += chunk
            cc = cc + 1 & 15
        self._cc[pid] = cc
        return bytes(out)

    def video(self, data: bytes, us: int) -> bytes:
        if self._us is not None:
            step = (us - self._us) % 2**32  # the clock wraps every 71 minutes
            self._v += step * 9 // 100 if step < 2**31 else 1  # a stamp that went backwards still moves on
        self._us = us
        return self._pes(VIDEO, 0xE0, self._v, data)

    def audio(self, data: bytes) -> bytes:
        if len(data) < 7 or data[0] != 0xFF:
            return b""
        if self._a is None or abs(self._a - self._v) > _RESYNC:
            self._a = self._v
        pts, i = self._a, 0
        while i + 7 <= len(data):  # one NVR packet can hold several ADTS frames
            self._a += 1024 * 90000 // _RATES[min(data[i + 2] >> 2 & 15, 12)]
            i += (data[i + 3] & 3) << 11 | data[i + 4] << 3 | data[i + 5] >> 5 or len(data)
        return self._pes(AUDIO, 0xC0, pts, data)


if __name__ == "__main__":
    m = TsMux(False, True)
    adts = bytes((0xFF, 0xF1, 0x60, 0x40, 0x01, 0x7F, 0xFC)) + b"\x00" * 4  # 16 kHz, 11 bytes
    ts = m.header + m.video(b"\x00\x00\x00\x01" + b"v" * 1000, 2**32 - 50000) + m.audio(adts * 2) + m.video(b"\x00\x00\x00\x01w", 50000)
    assert len(ts) % 188 == 0 and all(ts[i] == 0x47 for i in range(0, len(ts), 188))
    assert _crc(b"123456789") == bytes.fromhex("0376e6e7")
    assert m._v == 9000 and m._a == 2 * 5760, (m._v, m._a)  # 0.1s across the clock's wrap; two 64ms frames
    print("ok")
