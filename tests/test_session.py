"""Session-state and timeout tests."""

import pytest


@pytest.mark.asyncio
async def test_variable_persists(basic_worker):
    await basic_worker.execute("x = 42", timeout=10)
    result = await basic_worker.execute("print(x)", timeout=10)
    assert "42" in result


@pytest.mark.asyncio
async def test_function_persists(basic_worker):
    await basic_worker.execute("def greet(n): return f'hi {n}'", timeout=10)
    result = await basic_worker.execute("print(greet('world'))", timeout=10)
    assert "hi world" in result


@pytest.mark.asyncio
async def test_import_persists(basic_worker):
    await basic_worker.execute("import math", timeout=10)
    result = await basic_worker.execute("print(round(math.pi, 4))", timeout=10)
    assert "3.1416" in result


@pytest.mark.asyncio
async def test_reset_clears_variables(basic_worker):
    await basic_worker.execute("secret = 'gone'", timeout=10)
    await basic_worker.reset()
    result = await basic_worker.execute("print(secret)", timeout=10)
    assert "NameError" in result or "name" in result.lower()


@pytest.mark.asyncio
async def test_stateless_no_cross_call_state(stateless_ro):
    await stateless_ro.execute("x = 999", timeout=10)
    result = await stateless_ro.execute("print(x)", timeout=10)
    assert "NameError" in result or "name" in result.lower()


@pytest.mark.asyncio
async def test_timeout_returns_error(basic_worker):
    result = await basic_worker.execute("while True: pass", timeout=3)
    low = result.lower()
    assert "timeout" in low or "timed out" in low or "timeouter" in low


@pytest.mark.asyncio
async def test_worker_recovers_after_timeout(basic_worker):
    # First call times out
    await basic_worker.execute("while True: pass", timeout=3)
    # Second call should work normally
    result = await basic_worker.execute("print('recovered')", timeout=10)
    assert "recovered" in result


@pytest.mark.asyncio
async def test_write_worker_has_independent_state(basic_worker, write_worker):
    """The two persistent workers maintain separate namespaces."""
    await basic_worker.execute("shared = 'basic'", timeout=10)
    result = await write_worker.execute("print(shared)", timeout=10)
    # write_worker has its own namespace — 'shared' should not be defined there
    assert "NameError" in result or "basic" not in result
