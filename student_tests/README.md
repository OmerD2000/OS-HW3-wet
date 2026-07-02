# HW3 — Public self-check tests

This is a **subset** of the automated test suite, so you can sanity-check your
server before submitting.

> ⚠️ Passing all of these does **not** guarantee full marks. The graded suite
> contains many more — and stricter — tests. Use this only as a smoke test.

## What's included

| Test | Checks |
|------|--------|
| `argbuffers`, `argport`, `argthreads`, `argudpport`, `argudpequalstcp`, `argcount` | The server rejects invalid command-line arguments and exits. |
| `locks` | The server survives many concurrent GET requests without crashing. |
| `log_consistency` | GET appends an entry to the log; POST returns the full log. |
| `udp_stats` | A UDP ping for a thread id returns that thread's statistics. |

## UDP protocol used by `udp_stats`

- **Request:** send the target worker thread's id as an ASCII decimal string in
  the UDP datagram payload, e.g. `"1"`.
- **Response:** the server replies with that thread's five statistics, one per
  line, each formatted exactly as in the HTTP headers:

  ```
  Stat-Thread-Id:: <n>
  Stat-Thread-Count:: <n>
  Stat-Thread-Static:: <n>
  Stat-Thread-Dynamic:: <n>
  Stat-Thread-Post:: <n>
  ```

## How to run

Copy `server.py`, `toolspath.py`, and the `testing/` folder into your project
directory (next to your `Makefile` and source files), then:

```bash
python3 server.py            # builds with `make`, then runs all public tests
python3 server.py --no-build # skip the build step (use your existing binary)
python3 server.py -p PATH    # test a project located elsewhere
```

Requires Python 3 and a Linux environment (same as the course servers).
```
