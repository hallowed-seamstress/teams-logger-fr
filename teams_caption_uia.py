"""Teams live-caption logger using Windows UI Automation instead of OCR.

Reads caption text and speaker names directly from the Teams accessibility tree
(the same interface screen readers use). No screenshots, Tesseract, region
selection, audio, or network calls. Windows only; requires `uiautomation`.

    python teams_caption_uia.py --output C:\\Transcripts
    python teams_caption_uia.py --dump      # save the Teams tree for diagnosis

Press Ctrl+C to stop and export. Transcript/merge logic is shared with
teams_caption_capture.py.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from teams_caption_capture import Card, Output, Transcript

CAPTION_HINT = re.compile(r'caption', re.IGNORECASE)
TEAMS_TITLE = 'Microsoft Teams'


@dataclass
class Node:
    """Plain snapshot of a UIA element, so parsing is testable without Teams."""
    type: str
    name: str = ''
    automation_id: str = ''
    class_name: str = ''
    children: list[Node] = field(default_factory=list)


def snapshot(control, max_depth=40, depth=0) -> Node:
    node = Node(control.ControlTypeName, control.Name or '', control.AutomationId or '', control.ClassName or '')
    if depth < max_depth:
        node.children = [snapshot(child, max_depth, depth + 1) for child in control.GetChildren()]
    return node


def text_leaves(node: Node) -> list[str]:
    """Visible text in reading order. Chromium exposes text runs as TextControl."""
    if node.type == 'TextControl' and node.name.strip() and not node.children:
        return [node.name.strip()]
    result = []
    for child in node.children:
        result.extend(text_leaves(child))
    return result


def caption_items(node: Node) -> list[Node]:
    """Caption entries: each holds a speaker followed by one or more text runs."""
    while True:
        branches = [child for child in node.children if text_leaves(child)]
        if len(branches) != 1:
            break
        node = branches[0]  # unwrap layout-only wrappers around the list
    if any(len(text_leaves(b)) == 1 for b in branches):
        return [node]  # node is itself one entry: [speaker] [text...]
    return branches


def extract_cards(container: Node) -> list[Card]:
    cards = []
    for item in caption_items(container):
        speaker, *text = text_leaves(item)
        # Merge consecutive leaves; dedupe a speaker label repeated in the body.
        body = ' '.join(t for t in text if t != speaker).strip()
        if body and len(speaker) <= 80:
            cards.append(Card(speaker, body))
    return cards


CONTAINER_TYPES = {'GroupControl', 'ListControl', 'PaneControl', 'CustomControl'}


def is_caption_container(control) -> bool:
    # Only short labels on container elements: chat previews and messages that
    # merely mention "captions" are list/tree items or long text. Not ClassName:
    # Edge's title-bar buttons are "BrowserCaptionButtonContainer".
    if control.ControlTypeName not in CONTAINER_TYPES:
        return False
    return CAPTION_HINT.search(control.AutomationId or '') is not None or (
        len(control.Name or '') <= 40 and CAPTION_HINT.search(control.Name or '') is not None)


def teams_windows(auto):
    return [w for w in auto.GetRootControl().GetChildren()
            if TEAMS_TITLE in (w.Name or '') or (w.ClassName or '').startswith('TeamsWebView')]


def find_caption_container(auto):
    """Breadth-first within Teams' web content, so the outermost caption region
    wins over inner labels and native window chrome is ignored."""
    for window in teams_windows(auto):
        frontier = [(window, False)]
        while frontier:
            next_frontier = []
            for control, in_web in frontier:
                for child in control.GetChildren():
                    web = in_web or child.ControlTypeName == 'DocumentControl'
                    if web and is_caption_container(child):
                        return child
                    next_frontier.append((child, web))
            frontier = next_frontier
    return None


def dump(auto, path: Path):
    lines = []
    def walk(control, depth):
        lines.append('  ' * depth + f'{control.ControlTypeName} name={control.Name!r} '
                     f'id={control.AutomationId!r} class={control.ClassName!r}')
        for child in control.GetChildren():
            walk(child, depth + 1)
    for window in teams_windows(auto):
        walk(window, 0)
    path.write_text('\n'.join(lines), encoding='utf-8')
    print(f'Wrote {len(lines)} elements from {len(teams_windows(auto))} Teams window(s) to {path}')
    print('Note: this file contains whatever Teams is showing (chat text, names). Review before sharing.')


class CaptionLogger:
    """Reads the captions panel once per step(); the caller owns the loop.

    Construct and call from one thread (UIA objects are per-thread COM).
    """
    def __init__(self, auto, output: Output, gap=8.0):
        self.auto, self.output = auto, output
        self.transcript = Transcript(gap)
        self.container = None
        self.last_search = self.last_seen = 0.0
        self.last_docx = time.monotonic()

    @property
    def connected(self) -> bool:
        return self.container is not None

    def step(self) -> bool:
        """One read. Returns True when the transcript changed (already saved)."""
        began = time.monotonic()
        if self.container is not None and began - self.last_seen > 5:
            self.container = None  # alive but empty: Teams may have rebuilt the panel
        if self.container is None and began - self.last_search >= 2:
            self.last_search = began
            self.container = find_caption_container(self.auto)
            if self.container is not None:
                self.last_seen = began
        changed = False
        if self.container is not None:
            try:
                cards = extract_cards(snapshot(self.container))
            except Exception:  # element vanished mid-read (captions closed, meeting ended)
                self.container, cards = None, []
            if cards:
                self.last_seen = began
            if self.transcript.consume(cards, datetime.now().astimezone()):
                self.output.save(self.transcript)
                changed = True
        if time.monotonic() - self.last_docx >= 30:
            self.output.docx(self.transcript)
            self.last_docx = time.monotonic()
        return changed

    def finish(self):
        self.output.save(self.transcript)
        self.output.docx(self.transcript)


def run(auto, args):
    logger = CaptionLogger(auto, Output(args.output), args.gap)
    blocks = logger.transcript.blocks
    printed, was_connected = 0, False
    print(f'Saving to {logger.output.base}.txt  (Ctrl+C to stop)')
    print('Waiting for Teams live captions... (in a meeting: More > Language and speech > Show live captions)')
    try:
        while True:
            began = time.monotonic()
            if logger.step():
                # Echo finished blocks; the last block may still be growing.
                for block in blocks[printed:-1]:
                    print(f'\n[{block.start}] {block.speaker}\n{block.text}')
                printed = max(printed, len(blocks) - 1)
            if logger.connected != was_connected:
                was_connected = logger.connected
                print('Found live captions.' if was_connected else 'Lost live captions; searching...')
            time.sleep(max(0, args.interval - (time.monotonic() - began)))
    except KeyboardInterrupt:
        pass
    logger.finish()
    print(f'\nSaved: {logger.output.base.with_suffix(".txt")}')
    print(logger.output.docx_warning or f'Saved: {logger.output.base.with_suffix(".docx")}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--output', type=Path, default=Path.cwd() / 'transcripts', help='Output folder (default ./transcripts)')
    ap.add_argument('--interval', type=float, default=0.5, help='Seconds between reads (default 0.5)')
    ap.add_argument('--gap', type=float, default=8, help='Seconds without new text before a new block (default 8)')
    ap.add_argument('--dump', nargs='?', const=Path('teams_uia_dump.txt'), type=Path,
                    help='Write the Teams accessibility tree to a file and exit')
    args = ap.parse_args()
    if sys.platform != 'win32':
        ap.error('UI Automation is Windows-only.')
    import uiautomation as auto
    auto.SetGlobalSearchTimeout(1)
    if args.dump:
        dump(auto, args.dump)
    else:
        run(auto, args)


if __name__ == '__main__':
    main()
