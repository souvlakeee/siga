"""Reading progress out of other tools' output.

Stream turns raw output (escape codes, \\r redraws, split chunks) into text segments,
picking up OSC 9;4 progress reports on the way. Progress keeps the latest fraction it
can trust. Cleaner rewrites a terminal-style stream (from a pty) into the plain text a
non-terminal run would print.
"""
import re

# OSC 9;4;state[;percent] ST — the ConEmu/Windows Terminal progress report
OSC_PROGRESS = re.compile(r"\x1b\]9;4;(\d)(?:;(\d{0,3}))?(?:\x07|\x1b\\)")
# cursor up / previous line: a redraw of earlier lines, so a segment boundary
CSI_LINE_MOVE = re.compile(r"\x1b\[\d*[AF]")
# cursor to a column (node's progress/cli-progress redraw with ESC[1G, not \r)
CSI_COLUMN = re.compile(r"\x1b\[\d*G")
CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
ESC_OTHER = re.compile(r"\x1b[@-Z\\-_]|\x1b[()][0-9A-Za-z]")


def split_incomplete(text):
    """(complete, held): hold back an escape sequence cut off at the end of a chunk."""
    i = text.rfind("\x1b")
    if i < 0 or len(text) - i > 256:
        return text, ""
    seq = text[i:]
    if seq == "\x1b":
        # a lone ESC may be the start of an OSC's ST; then the whole OSC waits
        j = text.rfind("\x1b", 0, i)
        if j >= 0 and text.startswith("\x1b]", j) and "\x07" not in text[j:i]:
            return text[:j], text[j:]
        return text[:i], seq
    if seq.startswith("\x1b\\"):
        return text, ""  # ST closing an OSC that started earlier
    if seq.startswith("\x1b]"):
        return (text, "") if OSC.match(seq) else (text[:i], seq)
    if seq.startswith("\x1b["):
        return (text, "") if CSI.match(seq) else (text[:i], seq)
    return (text, "") if len(seq) >= 2 else (text[:i], seq)


def strip_escapes(text):
    text = CSI_COLUMN.sub("\r", CSI_LINE_MOVE.sub("\n", text))
    return ESC_OTHER.sub("", CSI.sub("", OSC.sub("", text)))


def _hms(m):
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


FF_DURATION = re.compile(r"Duration:\s*(\d+):(\d\d):(\d\d(?:\.\d+)?)")
FF_TIME = re.compile(r"time=\s*(\d+):(\d\d):(\d\d(?:\.\d+)?)")
# curl's default meter: "% Total  % Received ..." rows start with the total percent
CURL_ROW = re.compile(r"^\s*(\d{1,3})\s+[\d.]+[kMGTP]?\s+\d{1,3}\s+[\d.]+[kMGTP]?\s+\d+\s+\d+\s")
# docker BuildKit step lines: "#7 [builder 3/6] RUN ..."
DOCKER_STEP = re.compile(r"^#\d+\s+\[(?:[\w.-]+\s+)?(\d+)/(\d+)\]")
# cargo's pty bar: "Building [=====>     ] 123/456: crate"
CARGO = re.compile(r"Building\s+\[[=> -]*\]\s+(\d+)/(\d+)")
# git runs several 0-100% phases; the transfer is the one worth showing
GIT_RECEIVE = re.compile(r"Receiving objects:\s+(\d{1,3})%")
GIT_OTHER_PHASE = re.compile(r"^(remote: )?(Enumerating|Counting|Compressing) objects|^(Resolving deltas|Updating files|Checking out files)")

PERCENT = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)\s?%")
NUM = r"(\d{1,9}(?:[.,]\d+)?)"
RATIO = re.compile(r"(?<![\d./:])" + NUM + r"\s*(?:[kKMGT]i?B|B)?\s*/\s*" + NUM + r"(?![\d/:])")
OF = re.compile(r"\b(\d{1,7})\s+of\s+(\d{1,7})\b")


def _num(s):
    return float(s.replace(",", ""))


