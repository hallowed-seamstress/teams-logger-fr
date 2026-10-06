"""Teams Caption Logger window: Start/Stop around teams_caption_uia.CaptionLogger.

This is the entry point for the packaged TeamsCaptionLogger.exe.
"""
from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
from pathlib import Path

from teams_caption_capture import Output, dpi_awareness
from teams_caption_uia import CaptionLogger

INTERVAL = 0.5
HOW_TO = 'In the Teams meeting: More > Language and speech > Show live captions.'


def documents_folder() -> Path:
    """The real Documents folder, including OneDrive/known-folder redirection."""
    buffer = ctypes.create_unicode_buffer(260)
    if sys.platform == 'win32' and ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0:
        return Path(buffer.value)
    return Path.home() / 'Documents'


class App:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk
        from tkinter.scrolledtext import ScrolledText
        self.root = root
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = None
        self.closing = False
        self.folder = documents_folder() / 'Teams Transcripts'
        self.last_file = None

        root.title('Teams Caption Logger')
        root.geometry('720x480')
        root.minsize(480, 300)
        top = ttk.Frame(root, padding=(12, 12, 12, 4))
        top.pack(fill='x')
        self.start_button = ttk.Button(top, text='Start', command=self.start)
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(top, text='Stop', state='disabled', command=self.stop)
        self.stop_button.pack(side='left', padx=(6, 0))
        ttk.Button(top, text='Open folder', command=self.open_folder).pack(side='right')
        self.folder_button = ttk.Button(top, text='Change folder…', command=self.choose_folder)
        self.folder_button.pack(side='right', padx=(0, 6))

        self.status = tk.StringVar(value=f'Press Start before or during a meeting. {HOW_TO}')
        ttk.Label(root, textvariable=self.status, wraplength=690, padding=(12, 4)).pack(fill='x')
        self.folder_label = tk.StringVar()
        ttk.Label(root, textvariable=self.folder_label, foreground='gray', padding=(12, 0)).pack(fill='x')
        self.show_folder()

        self.preview = ScrolledText(root, wrap='word', font=('Segoe UI', 10), state='disabled')
        self.preview.pack(fill='both', expand=True, padx=12, pady=(6, 12))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def show_folder(self):
        target = self.last_file or self.folder
        self.folder_label.set(f'Saving to: {target}')

    def choose_folder(self):
        from tkinter import filedialog
        chosen = filedialog.askdirectory(parent=self.root, initialdir=self.folder, title='Choose transcript folder')
        if chosen:
            self.folder = Path(chosen)
            self.last_file = None
            self.show_folder()

    def open_folder(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self.folder))

    def start(self):
        from tkinter import messagebox
        if self.thread and self.thread.is_alive():
            return
        try:
            output = Output(self.folder)
        except OSError as exc:
            messagebox.showerror('Cannot save here', f'{self.folder}\n\n{exc}', parent=self.root)
            return
        self.last_file = output.base.with_suffix('.txt')
        self.show_folder()
        self.set_preview('')
        self.stop_event.clear()
        self.start_button.config(state='disabled')
        self.folder_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self.status.set(f'Looking for live captions… {HOW_TO}')
        self.thread = threading.Thread(target=self.worker, args=(output,), daemon=False)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.stop_button.config(state='disabled')
        self.status.set('Stopping and saving…')

    def close(self):
        if self.thread and self.thread.is_alive():
            self.closing = True
            self.stop()  # worker saves, then poll() destroys the window
        else:
            self.root.destroy()

    def worker(self, output):
        import uiautomation as auto
        logger = None
        try:
            with auto.UIAutomationInitializerInThread():
                logger = CaptionLogger(auto, output)
                connected = None
                while not self.stop_event.is_set():
                    if logger.step():
                        self.events.put(('text', logger.transcript.render()))
                    if logger.connected != connected:
                        connected = logger.connected
                        self.events.put(('status', 'Recording live captions. Transcript saves automatically as you go.'
                                         if connected else f'Looking for live captions… {HOW_TO}'))
                    self.stop_event.wait(INTERVAL)
        except Exception as exc:
            self.events.put(('error', f'Capture stopped: {exc}'))
        finally:
            try:
                if logger:
                    logger.finish()
                    blocks = len(logger.transcript.blocks)
                    message = f'Saved {blocks} speaker block(s) to {output.base.with_suffix(".txt").name}'
                    if output.docx_warning:
                        message += f'. {output.docx_warning}'
                    else:
                        message += ' and .docx.'
                    self.events.put(('status', message))
            except Exception as exc:
                self.events.put(('error', f'Final save failed: {exc}'))
            self.events.put(('done', None))

    def set_preview(self, text):
        self.preview.config(state='normal')
        self.preview.delete('1.0', 'end')
        self.preview.insert('end', text)
        self.preview.see('end')
        self.preview.config(state='disabled')

    def poll(self):
        from tkinter import messagebox
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'text':
                    self.set_preview(value)
                elif kind == 'status':
                    self.status.set(value)
                elif kind == 'error':
                    messagebox.showerror('Teams Caption Logger', value, parent=self.root)
                elif kind == 'done':
                    self.start_button.config(state='normal')
                    self.folder_button.config(state='normal')
                    self.stop_button.config(state='disabled')
                    if self.closing:
                        self.root.destroy()
                        return
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


def main():
    import tkinter as tk
    dpi_awareness()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
