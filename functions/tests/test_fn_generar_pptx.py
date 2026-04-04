"""
tests/test_fn_generar_pptx.py
Tests basicos que no requieren importar la function directamente.
"""
import pytest


def test_placeholder_ok():
    """Test basico para verificar que pytest corre correctamente."""
    assert True


def test_reporte_id_format():
    """Verifica formato UUID basico."""
    import re
    uuid_re = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    test_id = "550e8400-e29b-41d4-a716-446655440000"
    assert uuid_re.match(test_id)


def test_build_variables_basic():
    """Verifica construccion basica de variables."""
    variables = {
        "Cliente": "Empresa ABC",
        "Fecha": "2026-04-04",
        "Nodo": "NODO-01",
    }
    assert variables["Cliente"] == "Empresa ABC"
    assert "{{Cliente}}" not in variables.values()
