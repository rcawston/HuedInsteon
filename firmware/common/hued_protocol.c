// SPDX-License-Identifier: Apache-2.0
#include "hued_protocol.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *skip_ws(const char *cursor)
{
    while (*cursor == ' ' || *cursor == '\t' || *cursor == '\r' || *cursor == '\n') {
        cursor++;
    }
    return cursor;
}

static const char *find_json_value(const char *line, const char *key)
{
    char pattern[32];
    const char *cursor;
    const char *colon;

    if (snprintf(pattern, sizeof(pattern), "\"%s\"", key) >= (int)sizeof(pattern)) {
        return NULL;
    }

    cursor = strstr(line, pattern);
    if (cursor == NULL) {
        return NULL;
    }

    colon = strchr(cursor + strlen(pattern), ':');
    if (colon == NULL) {
        return NULL;
    }

    return skip_ws(colon + 1);
}

static bool json_get_string(const char *line, const char *key, char *out, size_t out_len)
{
    const char *value = find_json_value(line, key);
    size_t i = 0;

    if (value == NULL || *value != '"' || out_len == 0) {
        return false;
    }

    value++;
    while (*value != '\0' && *value != '"' && i + 1 < out_len) {
        out[i++] = *value++;
    }
    out[i] = '\0';

    return *value == '"';
}

static bool json_get_u32(const char *line, const char *key, uint32_t *out)
{
    const char *value = find_json_value(line, key);
    char *end = NULL;
    unsigned long parsed;

    if (value == NULL) {
        return false;
    }

    parsed = strtoul(value, &end, 10);
    if (end == value) {
        return false;
    }

    *out = (uint32_t)parsed;
    return true;
}

static bool json_get_bool(const char *line, const char *key, bool *out)
{
    const char *value = find_json_value(line, key);

    if (value == NULL) {
        return false;
    }
    if (strncmp(value, "true", 4) == 0 || *value == '1') {
        *out = true;
        return true;
    }
    if (strncmp(value, "false", 5) == 0 || *value == '0') {
        *out = false;
        return true;
    }
    return false;
}

static bool json_type_is(const char *line, const char *expected)
{
    char type[24];

    if (!json_get_string(line, "type", type, sizeof(type))) {
        return false;
    }
    return strcmp(type, expected) == 0;
}

int hued_encode_cmd_onoff(
    char *out,
    size_t out_len,
    uint8_t endpoint,
    bool on,
    uint32_t seq
)
{
    return snprintf(
        out,
        out_len,
        "{\"dir\":\"zb->pi\",\"type\":\"cmd\",\"endpoint\":%u,\"command\":\"%s\",\"seq\":%lu}\n",
        endpoint,
        on ? "on" : "off",
        (unsigned long)seq
    );
}

int hued_encode_cmd_toggle(char *out, size_t out_len, uint8_t endpoint, uint32_t seq)
{
    return snprintf(
        out,
        out_len,
        "{\"dir\":\"zb->pi\",\"type\":\"cmd\",\"endpoint\":%u,\"command\":\"toggle\",\"seq\":%lu}\n",
        endpoint,
        (unsigned long)seq
    );
}

int hued_encode_cmd_level(
    char *out,
    size_t out_len,
    uint8_t endpoint,
    uint8_t level,
    uint32_t transition_ms,
    uint32_t seq
)
{
    return snprintf(
        out,
        out_len,
        "{\"dir\":\"zb->pi\",\"type\":\"cmd\",\"endpoint\":%u,\"command\":\"level\","
        "\"level\":%u,\"transition_ms\":%lu,\"seq\":%lu}\n",
        endpoint,
        level,
        (unsigned long)transition_ms,
        (unsigned long)seq
    );
}

int hued_encode_health(
    char *out,
    size_t out_len,
    bool joined,
    uint8_t endpoint_count,
    const char *ieee,
    const char *nwk,
    bool has_seq,
    uint32_t seq
)
{
    const char *safe_ieee = ieee == NULL ? "" : ieee;
    const char *safe_nwk = nwk == NULL ? "" : nwk;

    if (has_seq) {
        return snprintf(
            out,
            out_len,
            "{\"dir\":\"zb->pi\",\"type\":\"health\",\"joined\":%s,\"endpoints\":%u,"
            "\"ieee\":\"%s\",\"nwk\":\"%s\",\"seq\":%lu}\n",
            joined ? "true" : "false",
            endpoint_count,
            safe_ieee,
            safe_nwk,
            (unsigned long)seq
        );
    }

    return snprintf(
        out,
        out_len,
        "{\"dir\":\"zb->pi\",\"type\":\"health\",\"joined\":%s,\"endpoints\":%u,"
        "\"ieee\":\"%s\",\"nwk\":\"%s\"}\n",
        joined ? "true" : "false",
        endpoint_count,
        safe_ieee,
        safe_nwk
    );
}

bool hued_decode_pi_line(const char *line, hued_serial_message_t *message)
{
    uint32_t parsed;

    if (line == NULL || message == NULL) {
        return false;
    }

    memset(message, 0, sizeof(*message));

    if (json_type_is(line, "health?")) {
        message->type = HUED_SERIAL_HEALTH_QUERY;
        if (json_get_u32(line, "seq", &parsed)) {
            message->data.health_query.has_seq = true;
            message->data.health_query.seq = parsed;
        }
        return true;
    }

    if (!json_type_is(line, "report")) {
        return false;
    }

    message->type = HUED_SERIAL_REPORT;

    if (!json_get_u32(line, "endpoint", &parsed) || parsed > UINT8_MAX) {
        return false;
    }
    message->data.report.endpoint = (uint8_t)parsed;

    if (!json_get_bool(line, "on", &message->data.report.on)) {
        return false;
    }

    if (!json_get_u32(line, "level", &parsed) || parsed < 1 || parsed > 254) {
        return false;
    }
    message->data.report.level = (uint8_t)parsed;

    if (json_get_u32(line, "transition_ms", &parsed)) {
        message->data.report.transition_ms = parsed;
    }

    if (json_get_u32(line, "seq", &parsed)) {
        message->data.report.has_seq = true;
        message->data.report.seq = parsed;
    }

    return true;
}

