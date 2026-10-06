# Teams Caption Capture — local Windows app

## Experimental: no-OCR version (`teams_caption_uia.py`)

Reads caption text and speaker names straight from Teams through Windows UI Automation (the accessibility interface screen readers use). No Tesseract, no region selection, and the Teams window can be moved or covered. It uses the same transcript, TXT/DOCX/JSONL output and recovery logic as the OCR version.

### Easiest: TeamsCaptionLogger.exe

Double-click `TeamsCaptionLogger.exe`, press **Start**, and turn on live captions in the meeting. The window shows the transcript as it builds. Press **Stop** (or close the window) to finish; the Word file is written on stop. Transcripts go to `Documents\Teams Transcripts` unless you pick another folder with **Change folder…**. No Python or other installs are needed.

Windows may show "Windows protected your PC" the first time because the exe isn't code-signed; choose **More info > Run anyway**, or ask IT to sign/allowlist it.

To build the exe yourself (needs Python 3.11+), run from this folder:

```powershell
powershell -ExecutionPolicy Bypass -File build_exe.ps1
```

This runs the tests and writes `dist\TeamsCaptionLogger.exe` (about 18 MB). `teams_caption_gui.py` is the window; run it with Python to use the window without building.

### Command-line version

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe teams_caption_uia.py --output C:\Transcripts
```

Turn on live captions in the meeting (**More > Language and speech > Show live captions**). Press **Ctrl+C** to stop and export.

Example output from a test meeting (captions are exactly what Teams showed, including its recognition errors; unidentified participants appear as "Speaker 1", etc.):

```text
Teams caption transcript
Timestamps are local screen-observation times, not audio timecodes.

[2026-10-06T08:52:41-06:00] Stiefvater, Daniel
OK. OK, is this working? Found caption ground control. It should, yeah.

[2026-10-06T08:52:41-06:00] Speaker 1
Oh, I still speak at 1:00.

[2026-10-06T08:52:41-06:00] Stiefvater, Daniel
So you're not as cool. So blah, blah blah blah. It might be a little bit of a delay that picks it up. But I don't know. This is for us. I think it will so. Oh yeah, I don't even hear in teams. Oh, you don't? OK, yeah. Alright, we'll we'll stop it for now.
```

Consecutive captions from the same speaker are joined into one paragraph; a new heading starts when the speaker changes or after an 8-second pause (`--gap`). The identical timestamps above are because this example was built from a single snapshot; in a live run each block is stamped when its first words appear. If it keeps saying "Waiting for Teams live captions", run `teams_caption_uia.py --dump` while captions are visible. This writes `teams_uia_dump.txt` so the caption-panel detection can be adjusted. The dump contains whatever Teams is showing, so review it before sharing.

The rest of this README covers the original OCR version.

Select a fixed rectangle containing Teams live captions. The app reads only that rectangle using local Tesseract OCR, joins caption cards into speaker blocks, and saves timestamped TXT and DOCX transcripts. No Teams API, bot, audio recording, meeting join, or cloud OCR. Installation needs downloads; capture works offline. No screenshots are saved.

## Included files

- `teams_caption_capture.py` — complete, editable application source.
- `requirements.txt` — Windows-compatible Python dependencies.
- `test_caption_logic.py` — 15 parser, deduplication, export, and recovery tests.
- `README.md` — this guide.

## 1. Install

Use Windows 10/11 with Python 3.11 or newer, including Tkinter (included with the standard python.org Windows installer). Install the Python extension in VS Code if you want editor integration. The program can also run directly from a terminal.

Install Tesseract OCR with English language data. In PowerShell:

```powershell
winget install --id UB-Mannheim.TesseractOCR --exact
```

If winget is unavailable, use the Windows installer linked from the Tesseract documentation:

- https://tesseract-ocr.github.io/tessdoc/Installation.html
- https://github.com/UB-Mannheim/tesseract/wiki

The default executable location is `C:\Program Files\Tesseract-OCR\tesseract.exe`. Tesseract is a separate application; pip does not install its OCR engine.

Extract this ZIP, then open the extracted **TeamsCaptionCapture** folder in VS Code using **File > Open Folder**. Open **Terminal > New Terminal** and run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe teams_caption_capture.py
```

