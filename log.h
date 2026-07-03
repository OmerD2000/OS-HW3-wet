#ifndef SERVER_LOG_H
#define SERVER_LOG_H

#include <sys/time.h>

//
// Shared statistics structures.
// Defined here (rather than request.h) because the log composes its entries
// from these stats, and request.h already includes log.h.
//

typedef struct Threads_stats {
    int id;           // Thread ID (1..N)
    int stat_req;     // Number of static requests handled
    int dynm_req;     // Number of dynamic requests handled
    int post_req;     // Number of POST requests handled
    int total_req;    // Total number of requests handled
} * threads_stats;

typedef struct Time_stats {
    struct timeval task_arrival;   // set by master thread on accept()
    struct timeval task_dispatch;  // set by worker when it picks the job
    struct timeval log_enter;      // set right before requesting the log lock
    struct timeval log_exit;       // set after the debug sleep, inside the critical section
} time_stats;

//
// Thread-safe server log.
// Multiple-readers / single-writer with WRITER PRIORITY:
// if a writer is waiting, new readers block until all writers are done.
//
// GET requests are writers (they append an entry).
// POST requests are readers (they return the whole log).
//

typedef struct Server_Log* server_log;

// Creates a new server log instance.
// debug_sleep_time > 0 enables the debug sleep (in seconds, may be fractional)
// executed inside every reader/writer critical section.
server_log create_log(double debug_sleep_time);

// Destroys and frees the log
void destroy_log(server_log log);

// READER: returns the log contents as a string (null-terminated).
// Records tm_stats->log_enter before requesting the lock, and
// tm_stats->log_exit after the debug sleep inside the critical section.
// NOTE: caller is responsible for freeing *dst.
int get_log(server_log log, char** dst, time_stats* tm_stats);

// WRITER: appends a new entry (the request's full statistics block) to the log.
// Records tm_stats->log_enter before requesting the lock, and
// tm_stats->log_exit after the debug sleep inside the critical section,
// before performing the append itself.
void add_to_log(server_log log, time_stats* tm_stats, threads_stats t_stats);

#endif // SERVER_LOG_H