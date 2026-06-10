// SPDX-License-Identifier: Apache-2.0
#ifndef HUED_ZSTACK_BRIDGE_H
#define HUED_ZSTACK_BRIDGE_H

#include "hued_app.h"

#include <stdbool.h>
#include <stdint.h>

#define HUED_ZCL_ON_OFF_OFF 0x00
#define HUED_ZCL_ON_OFF_ON 0x01
#define HUED_ZCL_ON_OFF_TOGGLE 0x02
#define HUED_ZCL_TRANSITION_DEFAULT 0xFFFF

typedef struct {
    void (*write_line)(const char *line, void *ctx);
    void (*apply_report)(uint8_t endpoint, bool on, uint8_t level, void *ctx);
    void (*publish_report)(uint8_t endpoint, void *ctx);
    bool (*is_joined)(void *ctx);
    const char *(*ieee)(void *ctx);
    const char *(*nwk)(void *ctx);
    void *ctx;
    uint32_t initial_seq;
} hued_zstack_bridge_config_t;

typedef struct {
    hued_app_t app;
} hued_zstack_bridge_t;

bool hued_zstack_bridge_init(
    hued_zstack_bridge_t *bridge,
    const hued_zstack_bridge_config_t *config
);
bool hued_zstack_bridge_on_off(
    hued_zstack_bridge_t *bridge,
    uint8_t endpoint,
    uint8_t command_id
);
bool hued_zstack_bridge_move_to_level(
    hued_zstack_bridge_t *bridge,
    uint8_t endpoint,
    uint8_t level,
    uint16_t transition_time_ds,
    bool with_on_off
);
bool hued_zstack_bridge_serial_line(hued_zstack_bridge_t *bridge, const char *line);
const hued_light_state_t *hued_zstack_bridge_state(
    const hued_zstack_bridge_t *bridge,
    uint8_t endpoint
);

#endif

