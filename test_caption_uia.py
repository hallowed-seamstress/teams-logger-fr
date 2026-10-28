"""Run: python -m unittest -v test_caption_uia.py (no Teams needed)."""
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from teams_caption_capture import Output, Transcript
from teams_caption_uia import Node, extract_cards, meeting_name


def text(value):
    return Node('TextControl', value)


def item(speaker, *lines):
    return Node('GroupControl', children=[Node('GroupControl', children=[text(speaker)]),
                                          Node('GroupControl', children=[text(l) for l in lines])])


class UiaParseTests(unittest.TestCase):
    def test_items_become_cards_in_order(self):
        panel = Node('GroupControl', 'Live Captions', children=[
            item('Grogan, John', 'We should review the line design.'),
            item('Smith, Jane', 'Agreed,', 'let us look at the foundations.')])
        cards = extract_cards(panel)
        self.assertEqual([(c.speaker, c.text) for c in cards],
                         [('Grogan, John', 'We should review the line design.'),
                          ('Smith, Jane', 'Agreed, let us look at the foundations.')])

    def test_real_teams_layout(self):
        # Shape from a new-Teams dump (Oct 2026): flat [speaker, text] groups
        # interleaved with empty spacer groups, plus a button bar.
        entry = lambda s, t: Node('GroupControl', children=[text(s), text(t)])
        spacer = lambda: Node('GroupControl')
        panel = Node('GroupControl', 'Live Captions', children=[
            Node('GroupControl', children=[Node('GroupControl', 'Stiefvater, Daniel OK. Speaker 1 Hi.', children=[
                spacer(), spacer(), entry('Stiefvater, Daniel', 'OK.'), spacer(), spacer(),
                entry('Speaker 1', 'Hi.'), spacer()])]),
            Node('GroupControl', children=[Node('ButtonControl', 'Hide live captions (Alt+Shift+C)')])])
        self.assertEqual([(c.speaker, c.text) for c in extract_cards(panel)],
                         [('Stiefvater, Daniel', 'OK.'), ('Speaker 1', 'Hi.')])

    def test_single_item_and_empty_panel(self):
        self.assertEqual(len(extract_cards(Node('GroupControl', children=[item('A B', 'Hi there')]))), 1)
        self.assertEqual(extract_cards(Node('GroupControl')), [])

    def test_speaker_only_item_is_skipped(self):
        panel = Node('GroupControl', children=[Node('GroupControl', children=[text('Grogan, John')])])
        self.assertEqual(extract_cards(panel), [])

    def test_feeds_shared_transcript(self):
        transcript = Transcript()
        now = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)
        transcript.consume(extract_cards(Node('GroupControl', children=[item('Grogan, John', 'We need')])), now)
        transcript.consume(extract_cards(Node('GroupControl', children=[
            item('Grogan, John', 'We need to review the foundations.')])), now)
        self.assertEqual(len(transcript.blocks), 1)
        self.assertEqual(transcript.blocks[0].text, 'We need to review the foundations.')


class NamingTests(unittest.TestCase):
    def test_meeting_name_from_window_title(self):
        self.assertEqual(meeting_name('Wang, Aurora C | Microsoft Teams'), 'Wang, Aurora C')
        self.assertEqual(meeting_name('Chat | Richardson, Connor | Microsoft Teams'), 'Richardson, Connor')
        self.assertEqual(meeting_name('Microsoft Teams'), '')

    def test_files_renamed_after_meeting(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Output(Path(folder))
            transcript = Transcript()
            output.save(transcript)
            self.assertTrue(output.name_after('Q3 review: site/plan v1.2'))
            self.assertEqual(output.base.name, f'Q3 review site plan v1 2_{output.stamp}')
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()),
                             [output.base.name + '.jsonl', output.base.name + '.txt'])
            self.assertFalse(output.name_after('Other'))  # once only
            output.save(transcript)
            self.assertEqual(len(list(Path(folder).iterdir())), 2)


if __name__ == '__main__':
    unittest.main()
