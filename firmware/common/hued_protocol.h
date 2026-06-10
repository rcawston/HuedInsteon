// SPDX-License-Identifier: Apache-2.0
#ifndef HUED_PROTOCOL_H
#define HUED_PROTOCOL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define HUED_LINE_MAX 192

typedef enum {
    HUED_SERIAL_NONE = 0,
    HUED_SERIAL_REPORT,
    HUED_SERIAL_HEALTH_QUERY
} hued_serial_type_t;

typedef struct {
    uint8_t endpoint;
    bool on;
    uint8_t level;
    uint32_t transition_ms;
    bool has_seq;
    uint32_t seq;
} hued_serial_report_t;

typedef struct {
    hued_serial_type_t type;
    union {
        hued_serial_report_t report;
        struct {
            bool has_seq;
            uint32_t seq;
        } health_query;
    } data;
} hued_serial_message_t;

int hued_encode_cmd_onoff(
    char *out,
    size_t out_len,
    uint8_t endpoint,
    bool on,
    uint32_t seq
);

int hued_encode_cmd_toggle(char *out, size_t out_len, uint8_t endpoint, uint32_t seq);

int hued_encode_cmd_level(
    char *out,
    size_t out_len,
    uint8_t endpoint,
    uint8_t level,
    uint32_t transition_ms,
    uint32_t seq
);

int hued_encode_health(
    char *out,
    size_t out_len,
    bool joined,
    uint8_t endpoint_count,
    const char *ieee,
    const char *nwk,
    bool has_seq,
    uint32_t seq
);

bool hued_decode_pi_line(const char *line, hued_serial_message_t *message);

#endif