class Progress:
    """The latest progress fraction found in the output, by priority within a segment."""

    def __init__(self, step=None, steps=None):
        # step: regex for a line that starts the next step of a custom script;
        # steps: how many there are (else unknown until the run ends)
        self.step = re.compile(step) if step else None
        self.steps = steps
        self.steps_seen = 0
        self.value = None
        self.state = None          # set by OSC 9;4: "busy" or "fail" (else "run")
        self.osc = False           # once a tool reports OSC 9;4, text is ignored
        self.ff_total = None
        self.hits = 0
        self.prio = 0              # strongest source seen so far; weaker ones are ignored

    def osc_report(self, state, pct):
        pct = min(100, int(pct)) / 100 if pct else None
        if state == "3":
            self.state = "busy"
        elif state == "2":
            self.state = "fail"
        elif state in ("1", "4"):
            self.state = "run"
        if pct is not None and state != "0":
            self.osc = True  # a tool that reports real values: trust only those
            self.value = pct
            self.hits = max(self.hits, 2)

    def feed(self, segment):
        if self.step:
            if self.step.search(segment):
                self.steps_seen += 1
                if self.steps:
                    # step k starting means k - 1 are finished
                    self.value = min(1.0, (self.steps_seen - 1) / self.steps)
                    self.hits = max(self.hits + 1, 2)
            return
        if self.osc or GIT_OTHER_PHASE.search(segment):
            return
        d = FF_DURATION.search(segment)
        if d:
            self.ff_total = _hms(d) or None
        best = None  # (priority, position, value)

        def offer(prio, pos, value):
            nonlocal best
            if 0 <= value <= 1 and (best is None or (prio, pos) > best[:2]):
                best = (prio, pos, value)

        if self.ff_total:
            for m in FF_TIME.finditer(segment):
                offer(3, m.start(), _hms(m) / self.ff_total)
        for rx in (CURL_ROW, GIT_RECEIVE):
            m = rx.search(segment)
            if m:
                offer(3, m.start(), int(m.group(1)) / 100)
        for rx in (DOCKER_STEP, CARGO):
            for m in rx.finditer(segment):
                n, total = int(m.group(1)), int(m.group(2))
                if total:
                    offer(3, m.start(), n / total)
        for m in PERCENT.finditer(segment):
            offer(2, m.start(), float(m.group(1)) / 100)
        for rx in (RATIO, OF):
            for m in rx.finditer(segment):
                n, total = _num(m.group(1)), _num(m.group(2))
                if total > 1 and n <= total:
                    offer(1, m.start(), n / total)
        # e.g. ffmpeg's closing x264 stats ("44.3% ...") must not undo its time= progress
        if best and best[0] >= self.prio:
            self.prio = best[0]
            self.hits += 1
            self.value = best[2]

    @property
    def trusted(self):
        # one stray "3/4" in a log line shouldn't end the busy or ETA display
        return self.value is not None and self.hits >= 2


class Stream:
    """Splits raw output into segments, holding back a half-received escape code."""

    def __init__(self, progress):
        self.progress = progress
        self.pending = ""
        self.tail = ""

    def feed(self, text):
        text, self.pending = split_incomplete(self.pending + text)
        for osc in OSC_PROGRESS.finditer(text):
            self.progress.osc_report(osc.group(1), osc.group(2))
        parts = re.split(r"[\r\n]", self.tail + strip_escapes(text))
        self.tail = parts.pop()[-400:]
        for seg in parts:
            self.progress.feed(seg)

    def close(self):
        if self.tail:
            self.progress.feed(self.tail)
            self.tail = ""


class Cleaner:
    """Rewrites terminal output (\\r redraws, escapes, \\r\\n) into plain final lines."""

    def __init__(self):
        self.pending = ""
        self.line = ""
        self.cr = False
        self.redrawn = False   # the current line was overwritten in place: a progress line
        self.last = None

    def feed(self, text):
        text, self.pending = split_incomplete(self.pending + text)
        out = []
        for ch in strip_escapes(text):
            if ch == "\n":
                self.cr = self.redrawn = False
                if self.line != self.last or not self.line.strip():
                    out.append(self.line + "\n")
                self.last, self.line = self.line, ""
            elif ch == "\r":
                self.cr = True
            else:
                if self.cr:
                    self.line, self.cr, self.redrawn = "", False, True
                self.line += ch
        return "".join(out)

    def close(self):
        # a last line that was only ever redrawn in place is a progress bar the tool
        # would have erased on a terminal; real output ends with a newline
        rest, self.line = self.line, ""
        return rest + "\n" if rest.strip() and not self.redrawn else ""
