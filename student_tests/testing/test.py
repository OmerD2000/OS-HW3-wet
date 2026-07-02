# import subprocess, os, sys, traceback, string, signal
# from time import time, sleep
#
#
# class Failure(Exception):
#     def __init__(self, value, detail=None):
#         self.value = value
#         self.detail = detail
#
#     def __str__(self):
#         return f"{self.value}\n{self.detail}" if self.detail else str(self.value)
#
#
# def restore_signals():
#     signals = ('SIGPIPE', 'SIGXFZ', 'SIGXFSZ')
#     for sig in signals:
#         if hasattr(signal, sig):
#             signal.signal(getattr(signal, sig), signal.SIG_DFL)
#
#
# class Test(object):
#     IN_PROGRESS, PASSED, FAILED = 1, 2, 3
#
#     # --- Framework Metadata ---
#     name = None
#     description = ""
#     max_score = 0
#     test_type = "standard"
#     timeout = 30
#
#     # --- Dependency & Process Sharing Logic ---
#     is_dependent = False  # If True, the engine will inject shared_proc/shared_port
#     shared_proc = None
#     shared_port = None
#
#     def __init__(self, project_path=None, log=None, max_score=0, test_type="standard"):
#         self.project_path = project_path
#         self.logfd = log or sys.stdout
#         self.state = self.IN_PROGRESS
#
#         # Injected duality attributes
#         self.max_score = max_score
#         self.test_type = test_type
#
#         # Log Template Attributes (for YAML/UI)
#         self.expected_output = ""
#         self.actual_output = ""
#         self.comment = ""
#         self.score = 0
#
#         self.notices = []
#         self.children = []
#
#     def fail(self, reason=None):
#         self.state = self.FAILED
#         self.score = 0
#         if reason:
#             self.notices.append(str(reason))
#
#     def warn(self, reason):
#         self.notices.append(str(reason))
#
#     def done(self):
#         if self.state != self.FAILED:
#             self.state = self.PASSED
#             self.score = self.max_score
#
#         if self.notices:
#             self.comment = " | ".join(self.notices)
#
#     # --- Execution Logic ---
#
#     def startexe(self, args, cwd=None):
#         """Starts a child process, handling Streamlit's lack of fileno."""
#         binary_path = os.path.join(self.project_path, args[0])
#         args[0] = binary_path
#
#         # Sharing logic for dependent groups
#         if hasattr(self, 'shared_proc') and self.shared_proc and self.shared_proc.poll() is None:
#             return self.shared_proc
#
#         # FIX: If we are in the UI (no fileno), redirect to a temporary log file
#         # so the subprocess has a real file descriptor.
#         out_target = self.logfd
#         if hasattr(self.logfd, 'write') and not hasattr(self.logfd, 'fileno'):
#             # Use the student's logfile.log as the physical sink
#             out_target = open(os.path.join(self.project_path, 'logfile.log'), 'a+')
#
#         child = subprocess.Popen(
#             args,
#             cwd=cwd or self.project_path,
#             stdout=out_target,
#             stderr=out_target,
#             preexec_fn=restore_signals if os.name != 'nt' else None
#         )
#         self.children.append(child)
#         return child
#
#     def run_util(self, args, cwd=None):
#         """Runs a utility (like make) and handles Streamlit redirection."""
#         target_dir = cwd or self.project_path
#
#         # UI Redirect logic: subprocess can't use StreamlitRedirect directly
#         if hasattr(self.logfd, 'write') and not hasattr(self.logfd, 'fileno'):
#             process = subprocess.Popen(
#                 args, cwd=target_dir,
#                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
#                 text=True, bufsize=1
#             )
#             # Manually relay lines to the UI
#             for line in process.stdout:
#                 self.log(line.strip())
#             return process.wait()
#         else:
#             child = subprocess.Popen(
#                 args, cwd=target_dir,
#                 stdout=self.logfd, stderr=self.logfd
#             )
#             return child.wait()
#
#     def log(self, msg):
#         if self.logfd:
#             self.logfd.write(str(msg) + "\n")
#             self.logfd.flush()
#
#     def capture_actual_output(self, lines=5):
#         """
#         Improved capture: Checks the physical log file first,
#         but falls back to the UI buffer if the file is empty/missing.
#         """
#         try:
#             # 1. Try to read from the physical log file
#             if hasattr(self.logfd, 'name') and os.path.exists(self.logfd.name):
#                 # Force a disk sync to make sure the OS wrote the data
#                 os.sync()
#                 with open(self.logfd.name, 'r') as f:
#                     all_lines = f.readlines()
#                     if all_lines:
#                         self.actual_output = " ".join([l.strip() for l in all_lines[-lines:]])
#                         return
#
#             # 2. FALLBACK: If we are in Streamlit and the file failed,
#             # pull from the Redirect object's internal text buffer.
#             if hasattr(self.logfd, 'text') and self.logfd.text:
#                 buffer_lines = self.logfd.text.strip().split('\n')
#                 self.actual_output = " ".join(buffer_lines[-lines:])
#             else:
#                 self.actual_output = "No output captured from process."
#
#         except Exception as e:
#             self.actual_output = f"Capture Error: {str(e)}"
#
#
# class TestResult(object):
#     def __init__(self, test):
#         self.name = test.name
#         self.description = test.description
#         self.state = test.state
#         self.max_score = test.max_score
#         self.score = test.score
#         self.test_type = test.test_type
#         self.expected_output = test.expected_output
#         self.actual_output = test.actual_output
#         self.comment = test.comment
#
#         # Crucial: Pass back the server handle to the engine for the NEXT test
#         # We look for a 'server_proc' attribute often set in ServerTest.run_server
#         self.server_proc = getattr(test, 'server_proc', None)
#         self.server_port = getattr(test, 'server_port', None)
#
#     def is_failed(self):
#         return self.state == 3
#
#
# def run_test(test, queue):
#     try:
#         if os.name != 'nt':
#             os.setpgrp()
#         test.run()
#     except Exception as e:
#         test.fail(f"Unexpected Exception: {e}")
#     finally:
#         test.done()
#         queue.put(TestResult(test))

