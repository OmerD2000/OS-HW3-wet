#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <unistd.h>
#include <pthread.h>
#include <sys/time.h>
#include "segel.h"
#include "log.h"
#include "request.h"   // for append_stats() - used to compose log entries

#define INITIAL_LOG_CAPACITY 4096

//
// Server log with a multiple-readers / single-writer lock, WRITER PRIORITY.
//
// State protected by 'mutex':
//   readers_inside  - number of readers currently in the critical section
//   writers_inside  - 1 if a writer is currently in the critical section
//   writers_waiting - number of writers blocked waiting for the lock
//
// Writer priority is achieved by making readers wait not only while a writer
// is INSIDE, but also while any writer is WAITING (writers_waiting > 0).
//
struct Server_Log {
    // --- log storage (dynamic string buffer) ---
    char* buf;
    int   len;   // current length (excluding null terminator)
    int   cap;   // allocated capacity

    // --- debug mode ---
    double sleep_time; // > 0 => sleep inside every critical section

    // --- readers/writers synchronization ---
    pthread_mutex_t mutex;
    pthread_cond_t  can_read;    // readers wait here
    pthread_cond_t  can_write;   // writers wait here
    int readers_inside;
    int writers_inside;
    int writers_waiting;
};

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

static void debug_sleep(server_log log)
{
    if (log->sleep_time > 0) {
        usleep((useconds_t)(log->sleep_time * 1e6));
    }
}

static void reader_lock(server_log log)
{
    pthread_mutex_lock(&log->mutex);
    // Writer priority: block while a writer is inside OR waiting
    while (log->writers_inside > 0 || log->writers_waiting > 0) {
        pthread_cond_wait(&log->can_read, &log->mutex);
    }
    log->readers_inside++;
    pthread_mutex_unlock(&log->mutex);
}

static void reader_unlock(server_log log)
{
    pthread_mutex_lock(&log->mutex);
    log->readers_inside--;
    if (log->readers_inside == 0) {
        // Last reader out - a waiting writer may now enter
        pthread_cond_signal(&log->can_write);
    }
    pthread_mutex_unlock(&log->mutex);
}

static void writer_lock(server_log log)
{
    pthread_mutex_lock(&log->mutex);
    log->writers_waiting++;   // announce intent => new readers will block
    while (log->readers_inside > 0 || log->writers_inside > 0) {
        pthread_cond_wait(&log->can_write, &log->mutex);
    }
    log->writers_waiting--;
    log->writers_inside = 1;
    pthread_mutex_unlock(&log->mutex);
}

static void writer_unlock(server_log log)
{
    pthread_mutex_lock(&log->mutex);
    log->writers_inside = 0;
    if (log->writers_waiting > 0) {
        // Writers first (priority): hand over to the next writer
        pthread_cond_signal(&log->can_write);
    } else {
        // No writers waiting - release all waiting readers
        pthread_cond_broadcast(&log->can_read);
    }
    pthread_mutex_unlock(&log->mutex);
}

// Ensures the buffer can hold 'extra' more bytes (plus null terminator).
// Must be called while holding the writer lock.
static void log_reserve(server_log log, int extra)
{
    int needed = log->len + extra + 1;
    if (needed <= log->cap)
        return;
    int new_cap = log->cap;
    while (new_cap < needed)
        new_cap *= 2;
    char* new_buf = realloc(log->buf, new_cap);
    if (new_buf == NULL) {
        fprintf(stderr, "Error: log realloc failed\n");
        exit(1);
    }
    log->buf = new_buf;
    log->cap = new_cap;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

server_log create_log(double debug_sleep_time)
{
    server_log log = malloc(sizeof(struct Server_Log));
    if (log == NULL) {
        fprintf(stderr, "Error: failed to allocate server log\n");
        exit(1);
    }
    log->buf = malloc(INITIAL_LOG_CAPACITY);
    if (log->buf == NULL) {
        fprintf(stderr, "Error: failed to allocate log buffer\n");
        exit(1);
    }
    log->buf[0] = '\0';
    log->len = 0;
    log->cap = INITIAL_LOG_CAPACITY;
    log->sleep_time = debug_sleep_time;

    pthread_mutex_init(&log->mutex, NULL);
    pthread_cond_init(&log->can_read, NULL);
    pthread_cond_init(&log->can_write, NULL);
    log->readers_inside  = 0;
    log->writers_inside  = 0;
    log->writers_waiting = 0;
    return log;
}

void destroy_log(server_log log)
{
    if (log == NULL)
        return;
    pthread_mutex_destroy(&log->mutex);
    pthread_cond_destroy(&log->can_read);
    pthread_cond_destroy(&log->can_write);
    free(log->buf);
    free(log);
}

// READER (POST request): copy out the whole log.
int get_log(server_log log, char** dst, time_stats* tm_stats)
{
    // Stat-Log-Arrival: before requesting the lock
    gettimeofday(&tm_stats->log_enter, NULL);

    reader_lock(log);
    // ---- reader critical section ----
    debug_sleep(log);                            // simulate slow disk I/O
    gettimeofday(&tm_stats->log_exit, NULL);     // after sleep, before the operation

    int len = log->len;
    *dst = malloc(len + 1);
    if (*dst != NULL) {
        memcpy(*dst, log->buf, len);
        (*dst)[len] = '\0';
    } else {
        len = 0;
    }
    // ---------------------------------
    reader_unlock(log);
    return len;
}

// WRITER (GET request): append this request's statistics block as a new entry.
// Entries are delimited by '#'.
void add_to_log(server_log log, time_stats* tm_stats, threads_stats t_stats)
{
    // Stat-Log-Arrival: before requesting the lock
    gettimeofday(&tm_stats->log_enter, NULL);

    writer_lock(log);
    // ---- writer critical section ----
    debug_sleep(log);                            // simulate slow disk I/O
    gettimeofday(&tm_stats->log_exit, NULL);     // after sleep, BEFORE the log operation

    // Compose the entry (job stats + thread stats), now that log_exit is final
    char entry[MAXBUF];
    entry[0] = '\0';
    int entry_len = append_stats(entry, t_stats, *tm_stats);

    // '#' between entries
    int extra = entry_len + (log->len > 0 ? 1 : 0);
    log_reserve(log, extra);
    if (log->len > 0) {
        log->buf[log->len++] = '#';
    }
    memcpy(log->buf + log->len, entry, entry_len);
    log->len += entry_len;
    log->buf[log->len] = '\0';
    // ---------------------------------
    writer_unlock(log);
}