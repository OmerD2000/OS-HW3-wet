#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# HW3 - Web Servers and Synchronization : PUBLIC self-check tests
#
# This is a SUBSET of the test suite, provided so you can sanity-check your
# server before submitting. Passing all of these does NOT guarantee full
# marks: the graded suite contains many more (and stricter) tests.
#
# Usage (run from your project directory, after `make`):
#     python3 server.py                 # build + run all public tests here
#     python3 server.py -p /path/proj   # test a project in another folder
#     python3 server.py --no-build      # skip the `make` step
# ---------------------------------------------------------------------------
import time, os, http.client, random, threading, re, socket, sys

import toolspath
from testing import Test, BuildTest
from testing.test import Failure

# Test Registry
test_list = []


def parse_stat_headers(headers):
    parsed = {}
    for key, val in headers:
        val = val.lstrip(':').strip()
        try:
            val = float(val) if '.' in val else int(val)
        except ValueError:
            pass
        parsed[key] = val
    return parsed


def parse_stat_string(raw):
    """Parse a raw UDP stats payload into a dict.

    The server answers a UDP ping with the target thread's statistics as
    'Stat-Thread-X:: <value>' fields. Fields may be separated by newlines or
    by '#'. Values are coerced to int/float when possible.
    """
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode(errors="replace")
    parsed = {}
    for field in re.split(r"[\n#]+", raw):
        field = field.strip()
        if not field or "::" not in field:
            continue
        key, val = field.split("::", 1)
        key = key.strip()
        val = val.strip()
        try:
            val = float(val) if '.' in val else int(val)
        except ValueError:
            pass
        parsed[key] = val
    return parsed


def test(cls):
    test_list.append(cls)
    return cls


# --- Base Classes ---

class ArgTest(Test):
    timeout = 2

    def run_argtest(self, port=0, udp_port=0, threads=1, buffers=1, debug=0, n=None):
        if (port == 0):
            port = random.randint(5000, 10000)
        if (udp_port == 0):
            udp_port = random.randint(10001, 15000)
        self.log(f"Starting server on tcp port {port}, udp port {udp_port}")
        # CLI: ./server [tcp_port] [udp_port] [threads] [queue_size] [debug]
        args = ["server", str(port), str(udp_port), str(threads), str(buffers), str(debug)]
        if n is not None:
            args.append(str(n))

        serverProc = self.startexe(args)
        time.sleep(0.5)

        if (serverProc.poll() == None):
            serverProc.kill()
            self.fail("Server stayed alive with invalid arguments")
        else:
            self.log(f"Server exited as expected (Code: {serverProc.returncode})")

    def run_argtest_raw(self, server_args):
        """Launch the server with an explicit argument list (without the
        program name) and require that it exits (rejects the arguments)."""
        args = ["server"] + [str(a) for a in server_args]
        self.log(f"Starting server with raw args: {server_args}")
        serverProc = self.startexe(args)
        time.sleep(0.5)

        if (serverProc.poll() == None):
            serverProc.kill()
            self.fail(f"Server stayed alive with invalid arguments: {server_args}")
        else:
            self.log(f"Server exited as expected (Code: {serverProc.returncode})")


class ServerTest(Test):
    timeout = 30

    def quiet_get(self, conn, item):
        try:
            conn.request('GET', item)
            return True
        except Exception:
            self.fail('Unable to send GET request; server may have crashed.')
            return False

    def quiet_post(self, conn, item):
        try:
            conn.request('POST', item)
            return True
        except Exception as e:
            self.fail('unable to send POST request; server may have crashed.')
            return False

    def client_run(self, conn):
        try:
            response = conn.getresponse()
            msg = response.read()
            conn.close()
            if (len(msg) == 0):
                self.fail("missing body in response")
        except Exception as inst:
            self.fail("Client failed with error: " + str(inst))

    def run_server(self, threads, q_size, debug=0):
        for i in range(5):
            port = random.randint(5000, 10000)
            udp_port = random.randint(10001, 15000)
            self.log(f"Starting server on tcp port {port}, udp port {udp_port}")
            # CLI: ./server [tcp_port] [udp_port] [threads] [queue_size] [debug]
            args = ["server", str(port), str(udp_port), str(threads), str(q_size), str(debug)]

            serverProc = self.startexe(args)
            time.sleep(0.2)

            if serverProc.poll() is None:
                self.port = port
                self.udp_port = udp_port
                self.serverProc = serverProc
                return serverProc
        raise Failure("Could not start server after 5 attempts")

    def send_udp_ping(self, thread_id, attempts=3, timeout=2):
        """Ping the server's UDP channel for a thread's statistics.

        Wire format:
          - request : the thread id as plain ASCII bytes, e.g. b"1"
          - response: that thread's 'Stat-Thread-X:: <value>' fields

        Retries because UDP is unreliable; returns the parsed stats dict, or
        raises socket.timeout if no reply arrives across all attempts.
        """
        last_err = None
        for _ in range(attempts):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            try:
                sock.sendto(str(thread_id).encode(), ("localhost", self.udp_port))
                data, _ = sock.recvfrom(4096)
                self.last_udp_raw = data
                return parse_stat_string(data)
            except socket.timeout as e:
                last_err = e
                continue
            finally:
                sock.close()
        raise last_err if last_err else socket.timeout("no UDP response")


