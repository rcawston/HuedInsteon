// SPDX-License-Identifier: Apache-2.0
#include "../common/hued_app.h"
#include "../ti_zstack/overlay/hued_zstack_bridge.h"

#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    char last_line[HUED_LINE_MAX];
    uint8_t applied_endpoint;
    bool applied_on;
    uint8_t applied_level;
    uint8_t published_endpoint;
} test_ctx_t;

static void write_line_cb(const char *line, void *ctx)
{
    test_ctx_t *test_ctx = (test_ctx_t *)ctx;

    snprintf(test_ctx->last_line, sizeof(test_ctx->last_line), "%s", line);
}

static void apply_report_cb(uint8_t endpoint, bool on, uint8_t level, void *ctx)
{
    test_ctx_t *test_ctx = (test_ctx_t *)ctx;

    test_ctx->applied_endpoint = endpoint;
    test_ctx->applied_on = on;
    test_ctx->applied_level = level;
}

static void publish_report_cb(uint8_t endpoint, void *ctx)
{
    test_ctx_t *test_ctx = (test_ctx_t *)ctx;

    test_ctx->published_endpoint = endpoint;
}

static bool joined_cb(void *ctx)
{
    (void)ctx;
    return true;
}

static const char *ieee_cb(void *ctx)
{
    (void)ctx;
    return "00124b0024abcd01";
}

static const char *nwk_cb(void *ctx)
{
    (void)ctx;
    return "0x1234";
}

static hued_app_config_t config_with_endpoints(test_ctx_t *ctx, const uint8_t *endpoints, uint8_t count)
{
    hued_app_config_t config;
    uint8_t i;

    memset(&config, 0, sizeof(config));
    config.write_line = write_line_cb;
    config.apply_report = apply_report_cb;
    config.publish_report = publish_report_cb;
    config.is_joined = joined_cb;
    config.ieee = ieee_cb;
    config.nwk = nwk_cb;
    config.ctx = ctx;
    config.endpoint_count = count;
    config.initial_seq = 40;
    for (i = 0; i < count; i++) {
        config.endpoints[i] = endpoints[i];
    }
    return config;
}

static hued_zstack_bridge_config_t zstack_bridge_config(test_ctx_t *ctx)
{
    hued_zstack_bridge_config_t config;

    memset(&config, 0, sizeof(config));
    config.write_line = write_line_cb;
    config.apply_report = apply_report_cb;
    config.publish_report = publish_report_cb;
    config.is_joined = joined_cb;
    config.ieee = ieee_cb;
    config.nwk = nwk_cb;
    config.ctx = ctx;
    config.initial_seq = 80;
    return config;
}

static void test_single_endpoint_level_command(void)
{
    test_ctx_t ctx;
    hued_app_t app;
    const uint8_t endpoints[] = {1};
    hued_app_config_t config;

    memset(&ctx, 0, sizeof(ctx));
    config = config_with_endpoints(&ctx, endpoints, 1);

    assert(hued_app_init(&app, &config));
    assert(hued_app_on_zcl_move_to_level(&app, 1, 128, 400));
    assert(strstr(ctx.last_line, "\"type\":\"cmd\"") != NULL);
    assert(strstr(ctx.last_line, "\"endpoint\":1") != NULL);
    assert(strstr(ctx.last_line, "\"command\":\"level\"") != NULL);
    assert(strstr(ctx.last_line, "\"level\":128") != NULL);
}

static void test_three_endpoint_command_routes_endpoint_three(void)
{
    test_ctx_t ctx;
    hued_app_t app;
    const uint8_t endpoints[] = {1, 2, 3};
    hued_app_config_t config;

    memset(&ctx, 0, sizeof(ctx));
    config = config_with_endpoints(&ctx, endpoints, 3);

    assert(hued_app_init(&app, &config));
    assert(hued_app_on_zcl_onoff(&app, 3, true));
    assert(strstr(ctx.last_line, "\"endpoint\":3") != NULL);
    assert(strstr(ctx.last_line, "\"command\":\"on\"") != NULL);
}

static void test_serial_report_updates_state_and_requests_publish(void)
{
    test_ctx_t ctx;
    hued_app_t app;
    const uint8_t endpoints[] = {1, 2, 3};
    hued_app_config_t config;

    memset(&ctx, 0, sizeof(ctx));
    config = config_with_endpoints(&ctx, endpoints, 3);

    assert(hued_app_init(&app, &config));
    assert(hued_app_on_serial_line(
        &app,
        "{\"dir\":\"pi->zb\",\"type\":\"report\",\"endpoint\":2,\"on\":true,\"level\":180,"
        "\"transition_ms\":0,\"seq\":991}\n"
    ));
    assert(ctx.applied_endpoint == 2);
    assert(ctx.applied_on == true);
    assert(ctx.applied_level == 180);
    assert(ctx.published_endpoint == 2);
}

static void test_health_query_response(void)
{
    test_ctx_t ctx;
    hued_app_t app;
    const uint8_t endpoints[] = {1, 2, 3};
    hued_app_config_t config;

    memset(&ctx, 0, sizeof(ctx));
    config = config_with_endpoints(&ctx, endpoints, 3);

    assert(hued_app_init(&app, &config));
    assert(hued_app_on_serial_line(&app, "{\"dir\":\"pi->zb\",\"type\":\"health?\",\"seq\":77}\n"));
    assert(strstr(ctx.last_line, "\"type\":\"health\"") != NULL);
    assert(strstr(ctx.last_line, "\"joined\":true") != NULL);
    assert(strstr(ctx.last_line, "\"endpoints\":3") != NULL);
    assert(strstr(ctx.last_line, "\"seq\":77") != NULL);
}

static void test_zstack_bridge_maps_zcl_commands(void)
{
    test_ctx_t ctx;
    hued_zstack_bridge_t bridge;
    hued_zstack_bridge_config_t config;
    const hued_light_state_t *state;

    memset(&ctx, 0, sizeof(ctx));
    config = zstack_bridge_config(&ctx);

    assert(hued_zstack_bridge_init(&bridge, &config));
    assert(hued_zstack_bridge_on_off(&bridge, 2, HUED_ZCL_ON_OFF_ON));
    assert(strstr(ctx.last_line, "\"endpoint\":2") != NULL);
    assert(strstr(ctx.last_line, "\"command\":\"on\"") != NULL);

    assert(hued_zstack_bridge_move_to_level(&bridge, 2, 122, 7, true));
    assert(strstr(ctx.last_line, "\"command\":\"level\"") != NULL);
    assert(strstr(ctx.last_line, "\"level\":122") != NULL);
    assert(strstr(ctx.last_line, "\"transition_ms\":700") != NULL);

    state = hued_zstack_bridge_state(&bridge, 2);
    assert(state != NULL);
    assert(state->on == true);
    assert(state->level == 122);
}

int main(void)
{
    test_single_endpoint_level_command();
    test_three_endpoint_command_routes_endpoint_three();
    test_serial_report_updates_state_and_requests_publish();
    test_health_query_response();
    test_zstack_bridge_maps_zcl_commands();
    return 0;
}
