from deeplake.constants import SPINNER_START_DELAY, SPINNER_ENABLED
from deeplake.client.log import configure_logger
from logging import StreamHandler
from itertools import cycle
from functools import wraps

import contextlib
import threading
import logging
import time
import sys

ACTIVE_SPINNER = None


class DummyFile:
    def __init__(self, file, spinner):
        self.spinner = spinner
        self.file = file

    def write(self, text):
        if len(text.strip()) > 0:
            with self.spinner._stdout_lock:
                self.spinner._clear_line()
                self.file.write(f"{text}\n")

    def __getattr__(self, attr):
        return getattr(self.file, attr)


@contextlib.contextmanager
def run_spinner(spinner):
    global ACTIVE_SPINNER
    try:
        if not isinstance(sys.stdout, DummyFile) and SPINNER_ENABLED:
            spinner.start()
            spinner_started = True
            save_stdout = sys.stdout
            save_stderr = sys.stderr
            sys.stdout = DummyFile(sys.stdout, spinner)
            sys.stderr = DummyFile(sys.stderr, spinner)
            # configure logger to use new stdout
            logger = logging.getLogger("deeplake")
            save_handlers = list(logger.handlers)
            logger.handlers.clear()
            logger.addHandler(StreamHandler(stream=sys.stdout))
            ACTIVE_SPINNER = spinner
        else:
            # another spinner active
            # or tests running
            spinner_started = False
        yield
    finally:
        if spinner_started:
            spinner._show_cursor()
            spinner.stop()
            sys.stdout = save_stdout
            sys.stderr = save_stderr
            logger.handlers = save_handlers
            ACTIVE_SPINNER = None


class Spinner(threading.Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop_event = threading.Event()
        self._hide_event = threading.Event()
        self._cur_line_len = 0
        self.daemon = True
        self._stdout_lock = threading.Lock()
        self.file = sys.stdout

    def run(self):
        time.sleep(SPINNER_START_DELAY)
        frames = cycle("/-\\|")
        if not self._hide_event.is_set():
            self._hide_cursor()
        while not self._stop_event.is_set():
            if self._hide_event.is_set():
                time.sleep(0.1)
                continue
            with self._stdout_lock:
                self._clear_line()
                self.file.write(next(frames))
                self.file.flush()
                self._cur_line_len = 1

            self._stop_event.wait(0.1)

    def hide(self):
        if not self._hide_event.is_set():
            with self._stdout_lock:
                self._hide_event.set()
                self._clear_line()
                self.file.flush()
                self._show_cursor()

    def show(self):
        if self._hide_event.is_set():
            with self._stdout_lock:
                self._hide_event.clear()
                self._clear_line()
                self._hide_cursor()

    def stop(self):
        self._stop_event.set()
        self.join()
        self._clear_line()
        self._show_cursor()

    def _clear_line(self):
        if self.file.isatty():
            # ANSI Control Sequence EL does not work in Jupyter
            self.file.write("\r\033[K")
        else:
            fill = " " * self._cur_line_len
            self.file.write(f"\r{fill}\r")

    def _hide_cursor(self):
        if self.file.isatty():
            # ANSI Control Sequence DECTCEM 1 does not work in Jupyter
            self.file.write("\033[?25l")
            self.file.flush()

    def _show_cursor(self):
        if self.file.isatty():
            # ANSI Control Sequence DECTCEM 2 does not work in Jupyter
            self.file.write("\033[?25h")
            self.file.flush()


def spinner(func):
    @wraps(func)
    def inner(*args, **kwargs):
        spinner = Spinner()

        with run_spinner(spinner):
            return func(*args, **kwargs)

    return inner