import subprocess, os, sys, traceback, string, signal
from time import time, sleep


class Failure(Exception):
    def __init__(self, value, detail=None):
        self.value = value
        self.detail = detail

    def __str__(self):
        return f"{self.value}\n{self.detail}" if self.detail else str(self.value)


def restore_signals():
    signals = ('SIGPIPE', 'SIGXFZ', 'SIGXFSZ')
    for sig in signals:
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), signal.SIG_DFL)


class Test(object):
    IN_PROGRESS, PASSED, FAILED = 1, 2, 3

    # Framework Defaults
    name = None
    description = ""
    timeout = 30
    is_dependent = False
    shared_proc = None
    shared_port = None

    def __init__(self, project_path=None, log=None, max_score=0, test_type="standard", use_gdb=False,
                 use_valgrind=False):
        # Arguments matched to runtests.py
        self.project_path = project_path
        self.logfd = log or sys.stdout
        self.state = self.IN_PROGRESS

        # Scoring & Metadata
        self.max_score = max_score
        self.test_type = test_type
        self.score = 0
        self.expected_output = ""
        self.actual_output = ""
        self.comment = ""

        # Debugging Features (from Script 1)
        self.use_gdb = use_gdb
        self.use_valgrind = use_valgrind

        self.notices = []
        self.children = []

    def log(self, msg):
        if self.logfd:
            self.logfd.write(str(msg) + "\n")
            self.logfd.flush()
        try:
            log_path = os.path.join(self.project_path, 'logfile.log')
            with open(log_path, 'a') as f:
                f.write(str(msg) + "\n")
        except:
            pass


    def set_affinity(self, pid):
        """Induces race conditions by pinning process to specific cores."""
        try:
            total_cores = os.cpu_count()
            # Pin to first half of cores to force thread contention
            server_cores = set(range(max(1, total_cores // 2)))
            os.sched_setaffinity(pid, server_cores)
            self.log(f"[DEBUG] Affinity set for PID {pid} to cores {server_cores}")
        except Exception as e:
            self.log(f"[DEBUG] Affinity skipped: {e}")

    def startexe(self, args, cwd=None):
        name = args[0]
        binary_path = os.path.join(self.project_path, name)
        args[0] = binary_path
        cwd = cwd or self.project_path

        # Handle Streamlit/UI redirection issues
        out_target = self.logfd
        if hasattr(self.logfd, 'write') and not hasattr(self.logfd, 'fileno'):
            out_target = open(os.path.join(self.project_path, 'logfile.log'), 'a+')

        # Execution Modes
        if self.use_gdb:
            cmd = ["xterm", "-title", f"GDB: {name}", "-e", "gdb", "--args"] + args
            child = subprocess.Popen(cmd, cwd=cwd, preexec_fn=restore_signals)
        elif self.use_valgrind:
            self.log("Running with VALGRIND...")
            cmd = ["valgrind", "--leak-check=full"] + args
            child = subprocess.Popen(cmd, cwd=cwd, stdout=out_target, stderr=out_target, preexec_fn=restore_signals)
            sleep(1)
        else:
            child = subprocess.Popen(args, cwd=cwd, stdout=out_target, stderr=out_target, preexec_fn=restore_signals)

        self.children.append(child)
        self.set_affinity(child.pid)
        return child

    def run_util(self, args, cwd=None):
        """
        Runs a utility (like 'make') and handles both Terminal and UI redirection.
        Line-by-line relay ensures real-time logging without 'fileno' crashes.
        """
        target_dir = cwd or self.project_path
        self.log(f"Executing utility: {' '.join(args)}")

        # Check if we are in a UI environment (no real file descriptor)
        if hasattr(self.logfd, 'write') and not hasattr(self.logfd, 'fileno'):
            process = subprocess.Popen(
                args,
                cwd=target_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merge stderr into stdout
                text=True,
                bufsize=1,
                preexec_fn=restore_signals
            )
            # Manually relay lines from the pipe to the UI log object
            for line in process.stdout:
                self.log(line.strip())

            return process.wait()
        else:
            # Standard terminal execution: Direct handover to the OS
            child = subprocess.Popen(
                args,
                cwd=target_dir,
                stdout=self.logfd,
                stderr=self.logfd,
                preexec_fn=restore_signals
            )
            self.children.append(child)
            return child.wait()
    def fail(self, reason=None):
        self.state = self.FAILED
        self.score = 0
        if reason: self.notices.append(str(reason))

    def is_failed(self):
        return self.state == self.FAILED

    def done(self):
        if self.state != self.FAILED:
            self.state = self.PASSED
            self.score = self.max_score
        if self.notices:
            self.comment = " | ".join(self.notices)
    def warn(self, reason):
        self.notices.append(str(reason))

class TestResult(object):
    """Data object to pass back through the multiprocessing Queue."""

    def __init__(self, test):
        self.name = test.name
        self.description = test.description
        self.state = test.state
        self.max_score = test.max_score
        self.score = test.score
        self.test_type = test.test_type
        self.expected_output = test.expected_output
        self.actual_output = test.actual_output
        self.comment = test.comment

        # Pass back server handles for dependent tests
        self.server_proc = getattr(test, 'server_proc', None)
        self.server_port = getattr(test, 'server_port', None)

    def is_failed(self):
        return self.state == 3


def run_test(test, queue):
    try:
        try:
            total_cores = os.cpu_count()
            midpoint = total_cores // 2
            # Pin the test runner to the second half (e.g., 10-19)
            env_cores = set(range(midpoint, total_cores))
            os.sched_setaffinity(0, env_cores)
        except:
            pass  # Fallback for systems that don't support affinity
        if os.name != 'nt':
            os.setpgrp()
        test.run()
    except Exception as e:
        test.fail(f"Unexpected Exception: {e}")
        traceback.print_exc()
    finally:
        test.done()
        queue.put(TestResult(test))