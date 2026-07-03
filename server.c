#include "segel.h"
#include "request.h"
#include "log.h"

//
// server.c: A multi-threaded web server with a fixed-size thread pool.
//
// Usage:
//   ./server [tcp_portnum] [udp_portnum] [threads] [queue_size] [debug_sleep_time]
//
// Architecture (producer-consumer):
//   - The MASTER thread (main) multiplexes two sockets with select():
//       * TCP listen socket: accepts connections, records their arrival time,
//         and enqueues them into a bounded FIFO queue. If the queue is "full"
//         (pending + currently-processed >= queue_size) the master BLOCKS.
//       * UDP socket: receives admin "pings" containing a worker thread id,
//         and registers the ping (sender address) to that thread.
//   - N WORKER threads, created once at startup, each:
//       * first answer all UDP pings registered to them (UDP before TCP),
//       * then dequeue the oldest pending connection (FIFO) and handle it.
//
// All shared state (the request queue + per-thread ping lists) is protected
// by a single mutex with two condition variables (no busy waiting):
//   - cond_work:  workers wait here when they have nothing to do
//   - cond_space: the master waits here when the queue is full
//

// ---------------------------------------------------------------------------
// Shared state
// ---------------------------------------------------------------------------

// A pending TCP job: the connection fd + its arrival time (set by the master)
typedef struct {
    int connfd;
    struct timeval arrival;
} job_t;

// A registered UDP ping: who to answer (linked list node)
typedef struct PingNode {
    struct sockaddr_in client_addr;
    struct PingNode* next;
} PingNode;

static job_t* request_queue;        // circular buffer of pending jobs
static int queue_capacity;          // max pending + in-progress requests
static int queue_head = 0;          // index of oldest pending job
static int pending_count = 0;       // jobs waiting in the queue
static int active_count = 0;        // jobs currently processed by workers

static PingNode** ping_head;        // per-thread FIFO of registered UDP pings
static PingNode** ping_tail;

static pthread_mutex_t pool_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t  cond_work  = PTHREAD_COND_INITIALIZER;  // workers wait
static pthread_cond_t  cond_space = PTHREAD_COND_INITIALIZER;  // master waits

static int num_threads;
static int udp_fd;                  // shared UDP socket (workers sendto on it)
static server_log slog;             // the shared server log

// ---------------------------------------------------------------------------
// Argument parsing
// ---------------------------------------------------------------------------

void getargs(int *tcp_port, int *udp_port, int *threads, int *queue_size,
             double *debug_sleep, int argc, char *argv[])
{
    if (argc != 6) {
        fprintf(stderr,
            "Usage: %s [tcp_portnum] [udp_portnum] [threads] [queue_size] [debug_sleep_time]\n",
            argv[0]);
        exit(1);
    }
    *tcp_port    = atoi(argv[1]);
    *udp_port    = atoi(argv[2]);
    *threads     = atoi(argv[3]);
    *queue_size  = atoi(argv[4]);
    *debug_sleep = atof(argv[5]);

    if (*tcp_port <= 1024 || *tcp_port > 65535) {
        fprintf(stderr, "Error: tcp_portnum must be in (1024, 65535]\n");
        exit(1);
    }
    if (*udp_port <= 1024 || *udp_port > 65535) {
        fprintf(stderr, "Error: udp_portnum must be in (1024, 65535]\n");
        exit(1);
    }
    if (*udp_port == *tcp_port) {
        fprintf(stderr, "Error: udp_portnum must be different from tcp_portnum\n");
        exit(1);
    }
    if (*threads <= 0) {
        fprintf(stderr, "Error: threads must be a positive integer\n");
        exit(1);
    }
    if (*queue_size <= 0) {
        fprintf(stderr, "Error: queue_size must be a positive integer\n");
        exit(1);
    }
}

// ---------------------------------------------------------------------------
// Worker threads (consumers)
// ---------------------------------------------------------------------------

// Answers one UDP ping: sends this thread's statistics to the ping's sender.
static void answer_ping(threads_stats stats, struct sockaddr_in *client_addr)
{
    char buf[MAXBUF];
    buf[0] = '\0';
    int len = append_thread_log(buf, stats);
    sendto(udp_fd, buf, len, 0,
           (struct sockaddr *)client_addr, sizeof(struct sockaddr_in));
}

static void* worker_thread(void* arg)
{
    int my_index = (int)(long)arg;   // 0..N-1

    // Each worker owns its statistics; ids are 1..N
    struct Threads_stats stats;
    stats.id        = my_index + 1;
    stats.stat_req  = 0;
    stats.dynm_req  = 0;
    stats.post_req  = 0;
    stats.total_req = 0;

    while (1) {
        pthread_mutex_lock(&pool_mutex);

        // Sleep until there is something for THIS thread to do:
        // a ping registered to it, or a pending TCP job (no busy waiting).
        while (ping_head[my_index] == NULL && pending_count == 0) {
            pthread_cond_wait(&cond_work, &pool_mutex);
        }

        // UDP first: answer a registered ping before taking any TCP job
        if (ping_head[my_index] != NULL) {
            PingNode* node = ping_head[my_index];
            ping_head[my_index] = node->next;
            if (ping_head[my_index] == NULL)
                ping_tail[my_index] = NULL;
            pthread_mutex_unlock(&pool_mutex);

            answer_ping(&stats, &node->client_addr);  // I/O outside the lock
            free(node);
            continue;  // re-check: more pings? then a TCP job?
        }

        // Take the OLDEST pending TCP job (FIFO)
        job_t job = request_queue[queue_head];
        queue_head = (queue_head + 1) % queue_capacity;
        pending_count--;
        active_count++;   // still occupies a queue slot while being processed
        pthread_mutex_unlock(&pool_mutex);
        // NOTE: lock released before processing - we never block other
        // threads while handling our request.

        // Fill the timing stats for this job
        time_stats tm;
        memset(&tm, 0, sizeof(tm));
        tm.task_arrival = job.arrival;               // set by master on accept
        gettimeofday(&tm.task_dispatch, NULL);       // now: lifted from queue

        requestHandle(job.connfd, tm, &stats, slog);
        Close(job.connfd);

        // Free the queue slot and wake the master if it was blocked
        pthread_mutex_lock(&pool_mutex);
        active_count--;
        pthread_cond_signal(&cond_space);
        pthread_mutex_unlock(&pool_mutex);
    }
    return NULL;
}

