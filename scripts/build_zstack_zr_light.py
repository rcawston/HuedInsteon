#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build TI's stock Z-Stack zr_light example from its projectspec.

This is intentionally a thin command-line harness around TI's SDK metadata. It
does not rewrite installed TI SDK sources; it parses the projectspec, runs
SysConfig, optionally creates patched build-local source copies, compiles the
listed C files, and links the result.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / ".vendor/ti/simplelink_cc13xx_cc26xx_sdk_8_32_00_07"
SYSCONFIG = ROOT / ".vendor/ti/sysconfig_1.27.1/sysconfig_cli.sh"
TICLANG_ROOT = (
    ROOT
    / ".vendor/ti/ti-cgt-armllvm_5.1.1.LTS/ti-cgt-armllvm_5.1.1.LTS"
)
PROJECTSPEC = (
    SDK
    / "examples/rtos/CC1352P_2_LAUNCHXL/zstack/zr_light/tirtos7/ticlang/"
    / "zr_light_CC1352P_2_LAUNCHXL_tirtos7_ticlang.projectspec"
)
SYSCFG = (
    SDK
    / "examples/rtos/CC1352P_2_LAUNCHXL/zstack/zr_light/tirtos7/zr_light.syscfg"
)
SAMPLE_LIGHT_C = SDK / "source/ti/zstack/apps/light/zcl_samplelight.c"
SAMPLE_LIGHT_H = SDK / "source/ti/zstack/apps/light/zcl_samplelight.h"
SAMPLE_LIGHT_DATA_C = SDK / "source/ti/zstack/apps/light/zcl_samplelight_data.c"
ZD_OBJECT_C = SDK / "source/ti/zstack/stack/zdo/zd_object.c"
ZD_APP_C = SDK / "source/ti/zstack/stack/zdo/zd_app.c"
ZD_PROFILE_C = SDK / "source/ti/zstack/stack/zdo/zd_profile.c"
ZMAC_CB_C = SDK / "source/ti/zstack/zmac/f8w/zmac_cb.c"


def describe(argv: list[str]) -> str:
    if len(argv) > 12:
        return " ".join(shlex.quote(str(a)) for a in argv[:8]) + f" ... ({len(argv)} args)"
    return " ".join(shlex.quote(str(a)) for a in argv)


def run(argv: list[str], *, cwd: Path | None = None) -> None:
    print("+", describe(argv))
    proc = subprocess.run(
        [str(a) for a in argv],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if proc.stdout:
        print(proc.stdout)
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, proc.args)