# --- Argument Validation Tests ---

@test
class ArgBuffers(ArgTest):
    name = "argbuffers"
    description = "invalid number of buffers"

    def run(self):
        self.run_argtest(buffers=-1)
        self.done()


@test
class ArgPort(ArgTest):
    name = "argport"
    description = "invalid port number"

    def run(self):
        self.run_argtest(port=22)
        self.done()


@test
class ArgThreads(ArgTest):
    name = "argthreads"
    description = "invalid number of threads"

    def run(self):
        self.run_argtest(threads=-1)
        self.done()


@test
class ArgUdpPort(ArgTest):
    name = "argudpport"
    description = "invalid udp port number"

    def run(self):
        self.run_argtest(udp_port=22)
        self.done()


@test
class ArgUdpEqualsTcp(ArgTest):
    name = "argudpequalstcp"
    description = "udp port must differ from tcp port"

    def run(self):
        same = random.randint(5000, 10000)
        self.run_argtest(port=same, udp_port=same)
        self.done()


@test
class ArgCount(ArgTest):
    name = "argcount"
    description = "too few command-line arguments"

    def run(self):
        port = random.randint(5000, 10000)
        self.run_argtest_raw([port, port + 1])
        self.done()


# --- Concurrency: one locking test ---

@test
class Locks(ServerTest):
    name = "locks"
    threads = 8
    buffers = 16
    num_clients = 20
    loops = 5
    description = "sends many concurrent requests to test locking."
    requests = ["/home.html", "/output.cgi?0.3", "/favicon.ico"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.description += (f' server params: threads {self.threads}, Q_size {self.buffers}. '
                             f'{self.num_clients} clients each requesting {self.requests}, {self.loops} times')

    def many_reqs(self):
        for i in range(self.loops):
            for request in self.requests:
                if self.is_failed():
                    return
                conn = http.client.HTTPConnection("localhost", self.port, timeout=20)
                if self.quiet_get(conn, request):
                    self.client_run(conn)

    def run(self):
        serverProc = self.run_server(threads=self.threads, q_size=self.buffers)
        clients = [threading.Thread(target=self.many_reqs) for _ in range(self.num_clients)]
        for client in clients:
            client.start()
        for client in clients:
            client.join()

        if (serverProc.poll() != None):
            self.fail("server exited or crashed")
        else:
            serverProc.kill()
        self.done()


# --- Log structure ---

@test
class LogConsistency(ServerTest):
    name = "log_consistency"
    description = "Check if GET appends to the log and POST retrieves the full log string."
    threads, buffers = 2, 5

    def run(self):
        serverProc = self.run_server(self.threads, self.buffers)
        try:
            # Step 1: Multiple GETs to fill the log
            for i in range(3):
                conn = http.client.HTTPConnection("localhost", self.port)
                self.quiet_get(conn, "/home.html")
                conn.getresponse().read()

            # Step 2: POST to retrieve the log
            conn = http.client.HTTPConnection("localhost", self.port)
            self.quiet_post(conn, "/home.html")
            response = conn.getresponse()
            body = response.read().decode()

            occurrences = len(re.findall("Stat-Req-Arrival::", body))
            if occurrences < 3:
                self.fail(f"Log expected at least 3 entries, found {occurrences}")
        finally:
            serverProc.kill()
        self.done()


# --- UDP statistics channel ---

@test
class UdpStats(ServerTest):
    name = "udp_stats"
    description = "Ping the UDP port for a thread id and verify the returned thread-statistics dictionary."
    threads, buffers = 4, 8

    required_thread_stats = [
        "Stat-Thread-Id", "Stat-Thread-Count", "Stat-Thread-Static",
        "Stat-Thread-Dynamic", "Stat-Thread-Post",
    ]
    # The exact reply format the server is expected to produce.
    expected_format = (
        "Stat-Thread-Id:: <int>\n"
        "Stat-Thread-Count:: <int>\n"
        "Stat-Thread-Static:: <int>\n"
        "Stat-Thread-Dynamic:: <int>\n"
        "Stat-Thread-Post:: <int>"
    )

    def _format_error(self, problem, raw):
        """Build a failure message that shows the expected format and what the
        server actually sent, so the issue is easy to fix."""
        return (f"{problem}\n"
                f"--- Expected UDP reply format (integer values, '::' separator) ---\n"
                f"{self.expected_format}\n"
                f"--- Actual reply received ---\n"
                f"{raw!r}")

    def run(self):
        serverProc = self.run_server(self.threads, self.buffers)
        try:
            # Generate some HTTP traffic first so threads have handled requests.
            for _ in range(5):
                conn = http.client.HTTPConnection("localhost", self.port, timeout=10)
                if self.quiet_get(conn, "/home.html"):
                    conn.getresponse().read()
                conn.close()

            target_id = 1
            try:
                stats = self.send_udp_ping(target_id)
            except socket.timeout:
                self.fail(f"No UDP response on port {self.udp_port} for thread {target_id} (timed out).\n"
                          f"The server must reply to a UDP ping with:\n{self.expected_format}")
                self.done()
                return
            except Exception as e:
                self.fail(f"UDP ping failed: {e}")
                self.done()
                return

            raw = getattr(self, "last_udp_raw", b"")
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode(errors="replace")
            self.actual_output = f"UDP reply: {raw!r}"
            self.log(f"UDP stats for thread {target_id}: {stats}")

            if not stats:
                self.fail(self._format_error("UDP response was empty or could not be parsed.", raw))
                self.done()
                return

            # 1) All five per-thread statistics must be present.
            for key in self.required_thread_stats:
                if key not in stats:
                    self.fail(self._format_error(f"Missing statistic '{key}' in the UDP response.", raw))
                    self.done()
                    return

            # 2) Each value must be an integer (format '<key>:: <int>').
            for key in self.required_thread_stats:
                if not isinstance(stats[key], int):
                    self.fail(self._format_error(
                        f"Statistic '{key}' must be an integer, got {stats[key]!r}.", raw))
                    self.done()
                    return

            # 3) The reply must describe the thread we asked about.
            if stats["Stat-Thread-Id"] != target_id:
                self.fail(self._format_error(
                    f"Reply reported Stat-Thread-Id {stats['Stat-Thread-Id']}, expected {target_id}.", raw))
                self.done()
                return

            if serverProc.poll() is not None:
                self.fail("Server crashed during the UDP stats test.")
        finally:
            serverProc.kill()
        self.done()


# ---------------------------------------------------------------------------
# Standalone runner (no grader). Builds with `make`, then runs each public
# test in an isolated subprocess with a timeout, and prints a summary.
# ---------------------------------------------------------------------------
def _main():
    import argparse, multiprocessing, queue as _queue
    from testing.test import run_test, TestResult

    try:
        multiprocessing.set_start_method("fork", force=True)
    except (ValueError, RuntimeError):
        pass

    ap = argparse.ArgumentParser(description="HW3 public self-check tests")
    ap.add_argument("-p", "--project-path", default=".", help="Project directory to test")
    ap.add_argument("-b", "--no-build", action="store_false", dest="build", default=True,
                    help="Skip the 'make' build step")
    ap.add_argument("-f", "--factor", type=float, default=1.5, help="Timeout multiplier")
    opts = ap.parse_args()

    project = os.path.abspath(opts.project_path)
    suite = ([BuildTest] if opts.build else []) + test_list

    passed = 0
    counted = 0
    for cls in suite:
        t = cls(project_path=project, log=sys.stdout, max_score=1)
        print("\n" + "=" * 60)
        print(f" {t.name}: {t.description}")
        print("=" * 60)

        result_q = multiprocessing.Queue()
        p = multiprocessing.Process(target=run_test, args=(t, result_q))
        p.start()
        timeout = (t.timeout or 30) * opts.factor
        try:
            result = result_q.get(block=True, timeout=timeout)
        except _queue.Empty:
            result = TestResult(t)
            result.state = Test.FAILED
            result.comment = f"TIMEOUT after {timeout:.0f}s"
        finally:
            if p.is_alive():
                p.terminate()
            result_q.close()

        ok = (result.state == Test.PASSED)
        status = "PASS" if ok else "FAIL"
        print(f"  >>> {status}" + (f"  ({result.comment})" if result.comment else ""))

        if t.name == "build":
            if not ok:
                print("\nBuild failed - fix compilation before running the tests.")
                return 1
            continue

        counted += 1
        if ok:
            passed += 1

    print("\n" + "=" * 60)
    print(f" RESULT: {passed}/{counted} public tests passed")
    print("=" * 60)
    print("Note: this is only a subset. The graded suite is larger and stricter.")
    return 0 if passed == counted else 1


if __name__ == "__main__":
    sys.exit(_main())
