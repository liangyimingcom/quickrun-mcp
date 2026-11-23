"""Basic execution tests."""

import pytest


@pytest.mark.asyncio
async def test_print(basic_worker):
    result = await basic_worker.execute("print('hello world')", timeout=10)
    assert "hello world" in result


@pytest.mark.asyncio
async def test_math(basic_worker):
    result = await basic_worker.execute("print(2 + 2)", timeout=10)
    assert "4" in result


@pytest.mark.asyncio
async def test_exception_reported(basic_worker):
    result = await basic_worker.execute("raise ValueError('boom')", timeout=10)
    assert "ValueError" in result
    assert "boom" in result


@pytest.mark.asyncio
async def test_stderr_captured(basic_worker):
    result = await basic_worker.execute(
        "import sys; sys.stderr.write('err_msg\\n')", timeout=10
    )
    assert "err_msg" in result


@pytest.mark.asyncio
async def test_workspace_dir_variable(basic_worker, workspace):
    result = await basic_worker.execute("print(WORKSPACE_DIR)", timeout=10)
    assert str(workspace) in result


@pytest.mark.asyncio
async def test_no_output(basic_worker):
    result = await basic_worker.execute("x = 42  # no output", timeout=10)
    assert result  # returns at least "(no output)"


@pytest.mark.asyncio
async def test_output_truncation(basic_worker):
    # 70 000 chars > 60 KB cap
    result = await basic_worker.execute("print('A' * 70000)", timeout=10)
    assert "TRUNCATED" in result


@pytest.mark.asyncio
async def test_write_to_workspace(basic_worker, workspace):
    result = await basic_worker.execute(
        "open(WORKSPACE_DIR + '/out.txt', 'w').write('ok')", timeout=10
    )
    assert (workspace / "out.txt").exists()


@pytest.mark.asyncio
async def test_workspace_files_listed(basic_worker, workspace):
    result = await basic_worker.execute(
        "open(WORKSPACE_DIR + '/report.txt', 'w').write('data')", timeout=10
    )
    assert "report.txt" in result


@pytest.mark.asyncio
async def test_stateless_print(stateless_ro):
    result = await stateless_ro.execute("print('stateless hello')", timeout=10)
    assert "stateless hello" in result


@pytest.mark.asyncio
async def test_stateless_math(stateless_ro):
    result = await stateless_ro.execute("print(3 * 7)", timeout=10)
    assert "21" in result
