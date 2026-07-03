#ifndef __REQUEST_H__
#define __REQUEST_H__

#include "log.h"   // defines threads_stats, time_stats, server_log

// Statistics helpers (provided): build the job/thread statistics blocks.
int append_job_log(char* buf, time_stats tm_stats);
int append_thread_log(char* buf, threads_stats t_stats);
int append_stats(char* buf, threads_stats t_stats, time_stats tm_stats);

// Handles a client request.
// - fd: the connection socket
// - tm_stats: timing statistics; task_arrival set by master, task_dispatch set
//   by the worker. log_enter/log_exit are filled in during log access.
// - t_stats: the calling worker thread's statistics (updated here):
//     * total_req is incremented for EVERY request (including errors)
//     * stat_req / dynm_req / post_req are incremented only for VALID requests
//     * 501/403/404 errors do not increment the type counters
// - log: server-wide shared log (GET = writer, POST = reader)
void requestHandle(int fd, time_stats tm_stats, threads_stats t_stats, server_log log);

#endif