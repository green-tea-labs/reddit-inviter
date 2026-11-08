"""UTF-8 console output and persistent, verbose logs for every script run."""

from __future__ import annotations

import atexit
import logging
import os
import platform
import sys
import threading
import time
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


_active_run = None


class _RunLog:
    def __init__(self, script_path, log_root=None):
        script_path = Path(script_path).resolve()
        root = Path(log_root) if log_root is not None else Path(__file__).resolve().parent / "logs"
        folder = root / script_path.stem
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
        self.path = folder / f"{stamp}_{os.getpid()}.txt"
        self.file = self.path.open("x", encoding="utf-8", buffering=1)
        self.lock = threading.RLock()
        self.started = time.monotonic()
        self.outcome = "running"
        self.closed = False
        self.original_stdout, self.original_stderr = sys.stdout, sys.stderr
        self.stdout = _TeeStream(self.original_stdout, self, "stdout")
        self.stderr = _TeeStream(self.original_stderr, self, "stderr")
        sys.stdout, sys.stderr = self.stdout, self.stderr
        self.original_excepthook = sys.excepthook

        def exception_hook(exc_type, exc, traceback):
            self.outcome = f"failed: {exc_type.__name__}: {exc}"
            self.original_excepthook(exc_type, exc, traceback)

        self.exception_hook = exception_hook
        sys.excepthook = exception_hook
        self.handler = logging.StreamHandler(_TeeStream(None, self, "debug"))
        self.handler.setFormatter(logging.Formatter("%(levelname)s %(name)s [%(threadName)s] %(message)s"))
        self.root_logger = logging.getLogger()
        self.previous_level = self.root_logger.level
        self.root_logger.addHandler(self.handler)
        self.root_logger.setLevel(logging.DEBUG)
        atexit.register(self.close)
        print(f"Log file: {self.path}", flush=True)
        print(f"Run started: {datetime.now().astimezone().isoformat()}", flush=True)
        print(f"Script: {script_path}\nArguments: {sys.argv[1:]!r}\nWorking directory: {Path.cwd()}", flush=True)
        print(f"Python: {sys.version}\nExecutable: {sys.executable}\nPlatform: {platform.platform()}\nPID: {os.getpid()}", flush=True)
        packages = []
        for name in ("uiautomator2", "adbutils", "requests"):
            try:
                packages.append(f"{name}={version(name)}")
            except PackageNotFoundError:
                packages.append(f"{name}=not installed")
        print("Dependencies: " + ", ".join(packages), flush=True)

    def close(self):
        with self.lock:
            if self.closed:
                return
            elapsed = time.monotonic() - self.started
            self.file.write(f"\n[{datetime.now().astimezone().isoformat(timespec='milliseconds')}] [run] End: {self.outcome}; runtime={elapsed:.2f}s\n")
            self.root_logger.removeHandler(self.handler)
            self.root_logger.setLevel(self.previous_level)
            if sys.stdout is self.stdout:
                sys.stdout = self.original_stdout
            if sys.stderr is self.stderr:
                sys.stderr = self.original_stderr
            if sys.excepthook is self.exception_hook:
                sys.excepthook = self.original_excepthook
            self.file.flush()
            self.closed = True
            self.file.close()


class _TeeStream:
    def __init__(self, original, run, channel):
        self.original, self.run, self.channel = original, run, channel
        self.at_line_start = True

    def write(self, text):
        with self.run.lock:
            if not self.run.closed:
                for part in text.splitlines(keepends=True):
                    if self.at_line_start:
                        stamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
                        self.run.file.write(f"[{stamp}] [{self.channel}] ")
                    self.run.file.write(part)
                    self.at_line_start = part.endswith(("\n", "\r"))
                self.run.file.flush()
            if self.original is not None:
                self.original.write(text)
        return len(text)

    def flush(self):
        with self.run.lock:
            if not self.run.closed:
                self.run.file.flush()
            if self.original is not None:
                self.original.flush()

    def __getattr__(self, name):
        if self.original is not None:
            return getattr(self.original, name)
        raise AttributeError(name)


def start_run_logging(script_path, *, log_root=None):
    """Start once, before optional dependencies load, and return the log path."""
    global _active_run
    configure_utf8_output()
    if _active_run is None:
        _active_run = _RunLog(script_path, log_root)
    return _active_run.path


def run_with_logging(script_path, callback, *, log_root=None):
    """Run an entry point with a unique log; imports alone do not create logs."""
    start_run_logging(script_path, log_root=log_root)
    try:
        result = callback()
    except SystemExit as exc:
        code = exc.code if exc.code is not None else 0
        _active_run.outcome = f"exit code {code!r}"
        raise
    except KeyboardInterrupt:
        _active_run.outcome = "interrupted (KeyboardInterrupt)"
        raise
    except BaseException as exc:
        _active_run.outcome = f"failed: {type(exc).__name__}: {exc}"
        raise
    else:
        _active_run.outcome = "success (exit code 0)"
        return result


def configure_utf8_output():
    """Keep Unicode and emoji logging reliable in background task runners."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, OSError, ValueError):
            pass