These commands use the environment's Python directly, so PowerShell script activation is unnecessary. If `py` is unavailable but Python is installed, use `python -m venv .venv` for the first command.

For VS Code's Run button: press **Ctrl+Shift+P**, choose **Python: Select Interpreter**, select `.venv\Scripts\python.exe`, open `teams_caption_capture.py`, then choose **Run Python File in Terminal**.

## 2. Select the caption region

1. Turn on Teams live captions and position the caption panel where it will stay. Use the black panel layout shown in your screenshot.
2. Start this app. Choose an output folder when prompted.
3. The desktop freezes temporarily for selection. Drag a rectangle around the **text column**. Begin just to the left of `Grogan, John`, to the right of the circular `JG` avatar. Include speaker names, the full width of captions, and complete caption lines, with a few pixels of margin. Exclude unrelated Teams controls.
4. Release the mouse. The rectangle's screen coordinates are stored and the app minimizes itself to keep its controls out of the capture area. OCR starts automatically.
5. Move your mouse freely. It does not move the capture region and is not used to determine where screenshots are taken.
6. To finish, restore the app from the taskbar and click **Stop & export**. Keep its window outside the caption rectangle when restoring it. Closing the window also stops capture and exports after the current OCR operation finishes.

Press **Esc** during selection to cancel. Click **Select region & start** to retry. Each new session gets a new filename.

**Keep Teams visible, at the same size and position.** Other windows covering the rectangle, moving/minimizing Teams, display scaling changes, monitor disconnection, or locking the computer can interrupt accurate capture. This app reads visible screen pixels; it cannot read an obscured window. If you move the panel, stop and select it again.

If you selected the whole caption panel including initials, either reselect just the text column or remove the avatar gutter with `--trim-left`. For the supplied 925-pixel-wide screenshot, approximately 72 pixels excludes the avatars. That value is specific to the screenshot; it is not a universal Teams setting.

## 3. Output

The folder you selected receives:

- `Teams_DATE_TIME.txt`: clean UTF-8 transcript, saved whenever recognized content changes.
- `Teams_DATE_TIME.docx`: Word transcript, refreshed about every 30 seconds and on Stop/close.
- `Teams_DATE_TIME.jsonl`: append-only local recovery journal of changed spoken blocks.

Example format (illustrative):

```text
[2026-10-01T15:21:15-06:00] Grogan, John
We're just kind of designing, keeping in mind that there are inherent places where this might come into play, but we don't. Obviously, we everyone understands subsurface is a big risk on any project...

[2026-10-01T15:21:32-06:00] Smith, Jane
Let's review the next structure.
```

Names appear once per consecutive spoken block. A change of speaker creates another block; new text after an eight-second gap also starts another block. Repeated names on consecutive cards do not create repeated transcript labels. Pauses are inferred from screen changes, not detected from audio.

Timestamps are the computer's local time, including its UTC offset, when text is first observed. Text already visible at startup receives the startup observation time. Historical audio timestamps cannot be reconstructed from screen captions. Each block's most recent update time is also retained in the JSONL journal.

The clean transcript receives only new content or in-place corrections to an evolving caption. TXT is rewritten atomically rather than physically appended, allowing OCR corrections without duplicate sentences. JSONL is the append-only recovery record. Leave the DOCX closed in Word while recording; if Word locks it, the app reports the export problem and keeps TXT/JSONL. Close Word before stopping to allow a final DOCX export.

## Options

Default OCR interval is 0.75 seconds. Set 0.5–1.0 seconds:

```powershell
.\.venv\Scripts\python.exe teams_caption_capture.py --interval 0.5
```

Explicit Tesseract location and output folder:

```powershell
.\.venv\Scripts\python.exe teams_caption_capture.py --tesseract "C:\Program Files\Tesseract-OCR\tesseract.exe" --output "C:\Transcripts"
```

Supply known Teams display names if automatic name recognition needs help:

```powershell
.\.venv\Scripts\python.exe teams_caption_capture.py --speaker "Grogan, John" --speaker "Smith, Jane"
```

Remove a selected avatar gutter, or change the new-block pause threshold:

```powershell
.\.venv\Scripts\python.exe teams_caption_capture.py --trim-left 72 --gap 12
```

Recover clean files from an interrupted session's journal:

```powershell
.\.venv\Scripts\python.exe teams_caption_capture.py --recover "C:\Transcripts\Teams_2026-10-01_15-21-15_123456.jsonl"
```

This creates `_recovered.txt` and `_recovered.docx` beside the journal. An incomplete last JSONL line is ignored. Recovery does not require screen capture or Tesseract.

## How the parser works

The selected region is converted to grayscale, inverted for the dark panel, and enlarged threefold. Tesseract returns word positions and confidence values. The parser reconstructs rows, recognizes smaller speaker headers above larger caption text, removes separated status icons, and joins wrapped lines beneath each header. Known names are reused with limited tolerance for OCR spelling differences. `--speaker` can explicitly identify names that do not follow the expected capitalization/font layout.

Successive card sequences are aligned in reading order. Matching cards update existing transcript segments. Newly appearing cards add new segments. Fuzzy comparisons handle small OCR edits; suffix/prefix comparisons handle rolling text. Duplicate removal is scoped to recent visible cards, not the entire meeting, so a person can repeat a statement later. Two separately visible identical short utterances are retained.

## Practical limits and troubleshooting

- This is OCR, not an official Teams transcript. It does not fix errors already present in Teams captions, infer inaudible words, or silently rewrite technical terminology. Review engineering names, dimensions, and quantities before relying on the transcript.
- Select full names and full caption lines. If the top of the rectangle begins midway through a card, that initial unlabeled fragment is skipped until a speaker header is visible. Partial glyphs at the image boundary are discarded.
- OCR cannot always distinguish a genuine repeated sentence from an unchanged caption, especially if the entire panel replaces one identical card with another between polls. Very different OCR errors or rapid changes can still cause missing/duplicate text. It is not possible to guarantee perfect deduplication from screenshots alone.
- The requested interval is start-to-start when OCR is fast enough. If OCR takes longer, the next capture starts after it finishes. The status bar reports the actual OCR duration; there is no growing backlog of screenshot tasks. A tighter region and the standard fast English language data improve speed.
- If no captions are recognized, check that names are included, initials circles are excluded, and Teams retains the smaller-name/larger-caption layout. Try `--speaker` for known attendees. Use readable caption size rather than an extremely small panel.
- If Tesseract is not found, use `--tesseract`. If English data is missing, reinstall with English selected. Additional installed languages can be selected with `--language`, but the included screenshot/parser validation used English.
- If screen coordinates are wrong, restart after changing display scaling. The selector uses Windows DPI awareness and virtual desktop coordinates, including monitors left of the primary display, but this must still be checked on your Windows setup.
- If export says permission denied, select a writable local folder. Recover from JSONL if needed. If DOCX reports a missing module, rerun the requirements installation with the same `.venv` Python.

## Validation

The supplied screenshot was processed with local Tesseract: all three visible `Grogan, John` caption cards were detected and joined into one speaker block, without the initials/status icons. The 15 automated tests cover growing/rolling text, wrapping, OCR corrections, scrolling, speaker changes and return, repeated short utterances, temporary empty frames, pause boundaries, TXT/DOCX export, and recovery from an incomplete journal record.

Run the tests:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_caption_logic.py
```

The Windows GUI and actual Teams capture were not run in the development environment. Before a meeting, make a short local check: select captions, move the mouse, let several cards scroll, stop, and verify the TXT and DOCX. Screenshots only establish what was visible at capture time; speech that appears and disappears between captures cannot be recovered.

Implementation references:

- MSS region capture: https://python-mss.readthedocs.io/latest/examples.html
- Tesseract installation: https://tesseract-ocr.github.io/tessdoc/Installation.html
- Word export: https://python-docx.readthedocs.io/en/latest/user/quickstart.html
