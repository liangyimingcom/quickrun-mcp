"""Sandbox / permission tests.

macOS sandbox-exec tests are skipped on non-Darwin or when sandbox-exec is absent.
Audit-hook tests run everywhere.
"""

import os
import sys
import pytest
from pathlib import Path

from quickrun_mcp.sandbox import has_sandbox_exec

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SANDBOX_ONLY = pytest.mark.skipif(
    not has_sandbox_exec(),
    reason="sandbox-exec not available on this platform",
)


# ---------------------------------------------------------------------------
# Write-access tests (run on all platforms — relies on audit hook when no sandbox-exec)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_to_workspace_allowed(basic_worker, workspace):
    """Code can write files inside WORKSPACE_DIR."""
    code = "open(WORKSPACE_DIR + '/w_test.txt', 'w').write('ok')"
    result = await basic_worker.execute(code, timeout=10)
    assert (workspace / "w_test.txt").exists()


@pytest.mark.asyncio
@SANDBOX_ONLY
async def test_write_outside_workspace_blocked_basic(basic_worker):
    """basic_worker must NOT write to a home-dir path outside workspace/tmp."""
    # Use a path in $HOME that the sandbox does not permit writing to.
    outside = str(Path.home() / "QCEMCP_SANDBOX_TEST_FORBIDDEN.txt")
    try:
        code = f"""
try:
    with open('{outside}', 'w') as f:
        f.write('bad')
    print('WRITE_OK')
except Exception as e:
    print(f'BLOCKED: {{e}}')
"""
        result = await basic_worker.execute(code, timeout=10)
        assert "WRITE_OK" not in result, f"sandbox should have blocked the write; got: {result}"
    finally:
        # Clean up if the file was somehow created
        try:
            Path(outside).unlink()
        except FileNotFoundError:
            pass


@pytest.mark.asyncio
@SANDBOX_ONLY
async def test_write_allowed_folder_requires_write_worker(
    basic_worker, write_worker, tmp_path
):
    """With-write worker can write to allowed_folder; basic cannot."""
    # Use a real allowed_folder in the home directory so the sandbox distinguishes it
    import tempfile
    allowed = Path.home() / ".quickrun" / "test_allowed_tmp"
    allowed.mkdir(parents=True, exist_ok=True)
    target = str(allowed / "output.txt")

    try:
        # write_worker should succeed (config has ALLOWED_FOLDERS pointing here)
        # We need a worker whose config actually includes this path.
        # For this test, directly verify the sandbox profile correctly allows/denies.
        from quickrun_mcp.config import Config
        from quickrun_mcp.executor import PersistentWorker
        import os

        # Create a config with allowed_folder set to our test folder
        old_af = os.environ.get("ALLOWED_FOLDERS", "")
        os.environ["ALLOWED_FOLDERS"] = str(allowed)
        cfg_write = Config()
        ww = PersistentWorker(cfg_write, with_write=True)
        ww_basic = PersistentWorker(cfg_write, with_write=False)

        code_write = f"open('{target}', 'w').write('from write_worker')"
        await ww.execute(code_write, timeout=10)
        assert Path(target).exists(), "write_worker should be able to write to allowed_folder"

        Path(target).unlink(missing_ok=True)

        code_basic = f"""
try:
    open('{target}', 'w').write('from basic_worker')
    print('BASIC_WROTE')
except Exception as e:
    print(f'BLOCKED: {{e}}')
"""
        res_basic = await ww_basic.execute(code_basic, timeout=10)
        assert "BASIC_WROTE" not in res_basic, (
            f"basic_worker should NOT write to allowed_folder; got: {res_basic}"
        )

        await ww.cleanup()
        await ww_basic.cleanup()
        os.environ["ALLOWED_FOLDERS"] = old_af

    finally:
        try:
            Path(target).unlink(missing_ok=True)
        except Exception:
            pass


@pytest.mark.asyncio
@SANDBOX_ONLY
async def test_sensitive_ssh_path_blocked(basic_worker):
    """.ssh directory must be unreadable under sandbox-exec."""
    ssh_dir = str(Path.home() / ".ssh")
    code = f"""
import os
try:
    contents = os.listdir('{ssh_dir}')
    print('SSH_LIST_OK', contents[:2])
except Exception as e:
    print(f'BLOCKED: {{e}}')
"""
    result = await basic_worker.execute(code, timeout=10)
    assert "SSH_LIST_OK" not in result


@pytest.mark.asyncio
@SANDBOX_ONLY
async def test_sensitive_aws_path_blocked(basic_worker):
    """.aws directory must be unreadable under sandbox-exec."""
    aws_dir = str(Path.home() / ".aws")
    code = f"""
import os
try:
    contents = os.listdir('{aws_dir}')
    print('AWS_LIST_OK', contents[:2])
except Exception as e:
    print(f'BLOCKED: {{e}}')
"""
    result = await basic_worker.execute(code, timeout=10)
    assert "AWS_LIST_OK" not in result


# ---------------------------------------------------------------------------
# Output truncation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_output_truncation(basic_worker):
    result = await basic_worker.execute("print('Z' * 70_000)", timeout=10)
    assert "TRUNCATED" in result


# ---------------------------------------------------------------------------
# Stateless write tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stateless_write_to_workspace(stateless_ro, workspace):
    code = "open(WORKSPACE_DIR + '/sl_test.txt', 'w').write('stateless')"
    await stateless_ro.execute(code, timeout=10)
    assert (workspace / "sl_test.txt").exists()


@pytest.mark.asyncio
async def test_stateless_rw_writes_allowed_folder(stateless_rw, allowed_folder):
    target = str(allowed_folder / "sl_output.txt")
    code = f"open('{target}', 'w').write('stateless rw')"
    await stateless_rw.execute(code, timeout=10)
    assert Path(target).exists()
