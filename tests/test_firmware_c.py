# SPDX-License-Identifier: Apache-2.0
import shutil
import subprocess
from pathlib import Path


def test_firmware_core_c_compiles_and_runs(tmp_path):
    cc = shutil.which("cc")
    if cc is None:
        return

    repo = Path(__file__).resolve().parents[1]
    binary = tmp_path / "test_hued_firmware_core"
    subprocess.run(
        [
            cc,
            "-std=c99",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Ifirmware/common",
            "-Ifirmware/ti_zstack/overlay",
            "-Ifirmware/three_endpoint",
            "firmware/common/hued_protocol.c",
            "firmware/common/hued_app.c",
            "firmware/ti_zstack/overlay/hued_zstack_bridge.c",
            "firmware/tests/test_hued_firmware_core.c",
            "-o",
            str(binary),
        ],
        cwd=repo,
        check=True,
    )
    subprocess.run([str(binary)], check=True)
