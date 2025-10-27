import pytest
from app.services.resolver import resolve

@pytest.mark.skip(reason="Requires database connection")
def test_resolve_symbol():
    result = resolve("AAPL")
    assert result.symbol == "AAPL"
    assert result.company_name is not None

@pytest.mark.skip(reason="Requires database connection")
def test_resolve_company_name():
    result = resolve("Apple")
    assert result.symbol == "AAPL"