// ---------------------------------------------------------------------------
// Master thread (producer)
// ---------------------------------------------------------------------------

// Registers a UDP ping to the requested worker thread.
static void register_ping(void)
{
    char buf[64];
    struct sockaddr_in client_addr;
    socklen_t addr_len = sizeof(client_addr);

    int n = recvfrom(udp_fd, buf, sizeof(buf) - 1, 0,
                     (struct sockaddr *)&client_addr, &addr_len);
    if (n < 0) {
        fprintf(stderr, "Error: UDP recvfrom failed\n");
        return;
    }
    buf[n] = '\0';

    int id = atoi(buf);              // ping payload: the target thread id
    if (id < 1 || id > num_threads)  // invalid id: ignore the ping
        return;

    PingNode* node = malloc(sizeof(PingNode));
    if (node == NULL) {
        fprintf(stderr, "Error: malloc failed for ping node\n");
        exit(1);
    }
    node->client_addr = client_addr;
    node->next = NULL;

    pthread_mutex_lock(&pool_mutex);
    if (ping_tail[id - 1] == NULL) {
        ping_head[id - 1] = node;
    } else {
        ping_tail[id - 1]->next = node;
    }
    ping_tail[id - 1] = node;
    // Broadcast: only thread (id-1) can serve this ping, so make sure it
    // wakes up even if another waiting thread is signaled first.
    pthread_cond_broadcast(&cond_work);
    pthread_mutex_unlock(&pool_mutex);
}

// Enqueues an accepted connection; blocks while the queue is full.
static void enqueue_connection(int connfd, struct timeval arrival)
{
    pthread_mutex_lock(&pool_mutex);

    // Queue limit counts pending + currently-processed requests
    while (pending_count + active_count >= queue_capacity) {
        pthread_cond_wait(&cond_space, &pool_mutex);
    }

    int tail = (queue_head + pending_count) % queue_capacity;
    request_queue[tail].connfd  = connfd;
    request_queue[tail].arrival = arrival;
    pending_count++;

    pthread_cond_signal(&cond_work);   // one worker is enough for one job
    pthread_mutex_unlock(&pool_mutex);
}

int main(int argc, char *argv[])
{
    int tcp_port, udp_port, queue_size;
    double debug_sleep;
    int listenfd, connfd, clientlen;
    struct sockaddr_in clientaddr;

    getargs(&tcp_port, &udp_port, &num_threads, &queue_size, &debug_sleep,
            argc, argv);

    // Create the global server log (debug_sleep > 0 enables the debug sleep)
    slog = create_log(debug_sleep);

    // Initialize the bounded request queue and per-thread ping lists
    queue_capacity = queue_size;
    request_queue = malloc(queue_capacity * sizeof(job_t));
    ping_head = calloc(num_threads, sizeof(PingNode*));
    ping_tail = calloc(num_threads, sizeof(PingNode*));
    if (request_queue == NULL || ping_head == NULL || ping_tail == NULL) {
        fprintf(stderr, "Error: failed to allocate server data structures\n");
        exit(1);
    }

    // Create the fixed-size worker thread pool
    pthread_t* workers = malloc(num_threads * sizeof(pthread_t));
    if (workers == NULL) {
        fprintf(stderr, "Error: failed to allocate thread pool\n");
        exit(1);
    }
    for (long i = 0; i < num_threads; i++) {
        if (pthread_create(&workers[i], NULL, worker_thread, (void*)i) != 0) {
            fprintf(stderr, "Error: pthread_create failed\n");
            exit(1);
        }
    }

    // Open both channels
    listenfd = Open_listenfd(tcp_port);
    udp_fd   = UDP_Open(udp_port);

    // Master loop: multiplex UDP pings and TCP connections with select()
    while (1) {
        fd_set read_fds;
        FD_ZERO(&read_fds);
        FD_SET(listenfd, &read_fds);
        FD_SET(udp_fd, &read_fds);
        int maxfd = (listenfd > udp_fd) ? listenfd : udp_fd;

        Select(maxfd + 1, &read_fds, NULL, NULL, NULL);

        // UDP first: register pings before accepting new TCP work
        if (FD_ISSET(udp_fd, &read_fds)) {
            register_ping();
        }

        if (FD_ISSET(listenfd, &read_fds)) {
            clientlen = sizeof(clientaddr);
            connfd = Accept(listenfd, (SA *)&clientaddr, (socklen_t*)&clientlen);

            // Record the arrival time, as first seen by the master thread
            struct timeval arrival;
            gettimeofday(&arrival, NULL);

            enqueue_connection(connfd, arrival);  // may block if queue is full
        }
    }

    // Unreachable in practice (the server runs forever), kept for completeness
    destroy_log(slog);
    free(request_queue);
    free(ping_head);
    free(ping_tail);
    free(workers);
    return 0;
}
