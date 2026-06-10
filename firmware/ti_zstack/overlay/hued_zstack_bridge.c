// SPDX-License-Identifier: Apache-2.0
#include "hued_zstack_bridge.h"

#include "hued_variant.h"

#include <stddef.h>
#include <string.h>

static int endpoint_index(const hued_zstack_bridge_t *bridge, uint8_t endpoint)
{
    uint8_t i;

    if (bridge == NULL) {
        return -1;
    }

    for (i = 0; i < bridge->app.config.endpoint_count; i++) {
        if (bridge->app.config.endpoints[i] == endpoint) {
            return i;
        }
    }
    return -1;
}

static uint32_t transition_ds_to_ms(uint16_t transition_time_ds)
{
    if (transition_time_ds == HUED_ZCL_TRANSITION_DEFAULT) {
        return 0;
    }
    return (uint32_t)transition_time_ds * 100U;
}

bool hued_zstack_bridge_init(
    hued_zstack_bridge_t *bridge,
    const hued_zstack_bridge_config_t *config
)
{
    hued_app_config_t app_config;

    if (bridge == NULL || config == NULL) {
        return false;
    }

    memset(&app_config, 0, sizeof(app_config));
    app_config.write_line = config->write_line;
    app_config.apply_report = config->apply_report;
    app_config.publish_report = config->publish_report;
    app_config.is_joined = config->is_joined;
    app_config.ieee = config->ieee;
    app_config.nwk = config->nwk;
    app_config.ctx = config->ctx;
    app_config.endpoint_count = HUED_VARIANT_ENDPOINT_COUNT;
    app_config.initial_seq = config->initial_seq;
    memcpy(app_config.endpoints, HUED_VARIANT_ENDPOINTS, HUED_VARIANT_ENDPOINT_COUNT);

    return hued_app_init(&bridge->app, &app_config);
}

bool hued_zstack_bridge_on_off(
    hued_zstack_bridge_t *bridge,
    uint8_t endpoint,
    uint8_t command_id
)
{
    if (bridge == NULL) {
        return false;
    }

    switch (command_id) {
    case HUED_ZCL_ON_OFF_OFF:
        return hued_app_on_zcl_onoff(&bridge->app, endpoint, false);
    case HUED_ZCL_ON_OFF_ON:
        return hued_app_on_zcl_onoff(&bridge->app, endpoint, true);
    case HUED_ZCL_ON_OFF_TOGGLE:
        return hued_app_on_zcl_toggle(&bridge->app, endpoint);
    default:
        return false;
    }
}

bool hued_zstack_bridge_move_to_level(
    hued_zstack_bridge_t *bridge,
    uint8_t endpoint,
    uint8_t level,
    uint16_t transition_time_ds,
    bool with_on_off
)
{
    (void)with_on_off;

    if (bridge == NULL) {
        return false;
    }

    return hued_app_on_zcl_move_to_level(
        &bridge->app,
        endpoint,
        level,
        transition_ds_to_ms(transition_time_ds)
    );
}

bool hued_zstack_bridge_serial_line(hued_zstack_bridge_t *bridge, const char *line)
{
    if (bridge == NULL) {
        return false;
    }
    return hued_app_on_serial_line(&bridge->app, line);
}

const hued_light_state_t *hued_zstack_bridge_state(
    const hued_zstack_bridge_t *bridge,
    uint8_t endpoint
)
{
    int index = endpoint_index(bridge, endpoint);

    if (index < 0) {
        return NULL;
    }
    return &bridge->app.states[index];
}

