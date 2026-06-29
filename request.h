#ifndef __REQUEST_H__
#define __REQUEST_H__

#include "log.h"

typedef struct Threads_stats {
    int id;           // Thread ID
    int stat_req;     // Number of static requests handled
    int dynm_req;     // Number of dynamic requests handled
    int post_req;     // Number of POST requests handled
    int total_req;    // Total number of requests handled
} * threads_stats;

typedef struct Time_stats {
    struct timeval task_arrival;
    struct timeval task_dispatch;
    struct timeval log_enter;
    struct timeval log_exit;
} time_stats;
// Handles a client request.
// - fd: the connection socket
// - arrival: time the request arrived
// - dispatch: time the thread began processing the request
// - t_stats: pointer to the current thread's statistics (must be updated by student)
// - log: server-wide shared log (thread-safe access required)
// TODO:
// - must correctly track and update per-thread statistics inside the request handler.
// - Update the following fields in `threads_stats`:
//   - total_req
//   - stat_req (for static requests)
//   - dynm_req (for dynamic requests)
//   - post_req (for POST requests)
// - These values should reflect accurate request processing for each thread and be used in response headers/logs.

// Statistics helpers (provided): build the job/thread statistics blocks.
int append_job_log(char* buf, time_stats tm_stats);
int append_thread_log(char* buf, threads_stats t_stats);

void requestHandle(int fd, time_stats tm_stats,  threads_stats t_stats, server_log log);
#endif
