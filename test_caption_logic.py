"""Run: python -m unittest -v test_caption_logic.py (no screen or Teams needed)."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from teams_caption_capture import Card, CaptionParser, Row, Transcript, Output, recover


class CaptionTests(unittest.TestCase):
    def setUp(self):
        self.t = Transcript()
        self.now = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)

    def feed(self, items, seconds=0):
        return self.t.consume([Card(speaker, text) for speaker, text in items], self.now + timedelta(seconds=seconds))

    def test_repeated_cards_and_wrapping(self):
        snapshot = [('Grogan, John', 'We should review the line design.'),
                    ('Grogan, John', 'The foundations require additional review.')]
        self.feed(snapshot)
        self.assertFalse(self.feed(snapshot, 1))
        self.feed([(s, text.replace(' ', '\n', 2)) for s, text in snapshot], 2)
        self.assertEqual(len(self.t.blocks), 1)
        self.assertEqual(self.t.blocks[0].text.count('We should'), 1)
        self.assertEqual(len(self.t.blocks[0].segments), 2)

    def test_growing_sentence(self):
        self.feed([('Grogan, John', 'We need')])
        self.feed([('Grogan, John', 'We need to review the foundations.')], 1)
        self.assertEqual(self.t.blocks[0].text, 'We need to review the foundations.')
        self.assertEqual(len(self.t.blocks[0].segments), 1)

    def test_short_growing_sentence(self):
        self.feed([('Grogan, John', 'The')])
        self.feed([('Grogan, John', 'The next structure is a dead end.')], 1)
        self.assertEqual(len(self.t.blocks[0].segments), 1)

    def test_scroll_and_append(self):
        a = ('Grogan, John', 'The first span is over a road.')
        b = ('Grogan, John', 'The next span crosses the river.')
        c = ('Grogan, John', 'Check the required clearances.')
        self.feed([a, b])
        self.feed([b, c], 1)
        self.assertEqual(self.t.blocks[0].text, ' '.join(x[1] for x in [a, b, c]))

    def test_ocr_correction_in_place(self):
        self.feed([('Grogan, John', 'We should review the foundatlons.')])
        self.feed([('Grogan, John', 'We should review the foundations.')], 1)
        self.assertEqual(self.t.blocks[0].text, 'We should review the foundations.')
        self.assertEqual(len(self.t.blocks[0].segments), 1)

    def test_speaker_changes_and_return(self):
        self.feed([('Grogan, John', 'Please review the first option.')])
        self.feed([('Smith, Jane', 'The second option is preferred.')], 1)
        self.feed([('Grogan, John', 'Please review the first option.')], 2)
        self.assertEqual([b.speaker for b in self.t.blocks], ['Grogan, John', 'Smith, Jane', 'Grogan, John'])

    def test_two_visible_identical_utterances(self):
        self.feed([('Grogan, John', 'Yes.'), ('Grogan, John', 'Yes.')])
        self.feed([('Grogan, John', 'Yes.'), ('Grogan, John', 'Yes.')], 1)
        self.assertEqual(self.t.blocks[0].text, 'Yes. Yes.')

    def test_rolling_sentence(self):
        self.feed([('Grogan, John', 'We need to review the foundations before construction.')])
        self.feed([('Grogan, John', 'the foundations before construction. Please check the drawings.')], 1)
        self.assertEqual(self.t.blocks[0].text, 'We need to review the foundations before construction. Please check the drawings.')

    def test_no_shortened_caption_deletion(self):
        self.feed([('Grogan, John', 'Please check the construction drawings carefully.')])
        self.feed([('Grogan, John', 'Please check the construction')], 1)
        self.assertIn('drawings carefully.', self.t.blocks[0].text)

    def test_temporary_empty_frame(self):
        a = [('Grogan, John', 'Check the foundation drawings.')]
        self.feed(a)
        self.feed([], 1)
        self.feed(a, 2)
        self.assertEqual(len(self.t.blocks[0].segments), 1)

    def test_pause_with_old_card_still_visible(self):
        a = ('Grogan, John', 'Check the foundation drawings.')
        self.feed([a])
        self.feed([a, ('Grogan, John', 'Now move on to the next topic.')], 15)
        self.assertEqual(len(self.t.blocks), 2)

    def test_layout_parser(self):
        rows = [Row('Grogan, John @', 2, 15), Row('We need to check the', 24, 21),
                Row('foundations.', 48, 21), Row('Grogan, John @', 72, 15),
                Row('Also the structure heights.', 94, 21)]
        cards = CaptionParser().parse(rows)
        self.assertEqual([c.speaker for c in cards], ['Grogan, John'] * 2)
        self.assertEqual(cards[0].text, 'We need to check the foundations.')

    def test_fuzzy_speaker_and_hyphenated_name(self):
        parser = CaptionParser(['Grogan, John'])
        self.assertEqual(parser.name_for(Row('Gr0gan, John', 0, 15), 21), 'Grogan, John')
        self.assertEqual(parser.name_for(Row("O'Neil, Anne-Marie", 0, 15), 21), "O'Neil, Anne-Marie")

    def test_sentence_not_speaker(self):
        self.assertIsNone(CaptionParser().name_for(Row('Obviously, We Need More Review', 0, 21), 21))

    def test_exports_and_recovery(self):
        from docx import Document
        self.feed([('Grogan, John', 'We need to review the foundations.')])
        with tempfile.TemporaryDirectory() as folder:
            output = Output(Path(folder))
            output.save(self.t)
            output.docx(self.t)
            self.assertFalse(output.docx_warning)
            document = Document(output.base.with_suffix('.docx'))
            self.assertIn('foundations.', '\n'.join(p.text for p in document.paragraphs))
            with output.journal.open('a') as handle:
                handle.write('{broken final record')
            recover(output.journal)
            recovered = output.base.with_name(output.base.name + '_recovered').with_suffix('.txt')
            self.assertEqual(recovered.read_text(), self.t.render())


if __name__ == '__main__':
    unittest.main()
