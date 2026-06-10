// SPDX-License-Identifier: Apache-2.0
#ifndef HUED_APP_H
#define HUED_APP_H

#include "hued_protocol.h"

#include <stdbool.h>
#include <stdint.h>

#ifndef HUED_MAX_ENDPOINTS
#define HUED_MAX_ENDPOINTS 3
#endif

typedef struct {
    bool on;
    uint8_t level;
} hued_light_state_t;

typedef struct {
    void (*write_line)(const char *line, void *ctx);
    void (*apply_report)(uint8_t endpoint, bool on, uint8_t level, void *ctx);
    void (*publish_report)(uint8_t endpoint, void *ctx);
    bool (*is_joined)(void *ctx);
    const char *(*ieee)(void *ctx);
    const char *(*nwk)(void *ctx);
    void *ctx;
    uint8_t endpoints[HUED_MAX_ENDPOINTS];
    uint8_t endpoint_count;
    uint32_t initial_seq;
} hued_app_config_t;

typedef struct {
    hued_app_config_t config;
    hued_light_state_t states[HUED_MAX_ENDPOINTS];
    uint32_t seq;
} hued_app_t;

bool hued_app_init(hued_app_t *app, const hued_app_config_t *config);
bool hued_app_set_initial_state(hued_app_t *app, uint8_t endpoint, bool on, uint8_t level);
bool hued_app_on_zcl_onoff(hued_app_t *app, uint8_t endpoint, bool on);
bool hued_app_on_zcl_toggle(hued_app_t *app, uint8_t endpoint);
bool hued_app_on_zcl_move_to_level(
    hued_app_t *app,
    uint8_t endpoint,
    uint8_t level,
    uint32_t transition_ms
);
bool hued_app_on_serial_line(hued_app_t *app, const char *line);

#endif

