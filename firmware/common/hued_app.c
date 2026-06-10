// SPDX-License-Identifier: Apache-2.0
#include "hued_app.h"

#include <string.h>

static int endpoint_index(const hued_app_t *app, uint8_t endpoint)
{
    uint8_t i;

    for (i = 0; i < app->config.endpoint_count; i++) {
        if (app->config.endpoints[i] == endpoint) {
            return i;
        }
    }
    return -1;
}

static uint32_t next_seq(hued_app_t *app)
{
    app->seq++;
    if (app->seq == 0) {
        app->seq = 1;
    }
    return app->seq;
}

static bool write_line(hued_app_t *app, const char *line)
{
    if (app->config.write_line == NULL) {
        return false;
    }
    app->config.write_line(line, app->config.ctx);
    return true;
}

bool hued_app_init(hued_app_t *app, const hued_app_config_t *config)
{
    uint8_t i;

    if (app == NULL || config == NULL || config->endpoint_count == 0 ||
        config->endpoint_count > HUED_MAX_ENDPOINTS) {
        return false;
    }

    memset(app, 0, sizeof(*app));
    app->config = *config;
    app->seq = config->initial_seq;

    for (i = 0; i < app->config.endpoint_count; i++) {
        if (app->config.endpoints[i] == 0) {
            return false;
        }
        app->states[i].on = false;
        app->states[i].level = 254;
    }
    return true;
}

bool hued_app_set_initial_state(hued_app_t *app, uint8_t endpoint, bool on, uint8_t level)
{
    int index;

    if (app == NULL || level < 1 || level > 254) {
        return false;
    }

    index = endpoint_index(app, endpoint);
    if (index < 0) {
        return false;
    }

    app->states[index].on = on;
    app->states[index].level = level;
    return true;
}

bool hued_app_on_zcl_onoff(hued_app_t *app, uint8_t endpoint, bool on)
{
    char line[HUED_LINE_MAX];
    int index;

    if (app == NULL) {
        return false;
    }

    index = endpoint_index(app, endpoint);
    if (index < 0) {
        return false;
    }

    app->states[index].on = on;
    if (hued_encode_cmd_onoff(line, sizeof(line), endpoint, on, next_seq(app)) >= (int)sizeof(line)) {
        return false;
    }
    return write_line(app, line);
}

bool hued_app_on_zcl_toggle(hued_app_t *app, uint8_t endpoint)
{
    char line[HUED_LINE_MAX];
    int index;

    if (app == NULL) {
        return false;
    }

    index = endpoint_index(app, endpoint);
    if (index < 0) {
        return false;
    }

    app->states[index].on = !app->states[index].on;
    if (hued_encode_cmd_toggle(line, sizeof(line), endpoint, next_seq(app)) >= (int)sizeof(line)) {
        return false;
    }
    return write_line(app, line);
}

bool hued_app_on_zcl_move_to_level(
    hued_app_t *app,
    uint8_t endpoint,
    uint8_t level,
    uint32_t transition_ms
)
{
    char line[HUED_LINE_MAX];
    int index;

    if (app == NULL || level < 1 || level > 254) {
        return false;
    }

    index = endpoint_index(app, endpoint);
    if (index < 0) {
        return false;
    }

    app->states[index].on = true;
    app->states[index].level = level;
    if (hued_encode_cmd_level(line, sizeof(line), endpoint, level, transition_ms, next_seq(app)) >=
        (int)sizeof(line)) {
        return false;
    }
    return write_line(app, line);
}

bool hued_app_on_serial_line(hued_app_t *app, const char *line)
{
    char out[HUED_LINE_MAX];
    hued_serial_message_t message;
    bool joined = false;
    const char *ieee = "";
    const char *nwk = "";
    int index;

    if (app == NULL || !hued_decode_pi_line(line, &message)) {
        return false;
    }

    if (message.type == HUED_SERIAL_HEALTH_QUERY) {
        if (app->config.is_joined != NULL) {
            joined = app->config.is_joined(app->config.ctx);
        }
        if (app->config.ieee != NULL) {
            ieee = app->config.ieee(app->config.ctx);
        }
        if (app->config.nwk != NULL) {
            nwk = app->config.nwk(app->config.ctx);
        }
        if (hued_encode_health(
                out,
                sizeof(out),
                joined,
                app->config.endpoint_count,
                ieee,
                nwk,
                message.data.health_query.has_seq,
                message.data.health_query.seq
            ) >= (int)sizeof(out)) {
            return false;
        }
        return write_line(app, out);
    }

    if (message.type != HUED_SERIAL_REPORT) {
        return false;
    }

    index = endpoint_index(app, message.data.report.endpoint);
    if (index < 0) {
        return false;
    }

    app->states[index].on = message.data.report.on;
    app->states[index].level = message.data.report.level;

    if (app->config.apply_report != NULL) {
        app->config.apply_report(
            message.data.report.endpoint,
            message.data.report.on,
            message.data.report.level,
            app->config.ctx
        );
    }
    if (app->config.publish_report != NULL) {
        app->config.publish_report(message.data.report.endpoint, app->config.ctx);
    }

    return true;
}