def expand_vars(text: str, build_dir: Path, project_root: Path) -> str:
    replacements = {
        "${PROJECT_ROOT}": str(project_root),
        "${ConfigName}": "default",
        "${CG_TOOL_ROOT}": str(TICLANG_ROOT),
        "${COM_TI_SIMPLELINK_CC13XX_CC26XX_SDK_INSTALL_DIR}": str(SDK),
        "${PROJECT_BUILD_DIR}": str(build_dir),
        "${ProjName}": "zr_light_CC1352P_2_LAUNCHXL_tirtos7_ticlang",
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text


def parse_projectspec() -> tuple[list[str], list[str], list[Path], list[Path]]:
    root = ET.parse(PROJECTSPEC).getroot()
    project = root.find(".//project")
    if project is None:
        raise RuntimeError(f"no <project> in {PROJECTSPEC}")

    compiler_options = shlex.split(project.attrib["compilerBuildOptions"])
    linker_options = shlex.split(project.attrib["linkerBuildOptions"])

    source_files: list[Path] = []
    linker_scripts: list[Path] = []
    for file_node in root.findall(".//file"):
        if file_node.attrib.get("excludeFromBuild", "false") != "false":
            continue
        raw = file_node.attrib.get("path", "")
        if not raw:
            continue
        path = Path(raw.replace("${COM_TI_SIMPLELINK_CC13XX_CC26XX_SDK_INSTALL_DIR}", str(SDK)))
        if raw.startswith("../../"):
            path = (PROJECTSPEC.parent / raw).resolve()
        if path.suffix == ".c":
            source_files.append(path)
        elif path.suffix == ".cmd":
            linker_scripts.append(path)

    return compiler_options, linker_options, source_files, linker_scripts


def replace_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise RuntimeError(f"expected syscfg fragment not found: {old[:80]!r}")
    return text.replace(old, new, 1)


def parse_eui64(value: str) -> bytes:
    normalized = value.replace(":", "").replace("-", "").strip()
    if len(normalized) != 16:
        raise argparse.ArgumentTypeError("EUI64 must be 16 hex digits")
    try:
        return bytes.fromhex(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("EUI64 must contain only hex digits") from exc


def write_sonoff_syscfg(build_dir: Path) -> Path:
    text = SYSCFG.read_text()
    text = replace_once(text, "var NVS2     = NVS.addInstance();\n", "")
    text = replace_once(text, "/* Left Button */\nButton1", "/* Boot / BSL Button */\nButton1")
    text = replace_once(
        text,
        """
/* External NVS */
NVS2.$name                          = "CONFIG_NVSEXTERNAL";
NVS2.nvsType                        = "External";
NVS2.$hardware                      = system.deviceData.board.components.MX25R8035F;
NVS2.externalFlash.regionBase       = 0;
NVS2.externalFlash.regionSize       = 0x256000;
NVS2.externalFlash.sectorSize       = 0x1000;
NVS2.externalFlash.verifyBufferSize = 64;


/* External NVS SPI instance */
var NVSSPI25XDevice1 = NVS2.externalFlash.spiFlashDevice;
var SPI1                   = NVSSPI25XDevice1.sharedSpiInstance;
SPI1.$name                 = "CONFIG_SPI_0";
SPI1.sclkPinInstance.$name = "CONFIG_PIN_SPI_SCLK";
SPI1.misoPinInstance.$name = "CONFIG_PIN_SPI_MISO";
SPI1.mosiPinInstance.$name = "CONFIG_PIN_SPI_MOSI";
""",
        "",
    )
    text = replace_once(
        text,
        """/* UART Display */
/* If a xds110Uart component exists, assign it to the Display_UART instance */
if (system.deviceData.board && system.deviceData.board.components.XDS110UART) {
    Display_UART.$hardware = system.deviceData.board.components.XDS110UART;
}
""",
        """/* UART Display */
Display_UART.$hardware = system.deviceData.board.components.XDS110UART;
""",
    )

    patched_syscfg = build_dir / "project/zr_light.sonoff_zbdongle_p.syscfg"
    patched_syscfg.parent.mkdir(parents=True, exist_ok=True)
    patched_syscfg.write_text(text)
    return patched_syscfg


def write_instrumented_sample_light(
    build_dir: Path,
    *,
    three_endpoints: bool,
    endpoint_specific_state: bool = False,
    diag_uart: bool = False,
    virtual_eui: str | None = None,
    virtual_child_count: int = 3,
) -> Path:
    text = SAMPLE_LIGHT_C.read_text()
    if virtual_eui:
        eui_bytes = parse_eui64(virtual_eui)
        eui_initializer = ", ".join(f"0x{byte:02x}" for byte in reversed(eui_bytes))
        text = replace_once(
            text,
            '#include "zstackapi.h"\n',
            '#include "zstackapi.h"\n#include "zmac.h"\n',
        )
        text = replace_once(
            text,
            "static void zclSampleLight_UpdateLedState(void);\n",
            (
                "static void zclSampleLight_UpdateLedState(void);\n"
                "static void huedInsteon_SetVirtualEui(void);\n"
            ),
        )
        text = replace_once(
            text,
            "static uint8_t discoveryInprogress = 0x00;\n#define DISCOVERY_IN_PROGRESS_TIMEOUT   3000\n",
            f"""static uint8_t discoveryInprogress = 0x00;
#define DISCOVERY_IN_PROGRESS_TIMEOUT   3000

static void huedInsteon_SetVirtualEui(void)
{{
#define HUEDINSTEON_HAS_VIRTUAL_EUI 1
  static uint8_t virtualEui[Z_EXTADDR_LEN] = {{{eui_initializer}}};
  uint8_t activeEui[Z_EXTADDR_LEN] = {{0}};
  uint8_t status;

  status = ZMacSetReq(ZMacExtAddr, virtualEui);
  ZMacGetReq(ZMacExtAddr, activeEui);
#ifdef HUEDINSTEON_DIAG
  huedInsteonDiag_Log("EUI set status=%u active=%02x%02x%02x%02x%02x%02x%02x%02x",
                      (unsigned)status,
                      (unsigned)activeEui[7],
                      (unsigned)activeEui[6],
                      (unsigned)activeEui[5],
                      (unsigned)activeEui[4],
                      (unsigned)activeEui[3],
                      (unsigned)activeEui[2],
                      (unsigned)activeEui[1],
                      (unsigned)activeEui[0]);
#endif
}}
""",
        )
        text = replace_once(
            text,
            "  // Call BDB initialization. Should be called once from application at startup to restore\n"
            "  // previous network configuration, if applicable.\n",
            "#ifdef HUEDINSTEON_DIAG\n"
            '  huedInsteonDiag_Log("EUI requested=' + virtual_eui.upper() + '");\n'
            "#endif\n"
            "  huedInsteon_SetVirtualEui();\n\n"
            "  // Call BDB initialization. Should be called once from application at startup to restore\n"
            "  // previous network configuration, if applicable.\n",
        )
    if diag_uart:
        text = replace_once(
            text,
            '#include "ti_zstack_config.h"\n',
            (
                '#include "ti_zstack_config.h"\n'
                "#ifdef HUEDINSTEON_DIAG\n"
                "#include <ti/drivers/UART2.h>\n"
                "#include <stdio.h>\n"
                "#include <stdarg.h>\n"
                '#include "addr_mgr.h"\n'
                '#include "aps.h"\n'
                '#include "aps_mede.h"\n'
                '#include "assoc_list.h"\n'
                '#include "bdb.h"\n'
                '#include "nwk.h"\n'
                '#include "nwk_globals.h"\n'
                '#include "osal_nv.h"\n'
                '#include "ssp.h"\n'
                '#include "zcomdef.h"\n'
                '#include "zd_sec_mgr.h"\n'
                '#include "zd_profile.h"\n'
                '#include "zmac.h"\n'
                "#endif\n"
            ),
        )
        text = replace_once(
            text,
            "#if defined(USE_DMM) && defined(BLE_START) || !defined(CUI_DISABLE)\n"
            "static uint16_t zclSampleLight_BdbCommissioningModes;\n"
            "#endif // defined(USE_DMM) && defined(BLE_START) || !defined(CUI_DISABLE)\n",
            "#if defined(USE_DMM) && defined(BLE_START) || !defined(CUI_DISABLE) || defined(HUEDINSTEON_DIAG)\n"
            "static uint16_t zclSampleLight_BdbCommissioningModes;\n"
            "#endif // defined(USE_DMM) && defined(BLE_START) || !defined(CUI_DISABLE) || defined(HUEDINSTEON_DIAG)\n",
        )
        text = replace_once(
            text,
            "#if !defined(CUI_DISABLE) || defined(USE_DMM) && defined(BLE_START)\n"
            "  // set up default application BDB commissioning modes based on build type\n",
            "#if !defined(CUI_DISABLE) || defined(USE_DMM) && defined(BLE_START) || defined(HUEDINSTEON_DIAG)\n"
            "  // set up default application BDB commissioning modes based on build type\n",
        )
        text = replace_once(
            text,
            "#endif // !defined(CUI_DISABLE) || defined(USE_DMM) && defined(BLE_START)\n\n"
            "#ifndef CUI_DISABLE\n",
            "#endif // !defined(CUI_DISABLE) || defined(USE_DMM) && defined(BLE_START) || defined(HUEDINSTEON_DIAG)\n\n"
            "#ifdef HUEDINSTEON_DIAG\n"
            "  huedInsteonDiag_Init();\n"
            "#endif\n\n"
            "#ifndef CUI_DISABLE\n",
        )
        text = replace_once(
            text,
            "static void zclSampleLight_UpdateLedState(void);\n",
            (
                "static void zclSampleLight_UpdateLedState(void);\n"
                "#ifdef HUEDINSTEON_DIAG\n"
                "static void huedInsteonDiag_Init(void);\n"
                "static void huedInsteonDiag_Process(void);\n"
                "static void huedInsteonDiag_LogState(const char *reason);\n"
                "static void huedInsteonDiag_Log(const char *fmt, ...);\n"
                "void huedInsteonDiag_ZdoTrace(const char *tag, uint16_t aoi, uint16_t src, uint8_t endpoint);\n"
                "void huedInsteonDiag_ZdoInTrace(uint16_t cluster, uint16_t src, uint16_t macDst, uint16_t macSrc, uint8_t sec, uint8_t len);\n"
                "void huedInsteonDiag_SecTrace(const char *tag, uint16_t src, uint16_t a, uint16_t b, const uint8_t *eui);\n"
                "void huedInsteonDiag_MacTrace(uint8_t event, uint8_t status, uint16_t shortAddr);\n"
                "static void huedInsteonDiag_AnnounceVirtualChild(uint8_t childIndex);\n"
                "static void huedInsteonDiag_ForwardVirtualChildJoin(uint8_t childIndex);\n"
                "static void huedInsteonDiag_NlmeVirtualChildJoin(uint8_t childIndex);\n"
                "static void huedInsteonDiag_SecMgrVirtualChildJoin(uint8_t childIndex);\n"
                "static void huedInsteonDiag_MacVirtualChildAssoc(uint8_t childIndex);\n"
                "static void huedInsteonDiag_OverAirMacVirtualChildAssoc(uint8_t childIndex);\n"
                "static void huedInsteonDiag_RestoreParentIdentity(void);\n"
                "static void huedInsteonDiag_RequestVirtualChildTcLinkKey(uint8_t childIndex);\n"
                "static void huedInsteonDiag_RequestVirtualChildTcLinkKeyWithDefault(uint8_t childIndex);\n"
                "static void huedInsteonDiag_AdmitVirtualChild(uint8_t childIndex);\n"
                "static void huedInsteonDiag_AnnounceVirtualParentShort(uint8_t childIndex);\n"
                "#endif\n"
            ),
        )
        text = replace_once(
            text,
            "static uint8_t discoveryInprogress = 0x00;\n#define DISCOVERY_IN_PROGRESS_TIMEOUT   3000\n",
            """static uint8_t discoveryInprogress = 0x00;
#define DISCOVERY_IN_PROGRESS_TIMEOUT   3000

#ifdef HUEDINSTEON_DIAG
#define HUEDINSTEON_DIAG_EVT 0x80000000UL
#define HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT __HUEDINSTEON_VIRTUAL_CHILD_COUNT__
#define HUEDINSTEON_DIAG_VIRTUAL_CHILD_STORAGE_COUNT __HUEDINSTEON_VIRTUAL_CHILD_STORAGE_COUNT__
static UART2_Handle huedInsteonDiag_Uart;
static char huedInsteonDiag_RxByte;
static char huedInsteonDiag_Line[32];
static char huedInsteonDiag_Command[32];
static uint8_t huedInsteonDiag_LineLen;
static volatile bool huedInsteonDiag_CommandReady;
static uint16_t huedInsteonDiag_ParentNwkBeforeMacAssoc = INVALID_NODE_ADDR;

static void huedInsteon_SetVirtualEui(void);
static void huedInsteonDiag_ArmRead(void);
static void huedInsteonDiag_Log(const char *fmt, ...);

static const uint16_t huedInsteonDiag_VirtualChildNwk[HUEDINSTEON_DIAG_VIRTUAL_CHILD_STORAGE_COUNT] =
{
  __HUEDINSTEON_VIRTUAL_CHILD_NWKS__
};
uint16_t huedInsteonDiag_VirtualChildLiveNwk[HUEDINSTEON_DIAG_VIRTUAL_CHILD_STORAGE_COUNT] =
{
  __HUEDINSTEON_VIRTUAL_CHILD_NWKS__
};

static const uint8_t huedInsteonDiag_VirtualChildEui[HUEDINSTEON_DIAG_VIRTUAL_CHILD_STORAGE_COUNT][Z_EXTADDR_LEN] =
{
  __HUEDINSTEON_VIRTUAL_CHILD_EUIS__
};

static uint8_t huedInsteonDiag_VirtualNwkSeq[HUEDINSTEON_DIAG_VIRTUAL_CHILD_STORAGE_COUNT] = { __HUEDINSTEON_VIRTUAL_NWK_SEQS__ };
static uint8_t huedInsteonDiag_VirtualApsSeq[HUEDINSTEON_DIAG_VIRTUAL_CHILD_STORAGE_COUNT] = { __HUEDINSTEON_VIRTUAL_APS_SEQS__ };
static uint32_t huedInsteonDiag_VirtualNwkFrameCounter[HUEDINSTEON_DIAG_VIRTUAL_CHILD_STORAGE_COUNT] = { 1 };
static bool huedInsteonDiag_VirtualChildJoined[HUEDINSTEON_DIAG_VIRTUAL_CHILD_STORAGE_COUNT] = { false };
static uint8_t huedInsteonDiag_VirtualChildOn[HUEDINSTEON_DIAG_VIRTUAL_CHILD_STORAGE_COUNT] = { LIGHT_OFF };
static uint8_t huedInsteonDiag_VirtualChildLevel[HUEDINSTEON_DIAG_VIRTUAL_CHILD_STORAGE_COUNT] = { 254 };
static uint8_t huedInsteonDiag_ParentOn = LIGHT_OFF;
static uint8_t huedInsteonDiag_ParentLevel = 254;
static uint32_t huedInsteonDiag_SerialSeq;

extern void MAC_CbackEvent(macCbackEvent_t *pData);

static int8_t huedInsteonDiag_VirtualChildIndex(uint16_t nwkAddr)
{
  uint8_t i;
  for (i = 0; i < HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT; i++)
  {
    if (huedInsteonDiag_VirtualChildNwk[i] == nwkAddr)
    {
      return (int8_t)i;
    }
    if (huedInsteonDiag_VirtualChildLiveNwk[i] == nwkAddr)
    {
      return (int8_t)i;
    }
  }
  return -1;
}

static int8_t huedInsteonDiag_IncomingChildIndex(const afIncomingMSGPacket_t *msg)
{
  if (msg == NULL)
  {
    return -1;
  }
  return huedInsteonDiag_VirtualChildIndex(msg->macDestAddr);
}

static uint8_t huedInsteonDiag_LogicalEndpointForChild(int8_t childIndex)
{
  if (childIndex >= 0)
  {
    return (uint8_t)(childIndex + 2);
  }
  return 1;
}

static void huedInsteonDiag_CopyEuiString(char *out, size_t outLen, int8_t childIndex)
{
  uint8_t eui[Z_EXTADDR_LEN] = {0};
  const uint8_t *src = eui;

  if ((childIndex >= 0) && (childIndex < HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT))
  {
    src = huedInsteonDiag_VirtualChildEui[childIndex];
  }
  else
  {
    ZMacGetReq(ZMacExtAddr, eui);
  }

  snprintf(out,
           outLen,
           "%02x%02x%02x%02x%02x%02x%02x%02x",
           (unsigned)src[7],
           (unsigned)src[6],
           (unsigned)src[5],
           (unsigned)src[4],
           (unsigned)src[3],
           (unsigned)src[2],
           (unsigned)src[1],
           (unsigned)src[0]);
}

static void huedInsteonDiag_RecordVirtualCommand(int8_t childIndex, uint8_t on, uint8_t level)
{
  if ((childIndex >= 0) && (childIndex < HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT))
  {
    huedInsteonDiag_VirtualChildOn[childIndex] = on;
    huedInsteonDiag_VirtualChildLevel[childIndex] = level;
  }
  else
  {
    huedInsteonDiag_ParentOn = on;
    huedInsteonDiag_ParentLevel = level;
  }
}

static void huedInsteonDiag_EmitCommand(const afIncomingMSGPacket_t *msg,
                                        const char *command,
                                        bool hasLevel,
                                        uint8_t level,
                                        uint32_t transitionMs)
{
  int8_t childIndex = huedInsteonDiag_IncomingChildIndex(msg);
  uint8_t endpoint = huedInsteonDiag_LogicalEndpointForChild(childIndex);
  uint16_t nwk = (msg != NULL) ? msg->macDestAddr : _NIB.nwkDevAddress;
  char eui[17];

  huedInsteonDiag_CopyEuiString(eui, sizeof(eui), childIndex);

  if (hasLevel)
  {
    huedInsteonDiag_Log("{\\\"dir\\\":\\\"zb->pi\\\",\\\"type\\\":\\\"cmd\\\",\\\"endpoint\\\":%u,\\\"identity\\\":%u,\\\"ieee\\\":\\\"%s\\\",\\\"nwk\\\":\\\"0x%04x\\\",\\\"command\\\":\\\"%s\\\",\\\"level\\\":%u,\\\"transition_ms\\\":%lu,\\\"seq\\\":%lu}",
                        (unsigned)endpoint,
                        (unsigned)endpoint,
                        eui,
                        (unsigned)nwk,
                        command,
                        (unsigned)level,
                        (unsigned long)transitionMs,
                        (unsigned long)++huedInsteonDiag_SerialSeq);
  }
  else
  {
    huedInsteonDiag_Log("{\\\"dir\\\":\\\"zb->pi\\\",\\\"type\\\":\\\"cmd\\\",\\\"endpoint\\\":%u,\\\"identity\\\":%u,\\\"ieee\\\":\\\"%s\\\",\\\"nwk\\\":\\\"0x%04x\\\",\\\"command\\\":\\\"%s\\\",\\\"seq\\\":%lu}",
                        (unsigned)endpoint,
                        (unsigned)endpoint,
                        eui,
                        (unsigned)nwk,
                        command,
                        (unsigned long)++huedInsteonDiag_SerialSeq);
  }
}

static bool huedInsteonDiag_ParseChildCommand(const char *command, const char *prefix, uint8_t *childIndex)
{
  uint16_t value = 0;
  size_t prefixLen = strlen(prefix);
  const char *p;

  if (strncmp(command, prefix, prefixLen) != 0)
  {
    return false;
  }

  p = command + prefixLen;
  if ((*p < '0') || (*p > '9'))
  {
    return false;
  }

  while ((*p >= '0') && (*p <= '9'))
  {
    value = (uint16_t)((value * 10) + (uint16_t)(*p - '0'));
    p++;
  }

  if ((*p != '\\0') || (value == 0) || (value > HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT))
  {
    return false;
  }

  *childIndex = (uint8_t)(value - 1);
  return true;
}

static void huedInsteonDiag_ReadCb(UART2_Handle handle, void *buf, size_t count, void *userArg, int_fast16_t status)
{
  (void)handle;
  (void)buf;
  (void)userArg;

  if ((status == UART2_STATUS_SUCCESS) && (count > 0))
  {
    char c = huedInsteonDiag_RxByte;
    if ((c == '\\r') || (c == '\\n'))
    {
      if (huedInsteonDiag_LineLen > 0)
      {
        huedInsteonDiag_Line[huedInsteonDiag_LineLen] = '\\0';
        if (!huedInsteonDiag_CommandReady)
        {
          strncpy(huedInsteonDiag_Command, huedInsteonDiag_Line, sizeof(huedInsteonDiag_Command) - 1);
          huedInsteonDiag_Command[sizeof(huedInsteonDiag_Command) - 1] = '\\0';
          huedInsteonDiag_CommandReady = true;
          appServiceTaskEvents |= HUEDINSTEON_DIAG_EVT;
          Semaphore_post(appSemHandle);
        }
        huedInsteonDiag_LineLen = 0;
      }
    }
    else if (huedInsteonDiag_LineLen < (sizeof(huedInsteonDiag_Line) - 1))
    {
      huedInsteonDiag_Line[huedInsteonDiag_LineLen++] = c;
    }
  }

  huedInsteonDiag_ArmRead();
}

static void huedInsteonDiag_ArmRead(void)
{
  if (huedInsteonDiag_Uart != NULL)
  {
    UART2_read(huedInsteonDiag_Uart, &huedInsteonDiag_RxByte, 1, NULL);
  }
}

static void huedInsteonDiag_Log(const char *fmt, ...)
{
  char line[240];
  va_list ap;
  int n;

  if (huedInsteonDiag_Uart == NULL)
  {
    return;
  }

  va_start(ap, fmt);
  n = vsnprintf(line, sizeof(line) - 3, fmt, ap);
  va_end(ap);

  if (n < 0)
  {
    return;
  }
  if (n > (int)(sizeof(line) - 3))
  {
    n = sizeof(line) - 3;
  }
  line[n++] = '\\r';
  line[n++] = '\\n';
  line[n] = '\\0';
  UART2_write(huedInsteonDiag_Uart, line, (size_t)n, NULL);
}

static const char *huedInsteonDiag_BdbModeName(uint8_t mode)
{
  switch (mode)
  {
    case BDB_COMMISSIONING_INITIALIZATION:
      return "initialization";
    case BDB_COMMISSIONING_NWK_STEERING:
      return "network-steering";
    case BDB_COMMISSIONING_FORMATION:
      return "formation";
    case BDB_COMMISSIONING_FINDING_BINDING:
      return "finding-binding";
    case BDB_COMMISSIONING_TOUCHLINK:
      return "touchlink";
    case BDB_COMMISSIONING_PARENT_LOST:
      return "parent-lost";
    default:
      return "unknown";
  }
}

static const char *huedInsteonDiag_BdbStatusName(uint8_t status)
{
  switch (status)
  {
    case BDB_COMMISSIONING_SUCCESS:
      return "success";
    case BDB_COMMISSIONING_IN_PROGRESS:
      return "in-progress";
    case BDB_COMMISSIONING_NO_NETWORK:
      return "no-network";
    case BDB_COMMISSIONING_TL_TARGET_FAILURE:
      return "tl-target-failure";
    case BDB_COMMISSIONING_TL_NOT_AA_CAPABLE:
      return "tl-not-aa-capable";
    case BDB_COMMISSIONING_TL_NO_SCAN_RESPONSE:
      return "tl-no-scan-response";
    case BDB_COMMISSIONING_TL_NOT_PERMITTED:
      return "tl-not-permitted";
    case BDB_COMMISSIONING_TCLK_EX_FAILURE:
      return "tclk-exchange-failure";
    case BDB_COMMISSIONING_FORMATION_FAILURE:
      return "formation-failure";
    case BDB_COMMISSIONING_FB_TARGET_IN_PROGRESS:
      return "fb-target-in-progress";
    case BDB_COMMISSIONING_FB_INITITATOR_IN_PROGRESS:
      return "fb-initiator-in-progress";
    case BDB_COMMISSIONING_FB_NO_IDENTIFY_QUERY_RESPONSE:
      return "fb-no-identify-query-response";
    case BDB_COMMISSIONING_FB_BINDING_TABLE_FULL:
      return "fb-binding-table-full";
    case BDB_COMMISSIONING_NETWORK_RESTORED:
      return "network-restored";
    case BDB_COMMISSIONING_FAILURE:
      return "failure";
    default:
      return "unknown";
  }
}

static const char *huedInsteonDiag_TclkStatusName(uint8_t status)
{
  switch (status)
  {
    case BDB_TC_LK_EXCH_PROCESS_JOINING:
      return "joining";
    case BDB_TC_LK_EXCH_PROCESS_EXCH_SUCCESS:
      return "exchange-success";
    case BDB_TC_LK_EXCH_PROCESS_EXCH_FAIL:
      return "exchange-fail";
    default:
      return "unknown";
  }
}

static void huedInsteonDiag_LogState(const char *reason)
{
  zstack_sysNwkInfoReadRsp_t rsp;
  memset(&rsp, 0, sizeof(rsp));
  Zstackapi_sysNwkInfoReadReq(appServiceTaskId, &rsp);
  huedInsteonDiag_Log("STATE reason=%s dev=%u pan=0x%04x channel=%u short=0x%04x",
                      reason,
                      (unsigned)rsp.devState,
                      (unsigned)rsp.panId,
                      (unsigned)rsp.logicalChannel,
                      (unsigned)rsp.nwkAddr);
}

static void huedInsteonDiag_Init(void)
{
  UART2_Params params;

  UART2_Params_init(&params);
  params.readMode = UART2_Mode_CALLBACK;
  params.writeMode = UART2_Mode_BLOCKING;
  params.readReturnMode = UART2_ReadReturnMode_FULL;
  params.readCallback = huedInsteonDiag_ReadCb;
  params.baudRate = 115200;

  huedInsteonDiag_Uart = UART2_open(CONFIG_DISPLAY_UART, &params);
  if (huedInsteonDiag_Uart != NULL)
  {
    UART2_rxEnable(huedInsteonDiag_Uart);
    huedInsteonDiag_ArmRead();
    huedInsteonDiag_Log("BOOT variant=diag");
    huedInsteonDiag_Log("READY commands=commission,state,reset,vchild1,vchild2,vchild3,vchildren,vjoin1,vjoin2,vjoin3,vjoins,vnlme1,vnlme2,vnlme3,vnlmes,vsec1,vsec2,vsec3,vsecs,vassoc1,vassoc2,vassoc3,vassocs,vmacassoc1,vmacassoc2,vmacassoc3,vmacassocs,vrestore,vreqkey1,vreqkey2,vreqkey3,vreqkeys,vreqdef1,vreqdef2,vreqdef3,vreqdefs,vadmit1,vadmit2,vadmit3,vadmits,vparent1,vparent2,vparent3,vparents,help");
  }
}

static afStatus_t huedInsteonDiag_AliasDeviceAnnce(uint16_t sourceNwkAddr, uint16_t payloadNwkAddr, const uint8_t *eui)
{
  uint16_t savedNwkAddr;
  uint8_t savedNwkSeq;
  uint8_t savedApsSeq;
  uint32_t savedNwkFrameCounter;
  uint8_t savedEui[Z_EXTADDR_LEN];
  int8_t idx;
  afStatus_t status;

  savedNwkAddr = _NIB.nwkDevAddress;
  savedNwkSeq = _NIB.SequenceNum;
  savedApsSeq = APS_Counter;
  savedNwkFrameCounter = nwkFrameCounter;
  ZMacGetReq(ZMacExtAddr, savedEui);

  idx = huedInsteonDiag_VirtualChildIndex(sourceNwkAddr);
  _NIB.nwkDevAddress = sourceNwkAddr;
  if (idx >= 0)
  {
    _NIB.SequenceNum = huedInsteonDiag_VirtualNwkSeq[idx]++;
    APS_Counter = huedInsteonDiag_VirtualApsSeq[idx]++;
    nwkFrameCounter = huedInsteonDiag_VirtualNwkFrameCounter[idx]++;
  }
  ZMacSetReq(ZMacExtAddr, (uint8_t *)eui);
  status = ZDP_DeviceAnnce(payloadNwkAddr, (uint8_t *)eui, CAPINFO_ALTPANCOORD | CAPINFO_DEVICETYPE_FFD | CAPINFO_POWER_AC | CAPINFO_RCVR_ON_IDLE | CAPINFO_SECURITY_CAPABLE, FALSE);
  if (idx >= 0)
  {
    huedInsteonDiag_VirtualNwkFrameCounter[idx] = nwkFrameCounter;
  }
  ZMacSetReq(ZMacExtAddr, savedEui);
  nwkFrameCounter = savedNwkFrameCounter;
  APS_Counter = savedApsSeq;
  _NIB.SequenceNum = savedNwkSeq;
  _NIB.nwkDevAddress = savedNwkAddr;

  return status;
}

void huedInsteonDiag_ZdoTrace(const char *tag, uint16_t aoi, uint16_t src, uint8_t endpoint)
{
  huedInsteonDiag_Log("VZDO %s aoi=0x%04x src=0x%04x ep=%u", tag, (unsigned)aoi, (unsigned)src, (unsigned)endpoint);
}

void huedInsteonDiag_ZdoInTrace(uint16_t cluster, uint16_t src, uint16_t macDst, uint16_t macSrc, uint8_t sec, uint8_t len)
{
  huedInsteonDiag_Log("ZIN c=0x%04x src=0x%04x md=0x%04x ms=0x%04x sec=%u len=%u",
                      (unsigned)cluster,
                      (unsigned)src,
                      (unsigned)macDst,
                      (unsigned)macSrc,
                      (unsigned)sec,
                      (unsigned)len);
}

void huedInsteonDiag_SecTrace(const char *tag, uint16_t src, uint16_t a, uint16_t b, const uint8_t *eui)
{
  if (eui != NULL)
  {
    huedInsteonDiag_Log("SEC %s src=0x%04x a=%u b=%u eui=%02x%02x%02x%02x%02x%02x%02x%02x",
                        tag,
                        (unsigned)src,
                        (unsigned)a,
                        (unsigned)b,
                        (unsigned)eui[7],
                        (unsigned)eui[6],
                        (unsigned)eui[5],
                        (unsigned)eui[4],
                        (unsigned)eui[3],
                        (unsigned)eui[2],
                        (unsigned)eui[1],
                        (unsigned)eui[0]);
  }
  else
  {
    huedInsteonDiag_Log("SEC %s src=0x%04x a=%u b=%u",
                        tag,
                        (unsigned)src,
                        (unsigned)a,
                        (unsigned)b);
  }
}

void huedInsteonDiag_MacTrace(uint8_t event, uint8_t status, uint16_t shortAddr)
{
  uint8_t activeEui[Z_EXTADDR_LEN] = {0};
  int8_t childIndex;

  if ((event == MAC_MLME_ASSOCIATE_CNF) && (status == ZSuccess))
  {
    ZMacGetReq(ZMacExtAddr, activeEui);
    for (childIndex = 0; childIndex < HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT; childIndex++)
    {
      if (memcmp(activeEui, huedInsteonDiag_VirtualChildEui[childIndex], Z_EXTADDR_LEN) == 0)
      {
        huedInsteonDiag_VirtualChildLiveNwk[childIndex] = shortAddr;
        huedInsteonDiag_VirtualChildJoined[childIndex] = true;
        break;
      }
    }
  }

  huedInsteonDiag_Log("MAC event=%u status=%u short=0x%04x",
                      (unsigned)event,
                      (unsigned)status,
                      (unsigned)shortAddr);
}

static void huedInsteonDiag_AnnounceVirtualChild(uint8_t childIndex)
{
  associated_devices_t *assoc;
  AddrMgrEntry_t addr;
  const uint8_t *eui;
  uint16_t nwkAddr;
  afStatus_t status;

  if (childIndex >= HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT)
  {
    huedInsteonDiag_Log("ERR virtual-child index=%u", (unsigned)childIndex);
    return;
  }

  eui = huedInsteonDiag_VirtualChildEui[childIndex];
  nwkAddr = huedInsteonDiag_VirtualChildNwk[childIndex];

  memset(&addr, 0, sizeof(addr));
  addr.user = ADDRMGR_USER_DEFAULT;
  addr.nwkAddr = nwkAddr;
  AddrMgrExtAddrSet(addr.extAddr, (uint8_t *)eui);
  AddrMgrEntryUpdate(&addr);

  assoc = AssocAddNew(nwkAddr, (uint8_t *)eui, CHILD_RFD_RX_IDLE);
  if (assoc != NULL)
  {
    assoc->devStatus |= DEV_SEC_AUTH_STATUS | DEV_SECURED_JOIN;
    assoc->age = 0;
    assoc->endDev.deviceTimeout = TIMEOUT_DONT_AGE_OUT;
    assoc->timeoutCounter = TIMEOUT_DONT_AGE_OUT;
    assoc->keepaliveRcv = true;
  }

  status = huedInsteonDiag_AliasDeviceAnnce(nwkAddr, nwkAddr, eui);

  huedInsteonDiag_Log("VCHILD-ALIAS idx=%u nwk=0x%04x eui=%02x%02x%02x%02x%02x%02x%02x%02x assoc=%u annce=%u restored=0x%04x",
                      (unsigned)(childIndex + 1),
                      (unsigned)nwkAddr,
                      (unsigned)eui[7],
                      (unsigned)eui[6],
                      (unsigned)eui[5],
                      (unsigned)eui[4],
                      (unsigned)eui[3],
                      (unsigned)eui[2],
                      (unsigned)eui[1],
                      (unsigned)eui[0],
                      (unsigned)(assoc != NULL),
                      (unsigned)status,
                      (unsigned)_NIB.nwkDevAddress);
}

static void huedInsteonDiag_ForwardVirtualChildJoin(uint8_t childIndex)
{
  associated_devices_t *assoc;
  AddrMgrEntry_t addr;
  APSME_UpdateDeviceReq_t req;
  const uint8_t *eui;
  uint16_t nwkAddr;
  ZStatus_t plainStatus;
  ZStatus_t secureStatus;
  afStatus_t annceStatus;

  if (childIndex >= HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT)
  {
    huedInsteonDiag_Log("ERR virtual-join index=%u", (unsigned)childIndex);
    return;
  }

  eui = huedInsteonDiag_VirtualChildEui[childIndex];
  nwkAddr = huedInsteonDiag_VirtualChildNwk[childIndex];

  memset(&addr, 0, sizeof(addr));
  addr.user = ADDRMGR_USER_DEFAULT;
  addr.nwkAddr = nwkAddr;
  AddrMgrExtAddrSet(addr.extAddr, (uint8_t *)eui);
  AddrMgrEntryUpdate(&addr);

  assoc = AssocAddNew(nwkAddr, (uint8_t *)eui, CHILD_RFD_RX_IDLE);
  if (assoc != NULL)
  {
    assoc->devStatus |= DEV_SEC_AUTH_STATUS | DEV_SECURED_JOIN;
    assoc->age = 0;
    assoc->endDev.deviceTimeout = TIMEOUT_DONT_AGE_OUT;
    assoc->timeoutCounter = TIMEOUT_DONT_AGE_OUT;
    assoc->keepaliveRcv = true;
  }

  memset(&req, 0, sizeof(req));
  req.dstAddr = APSME_TRUSTCENTER_NWKADDR;
  req.devAddr = nwkAddr;
  req.devExtAddr = (uint8_t *)eui;
  req.status = APSME_UD_STANDARD_UNSECURED_JOIN;

  req.apsSecure = FALSE;
  plainStatus = APSME_UpdateDeviceReq(&req);

  req.apsSecure = TRUE;
  secureStatus = APSME_UpdateDeviceReq(&req);

  annceStatus = huedInsteonDiag_AliasDeviceAnnce(nwkAddr, nwkAddr, eui);

  huedInsteonDiag_Log("VJOIN idx=%u nwk=0x%04x eui=%02x%02x%02x%02x%02x%02x%02x%02x assoc=%u update-plain=%u update-secure=%u annce=%u restored=0x%04x",
                      (unsigned)(childIndex + 1),
                      (unsigned)nwkAddr,
                      (unsigned)eui[7],
                      (unsigned)eui[6],
                      (unsigned)eui[5],
                      (unsigned)eui[4],
                      (unsigned)eui[3],
                      (unsigned)eui[2],
                      (unsigned)eui[1],
                      (unsigned)eui[0],
                      (unsigned)(assoc != NULL),
                      (unsigned)plainStatus,
                      (unsigned)secureStatus,
                      (unsigned)annceStatus,
                      (unsigned)_NIB.nwkDevAddress);
}

static void huedInsteonDiag_NlmeVirtualChildJoin(uint8_t childIndex)
{
  associated_devices_t *assoc;
  AddrMgrEntry_t addr;
  const uint8_t *eui;
  uint16_t nwkAddr;
  ZStatus_t joinStatus;
  afStatus_t annceStatus;

  if (childIndex >= HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT)
  {
    huedInsteonDiag_Log("ERR virtual-nlme index=%u", (unsigned)childIndex);
    return;
  }

  eui = huedInsteonDiag_VirtualChildEui[childIndex];
  nwkAddr = huedInsteonDiag_VirtualChildNwk[childIndex];

  memset(&addr, 0, sizeof(addr));
  addr.user = ADDRMGR_USER_DEFAULT;
  addr.nwkAddr = nwkAddr;
  AddrMgrExtAddrSet(addr.extAddr, (uint8_t *)eui);
  AddrMgrEntryUpdate(&addr);

  assoc = AssocAddNew(nwkAddr, (uint8_t *)eui, CHILD_RFD_RX_IDLE);
  if (assoc != NULL)
  {
    assoc->devStatus &= ~(DEV_SEC_AUTH_STATUS | DEV_SECURED_JOIN | DEV_REJOIN_STATUS);
    assoc->devStatus |= DEV_SEC_INIT_STATUS;
    assoc->age = 0;
    assoc->endDev.deviceTimeout = TIMEOUT_DONT_AGE_OUT;
    assoc->timeoutCounter = TIMEOUT_DONT_AGE_OUT;
    assoc->keepaliveRcv = true;
  }

  joinStatus = NLME_JoinIndication(nwkAddr, (uint8_t *)eui,
                                   CAPINFO_POWER_AC | CAPINFO_RCVR_ON_IDLE | CAPINFO_SECURITY_CAPABLE,
                                   NWK_ASSOC_JOIN);
  annceStatus = huedInsteonDiag_AliasDeviceAnnce(nwkAddr, nwkAddr, eui);

  huedInsteonDiag_Log("VNLME idx=%u nwk=0x%04x eui=%02x%02x%02x%02x%02x%02x%02x%02x assoc=%u join-ind=%u annce=%u restored=0x%04x",
                      (unsigned)(childIndex + 1),
                      (unsigned)nwkAddr,
                      (unsigned)eui[7],
                      (unsigned)eui[6],
                      (unsigned)eui[5],
                      (unsigned)eui[4],
                      (unsigned)eui[3],
                      (unsigned)eui[2],
                      (unsigned)eui[1],
                      (unsigned)eui[0],
                      (unsigned)(assoc != NULL),
                      (unsigned)joinStatus,
                      (unsigned)annceStatus,
                      (unsigned)_NIB.nwkDevAddress);
}

static void huedInsteonDiag_SecMgrVirtualChildJoin(uint8_t childIndex)
{
  associated_devices_t *assoc;
  AddrMgrEntry_t addr;
  const uint8_t *eui;
  uint16_t nwkAddr;
  ZStatus_t joinStatus;
  uint8_t secStatus;
  afStatus_t annceStatus;

  if (childIndex >= HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT)
  {
    huedInsteonDiag_Log("ERR virtual-sec index=%u", (unsigned)childIndex);
    return;
  }

  eui = huedInsteonDiag_VirtualChildEui[childIndex];
  nwkAddr = huedInsteonDiag_VirtualChildNwk[childIndex];

  memset(&addr, 0, sizeof(addr));
  addr.user = ADDRMGR_USER_DEFAULT;
  addr.nwkAddr = nwkAddr;
  AddrMgrExtAddrSet(addr.extAddr, (uint8_t *)eui);
  AddrMgrEntryUpdate(&addr);

  assoc = AssocAddNew(nwkAddr, (uint8_t *)eui, CHILD_RFD_RX_IDLE);
  if (assoc != NULL)
  {
    assoc->devStatus &= ~(DEV_SEC_AUTH_STATUS | DEV_SECURED_JOIN | DEV_REJOIN_STATUS);
    assoc->devStatus |= DEV_SEC_INIT_STATUS;
    assoc->age = 0;
    assoc->endDev.deviceTimeout = TIMEOUT_DONT_AGE_OUT;
    assoc->timeoutCounter = TIMEOUT_DONT_AGE_OUT;
    assoc->keepaliveRcv = true;
  }

  joinStatus = NLME_JoinIndication(nwkAddr, (uint8_t *)eui,
                                   CAPINFO_POWER_AC | CAPINFO_RCVR_ON_IDLE | CAPINFO_SECURITY_CAPABLE,
                                   NWK_ASSOC_JOIN);
  secStatus = ZDSecMgrNewDeviceEvent(nwkAddr);
  annceStatus = huedInsteonDiag_AliasDeviceAnnce(nwkAddr, nwkAddr, eui);

  huedInsteonDiag_Log("VSEC idx=%u nwk=0x%04x eui=%02x%02x%02x%02x%02x%02x%02x%02x assoc=%u join-ind=%u sec-new=%u annce=%u restored=0x%04x",
                      (unsigned)(childIndex + 1),
                      (unsigned)nwkAddr,
                      (unsigned)eui[7],
                      (unsigned)eui[6],
                      (unsigned)eui[5],
                      (unsigned)eui[4],
                      (unsigned)eui[3],
                      (unsigned)eui[2],
                      (unsigned)eui[1],
                      (unsigned)eui[0],
                      (unsigned)(assoc != NULL),
                      (unsigned)joinStatus,
                      (unsigned)secStatus,
                      (unsigned)annceStatus,
                      (unsigned)_NIB.nwkDevAddress);
}

static void huedInsteonDiag_MacVirtualChildAssoc(uint8_t childIndex)
{
  macCbackEvent_t evt;
  const uint8_t *eui;
  associated_devices_t *assoc;
  uint8_t secStatus;
  afStatus_t annceStatus;

  if (childIndex >= HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT)
  {
    huedInsteonDiag_Log("ERR virtual-assoc index=%u", (unsigned)childIndex);
    return;
  }

  eui = huedInsteonDiag_VirtualChildEui[childIndex];

  memset(&evt, 0, sizeof(evt));
  evt.associateInd.hdr.event = MAC_MLME_ASSOCIATE_IND;
  evt.associateInd.hdr.status = ZSuccess;
  OsalPort_memcpy(evt.associateInd.deviceAddress, eui, Z_EXTADDR_LEN);
  evt.associateInd.capabilityInformation = CAPINFO_POWER_AC | CAPINFO_RCVR_ON_IDLE | CAPINFO_SECURITY_CAPABLE;

  MAC_CbackEvent(&evt);

  assoc = AssocGetWithExt((uint8_t *)eui);
  secStatus = FALSE;
  annceStatus = afStatus_FAILED;
  if (assoc != NULL)
  {
    huedInsteonDiag_VirtualChildLiveNwk[childIndex] = assoc->shortAddr;
    huedInsteonDiag_VirtualChildJoined[childIndex] = true;
    assoc->age = 0;
    assoc->endDev.deviceTimeout = TIMEOUT_DONT_AGE_OUT;
    assoc->timeoutCounter = TIMEOUT_DONT_AGE_OUT;
    assoc->keepaliveRcv = true;
    secStatus = ZDSecMgrNewDeviceEvent(assoc->shortAddr);
    annceStatus = huedInsteonDiag_AliasDeviceAnnce(assoc->shortAddr, assoc->shortAddr, eui);
  }

  huedInsteonDiag_Log("VASSOC idx=%u eui=%02x%02x%02x%02x%02x%02x%02x%02x queued=1 assoc-now=%u short=0x%04x rel=%u dev=0x%02x sec-new=%u annce=%u",
                      (unsigned)(childIndex + 1),
                      (unsigned)eui[7],
                      (unsigned)eui[6],
                      (unsigned)eui[5],
                      (unsigned)eui[4],
                      (unsigned)eui[3],
                      (unsigned)eui[2],
                      (unsigned)eui[1],
                      (unsigned)eui[0],
                      (unsigned)(assoc != NULL),
                      (unsigned)((assoc != NULL) ? assoc->shortAddr : INVALID_NODE_ADDR),
                      (unsigned)((assoc != NULL) ? assoc->nodeRelation : 0xff),
                      (unsigned)((assoc != NULL) ? assoc->devStatus : 0xff),
                      (unsigned)secStatus,
                      (unsigned)annceStatus);
}

static void huedInsteonDiag_RestoreParentIdentity(void)
{
  uint16_t parentShort;
  uint8_t activeEui[Z_EXTADDR_LEN] = {0};
  uint8_t euiStatus;
  uint8_t shortStatus;

  huedInsteon_SetVirtualEui();
  euiStatus = 0;

  parentShort = (huedInsteonDiag_ParentNwkBeforeMacAssoc != INVALID_NODE_ADDR)
                  ? huedInsteonDiag_ParentNwkBeforeMacAssoc
                  : _NIB.nwkDevAddress;
  _NIB.nwkDevAddress = parentShort;
  shortStatus = ZMacSetReq(ZMacShortAddress, (uint8_t *)&parentShort);
  ZMacGetReq(ZMacExtAddr, activeEui);
  huedInsteonDiag_Log("VRESTORE eui-status=%u short-status=%u parent-short=0x%04x active=%02x%02x%02x%02x%02x%02x%02x%02x",
                      (unsigned)euiStatus,
                      (unsigned)shortStatus,
                      (unsigned)parentShort,
                      (unsigned)activeEui[7],
                      (unsigned)activeEui[6],
                      (unsigned)activeEui[5],
                      (unsigned)activeEui[4],
                      (unsigned)activeEui[3],
                      (unsigned)activeEui[2],
                      (unsigned)activeEui[1],
                      (unsigned)activeEui[0]);
}

static void huedInsteonDiag_OverAirMacVirtualChildAssoc(uint8_t childIndex)
{
  const uint8_t *eui;
  uint8_t activeEui[Z_EXTADDR_LEN] = {0};
  uint16_t invalidShort;
  uint16_t parentShort;
  ZMacAssociateReq_t req;
  ZMacStatus_t status;
  uint8_t euiStatus;
  uint8_t shortStatus;

  if (childIndex >= HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT)
  {
    huedInsteonDiag_Log("ERR virtual-mac-assoc index=%u", (unsigned)childIndex);
    return;
  }

  eui = huedInsteonDiag_VirtualChildEui[childIndex];
  if (huedInsteonDiag_ParentNwkBeforeMacAssoc == INVALID_NODE_ADDR)
  {
    huedInsteonDiag_ParentNwkBeforeMacAssoc = _NIB.nwkDevAddress;
  }
  invalidShort = INVALID_NODE_ADDR;
  parentShort = (_NIB.nwkCoordAddress != INVALID_NODE_ADDR) ? _NIB.nwkCoordAddress : 0x0000;

  euiStatus = ZMacSetReq(ZMacExtAddr, (uint8_t *)eui);
  shortStatus = ZMacSetReq(ZMacShortAddress, (uint8_t *)&invalidShort);
  ZMacGetReq(ZMacExtAddr, activeEui);

  memset(&req, 0, sizeof(req));
  req.LogicalChannel = _NIB.nwkLogicalChannel;
  req.ChannelPage = 0;
  req.CoordAddress.addrMode = Addr16Bit;
  req.CoordAddress.addr.shortAddr = parentShort;
  req.CoordPANId = _NIB.nwkPanId;
  req.CapabilityFlags = CAPINFO_POWER_AC | CAPINFO_RCVR_ON_IDLE | CAPINFO_SECURITY_CAPABLE | CAPINFO_ALLOC_ADDR;
  status = ZMacAssociateReq(&req);

  huedInsteonDiag_Log("VMACASSOC idx=%u eui=%02x%02x%02x%02x%02x%02x%02x%02x pan=0x%04x ch=%u coord=0x%04x cap=0x%02x eui-status=%u short-status=%u status=%u active=%02x%02x%02x%02x%02x%02x%02x%02x restore-with=vrestore",
                      (unsigned)(childIndex + 1),
                      (unsigned)eui[7],
                      (unsigned)eui[6],
                      (unsigned)eui[5],
                      (unsigned)eui[4],
                      (unsigned)eui[3],
                      (unsigned)eui[2],
                      (unsigned)eui[1],
                      (unsigned)eui[0],
                      (unsigned)_NIB.nwkPanId,
                      (unsigned)_NIB.nwkLogicalChannel,
                      (unsigned)parentShort,
                      (unsigned)req.CapabilityFlags,
                      (unsigned)euiStatus,
                      (unsigned)shortStatus,
                      (unsigned)status,
                      (unsigned)activeEui[7],
                      (unsigned)activeEui[6],
                      (unsigned)activeEui[5],
                      (unsigned)activeEui[4],
                      (unsigned)activeEui[3],
                      (unsigned)activeEui[2],
                      (unsigned)activeEui[1],
                      (unsigned)activeEui[0]);
}

static void huedInsteonDiag_RequestVirtualChildTcLinkKey(uint8_t childIndex)
{
  const uint8_t *eui;
  associated_devices_t *assoc;
  APSME_RequestKeyReq_t req;
  uint16_t childNwkAddr;
  uint16_t savedNwkAddr;
  uint8_t savedNwkSeq;
  uint8_t savedApsSeq;
  uint32_t savedNwkFrameCounter;
  uint8_t savedEui[Z_EXTADDR_LEN];
  ZStatus_t status;

  if (childIndex >= HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT)
  {
    huedInsteonDiag_Log("ERR virtual-reqkey index=%u", (unsigned)childIndex);
    return;
  }

  eui = huedInsteonDiag_VirtualChildEui[childIndex];
  assoc = AssocGetWithExt((uint8_t *)eui);
  childNwkAddr = (assoc != NULL) ? assoc->shortAddr : huedInsteonDiag_VirtualChildLiveNwk[childIndex];
  if (assoc == NULL)
  {
    assoc = AssocAddNew(childNwkAddr, (uint8_t *)eui, CHILD_RFD_RX_IDLE);
  }
  if (assoc != NULL)
  {
    huedInsteonDiag_VirtualChildLiveNwk[childIndex] = assoc->shortAddr;
    huedInsteonDiag_VirtualChildJoined[childIndex] = true;
    childNwkAddr = assoc->shortAddr;
    assoc->age = 0;
    assoc->endDev.deviceTimeout = TIMEOUT_DONT_AGE_OUT;
    assoc->timeoutCounter = TIMEOUT_DONT_AGE_OUT;
    assoc->keepaliveRcv = true;
  }

  savedNwkAddr = _NIB.nwkDevAddress;
  savedNwkSeq = _NIB.SequenceNum;
  savedApsSeq = APS_Counter;
  savedNwkFrameCounter = nwkFrameCounter;
  ZMacGetReq(ZMacExtAddr, savedEui);

  _NIB.nwkDevAddress = childNwkAddr;
  _NIB.SequenceNum = huedInsteonDiag_VirtualNwkSeq[childIndex]++;
  APS_Counter = huedInsteonDiag_VirtualApsSeq[childIndex]++;
  nwkFrameCounter = huedInsteonDiag_VirtualNwkFrameCounter[childIndex]++;
  ZMacSetReq(ZMacExtAddr, (uint8_t *)eui);

  memset(&req, 0, sizeof(req));
  req.dstAddr = APSME_TRUSTCENTER_NWKADDR;
  req.keyType = KEY_TYPE_TC_LINK;
  req.partExtAddr = NULL;
  status = APSME_RequestKeyReq(&req);
  huedInsteonDiag_VirtualNwkFrameCounter[childIndex] = nwkFrameCounter;

  ZMacSetReq(ZMacExtAddr, savedEui);
  nwkFrameCounter = savedNwkFrameCounter;
  APS_Counter = savedApsSeq;
  _NIB.SequenceNum = savedNwkSeq;
  _NIB.nwkDevAddress = savedNwkAddr;

  huedInsteonDiag_Log("VREQKEY idx=%u eui=%02x%02x%02x%02x%02x%02x%02x%02x assoc=%u short=0x%04x status=%u restored=0x%04x",
                      (unsigned)(childIndex + 1),
                      (unsigned)eui[7],
                      (unsigned)eui[6],
                      (unsigned)eui[5],
                      (unsigned)eui[4],
                      (unsigned)eui[3],
                      (unsigned)eui[2],
                      (unsigned)eui[1],
                      (unsigned)eui[0],
                      (unsigned)(assoc != NULL),
                      (unsigned)childNwkAddr,
                      (unsigned)status,
                      (unsigned)_NIB.nwkDevAddress);
}

static void huedInsteonDiag_RequestVirtualChildTcLinkKeyWithDefault(uint8_t childIndex)
{
  uint8_t savedJoinKey[SEC_KEY_LEN];
  uint8_t readStatus;
  uint8_t writeDefaultStatus;
  uint8_t restoreStatus;

  readStatus = osal_nv_read(ZCD_NV_TCLK_JOIN_DEV, 0, SEC_KEY_LEN, savedJoinKey);
  writeDefaultStatus = osal_nv_write(ZCD_NV_TCLK_JOIN_DEV, SEC_KEY_LEN, (void *)defaultTCLinkKey);
  bdb_acceptNewTrustCenterLinkKey = TRUE;
  huedInsteonDiag_RequestVirtualChildTcLinkKey(childIndex);
  restoreStatus = osal_nv_write(ZCD_NV_TCLK_JOIN_DEV, SEC_KEY_LEN, savedJoinKey);

  huedInsteonDiag_Log("VREQDEF idx=%u read=%u write-default=%u restore=%u accept=%u",
                      (unsigned)(childIndex + 1),
                      (unsigned)readStatus,
                      (unsigned)writeDefaultStatus,
                      (unsigned)restoreStatus,
                      (unsigned)bdb_acceptNewTrustCenterLinkKey);
}

static void huedInsteonDiag_AdmitVirtualChild(uint8_t childIndex)
{
  associated_devices_t *assoc;
  const uint8_t *eui;
  uint8_t secStatus;
  afStatus_t annceStatus;

  if (childIndex >= HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT)
  {
    huedInsteonDiag_Log("ERR virtual-admit index=%u", (unsigned)childIndex);
    return;
  }

  huedInsteonDiag_MacVirtualChildAssoc(childIndex);
  eui = huedInsteonDiag_VirtualChildEui[childIndex];
  assoc = AssocGetWithExt((uint8_t *)eui);
  secStatus = FALSE;
  annceStatus = afStatus_FAILED;
  if (assoc != NULL)
  {
    huedInsteonDiag_VirtualChildLiveNwk[childIndex] = assoc->shortAddr;
    assoc->age = 0;
    assoc->endDev.deviceTimeout = TIMEOUT_DONT_AGE_OUT;
    assoc->timeoutCounter = TIMEOUT_DONT_AGE_OUT;
    assoc->keepaliveRcv = true;
    secStatus = ZDSecMgrNewDeviceEvent(assoc->shortAddr);
  }
  huedInsteonDiag_RequestVirtualChildTcLinkKey(childIndex);
  assoc = AssocGetWithExt((uint8_t *)eui);
  if (assoc != NULL)
  {
    annceStatus = huedInsteonDiag_AliasDeviceAnnce(assoc->shortAddr, assoc->shortAddr, eui);
  }

  huedInsteonDiag_Log("VADMIT idx=%u assoc=%u short=0x%04x sec-new=%u annce=%u",
                      (unsigned)(childIndex + 1),
                      (unsigned)(assoc != NULL),
                      (unsigned)((assoc != NULL) ? assoc->shortAddr : huedInsteonDiag_VirtualChildLiveNwk[childIndex]),
                      (unsigned)secStatus,
                      (unsigned)annceStatus);
}

static void huedInsteonDiag_AnnounceVirtualParentShort(uint8_t childIndex)
{
  const uint8_t *eui;
  uint16_t nwkAddr;
  afStatus_t status;

  if (childIndex >= HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT)
  {
    huedInsteonDiag_Log("ERR virtual-parent-short index=%u", (unsigned)childIndex);
    return;
  }

  eui = huedInsteonDiag_VirtualChildEui[childIndex];
  nwkAddr = _NIB.nwkDevAddress;
  status = huedInsteonDiag_AliasDeviceAnnce(nwkAddr, nwkAddr, eui);

  huedInsteonDiag_Log("VPARENT-ANNCE idx=%u nwk=0x%04x eui=%02x%02x%02x%02x%02x%02x%02x%02x annce=%u",
                      (unsigned)(childIndex + 1),
                      (unsigned)nwkAddr,
                      (unsigned)eui[7],
                      (unsigned)eui[6],
                      (unsigned)eui[5],
                      (unsigned)eui[4],
                      (unsigned)eui[3],
                      (unsigned)eui[2],
                      (unsigned)eui[1],
                      (unsigned)eui[0],
                      (unsigned)status);
}

static void huedInsteonDiag_Process(void)
{
  char command[32];
  uint8_t childIndex;

  if (!huedInsteonDiag_CommandReady)
  {
    return;
  }

  strncpy(command, huedInsteonDiag_Command, sizeof(command) - 1);
  command[sizeof(command) - 1] = '\\0';
  huedInsteonDiag_CommandReady = false;

  if ((strcmp(command, "commission") == 0) || (strcmp(command, "c") == 0))
  {
    zstack_bdbStartCommissioningReq_t req;
    req.commissioning_mode = zclSampleLight_BdbCommissioningModes;
    huedInsteonDiag_Log("CMD commission mode=0x%04x", (unsigned)req.commissioning_mode);
    Zstackapi_bdbStartCommissioningReq(appServiceTaskId, &req);
  }
  else if ((strcmp(command, "state") == 0) || (strcmp(command, "s") == 0))
  {
    huedInsteonDiag_LogState("cmd");
  }
  else if (strcmp(command, "reset") == 0)
  {
    huedInsteonDiag_Log("CMD reset-local");
    Zstackapi_bdbResetLocalActionReq(appServiceTaskId);
  }
  else if (strcmp(command, "vchildren") == 0)
  {
    for (childIndex = 0; childIndex < HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT; childIndex++)
    {
      huedInsteonDiag_AnnounceVirtualChild(childIndex);
    }
  }
  else if (huedInsteonDiag_ParseChildCommand(command, "vchild", &childIndex))
  {
    huedInsteonDiag_AnnounceVirtualChild(childIndex);
  }
  else if (strcmp(command, "vjoins") == 0)
  {
    for (childIndex = 0; childIndex < HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT; childIndex++)
    {
      huedInsteonDiag_ForwardVirtualChildJoin(childIndex);
    }
  }
  else if (huedInsteonDiag_ParseChildCommand(command, "vjoin", &childIndex))
  {
    huedInsteonDiag_ForwardVirtualChildJoin(childIndex);
  }
  else if (strcmp(command, "vnlmes") == 0)
  {
    for (childIndex = 0; childIndex < HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT; childIndex++)
    {
      huedInsteonDiag_NlmeVirtualChildJoin(childIndex);
    }
  }
  else if (huedInsteonDiag_ParseChildCommand(command, "vnlme", &childIndex))
  {
    huedInsteonDiag_NlmeVirtualChildJoin(childIndex);
  }
  else if (strcmp(command, "vsecs") == 0)
  {
    for (childIndex = 0; childIndex < HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT; childIndex++)
    {
      huedInsteonDiag_SecMgrVirtualChildJoin(childIndex);
    }
  }
  else if (huedInsteonDiag_ParseChildCommand(command, "vsec", &childIndex))
  {
    huedInsteonDiag_SecMgrVirtualChildJoin(childIndex);
  }
  else if (strcmp(command, "vassocs") == 0)
  {
    for (childIndex = 0; childIndex < HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT; childIndex++)
    {
      huedInsteonDiag_MacVirtualChildAssoc(childIndex);
    }
  }
  else if (huedInsteonDiag_ParseChildCommand(command, "vassoc", &childIndex))
  {
    huedInsteonDiag_MacVirtualChildAssoc(childIndex);
  }
  else if (strcmp(command, "vmacassocs") == 0)
  {
    for (childIndex = 0; childIndex < HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT; childIndex++)
    {
      huedInsteonDiag_OverAirMacVirtualChildAssoc(childIndex);
    }
  }
  else if (huedInsteonDiag_ParseChildCommand(command, "vmacassoc", &childIndex))
  {
    huedInsteonDiag_OverAirMacVirtualChildAssoc(childIndex);
  }
  else if (strcmp(command, "vreqkeys") == 0)
  {
    for (childIndex = 0; childIndex < HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT; childIndex++)
    {
      huedInsteonDiag_RequestVirtualChildTcLinkKey(childIndex);
    }
  }
  else if (huedInsteonDiag_ParseChildCommand(command, "vreqkey", &childIndex))
  {
    huedInsteonDiag_RequestVirtualChildTcLinkKey(childIndex);
  }
  else if (strcmp(command, "vreqdefs") == 0)
  {
    for (childIndex = 0; childIndex < HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT; childIndex++)
    {
      huedInsteonDiag_RequestVirtualChildTcLinkKeyWithDefault(childIndex);
    }
  }
  else if (huedInsteonDiag_ParseChildCommand(command, "vreqdef", &childIndex))
  {
    huedInsteonDiag_RequestVirtualChildTcLinkKeyWithDefault(childIndex);
  }
  else if (strcmp(command, "vadmits") == 0)
  {
    for (childIndex = 0; childIndex < HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT; childIndex++)
    {
      huedInsteonDiag_AdmitVirtualChild(childIndex);
    }
  }
  else if (huedInsteonDiag_ParseChildCommand(command, "vadmit", &childIndex))
  {
    huedInsteonDiag_AdmitVirtualChild(childIndex);
  }
  else if (strcmp(command, "vparents") == 0)
  {
    for (childIndex = 0; childIndex < HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT; childIndex++)
    {
      huedInsteonDiag_AnnounceVirtualParentShort(childIndex);
    }
  }
  else if (huedInsteonDiag_ParseChildCommand(command, "vparent", &childIndex))
  {
    huedInsteonDiag_AnnounceVirtualParentShort(childIndex);
  }
  else if (strcmp(command, "vchild1") == 0)
  {
    huedInsteonDiag_AnnounceVirtualChild(0);
  }
  else if (strcmp(command, "vchild2") == 0)
  {
    huedInsteonDiag_AnnounceVirtualChild(1);
  }
  else if (strcmp(command, "vchild3") == 0)
  {
    huedInsteonDiag_AnnounceVirtualChild(2);
  }
  else if (strcmp(command, "vchildren") == 0)
  {
    huedInsteonDiag_AnnounceVirtualChild(0);
    huedInsteonDiag_AnnounceVirtualChild(1);
    huedInsteonDiag_AnnounceVirtualChild(2);
  }
  else if (strcmp(command, "vjoin1") == 0)
  {
    huedInsteonDiag_ForwardVirtualChildJoin(0);
  }
  else if (strcmp(command, "vjoin2") == 0)
  {
    huedInsteonDiag_ForwardVirtualChildJoin(1);
  }
  else if (strcmp(command, "vjoin3") == 0)
  {
    huedInsteonDiag_ForwardVirtualChildJoin(2);
  }
  else if (strcmp(command, "vjoins") == 0)
  {
    huedInsteonDiag_ForwardVirtualChildJoin(0);
    huedInsteonDiag_ForwardVirtualChildJoin(1);
    huedInsteonDiag_ForwardVirtualChildJoin(2);
  }
  else if (strcmp(command, "vnlme1") == 0)
  {
    huedInsteonDiag_NlmeVirtualChildJoin(0);
  }
  else if (strcmp(command, "vnlme2") == 0)
  {
    huedInsteonDiag_NlmeVirtualChildJoin(1);
  }
  else if (strcmp(command, "vnlme3") == 0)
  {
    huedInsteonDiag_NlmeVirtualChildJoin(2);
  }
  else if (strcmp(command, "vnlmes") == 0)
  {
    huedInsteonDiag_NlmeVirtualChildJoin(0);
    huedInsteonDiag_NlmeVirtualChildJoin(1);
    huedInsteonDiag_NlmeVirtualChildJoin(2);
  }
  else if (strcmp(command, "vsec1") == 0)
  {
    huedInsteonDiag_SecMgrVirtualChildJoin(0);
  }
  else if (strcmp(command, "vsec2") == 0)
  {
    huedInsteonDiag_SecMgrVirtualChildJoin(1);
  }
  else if (strcmp(command, "vsec3") == 0)
  {
    huedInsteonDiag_SecMgrVirtualChildJoin(2);
  }
  else if (strcmp(command, "vsecs") == 0)
  {
    huedInsteonDiag_SecMgrVirtualChildJoin(0);
    huedInsteonDiag_SecMgrVirtualChildJoin(1);
    huedInsteonDiag_SecMgrVirtualChildJoin(2);
  }
  else if (strcmp(command, "vassoc1") == 0)
  {
    huedInsteonDiag_MacVirtualChildAssoc(0);
  }
  else if (strcmp(command, "vassoc2") == 0)
  {
    huedInsteonDiag_MacVirtualChildAssoc(1);
  }
  else if (strcmp(command, "vassoc3") == 0)
  {
    huedInsteonDiag_MacVirtualChildAssoc(2);
  }
  else if (strcmp(command, "vassocs") == 0)
  {
    huedInsteonDiag_MacVirtualChildAssoc(0);
    huedInsteonDiag_MacVirtualChildAssoc(1);
    huedInsteonDiag_MacVirtualChildAssoc(2);
  }
  else if (strcmp(command, "vmacassoc1") == 0)
  {
    huedInsteonDiag_OverAirMacVirtualChildAssoc(0);
  }
  else if (strcmp(command, "vmacassoc2") == 0)
  {
    huedInsteonDiag_OverAirMacVirtualChildAssoc(1);
  }
  else if (strcmp(command, "vmacassoc3") == 0)
  {
    huedInsteonDiag_OverAirMacVirtualChildAssoc(2);
  }
  else if (strcmp(command, "vmacassocs") == 0)
  {
    huedInsteonDiag_OverAirMacVirtualChildAssoc(0);
    huedInsteonDiag_OverAirMacVirtualChildAssoc(1);
    huedInsteonDiag_OverAirMacVirtualChildAssoc(2);
  }
  else if (strcmp(command, "vrestore") == 0)
  {
    huedInsteonDiag_RestoreParentIdentity();
  }
  else if (strcmp(command, "vreqkey1") == 0)
  {
    huedInsteonDiag_RequestVirtualChildTcLinkKey(0);
  }
  else if (strcmp(command, "vreqkey2") == 0)
  {
    huedInsteonDiag_RequestVirtualChildTcLinkKey(1);
  }
  else if (strcmp(command, "vreqkey3") == 0)
  {
    huedInsteonDiag_RequestVirtualChildTcLinkKey(2);
  }
  else if (strcmp(command, "vreqkeys") == 0)
  {
    huedInsteonDiag_RequestVirtualChildTcLinkKey(0);
    huedInsteonDiag_RequestVirtualChildTcLinkKey(1);
    huedInsteonDiag_RequestVirtualChildTcLinkKey(2);
  }
  else if (strcmp(command, "vreqdef1") == 0)
  {
    huedInsteonDiag_RequestVirtualChildTcLinkKeyWithDefault(0);
  }
  else if (strcmp(command, "vreqdef2") == 0)
  {
    huedInsteonDiag_RequestVirtualChildTcLinkKeyWithDefault(1);
  }
  else if (strcmp(command, "vreqdef3") == 0)
  {
    huedInsteonDiag_RequestVirtualChildTcLinkKeyWithDefault(2);
  }
  else if (strcmp(command, "vreqdefs") == 0)
  {
    huedInsteonDiag_RequestVirtualChildTcLinkKeyWithDefault(0);
    huedInsteonDiag_RequestVirtualChildTcLinkKeyWithDefault(1);
    huedInsteonDiag_RequestVirtualChildTcLinkKeyWithDefault(2);
  }
  else if (strcmp(command, "vadmit1") == 0)
  {
    huedInsteonDiag_AdmitVirtualChild(0);
  }
  else if (strcmp(command, "vadmit2") == 0)
  {
    huedInsteonDiag_AdmitVirtualChild(1);
  }
  else if (strcmp(command, "vadmit3") == 0)
  {
    huedInsteonDiag_AdmitVirtualChild(2);
  }
  else if (strcmp(command, "vadmits") == 0)
  {
    huedInsteonDiag_AdmitVirtualChild(0);
    huedInsteonDiag_AdmitVirtualChild(1);
    huedInsteonDiag_AdmitVirtualChild(2);
  }
  else if (strcmp(command, "vparent1") == 0)
  {
    huedInsteonDiag_AnnounceVirtualParentShort(0);
  }
  else if (strcmp(command, "vparent2") == 0)
  {
    huedInsteonDiag_AnnounceVirtualParentShort(1);
  }
  else if (strcmp(command, "vparent3") == 0)
  {
    huedInsteonDiag_AnnounceVirtualParentShort(2);
  }
  else if (strcmp(command, "vparents") == 0)
  {
    huedInsteonDiag_AnnounceVirtualParentShort(0);
    huedInsteonDiag_AnnounceVirtualParentShort(1);
    huedInsteonDiag_AnnounceVirtualParentShort(2);
  }
  else if (strcmp(command, "help") == 0)
  {
    huedInsteonDiag_Log("HELP commission|c state|s reset vchild1 vchild2 vchild3 vchildren vjoin1 vjoin2 vjoin3 vjoins vnlme1 vnlme2 vnlme3 vnlmes vsec1 vsec2 vsec3 vsecs vassoc1 vassoc2 vassoc3 vassocs vmacassoc1 vmacassoc2 vmacassoc3 vmacassocs vrestore vreqkey1 vreqkey2 vreqkey3 vreqkeys vreqdef1 vreqdef2 vreqdef3 vreqdefs vadmit1 vadmit2 vadmit3 vadmits vparent1 vparent2 vparent3 vparents help");
  }
  else
  {
    huedInsteonDiag_Log("ERR unknown=%s", command);
  }

  appServiceTaskEvents &= ~HUEDINSTEON_DIAG_EVT;
}
#endif
""",
        )
        text = replace_once(
            text,
            "#ifndef CUI_DISABLE\n            //Process the events that the UI may have\n            zclsampleApp_ui_event_loop();\n#endif\n\n            if ( appServiceTaskEvents & SAMPLEAPP_DISCOVERY_TIMEOUT_EVT )\n",
            "#ifndef CUI_DISABLE\n            //Process the events that the UI may have\n            zclsampleApp_ui_event_loop();\n#endif\n\n#ifdef HUEDINSTEON_DIAG\n            if ( appServiceTaskEvents & HUEDINSTEON_DIAG_EVT )\n            {\n              huedInsteonDiag_Process();\n            }\n#endif\n\n            if ( appServiceTaskEvents & SAMPLEAPP_DISCOVERY_TIMEOUT_EVT )\n",
        )
        text = replace_once(
            text,
            "        case zstackmsg_CmdIDs_DEV_STATE_CHANGE_IND:\n        {\n#if !defined(CUI_DISABLE) || defined(USE_DMM) && defined(BLE_START)\n",
            "        case zstackmsg_CmdIDs_DEV_STATE_CHANGE_IND:\n        {\n#ifdef HUEDINSTEON_DIAG\n            zstackmsg_devStateChangeInd_t *diagStateInd = (zstackmsg_devStateChangeInd_t *)pMsg;\n            huedInsteonDiag_Log(\"DEV state=%u\", (unsigned)diagStateInd->req.state);\n            huedInsteonDiag_LogState(\"dev-state\");\n#endif\n#if !defined(CUI_DISABLE) || defined(USE_DMM) && defined(BLE_START)\n",
        )
        text = replace_once(
            text,
            "        case zstackmsg_CmdIDs_BDB_CBKE_TC_LINK_KEY_EXCHANGE_IND:\n        {\n          zstack_bdbCBKETCLinkKeyExchangeAttemptReq_t zstack_bdbCBKETCLinkKeyExchangeAttemptReq;\n",
            "        case zstackmsg_CmdIDs_BDB_CBKE_TC_LINK_KEY_EXCHANGE_IND:\n        {\n#ifdef HUEDINSTEON_DIAG\n          huedInsteonDiag_Log(\"TCLK cbke-ind fallback=aps-key\");\n          huedInsteonDiag_LogState(\"tclk-cbke\");\n#endif\n          zstack_bdbCBKETCLinkKeyExchangeAttemptReq_t zstack_bdbCBKETCLinkKeyExchangeAttemptReq;\n",
        )
        text = replace_once(
            text,
            "        case zstackmsg_CmdIDs_DEV_PERMIT_JOIN_IND:\n        case zstackmsg_CmdIDs_BDB_TC_LINK_KEY_EXCHANGE_NOTIFICATION_IND:\n        case zstackmsg_CmdIDs_AF_DATA_CONFIRM_IND:\n",
            "        case zstackmsg_CmdIDs_DEV_PERMIT_JOIN_IND:\n          break;\n\n        case zstackmsg_CmdIDs_BDB_TC_LINK_KEY_EXCHANGE_NOTIFICATION_IND:\n        {\n#ifdef HUEDINSTEON_DIAG\n          zstackmsg_bdbTCLinkKeyExchangeInd_t *tclkInd = (zstackmsg_bdbTCLinkKeyExchangeInd_t *)pMsg;\n          huedInsteonDiag_Log(\"TCLK notify status=%u/%s nwk=0x%04x eui=%02x%02x%02x%02x%02x%02x%02x%02x\",\n                              (unsigned)tclkInd->Req.status,\n                              huedInsteonDiag_TclkStatusName(tclkInd->Req.status),\n                              (unsigned)tclkInd->Req.nwkAddr,\n                              (unsigned)tclkInd->Req.extAddr[7],\n                              (unsigned)tclkInd->Req.extAddr[6],\n                              (unsigned)tclkInd->Req.extAddr[5],\n                              (unsigned)tclkInd->Req.extAddr[4],\n                              (unsigned)tclkInd->Req.extAddr[3],\n                              (unsigned)tclkInd->Req.extAddr[2],\n                              (unsigned)tclkInd->Req.extAddr[1],\n                              (unsigned)tclkInd->Req.extAddr[0]);\n          huedInsteonDiag_LogState(\"tclk-notify\");\n#endif\n        }\n        break;\n\n        case zstackmsg_CmdIDs_AF_DATA_CONFIRM_IND:\n",
        )
        text = replace_once(
            text,
            "static void zclSampleLight_ProcessCommissioningStatus(bdbCommissioningModeMsg_t *bdbCommissioningModeMsg)\n{\n  switch(bdbCommissioningModeMsg->bdbCommissioningMode)\n",
            "static void zclSampleLight_ProcessCommissioningStatus(bdbCommissioningModeMsg_t *bdbCommissioningModeMsg)\n{\n#ifdef HUEDINSTEON_DIAG\n  huedInsteonDiag_Log(\"BDB mode=%u/%s status=%u/%s\",\n                      (unsigned)bdbCommissioningModeMsg->bdbCommissioningMode,\n                      huedInsteonDiag_BdbModeName(bdbCommissioningModeMsg->bdbCommissioningMode),\n                      (unsigned)bdbCommissioningModeMsg->bdbCommissioningStatus,\n                      huedInsteonDiag_BdbStatusName(bdbCommissioningModeMsg->bdbCommissioningStatus));\n  huedInsteonDiag_LogState(\"bdb\");\n#endif\n  switch(bdbCommissioningModeMsg->bdbCommissioningMode)\n",
        )
        virtual_child_storage_count = max(1, virtual_child_count)
        virtual_child_nwks = ",\n  ".join(
            f"0x{0x7E01 + i:04x}" for i in range(virtual_child_storage_count)
        )
        virtual_child_euis = ",\n  ".join(
            "{"
            + ", ".join(
                f"0x{byte:02x}"
                for byte in [
                    0xA1 + i,
                    0x6F,
                    0x12,
                    0x3A,
                    0x00,
                    0x4B,
                    0x12,
                    0x00,
                ]
            )
            + "}"
            for i in range(virtual_child_storage_count)
        )
        virtual_nwk_seqs = ", ".join(
            f"0x{(0x21 + (0x20 * i)) & 0xff:02x}"
            for i in range(virtual_child_storage_count)
        )
        virtual_aps_seqs = ", ".join(
            f"0x{(0x22 + (0x20 * i)) & 0xff:02x}"
            for i in range(virtual_child_storage_count)
        )
        text = (
            text.replace("__HUEDINSTEON_VIRTUAL_CHILD_NWKS__", virtual_child_nwks)
            .replace("__HUEDINSTEON_VIRTUAL_CHILD_EUIS__", virtual_child_euis)
            .replace("__HUEDINSTEON_VIRTUAL_NWK_SEQS__", virtual_nwk_seqs)
            .replace("__HUEDINSTEON_VIRTUAL_APS_SEQS__", virtual_aps_seqs)
            .replace("__HUEDINSTEON_VIRTUAL_CHILD_COUNT__", str(virtual_child_count))
            .replace("__HUEDINSTEON_VIRTUAL_CHILD_STORAGE_COUNT__", str(virtual_child_storage_count))
        )

    if three_endpoints:
        text = replace_once(
            text,
            "static endPointDesc_t  zclSampleLightEpDesc = {0};\n",
            """#define HUEDINSTEON_ENDPOINT_COUNT 3

static const uint8_t huedInsteon_Endpoints[HUEDINSTEON_ENDPOINT_COUNT] = {1, 2, 3};

static const cId_t huedInsteon_InClusterList[] =
{
  ZCL_CLUSTER_ID_GENERAL_BASIC,
  ZCL_CLUSTER_ID_GENERAL_IDENTIFY,
  ZCL_CLUSTER_ID_GENERAL_GROUPS,
  ZCL_CLUSTER_ID_GENERAL_SCENES,
  ZCL_CLUSTER_ID_GENERAL_ON_OFF
#ifdef ZCL_LEVEL_CTRL
  , ZCL_CLUSTER_ID_GENERAL_LEVEL_CONTROL
#endif
};

#define HUEDINSTEON_MAX_INCLUSTERS (sizeof(huedInsteon_InClusterList) / sizeof(huedInsteon_InClusterList[0]))

static SimpleDescriptionFormat_t huedInsteon_SimpleDesc[HUEDINSTEON_ENDPOINT_COUNT] =
{
  {
    1,
    ZCL_HA_PROFILE_ID,
#ifdef ZCL_LEVEL_CTRL
    ZCL_DEVICEID_DIMMABLE_LIGHT,
#else
    ZCL_DEVICEID_ON_OFF_LIGHT,
#endif
    1,
    0,
    HUEDINSTEON_MAX_INCLUSTERS,
    (cId_t *)huedInsteon_InClusterList,
    0,
    NULL
  },
  {
    2,
    ZCL_HA_PROFILE_ID,
#ifdef ZCL_LEVEL_CTRL
    ZCL_DEVICEID_DIMMABLE_LIGHT,
#else
    ZCL_DEVICEID_ON_OFF_LIGHT,
#endif
    1,
    0,
    HUEDINSTEON_MAX_INCLUSTERS,
    (cId_t *)huedInsteon_InClusterList,
    0,
    NULL
  },
  {
    3,
    ZCL_HA_PROFILE_ID,
#ifdef ZCL_LEVEL_CTRL
    ZCL_DEVICEID_DIMMABLE_LIGHT,
#else
    ZCL_DEVICEID_ON_OFF_LIGHT,
#endif
    1,
    0,
    HUEDINSTEON_MAX_INCLUSTERS,
    (cId_t *)huedInsteon_InClusterList,
    0,
    NULL
  }
};

static endPointDesc_t zclSampleLightEpDesc[HUEDINSTEON_ENDPOINT_COUNT] = {{0}};
""",
        )
    text = replace_once(
        text,
        "static uint32_t gSampleLightInfoLine;\n#endif\n",
        (
            "static uint32_t gSampleLightInfoLine;\n"
            'static const char *zclSampleLight_LastCommand = "boot";\n'
            "#endif\n"
        ),
    )
    text = replace_once(
        text,
        "  if( ((zclSampleLight_getOnOffAttribute() == LIGHT_ON) && (OnOff == LIGHT_ON)) ||\n",
        (
            "#ifdef HUEDINSTEON_DIAG\n"
            "  huedInsteonDiag_RecordVirtualCommand(huedInsteonDiag_IncomingChildIndex(pPtr), OnOff, zclSampleLight_getCurrentLevelAttribute());\n"
            "  if ( cmd == COMMAND_ON_OFF_ON )\n"
            "  {\n"
            '    huedInsteonDiag_EmitCommand(pPtr, "on", false, 0, 0);\n'
            "  }\n"
            "  else if ( cmd == COMMAND_ON_OFF_OFF )\n"
            "  {\n"
            '    huedInsteonDiag_EmitCommand(pPtr, "off", false, 0, 0);\n'
            "  }\n"
            "  else if ( cmd == COMMAND_ON_OFF_TOGGLE )\n"
            "  {\n"
            '    huedInsteonDiag_EmitCommand(pPtr, "toggle", false, 0, 0);\n'
            "  }\n"
            "#endif\n"
            "\n"
            "#ifndef CUI_DISABLE\n"
            "  if ( cmd == COMMAND_ON_OFF_ON )\n"
            "  {\n"
            '    zclSampleLight_LastCommand = "on";\n'
            "  }\n"
            "  else if ( cmd == COMMAND_ON_OFF_OFF )\n"
            "  {\n"
            '    zclSampleLight_LastCommand = "off";\n'
            "  }\n"
            "  else if ( cmd == COMMAND_ON_OFF_TOGGLE )\n"
            "  {\n"
            '    zclSampleLight_LastCommand = "toggle";\n'
            "  }\n"
            "#endif\n"
            "\n"
            "  if( ((zclSampleLight_getOnOffAttribute() == LIGHT_ON) && (OnOff == LIGHT_ON)) ||\n"
        ),
    )
    text = replace_once(
        text,
        "    // if light is off and received an off command, ignore it.\n    return;\n",
        (
            "    // if light is off and received an off command, ignore it.\n"
            "#ifndef CUI_DISABLE\n"
            "    zclSampleLight_UpdateStatusLine();\n"
            "#endif\n"
            "    return;\n"
        ),
    )
    text = replace_once(
        text,
        "  zclSampleLight_WithOnOff = pCmd->withOnOff;\n  zclSampleLight_MoveBasedOnTime( pCmd->level, pCmd->transitionTime );\n}\n",
        (
            "  zclSampleLight_WithOnOff = pCmd->withOnOff;\n"
            "#ifdef HUEDINSTEON_DIAG\n"
            "  huedInsteonDiag_RecordVirtualCommand(huedInsteonDiag_IncomingChildIndex(pPtr), zclSampleLight_getOnOffAttribute(), pCmd->level);\n"
            '  huedInsteonDiag_EmitCommand(pPtr, "level", true, pCmd->level, ((uint32_t)pCmd->transitionTime) * 100UL);\n'
            "#endif\n"
            "  zclSampleLight_MoveBasedOnTime( pCmd->level, pCmd->transitionTime );\n"
            "#ifndef CUI_DISABLE\n"
            '  zclSampleLight_LastCommand = "move-to-level";\n'
            "  zclSampleLight_UpdateStatusLine();\n"
            "#endif\n"
            "}\n"
        ),
    )
    text = replace_once(
        text,
        "  rate = (uint32_t)100 * pCmd->rate;\n  zclSampleLight_MoveBasedOnRate( newLevel, rate );\n}\n",
        (
            "  rate = (uint32_t)100 * pCmd->rate;\n"
            "#ifdef HUEDINSTEON_DIAG\n"
            "  huedInsteonDiag_RecordVirtualCommand(huedInsteonDiag_IncomingChildIndex(pPtr), zclSampleLight_getOnOffAttribute(), newLevel);\n"
            '  huedInsteonDiag_EmitCommand(pPtr, "move", true, newLevel, 0);\n'
            "#endif\n"
            "  zclSampleLight_MoveBasedOnRate( newLevel, rate );\n"
            "#ifndef CUI_DISABLE\n"
            '  zclSampleLight_LastCommand = "move";\n'
            "  zclSampleLight_UpdateStatusLine();\n"
            "#endif\n"
            "}\n"
        ),
    )
    text = replace_once(
        text,
        "  zclSampleLight_WithOnOff = pCmd->withOnOff;\n  zclSampleLight_MoveBasedOnTime( newLevel, pCmd->transitionTime );\n}\n",
        (
            "  zclSampleLight_WithOnOff = pCmd->withOnOff;\n"
            "#ifdef HUEDINSTEON_DIAG\n"
            "  huedInsteonDiag_RecordVirtualCommand(huedInsteonDiag_IncomingChildIndex(pPtr), zclSampleLight_getOnOffAttribute(), newLevel);\n"
            '  huedInsteonDiag_EmitCommand(pPtr, "step", true, newLevel, ((uint32_t)pCmd->transitionTime) * 100UL);\n'
            "#endif\n"
            "  zclSampleLight_MoveBasedOnTime( newLevel, pCmd->transitionTime );\n"
            "#ifndef CUI_DISABLE\n"
            '  zclSampleLight_LastCommand = "step";\n'
            "  zclSampleLight_UpdateStatusLine();\n"
            "#endif\n"
            "}\n"
        ),
    )
    text = replace_once(
        text,
        "  zclSampleLight_LevelRemainingTime = 0;\n}\n",
        (
            "  zclSampleLight_LevelRemainingTime = 0;\n"
            "#ifdef HUEDINSTEON_DIAG\n"
            "  huedInsteonDiag_RecordVirtualCommand(huedInsteonDiag_IncomingChildIndex(pPtr), zclSampleLight_getOnOffAttribute(), zclSampleLight_getCurrentLevelAttribute());\n"
            '  huedInsteonDiag_EmitCommand(pPtr, "stop", false, 0, 0);\n'
            "#endif\n"
            "#ifndef CUI_DISABLE\n"
            '  zclSampleLight_LastCommand = "stop";\n'
            "  zclSampleLight_UpdateStatusLine();\n"
            "#endif\n"
            "}\n"
        ),
    )
    text = replace_once(
        text,
        '    strcat(lineFormat, " ["CUI_COLOR_YELLOW"Level"CUI_COLOR_RESET"] %03d");\n'
        "    CUI_statusLinePrintf(gCuiHandle, gSampleLightInfoLine, lineFormat, zclSampleLight_getCurrentLevelAttribute());\n"
        "#else\n"
        "    CUI_statusLinePrintf(gCuiHandle, gSampleLightInfoLine, lineFormat);\n",
        (
            '    strcat(lineFormat, " ["CUI_COLOR_YELLOW"Level"CUI_COLOR_RESET"] %03d ["CUI_COLOR_YELLOW"Last"CUI_COLOR_RESET"] %s");\n'
            "    CUI_statusLinePrintf(gCuiHandle, gSampleLightInfoLine, lineFormat, zclSampleLight_getCurrentLevelAttribute(), zclSampleLight_LastCommand);\n"
            "#else\n"
            '    strcat(lineFormat, " ["CUI_COLOR_YELLOW"Last"CUI_COLOR_RESET"] %s");\n'
            "    CUI_statusLinePrintf(gCuiHandle, gSampleLightInfoLine, lineFormat, zclSampleLight_LastCommand);\n"
        ),
    )
    if diag_uart and not three_endpoints:
        text = replace_once(
            text,
            "static void zclSampleLight_LevelControlMoveToLevelCB( zclLCMoveToLevel_t *pCmd )\n{\n",
            (
                "static void zclSampleLight_LevelControlMoveToLevelCB( zclLCMoveToLevel_t *pCmd )\n"
                "{\n"
                "  afIncomingMSGPacket_t *pPtr = zcl_getRawAFMsg();\n"
            ),
        )
        text = replace_once(
            text,
            "static void zclSampleLight_LevelControlMoveCB( zclLCMove_t *pCmd )\n{\n",
            (
                "static void zclSampleLight_LevelControlMoveCB( zclLCMove_t *pCmd )\n"
                "{\n"
                "  afIncomingMSGPacket_t *pPtr = zcl_getRawAFMsg();\n"
            ),
        )
        text = replace_once(
            text,
            "static void zclSampleLight_LevelControlStepCB( zclLCStep_t *pCmd )\n{\n",
            (
                "static void zclSampleLight_LevelControlStepCB( zclLCStep_t *pCmd )\n"
                "{\n"
                "  afIncomingMSGPacket_t *pPtr = zcl_getRawAFMsg();\n"
            ),
        )
        text = replace_once(
            text,
            "static void zclSampleLight_LevelControlStopCB( zclLCStop_t *pCmd )\n{\n",
            (
                "static void zclSampleLight_LevelControlStopCB( zclLCStop_t *pCmd )\n"
                "{\n"
                "  afIncomingMSGPacket_t *pPtr = zcl_getRawAFMsg();\n"
            ),
        )
    if three_endpoints:
        if endpoint_specific_state:
            text = replace_once(
                text,
                "static void zclSampleLight_UpdateLedState(void);\n",
                (
                    "static void zclSampleLight_UpdateLedState(void);\n"
                    "extern CONST zclAttrRec_t *zclSampleLight_AttrsForEndpoint(uint8_t endpoint);\n"
                    "extern void zclSampleLight_SetCurrentEndpoint(uint8_t endpoint);\n"
                ),
            )
        else:
            text = replace_once(
                text,
                "static void zclSampleLight_UpdateLedState(void);\n",
                (
                    "static void zclSampleLight_UpdateLedState(void);\n"
                    "static void zclSampleLight_SetCurrentEndpoint(uint8_t endpoint) { (void)endpoint; }\n"
                ),
            )
        attr_list_expr = (
            "zclSampleLight_AttrsForEndpoint(endpoint)"
            if endpoint_specific_state
            else "zclSampleLight_Attrs"
        )
        text = replace_once(
            text,
            """  //Register Endpoint
  zclSampleLightEpDesc.endPoint = SAMPLELIGHT_ENDPOINT;
  zclSampleLightEpDesc.simpleDesc = &zclSampleLight_SimpleDesc;
  zclport_registerEndpoint(appServiceTaskId, &zclSampleLightEpDesc);

#if defined (ENABLE_GREENPOWER_COMBO_BASIC)
  zclGp_RegisterCBForGPDCommand(&zclSampleLight_GpSink_AppCallbacks);
#endif


  // Register the ZCL General Cluster Library callback functions
  zclGeneral_RegisterCmdCallbacks( SAMPLELIGHT_ENDPOINT, &zclSampleLight_CmdCallbacks );

  // Register the application's attribute list and reset to default values
  zclSampleLight_ResetAttributesToDefaultValues();
  zcl_registerAttrList( SAMPLELIGHT_ENDPOINT, zclSampleLight_NumAttributes, zclSampleLight_Attrs );

  // Register the Application to receive the unprocessed Foundation command/response messages
  zclport_registerZclHandleExternal(SAMPLELIGHT_ENDPOINT, zclSampleLight_ProcessIncomingMsg);
""",
            """  // Register three Hue-visible Dimmable Light endpoints.
  for (uint8_t i = 0; i < HUEDINSTEON_ENDPOINT_COUNT; ++i)
  {
    uint8_t endpoint = huedInsteon_Endpoints[i];

    zclSampleLightEpDesc[i].endPoint = endpoint;
    zclSampleLightEpDesc[i].simpleDesc = &huedInsteon_SimpleDesc[i];
    zclport_registerEndpoint(appServiceTaskId, &zclSampleLightEpDesc[i]);

    zclGeneral_RegisterCmdCallbacks(endpoint, &zclSampleLight_CmdCallbacks);
  }

#if defined (ENABLE_GREENPOWER_COMBO_BASIC)
  zclGp_RegisterCBForGPDCommand(&zclSampleLight_GpSink_AppCallbacks);
#endif

  // Register shared prototype attributes for all endpoints. The next pass
  // replaces these with endpoint-specific state.
  zclSampleLight_ResetAttributesToDefaultValues();
  for (uint8_t i = 0; i < HUEDINSTEON_ENDPOINT_COUNT; ++i)
  {
    uint8_t endpoint = huedInsteon_Endpoints[i];

    zcl_registerAttrList(endpoint, zclSampleLight_NumAttributes, ATTR_LIST_EXPR);
    zclport_registerZclHandleExternal(endpoint, zclSampleLight_ProcessIncomingMsg);
  }
""".replace("ATTR_LIST_EXPR", attr_list_expr),
        )
        text = replace_once(
            text,
            """#ifdef ZCL_DISCOVER
  // Register the application's command list
  zcl_registerCmdList( SAMPLELIGHT_ENDPOINT, zclCmdsArraySize, zclSampleLight_Cmds );
#endif

  zcl_registerReadWriteCB(SAMPLELIGHT_ENDPOINT,zclSampleLight_ReadWriteAttrCB,NULL);
""",
            """#ifdef ZCL_DISCOVER
  // Register the application's command list
  for (uint8_t i = 0; i < HUEDINSTEON_ENDPOINT_COUNT; ++i)
  {
    zcl_registerCmdList(huedInsteon_Endpoints[i], zclCmdsArraySize, zclSampleLight_Cmds);
  }
#endif

  for (uint8_t i = 0; i < HUEDINSTEON_ENDPOINT_COUNT; ++i)
  {
    zcl_registerReadWriteCB(huedInsteon_Endpoints[i], zclSampleLight_ReadWriteAttrCB, NULL);
  }
""",
        )
        text = replace_once(
            text,
            """#ifdef BDB_REPORTING
  //Adds the default configuration values for the temperature attribute of the ZCL_CLUSTER_ID_MS_TEMPERATURE_MEASUREMENT cluster, for endpoint SAMPLETEMPERATURESENSOR_ENDPOINT
  //Default maxReportingInterval value is 10 seconds
  //Default minReportingInterval value is 3 seconds
  //Default reportChange value is 300 (3 degrees)
  Req.attrID = ATTRID_ON_OFF_ON_OFF;
  Req.cluster = ZCL_CLUSTER_ID_GENERAL_ON_OFF;
  Req.endpoint = SAMPLELIGHT_ENDPOINT;
  Req.maxReportInt = 10;
  Req.minReportInt = 0;
  OsalPort_memcpy(Req.reportableChange,reportableChange,BDBREPORTING_MAX_ANALOG_ATTR_SIZE);

  Zstackapi_bdbRepAddAttrCfgRecordDefaultToListReq(appServiceTaskId,&Req);

#ifdef ZCL_LEVEL_CTRL
  Req.attrID = ATTRID_LEVEL_CURRENT_LEVEL;
  Req.cluster = ZCL_CLUSTER_ID_GENERAL_LEVEL_CONTROL;
  Req.endpoint = SAMPLELIGHT_ENDPOINT;
  Req.maxReportInt = 10;
  Req.minReportInt = 0;
  OsalPort_memcpy(Req.reportableChange,reportableChange,BDBREPORTING_MAX_ANALOG_ATTR_SIZE);

  Zstackapi_bdbRepAddAttrCfgRecordDefaultToListReq(appServiceTaskId,&Req);
#endif

#endif
""",
            """#ifdef BDB_REPORTING
  for (uint8_t i = 0; i < HUEDINSTEON_ENDPOINT_COUNT; ++i)
  {
    uint8_t endpoint = huedInsteon_Endpoints[i];

    Req.attrID = ATTRID_ON_OFF_ON_OFF;
    Req.cluster = ZCL_CLUSTER_ID_GENERAL_ON_OFF;
    Req.endpoint = endpoint;
    Req.maxReportInt = 10;
    Req.minReportInt = 0;
    OsalPort_memcpy(Req.reportableChange, reportableChange, BDBREPORTING_MAX_ANALOG_ATTR_SIZE);
    Zstackapi_bdbRepAddAttrCfgRecordDefaultToListReq(appServiceTaskId, &Req);

#ifdef ZCL_LEVEL_CTRL
    Req.attrID = ATTRID_LEVEL_CURRENT_LEVEL;
    Req.cluster = ZCL_CLUSTER_ID_GENERAL_LEVEL_CONTROL;
    Req.endpoint = endpoint;
    Req.maxReportInt = 10;
    Req.minReportInt = 0;
    OsalPort_memcpy(Req.reportableChange, reportableChange, BDBREPORTING_MAX_ANALOG_ATTR_SIZE);
    Zstackapi_bdbRepAddAttrCfgRecordDefaultToListReq(appServiceTaskId, &Req);
#endif
  }
#endif
""",
        )
        text = replace_once(
            text,
            "static void zclSampleLight_OnOffCB( uint8_t cmd )\n{\n  afIncomingMSGPacket_t *pPtr = zcl_getRawAFMsg();\n",
            (
                "static void zclSampleLight_OnOffCB( uint8_t cmd )\n"
                "{\n"
                "  afIncomingMSGPacket_t *pPtr = zcl_getRawAFMsg();\n"
                "  if (pPtr != NULL)\n"
                "  {\n"
                "    zclSampleLight_SetCurrentEndpoint(pPtr->endPoint);\n"
                "  }\n"
            ),
        )
        text = replace_once(
            text,
            "static void zclSampleLight_LevelControlMoveToLevelCB( zclLCMoveToLevel_t *pCmd )\n{\n",
            (
                "static void zclSampleLight_LevelControlMoveToLevelCB( zclLCMoveToLevel_t *pCmd )\n"
                "{\n"
                "  afIncomingMSGPacket_t *pPtr = zcl_getRawAFMsg();\n"
                "  if (pPtr != NULL)\n"
                "  {\n"
                "    zclSampleLight_SetCurrentEndpoint(pPtr->endPoint);\n"
                "  }\n"
            ),
        )
        text = replace_once(
            text,
            "static void zclSampleLight_LevelControlMoveCB( zclLCMove_t *pCmd )\n{\n",
            (
                "static void zclSampleLight_LevelControlMoveCB( zclLCMove_t *pCmd )\n"
                "{\n"
                "  afIncomingMSGPacket_t *pPtr = zcl_getRawAFMsg();\n"
                "  if (pPtr != NULL)\n"
                "  {\n"
                "    zclSampleLight_SetCurrentEndpoint(pPtr->endPoint);\n"
                "  }\n"
            ),
        )
        text = replace_once(
            text,
            "static void zclSampleLight_LevelControlStepCB( zclLCStep_t *pCmd )\n{\n",
            (
                "static void zclSampleLight_LevelControlStepCB( zclLCStep_t *pCmd )\n"
                "{\n"
                "  afIncomingMSGPacket_t *pPtr = zcl_getRawAFMsg();\n"
                "  if (pPtr != NULL)\n"
                "  {\n"
                "    zclSampleLight_SetCurrentEndpoint(pPtr->endPoint);\n"
                "  }\n"
            ),
        )
        text = replace_once(
            text,
            "static void zclSampleLight_LevelControlStopCB( zclLCStop_t *pCmd )\n{\n",
            (
                "static void zclSampleLight_LevelControlStopCB( zclLCStop_t *pCmd )\n"
                "{\n"
                "  afIncomingMSGPacket_t *pPtr = zcl_getRawAFMsg();\n"
                "  if (pPtr != NULL)\n"
                "  {\n"
                "    zclSampleLight_SetCurrentEndpoint(pPtr->endPoint);\n"
                "  }\n"
            ),
        )

    patched = build_dir / "patched_sources/zcl_samplelight.c"
    patched.parent.mkdir(parents=True, exist_ok=True)
    patched.write_text(text)
    return patched


def write_three_endpoint_sample_light_data(build_dir: Path) -> Path:
    text = SAMPLE_LIGHT_DATA_C.read_text()
    text = replace_once(
        text,
        "static uint8_t  zclSampleLight_OnOff;\n",
        "static uint8_t zclSampleLight_OnOff[3];\n",
    )
    text = replace_once(
        text,
        "static uint8_t  zclSampleLight_LevelCurrentLevel;\n",
        "static uint8_t zclSampleLight_LevelCurrentLevel[3];\n",
    )
    text = replace_once(
        text,
        "uint8_t  zclSampleLight_ScenesNameSupport = 0;\n",
        (
            "uint8_t  zclSampleLight_ScenesNameSupport = 0;\n"
            "static uint8_t huedInsteon_ScenesCurrentScene[3] = {0};\n"
            "static uint16_t huedInsteon_ScenesCurrentGroup[3] = {0};\n"
            "static uint8_t huedInsteon_ScenesValid[3] = {0};\n"
        ),
    )

    helper = """
static uint8_t zclSampleLight_CurrentEndpoint = 1;

static uint8_t zclSampleLight_EndpointIndex(uint8_t endpoint)
{
    if ((endpoint >= 1) && (endpoint <= 3))
    {
        return endpoint - 1;
    }
    return 0;
}

static uint8_t zclSampleLight_ActiveEndpoint(void)
{
    afIncomingMSGPacket_t *pMsg = zcl_getRawAFMsg();
    if (pMsg != NULL)
    {
        return pMsg->endPoint;
    }
    return zclSampleLight_CurrentEndpoint;
}

void zclSampleLight_SetCurrentEndpoint(uint8_t endpoint)
{
    if ((endpoint >= 1) && (endpoint <= 3))
    {
        zclSampleLight_CurrentEndpoint = endpoint;
    }
}

"""
    text = replace_once(
        text,
        "extern uint8_t  appServiceTaskId;\n",
        "extern uint8_t  appServiceTaskId;\n" + helper,
    )

    attrs_start = text.index("CONST zclAttrRec_t zclSampleLight_Attrs[] =")
    attrs_end = text.index("uint8_t CONST zclSampleLight_NumAttributes", attrs_start)
    attrs_block = text[attrs_start:attrs_end]

    endpoint_blocks: list[str] = []
    for idx, endpoint in enumerate([1, 2, 3]):
        block = attrs_block
        block = block.replace("zclSampleLight_Attrs[]", f"zclSampleLight_AttrsEp{endpoint}[]")
        block = block.replace("(void*)&zclSampleLight_OnOff", f"(void*)&zclSampleLight_OnOff[{idx}]")
        block = block.replace("(void*)&zclSampleLight_LevelCurrentLevel", f"(void*)&zclSampleLight_LevelCurrentLevel[{idx}]")
        block = block.replace("(void *)&zclSampleLight_ScenesCurrentScene", f"(void *)&huedInsteon_ScenesCurrentScene[{idx}]")
        block = block.replace("(void *)&zclSampleLight_ScenesCurrentGroup", f"(void *)&huedInsteon_ScenesCurrentGroup[{idx}]")
        block = block.replace("(void *)&zclSampleLight_ScenesValid", f"(void *)&huedInsteon_ScenesValid[{idx}]")
        endpoint_blocks.append(block)
    endpoint_attrs = "".join(endpoint_blocks)
    endpoint_attrs += """
CONST zclAttrRec_t *zclSampleLight_AttrsForEndpoint(uint8_t endpoint)
{
    switch (endpoint)
    {
    case 1:
        return zclSampleLight_AttrsEp1;
    case 2:
        return zclSampleLight_AttrsEp2;
    case 3:
        return zclSampleLight_AttrsEp3;
    default:
        return zclSampleLight_AttrsEp1;
    }
}

"""
    text = text[:attrs_start] + endpoint_attrs + text[attrs_end:]

    text = replace_once(
        text,
        "uint8_t CONST zclSampleLight_NumAttributes = ( sizeof(zclSampleLight_Attrs) / sizeof(zclSampleLight_Attrs[0]) );\n",
        "uint8_t CONST zclSampleLight_NumAttributes = ( sizeof(zclSampleLight_AttrsEp1) / sizeof(zclSampleLight_AttrsEp1[0]) );\n",
    )
    text = replace_once(
        text,
        "    if(zclSampleLight_OnOff != OnOff)\n    {\n        zclSampleLight_OnOff = OnOff;\n        zclSampleLight_ScenesValid = FALSE;\n",
        (
            "    uint8_t endpoint = zclSampleLight_ActiveEndpoint();\n"
            "    uint8_t idx = zclSampleLight_EndpointIndex(endpoint);\n"
            "    if(zclSampleLight_OnOff[idx] != OnOff)\n"
            "    {\n"
            "        zclSampleLight_OnOff[idx] = OnOff;\n"
            "        huedInsteon_ScenesValid[idx] = FALSE;\n"
        ),
    )
    text = replace_once(
        text,
        "        Req.endpoint = SAMPLELIGHT_ENDPOINT;\n",
        "        Req.endpoint = endpoint;\n",
    )
    text = replace_once(
        text,
        "    return zclSampleLight_OnOff;\n",
        "    return zclSampleLight_OnOff[zclSampleLight_EndpointIndex(zclSampleLight_ActiveEndpoint())];\n",
    )
    text = replace_once(
        text,
        "    if(zclSampleLight_LevelCurrentLevel != CurrentLevel)\n    {\n        zclSampleLight_LevelCurrentLevel = CurrentLevel;\n        zclSampleLight_ScenesValid = FALSE;\n",
        (
            "    uint8_t endpoint = zclSampleLight_ActiveEndpoint();\n"
            "    uint8_t idx = zclSampleLight_EndpointIndex(endpoint);\n"
            "    if(zclSampleLight_LevelCurrentLevel[idx] != CurrentLevel)\n"
            "    {\n"
            "        zclSampleLight_LevelCurrentLevel[idx] = CurrentLevel;\n"
            "        huedInsteon_ScenesValid[idx] = FALSE;\n"
        ),
    )
    text = replace_once(
        text,
        "        Req.endpoint = SAMPLELIGHT_ENDPOINT;\n",
        "        Req.endpoint = endpoint;\n",
    )
    text = replace_once(
        text,
        "    return zclSampleLight_LevelCurrentLevel;\n",
        "    return zclSampleLight_LevelCurrentLevel[zclSampleLight_EndpointIndex(zclSampleLight_ActiveEndpoint())];\n",
    )
    text = replace_once(
        text,
        "void zclSampleLight_ResetAttributesToDefaultValues(void)\n{\n  zclSampleLight_PhysicalEnvironment = PHY_UNSPECIFIED_ENV;\n",
        (
            "void zclSampleLight_ResetAttributesToDefaultValues(void)\n"
            "{\n"
            "  zclSampleLight_PhysicalEnvironment = PHY_UNSPECIFIED_ENV;\n"
            "  for (uint8_t endpoint = 1; endpoint <= 3; ++endpoint)\n"
            "  {\n"
            "    zclSampleLight_SetCurrentEndpoint(endpoint);\n"
        ),
    )
    text = replace_once(
        text,
        "\n  zclSampleLight_IdentifyTime = 0;\n}\n",
        "\n  }\n  zclSampleLight_SetCurrentEndpoint(1);\n  zclSampleLight_IdentifyTime = 0;\n}\n",
    )

    patched = build_dir / "patched_sources/zcl_samplelight_data.c"
    patched.parent.mkdir(parents=True, exist_ok=True)
    patched.write_text(text)
    return patched


def write_virtual_zdo_object(build_dir: Path, virtual_child_count: int = 3) -> Path:
    text = ZD_OBJECT_C.read_text()
    text = replace_once(
        text,
        '#include "zd_sec_mgr.h"\n',
        '#include "zd_sec_mgr.h"\n'
        '#ifdef HUEDINSTEON_DIAG\n'
        '#include "aps.h"\n'
        '#include "zmac.h"\n'
        '#endif\n',
    )
    text = replace_once(
        text,
        "// NLME Stub Implementations\n#define ZDO_ProcessMgmtPermitJoinTimeout NLME_PermitJoiningTimeout\n",
        """// NLME Stub Implementations
#define ZDO_ProcessMgmtPermitJoinTimeout NLME_PermitJoiningTimeout

#ifdef HUEDINSTEON_DIAG
#define HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT __HUEDINSTEON_VIRTUAL_CHILD_COUNT__
#define HUEDINSTEON_DIAG_VIRTUAL_CHILD_STORAGE_COUNT __HUEDINSTEON_VIRTUAL_CHILD_STORAGE_COUNT__
extern void huedInsteonDiag_ZdoTrace(const char *tag, uint16_t aoi, uint16_t src, uint8_t endpoint);

extern uint16_t huedInsteonDiag_VirtualChildLiveNwk[HUEDINSTEON_DIAG_VIRTUAL_CHILD_STORAGE_COUNT];

static const uint16_t huedInsteonZdo_InClusters[] =
{
  0x0000, // Basic
  0x0003, // Identify
  0x0004, // Groups
  0x0005, // Scenes
  0x0006, // On/Off
  0x0008  // Level Control
};

static bool huedInsteonZdo_IsVirtualNwk(uint16_t nwkAddr)
{
  uint8_t i;
  for (i = 0; i < HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT; i++)
  {
    if (huedInsteonDiag_VirtualChildLiveNwk[i] == nwkAddr)
    {
      return true;
    }
  }
  return false;
}

static int8_t huedInsteonZdo_VirtualIndex(uint16_t nwkAddr)
{
  uint8_t i;
  for (i = 0; i < HUEDINSTEON_DIAG_VIRTUAL_CHILD_COUNT; i++)
  {
    if (huedInsteonDiag_VirtualChildLiveNwk[i] == nwkAddr)
    {
      return (int8_t)i;
    }
  }
  return -1;
}

static uint8_t huedInsteonZdo_VirtualNwkSeq[HUEDINSTEON_DIAG_VIRTUAL_CHILD_STORAGE_COUNT] = { 0x31 };
static uint8_t huedInsteonZdo_VirtualApsSeq[HUEDINSTEON_DIAG_VIRTUAL_CHILD_STORAGE_COUNT] = { 0x32 };

static void huedInsteonZdo_BeginVirtualSource(uint16_t nwkAddr,
                                              uint16_t *savedNwkAddr,
                                              uint8_t *savedNwkSeq,
                                              uint8_t *savedApsSeq)
{
  int8_t idx = huedInsteonZdo_VirtualIndex(nwkAddr);

  *savedNwkAddr = _NIB.nwkDevAddress;
  *savedNwkSeq = _NIB.SequenceNum;
  *savedApsSeq = APS_Counter;

  if (idx >= 0)
  {
    _NIB.nwkDevAddress = nwkAddr;
    _NIB.SequenceNum = huedInsteonZdo_VirtualNwkSeq[idx]++;
    APS_Counter = huedInsteonZdo_VirtualApsSeq[idx]++;
  }
}

static void huedInsteonZdo_EndVirtualSource(uint16_t savedNwkAddr,
                                            uint8_t savedNwkSeq,
                                            uint8_t savedApsSeq)
{
  _NIB.nwkDevAddress = savedNwkAddr;
  _NIB.SequenceNum = savedNwkSeq;
  APS_Counter = savedApsSeq;
}

static void huedInsteonZdo_VirtualNodeDescRsp(zdoIncomingMsg_t *inMsg, uint16_t aoi, NodeDescriptorFormat_t *desc)
{
  uint16_t savedNwkAddr;
  uint8_t savedNwkSeq;
  uint8_t savedApsSeq;

  huedInsteonZdo_BeginVirtualSource(aoi, &savedNwkAddr, &savedNwkSeq, &savedApsSeq);
  ZDP_NodeDescMsg( inMsg, aoi, desc );
  huedInsteonZdo_EndVirtualSource(savedNwkAddr, savedNwkSeq, savedApsSeq);
}

static void huedInsteonZdo_VirtualPowerDescRsp(zdoIncomingMsg_t *inMsg, uint16_t aoi, NodePowerDescriptorFormat_t *desc)
{
  uint16_t savedNwkAddr;
  uint8_t savedNwkSeq;
  uint8_t savedApsSeq;

  huedInsteonZdo_BeginVirtualSource(aoi, &savedNwkAddr, &savedNwkSeq, &savedApsSeq);
  ZDP_PowerDescMsg( inMsg, aoi, desc );
  huedInsteonZdo_EndVirtualSource(savedNwkAddr, savedNwkSeq, savedApsSeq);
}

static void huedInsteonZdo_VirtualSimpleDescRsp(zdoIncomingMsg_t *inMsg, uint16_t aoi, byte stat, SimpleDescriptionFormat_t *desc)
{
  uint16_t savedNwkAddr;
  uint8_t savedNwkSeq;
  uint8_t savedApsSeq;

  huedInsteonZdo_BeginVirtualSource(aoi, &savedNwkAddr, &savedNwkSeq, &savedApsSeq);
  ZDP_SimpleDescMsg( inMsg, stat, desc );
  huedInsteonZdo_EndVirtualSource(savedNwkAddr, savedNwkSeq, savedApsSeq);
}

static void huedInsteonZdo_VirtualActiveEpRsp(uint8_t transSeq, zAddrType_t *dstAddr, byte stat,
                                              uint16_t aoi, byte cnt, uint8_t *epList, byte secUse)
{
  uint16_t savedNwkAddr;
  uint8_t savedNwkSeq;
  uint8_t savedApsSeq;

  huedInsteonZdo_BeginVirtualSource(aoi, &savedNwkAddr, &savedNwkSeq, &savedApsSeq);
  ZDP_ActiveEPRsp( transSeq, dstAddr, stat, aoi, cnt, epList, secUse );
  huedInsteonZdo_EndVirtualSource(savedNwkAddr, savedNwkSeq, savedApsSeq);
}

static void huedInsteonZdo_VirtualMatchDescRsp(uint8_t transSeq, zAddrType_t *dstAddr, byte stat,
                                               uint16_t aoi, byte cnt, uint8_t *epList, byte secUse)
{
  uint16_t savedNwkAddr;
  uint8_t savedNwkSeq;
  uint8_t savedApsSeq;

  huedInsteonZdo_BeginVirtualSource(aoi, &savedNwkAddr, &savedNwkSeq, &savedApsSeq);
  ZDP_MatchDescRsp( transSeq, dstAddr, stat, aoi, cnt, epList, secUse );
  huedInsteonZdo_EndVirtualSource(savedNwkAddr, savedNwkSeq, savedApsSeq);
}

static SimpleDescriptionFormat_t huedInsteonZdo_VirtualSimpleDesc(uint8_t endpoint)
{
  SimpleDescriptionFormat_t desc;
  memset(&desc, 0, sizeof(desc));
  desc.EndPoint = endpoint;
  desc.AppProfId = 0x0104;
  desc.AppDeviceId = 0x0101;
  desc.AppDevVer = 0;
  desc.AppNumInClusters = sizeof(huedInsteonZdo_InClusters) / sizeof(huedInsteonZdo_InClusters[0]);
  desc.pAppInClusterList = (uint16_t *)huedInsteonZdo_InClusters;
  desc.AppNumOutClusters = 0;
  desc.pAppOutClusterList = NULL;
  return desc;
}

static NodeDescriptorFormat_t huedInsteonZdo_VirtualNodeDesc(void)
{
  NodeDescriptorFormat_t desc = ZDO_Config_Node_Descriptor;
  desc.LogicalType = NODETYPE_DEVICE;
  desc.CapabilityFlags = CAPINFO_DEVICETYPE_RFD | CAPINFO_POWER_AC | CAPINFO_RCVR_ON_IDLE | CAPINFO_SECURITY_CAPABLE;
  return desc;
}
#endif
""",
    )
    text = (
        text.replace("__HUEDINSTEON_VIRTUAL_CHILD_COUNT__", str(virtual_child_count))
        .replace("__HUEDINSTEON_VIRTUAL_CHILD_STORAGE_COUNT__", str(max(1, virtual_child_count)))
    )
    text = replace_once(
        text,
        """  if ( aoi == ZDAppNwkAddr.addr.shortAddr )
  {
    desc = &ZDO_Config_Node_Descriptor;
  }

  if ( desc != NULL )
""",
        """  if ( aoi == ZDAppNwkAddr.addr.shortAddr )
  {
    desc = &ZDO_Config_Node_Descriptor;
  }
#ifdef HUEDINSTEON_DIAG
  else if (huedInsteonZdo_IsVirtualNwk(aoi))
  {
    NodeDescriptorFormat_t virtualDesc = huedInsteonZdo_VirtualNodeDesc();
    huedInsteonDiag_ZdoTrace("node", aoi, inMsg->srcAddr.addr.shortAddr, 0);
    huedInsteonZdo_VirtualNodeDescRsp( inMsg, aoi, &virtualDesc );
    return;
  }
#endif

  if ( desc != NULL )
""",
    )
    text = replace_once(
        text,
        """  if ( aoi == ZDAppNwkAddr.addr.shortAddr )
  {
    desc = &ZDO_Config_Power_Descriptor;
  }

  if ( desc != NULL )
""",
        """  if ( aoi == ZDAppNwkAddr.addr.shortAddr )
  {
    desc = &ZDO_Config_Power_Descriptor;
  }
#ifdef HUEDINSTEON_DIAG
  else if (huedInsteonZdo_IsVirtualNwk(aoi))
  {
    huedInsteonDiag_ZdoTrace("power", aoi, inMsg->srcAddr.addr.shortAddr, 0);
    huedInsteonZdo_VirtualPowerDescRsp( inMsg, aoi, &ZDO_Config_Power_Descriptor );
    return;
  }
#endif

  if ( desc != NULL )
""",
    )
    text = replace_once(
        text,
        """  else if ( aoi == ZDAppNwkAddr.addr.shortAddr )
  {
    free = afFindSimpleDesc( &sDesc, endPoint );
    if ( sDesc == NULL )
    {
      stat = ZDP_NOT_ACTIVE;
    }
  }
  else
""",
        """  else if ( aoi == ZDAppNwkAddr.addr.shortAddr )
  {
#ifdef HUEDINSTEON_VIRTUAL_CHILDREN_ONLY
    stat = ZDP_INVALID_EP;
#else
    free = afFindSimpleDesc( &sDesc, endPoint );
    if ( sDesc == NULL )
    {
      stat = ZDP_NOT_ACTIVE;
    }
#endif
  }
#ifdef HUEDINSTEON_DIAG
  else if (huedInsteonZdo_IsVirtualNwk(aoi))
  {
    huedInsteonDiag_ZdoTrace("simple", aoi, inMsg->srcAddr.addr.shortAddr, endPoint);
    if (endPoint == 1)
    {
      SimpleDescriptionFormat_t virtualDesc = huedInsteonZdo_VirtualSimpleDesc(1);
      huedInsteonZdo_VirtualSimpleDescRsp( inMsg, aoi, ZDP_SUCCESS, &virtualDesc );
      return;
    }
    huedInsteonZdo_VirtualSimpleDescRsp( inMsg, aoi, ZDP_INVALID_EP, NULL );
    return;
  }
#endif
  else
""",
    )
    text = replace_once(
        text,
        """  if ( aoi == NLME_GetShortAddr() )
  {
    cnt = afNumEndPoints() - 1;  // -1 for ZDO endpoint descriptor
    afEndPoints( (uint8_t *)ZDOBuildBuf, true );
  }
  else
""",
        """  if ( aoi == NLME_GetShortAddr() )
  {
#ifdef HUEDINSTEON_VIRTUAL_CHILDREN_ONLY
    cnt = 0;
#else
    cnt = afNumEndPoints() - 1;  // -1 for ZDO endpoint descriptor
    afEndPoints( (uint8_t *)ZDOBuildBuf, true );
#endif
  }
#ifdef HUEDINSTEON_DIAG
  else if (huedInsteonZdo_IsVirtualNwk(aoi))
  {
    huedInsteonDiag_ZdoTrace("active", aoi, inMsg->srcAddr.addr.shortAddr, 0);
    cnt = 1;
    ((uint8_t *)ZDOBuildBuf)[0] = 1;
    huedInsteonZdo_VirtualActiveEpRsp( inMsg->TransSeq, &(inMsg->srcAddr), stat,
                                       aoi, cnt, (uint8_t *)ZDOBuildBuf, inMsg->SecurityUse );
    return;
  }
#endif
  else
""",
    )
    text = replace_once(
        text,
        """  if ( ADDR_BCAST_NOT_ME == NLME_IsAddressBroadcast(aoi) )
  {
    ZDP_MatchDescRsp( inMsg->TransSeq, &(inMsg->srcAddr), ZDP_INVALID_REQTYPE,
                          aoi, 0, NULL, inMsg->SecurityUse );
    return;
  }
  else if ( (ADDR_NOT_BCAST == NLME_IsAddressBroadcast(aoi)) && (aoi != ZDAppNwkAddr.addr.shortAddr) )
  {
#if (ZG_BUILD_ENDDEVICE_TYPE)
    if(ZG_DEVICE_ENDDEVICE_TYPE)
    {
    ZDP_MatchDescRsp( inMsg->TransSeq, &(inMsg->srcAddr), ZDP_INVALID_REQTYPE,
                             aoi, 0, NULL, inMsg->SecurityUse );
    }
#else
    if (ZG_DEVICE_RTR_TYPE)
    {
    ZDP_MatchDescRsp( inMsg->TransSeq, &(inMsg->srcAddr), ZDP_DEVICE_NOT_FOUND,
                             aoi, 0, NULL, inMsg->SecurityUse );
    }
#endif
    return;
  }
""",
        """  if ( ADDR_BCAST_NOT_ME == NLME_IsAddressBroadcast(aoi) )
  {
    ZDP_MatchDescRsp( inMsg->TransSeq, &(inMsg->srcAddr), ZDP_INVALID_REQTYPE,
                          aoi, 0, NULL, inMsg->SecurityUse );
    return;
  }
#ifdef HUEDINSTEON_VIRTUAL_CHILDREN_ONLY
  else if ( aoi == ZDAppNwkAddr.addr.shortAddr )
  {
    ZDP_MatchDescRsp( inMsg->TransSeq, &(inMsg->srcAddr), ZDP_SUCCESS,
                      aoi, 0, NULL, inMsg->SecurityUse );
    return;
  }
#endif
#ifdef HUEDINSTEON_DIAG
  else if (huedInsteonZdo_IsVirtualNwk(aoi))
  {
    SimpleDescriptionFormat_t virtualDesc = huedInsteonZdo_VirtualSimpleDesc(1);
    uint8_t ep = 1;
    uint8_t matched = false;
    huedInsteonDiag_ZdoTrace("match", aoi, inMsg->srcAddr.addr.shortAddr, 0);

    if ((numInClusters = *msg++) &&
        (inClusters = (uint16_t*)OsalPort_malloc( numInClusters * sizeof( uint16_t ) )))
    {
      msg = ZDO_ConvertOTAClusters( numInClusters, msg, inClusters );
    }
    else
    {
      numInClusters = 0;
    }

    if ((numOutClusters = *msg++) &&
        (outClusters = (uint16_t *)OsalPort_malloc( numOutClusters * sizeof( uint16_t ) )))
    {
      msg = ZDO_ConvertOTAClusters( numOutClusters, msg, outClusters );
    }
    else
    {
      numOutClusters = 0;
    }

    if ( ((virtualDesc.AppProfId == profileID) || (profileID == ZDO_WILDCARD_PROFILE_ID)) &&
         (ZDO_AnyClusterMatches( numInClusters, inClusters,
                                 virtualDesc.AppNumInClusters, virtualDesc.pAppInClusterList ) ||
          ZDO_AnyClusterMatches( numOutClusters, outClusters,
                                 virtualDesc.AppNumOutClusters, virtualDesc.pAppOutClusterList )) )
    {
      matched = true;
    }

    huedInsteonZdo_VirtualMatchDescRsp( inMsg->TransSeq, &(inMsg->srcAddr), ZDP_SUCCESS,
                                        aoi, matched ? 1 : 0, matched ? &ep : NULL, inMsg->SecurityUse );

    if ( inClusters != NULL )
    {
      OsalPort_free( inClusters );
    }
    if ( outClusters != NULL )
    {
      OsalPort_free( outClusters );
    }
    return;
  }
#endif
  else if ( (ADDR_NOT_BCAST == NLME_IsAddressBroadcast(aoi)) && (aoi != ZDAppNwkAddr.addr.shortAddr) )
  {
#if (ZG_BUILD_ENDDEVICE_TYPE)
    if(ZG_DEVICE_ENDDEVICE_TYPE)
    {
    ZDP_MatchDescRsp( inMsg->TransSeq, &(inMsg->srcAddr), ZDP_INVALID_REQTYPE,
                             aoi, 0, NULL, inMsg->SecurityUse );
    }
#else
    if (ZG_DEVICE_RTR_TYPE)
    {
    ZDP_MatchDescRsp( inMsg->TransSeq, &(inMsg->srcAddr), ZDP_DEVICE_NOT_FOUND,
                             aoi, 0, NULL, inMsg->SecurityUse );
    }
#endif
    return;
  }
""",
    )

    patched = build_dir / "patched_sources/zd_object.c"
    patched.parent.mkdir(parents=True, exist_ok=True)
    patched.write_text(text)
    return patched


def write_instrumented_zd_app(build_dir: Path) -> Path:
    text = ZD_APP_C.read_text()
    text = replace_once(
        text,
        '#include "zd_app.h"\n',
        '#include "zd_app.h"\n'
        '#ifdef HUEDINSTEON_DIAG\n'
        'extern void huedInsteonDiag_SecTrace(const char *tag, uint16_t src, uint16_t a, uint16_t b, const uint8_t *eui);\n'
        '#endif\n',
    )
    text = replace_once(
        text,
        "void ZDApp_ProcessSecMsg( OsalPort_EventHdr *msgPtr )\n{\n  switch ( msgPtr->event )\n  {\n",
        """void ZDApp_ProcessSecMsg( OsalPort_EventHdr *msgPtr )
{
#ifdef HUEDINSTEON_DIAG
  huedInsteonDiag_SecTrace("event", (uint16_t)msgPtr->event, 0, 0, NULL);
#endif
  switch ( msgPtr->event )
  {
""",
    )
    text = replace_once(
        text,
        "    case ZDO_TRANSPORT_KEY_IND:\n      if ( ZG_BUILD_JOINING_TYPE && ZG_DEVICE_JOINING_TYPE )\n",
        """    case ZDO_TRANSPORT_KEY_IND:
#ifdef HUEDINSTEON_DIAG
      huedInsteonDiag_SecTrace("transport",
                               ((ZDO_TransportKeyInd_t*)msgPtr)->srcAddr,
                               ((ZDO_TransportKeyInd_t*)msgPtr)->keyType,
                               ((ZDO_TransportKeyInd_t*)msgPtr)->keySeqNum,
                               ((ZDO_TransportKeyInd_t*)msgPtr)->srcExtAddr);
#endif
      if ( ZG_BUILD_JOINING_TYPE && ZG_DEVICE_JOINING_TYPE )
""",
    )
    text = replace_once(
        text,
        "    case ZDO_UPDATE_DEVICE_IND:\n      if ( ZG_BUILD_COORDINATOR_TYPE && ZG_DEVICE_COORDINATOR_TYPE )\n",
        """    case ZDO_UPDATE_DEVICE_IND:
#ifdef HUEDINSTEON_DIAG
      huedInsteonDiag_SecTrace("update",
                               ((ZDO_UpdateDeviceInd_t*)msgPtr)->srcAddr,
                               ((ZDO_UpdateDeviceInd_t*)msgPtr)->devAddr,
                               ((ZDO_UpdateDeviceInd_t*)msgPtr)->status,
                               ((ZDO_UpdateDeviceInd_t*)msgPtr)->devExtAddr);
#endif
      if ( ZG_BUILD_COORDINATOR_TYPE && ZG_DEVICE_COORDINATOR_TYPE )
""",
    )
    text = replace_once(
        text,
        "    case ZDO_REMOVE_DEVICE_IND:\n      if ( (ZG_BUILD_ALL_DEVICES_TYPE || ZG_BUILD_RTRONLY_TYPE) && ( zgDeviceLogicalType == ZG_DEVICETYPE_ROUTER ) )\n",
        """    case ZDO_REMOVE_DEVICE_IND:
#ifdef HUEDINSTEON_DIAG
      huedInsteonDiag_SecTrace("remove",
                               ((ZDO_RemoveDeviceInd_t*)msgPtr)->srcAddr,
                               0,
                               0,
                               ((ZDO_RemoveDeviceInd_t*)msgPtr)->childExtAddr);
#endif
      if ( (ZG_BUILD_ALL_DEVICES_TYPE || ZG_BUILD_RTRONLY_TYPE) && ( zgDeviceLogicalType == ZG_DEVICETYPE_ROUTER ) )
""",
    )
    text = replace_once(
        text,
        "    case ZDO_REQUEST_KEY_IND:\n      if ( ZG_BUILD_COORDINATOR_TYPE && ZG_DEVICE_COORDINATOR_TYPE )\n",
        """    case ZDO_REQUEST_KEY_IND:
#ifdef HUEDINSTEON_DIAG
      huedInsteonDiag_SecTrace("request",
                               ((ZDO_RequestKeyInd_t*)msgPtr)->srcAddr,
                               ((ZDO_RequestKeyInd_t*)msgPtr)->keyType,
                               0,
                               ((ZDO_RequestKeyInd_t*)msgPtr)->partExtAddr);
#endif
      if ( ZG_BUILD_COORDINATOR_TYPE && ZG_DEVICE_COORDINATOR_TYPE )
""",
    )
    text = replace_once(
        text,
        "    case ZDO_VERIFY_KEY_IND:\n#if (ZG_BUILD_COORDINATOR_TYPE)\n",
        """    case ZDO_VERIFY_KEY_IND:
#ifdef HUEDINSTEON_DIAG
      huedInsteonDiag_SecTrace("verify",
                               ((ZDO_VerifyKeyInd_t*)msgPtr)->srcAddr,
                               ((ZDO_VerifyKeyInd_t*)msgPtr)->keyType,
                               ((ZDO_VerifyKeyInd_t*)msgPtr)->verifyKeyStatus,
                               ((ZDO_VerifyKeyInd_t*)msgPtr)->extAddr);
#endif
#if (ZG_BUILD_COORDINATOR_TYPE)
""",
    )
    text = replace_once(
        text,
        "    case ZDO_SWITCH_KEY_IND:\n      if ( ZG_BUILD_JOINING_TYPE && ZG_DEVICE_JOINING_TYPE )\n",
        """    case ZDO_SWITCH_KEY_IND:
#ifdef HUEDINSTEON_DIAG
      huedInsteonDiag_SecTrace("switch",
                               ((ZDO_SwitchKeyInd_t*)msgPtr)->srcAddr,
                               ((ZDO_SwitchKeyInd_t*)msgPtr)->keySeqNum,
                               0,
                               NULL);
#endif
      if ( ZG_BUILD_JOINING_TYPE && ZG_DEVICE_JOINING_TYPE )
""",
    )

    patched = build_dir / "patched_sources/zd_app.c"
    patched.parent.mkdir(parents=True, exist_ok=True)
    patched.write_text(text)
    return patched


def write_instrumented_zd_profile(build_dir: Path) -> Path:
    text = ZD_PROFILE_C.read_text()
    text = replace_once(
        text,
        '#include "zd_profile.h"\n',
        '#include "zd_profile.h"\n'
        '#ifdef HUEDINSTEON_DIAG\n'
        'extern void huedInsteonDiag_ZdoInTrace(uint16_t cluster, uint16_t src, uint16_t macDst, uint16_t macSrc, uint8_t sec, uint8_t len);\n'
        '#endif\n',
    )
    text = replace_once(
        text,
        "  inMsg.macDestAddr = pData->macDestAddr;\n  inMsg.macSrcAddr = pData->macSrcAddr;\n\n  handled = ZDO_SendMsgCBs( &inMsg );\n",
        """  inMsg.macDestAddr = pData->macDestAddr;
  inMsg.macSrcAddr = pData->macSrcAddr;

#ifdef HUEDINSTEON_DIAG
  huedInsteonDiag_ZdoInTrace(inMsg.clusterID,
                             inMsg.srcAddr.addr.shortAddr,
                             inMsg.macDestAddr,
                             inMsg.macSrcAddr,
                             inMsg.SecurityUse,
                             inMsg.asduLen);
#endif

  handled = ZDO_SendMsgCBs( &inMsg );
""",
    )

    patched = build_dir / "patched_sources/zd_profile.c"
    patched.parent.mkdir(parents=True, exist_ok=True)
    patched.write_text(text)
    return patched


def write_instrumented_zmac_cb(build_dir: Path) -> Path:
    text = ZMAC_CB_C.read_text()
    text = replace_once(
        text,
        '#include "zmac.h"\n',
        '#include "zmac.h"\n#ifdef HUEDINSTEON_DIAG\nextern void huedInsteonDiag_MacTrace(uint8_t event, uint8_t status, uint16_t shortAddr);\n#endif\n',
    )
    text = replace_once(
        text,
        "  uint8_t event = pData->hdr.event;\n  uint16_t tmp = zmacCBSizeTable[event];\n",
        """  uint8_t event = pData->hdr.event;
  uint16_t tmp = zmacCBSizeTable[event];
#ifdef HUEDINSTEON_DIAG
  if (event == MAC_MLME_ASSOCIATE_CNF)
  {
    huedInsteonDiag_MacTrace(event, pData->associateCnf.hdr.status, pData->associateCnf.assocShortAddress);
  }
  else if (event == MAC_MLME_ASSOCIATE_IND)
  {
    huedInsteonDiag_MacTrace(event, pData->associateInd.hdr.status, 0xffff);
  }
#endif
""",
    )

    patched = build_dir / "patched_sources/zmac_cb.c"
    patched.parent.mkdir(parents=True, exist_ok=True)
    patched.write_text(text)
    return patched


def write_endpoint1_sample_light_header(build_dir: Path) -> Path:
    text = SAMPLE_LIGHT_H.read_text()
    text = replace_once(
        text,
        "#define SAMPLELIGHT_ENDPOINT            8\n",
        "#define SAMPLELIGHT_ENDPOINT            1\n",
    )
    patched = build_dir / "project/zcl_samplelight.h"
    patched.parent.mkdir(parents=True, exist_ok=True)
    patched.write_text(text)
    return patched


def prepare_source_files(
    source_files: list[Path],
    variant: str,
    build_dir: Path,
    virtual_eui: str | None,
    virtual_child_count: int,
) -> list[Path]:
    sonoff_variants = {
        "sonoff",
        "sonoff_diag",
        "sonoff_3ep",
        "sonoff_3ep_diag",
        "sonoff_3ep_shared",
        "sonoff_3ep_shared_diag",
        "sonoff_vchildren_diag",
    }
    three_endpoint_variants = {
        "sonoff_3ep",
        "sonoff_3ep_diag",
        "sonoff_3ep_shared",
        "sonoff_3ep_shared_diag",
    }
    endpoint_specific_variants = {"sonoff_3ep", "sonoff_3ep_diag"}
    diag_variants = {
        "sonoff_diag",
        "sonoff_3ep_diag",
        "sonoff_3ep_shared_diag",
        "sonoff_vchildren_diag",
    }

    if variant not in sonoff_variants:
        return source_files

    if variant in diag_variants and variant not in three_endpoint_variants:
        write_endpoint1_sample_light_header(build_dir)

    patched_sample_light = write_instrumented_sample_light(
        build_dir,
        three_endpoints=(variant in three_endpoint_variants),
        endpoint_specific_state=(variant in endpoint_specific_variants),
        diag_uart=(variant in diag_variants),
        virtual_eui=virtual_eui,
        virtual_child_count=virtual_child_count,
    )
    patched_sample_light_data = (
        write_three_endpoint_sample_light_data(build_dir)
        if variant in endpoint_specific_variants
        else None
    )
    patched_zdo_object = (
        write_virtual_zdo_object(build_dir, virtual_child_count=virtual_child_count)
        if variant in diag_variants
        else None
    )
    patched_zd_app = (
        write_instrumented_zd_app(build_dir)
        if variant in diag_variants
        else None
    )
    patched_zd_profile = (
        write_instrumented_zd_profile(build_dir)
        if variant in diag_variants
        else None
    )
    patched_zmac_cb = (
        write_instrumented_zmac_cb(build_dir)
        if variant in diag_variants
        else None
    )
    prepared: list[Path] = []
    for source in source_files:
        if source.resolve() == SAMPLE_LIGHT_C.resolve():
            prepared.append(patched_sample_light)
        elif (
            patched_sample_light_data is not None
            and source.resolve() == SAMPLE_LIGHT_DATA_C.resolve()
        ):
            prepared.append(patched_sample_light_data)
        elif (
            patched_zdo_object is not None
            and source.resolve() == ZD_OBJECT_C.resolve()
        ):
            prepared.append(patched_zdo_object)
        elif (
            patched_zd_app is not None
            and source.resolve() == ZD_APP_C.resolve()
        ):
            prepared.append(patched_zd_app)
        elif (
            patched_zd_profile is not None
            and source.resolve() == ZD_PROFILE_C.resolve()
        ):
            prepared.append(patched_zd_profile)
        elif (
            patched_zmac_cb is not None
            and source.resolve() == ZMAC_CB_C.resolve()
        ):
            prepared.append(patched_zmac_cb)
        else:
            prepared.append(source)
    return prepared


def prepare_syscfg(variant: str, build_dir: Path) -> tuple[Path, Path]:
    if variant == "stock":
        return SYSCFG, SDK

    return write_sonoff_syscfg(build_dir), SDK


def normalize_compiler_options(
    raw_options: list[str], build_dir: Path, project_root: Path, variant: str
) -> list[str]:
    options: list[str] = []
    syscfg_dir = build_dir / "syscfg"
    for raw in raw_options:
        expanded = expand_vars(raw, build_dir, project_root)
        if expanded.startswith("-I"):
            include = Path(expanded[2:])
            if include.exists():
                options.append(expanded)
            continue
        if expanded.startswith("@"):
            opt_file = Path(expanded[1:])
            if opt_file.exists():
                options.append(expanded)
            continue
        options.append(expanded)

    options.extend(
        [
            f"-I{syscfg_dir}",
            f"@{syscfg_dir / 'ti_utils_build_compiler.opt'}",
            f"@{SDK / 'source/ti/zstack/config/f8wrouter.opts'}",
        ]
    )
    if variant in {
        "sonoff",
        "sonoff_diag",
        "sonoff_3ep",
        "sonoff_3ep_diag",
        "sonoff_3ep_shared",
        "sonoff_3ep_shared_diag",
        "sonoff_vchildren_diag",
    }:
        options.extend(
            [
                "-DDEFAULT_CHANLIST=0x07FFF800",
                "-DSECONDARY_CHANLIST=0x07FFF800",
            ]
        )
    if variant in {"sonoff_diag", "sonoff_3ep_diag", "sonoff_3ep_shared_diag", "sonoff_vchildren_diag"}:
        options.extend(
            [
                "-DHUEDINSTEON_DIAG",
                "-DCUI_DISABLE",
            ]
        )
    if variant == "sonoff_vchildren_diag":
        options.append("-DHUEDINSTEON_VIRTUAL_CHILDREN_ONLY")
    return options


def linker_options(build_dir: Path) -> list[str]:
    syscfg_dir = build_dir / "syscfg"
    return [
        "--diag_wrap=off",
        "--unused_section_elimination=on",
        f"--xml_link_info={build_dir / 'zr_light_linkInfo.xml'}",
        "--display_error_number",
        "--rom_model",
        "--warn_sections",
        "-x",
        "--define=NVOCMP_NVPAGES=2",
        f"-i{SDK / 'source'}",
        f"-i{SDK / 'kernel/tirtos7/packages'}",
        f"-i{syscfg_dir}",
        f"-i{TICLANG_ROOT / 'lib'}",
        f"-l{syscfg_dir / 'ti_utils_build_linker.cmd.genlibs'}",
        f"-l{SDK / 'source/ti/ti154stack/rom/lib/ticlang/timac_rom_PG2_0_rom_api_linker.cmd'}",
        f"-l{TICLANG_ROOT / 'lib/libc.a'}",
        f"-l{TICLANG_ROOT / 'lib/armv7em-ti-none-eabihf/libclang_rt.builtins.a'}",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=None,
        help="Output directory for objects and artifacts.",
    )
    parser.add_argument(
        "--variant",
        choices=[
            "stock",
            "sonoff",
            "sonoff_diag",
            "sonoff_3ep",
            "sonoff_3ep_diag",
            "sonoff_3ep_shared",
            "sonoff_3ep_shared_diag",
            "sonoff_vchildren_diag",
        ],
        default="stock",
        help="Build TI's unmodified LaunchPad example or a Sonoff board variant.",
    )
    parser.add_argument(
        "--virtual-eui",
        type=str,
        default=None,
        help="Override the runtime Zigbee IEEE address, e.g. 00124B003A126F8E.",
    )
    parser.add_argument(
        "--virtual-child-count",
        type=int,
        default=3,
        help="Number of virtual child Zigbee identities to compile into diagnostic firmware.",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue compiling after individual source failures.",
    )
    args = parser.parse_args()

    for required in [SDK, SYSCONFIG, TICLANG_ROOT, PROJECTSPEC, SYSCFG]:
        if not required.exists():
            print(f"missing required path: {required}", file=sys.stderr)
            return 2

    build_dir = (
        args.build_dir or ROOT / f".vendor/build/zr_light_{args.variant}"
    ).resolve()
    syscfg_dir = build_dir / "syscfg"
    obj_dir = build_dir / "obj"
    project_root = build_dir / "project"
    for directory in [syscfg_dir, obj_dir, project_root]:
        directory.mkdir(parents=True, exist_ok=True)

    syscfg_script, sysconfig_sdk = prepare_syscfg(args.variant, build_dir)

    run(
        [
            SYSCONFIG,
            "--product",
            sysconfig_sdk / ".metadata/product.json",
            "--script",
            syscfg_script,
            "--compiler",
            "ticlang",
            "--output",
            syscfg_dir,
        ]
    )

    compiler_raw, _linker_raw, source_files, linker_scripts = parse_projectspec()
    if args.virtual_eui is not None:
        parse_eui64(args.virtual_eui)
    if args.virtual_child_count < 0 or args.virtual_child_count > 15:
        print("--virtual-child-count must be between 0 and 15", file=sys.stderr)
        return 2

    source_files = prepare_source_files(
        source_files,
        args.variant,
        build_dir,
        args.virtual_eui,
        args.virtual_child_count,
    )
    generated_sources = sorted(syscfg_dir.glob("*.c"))
    all_sources = source_files + generated_sources
    compile_options = normalize_compiler_options(
        compiler_raw, build_dir, project_root, args.variant
    )
    link_options = linker_options(build_dir)

    compiler = TICLANG_ROOT / "bin/tiarmclang"
    obj_files: list[Path] = []
    failures = 0
    for source in all_sources:
        if not source.exists():
            raise FileNotFoundError(source)
        obj = obj_dir / (source.stem + ".o")
        obj.parent.mkdir(parents=True, exist_ok=True)
        cmd = [compiler, *compile_options, "-c", source, "-o", obj]
        try:
            run(cmd)
        except subprocess.CalledProcessError:
            failures += 1
            if not args.keep_going:
                raise
        else:
            obj_files.append(obj)

    if failures:
        print(f"{failures} compile failure(s)", file=sys.stderr)
        return 1

    artifact_stem = f"zr_light_{args.variant}"
    elf = build_dir / f"{artifact_stem}.out"
    hex_file = build_dir / f"{artifact_stem}.hex"
    bin_file = build_dir / f"{artifact_stem}.bin"
    linker = TICLANG_ROOT / "bin/tiarmlnk"
    link_cmd = [
        linker,
        *obj_files,
        *linker_scripts,
        *link_options,
        "-o",
        elf,
    ]
    run(link_cmd)
    run([TICLANG_ROOT / "bin/tiarmobjcopy", elf, "--output-target", "ihex", hex_file])
    run([TICLANG_ROOT / "bin/tiarmobjcopy", elf, "--output-target", "binary", bin_file])
    print(f"built {elf}")
    print(f"built {hex_file}")
    print(f"built {bin_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
