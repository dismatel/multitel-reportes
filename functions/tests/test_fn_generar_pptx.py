"""
tests/test_fn_generar_pptx.py
Tests unitarios para la funcion fn_generar_pptx.
Especialmente el run merging de python-pptx.
"""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from io import BytesIO

# Agregar el directorio functions al path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fn_generar_pptx import (
    _merge_runs_in_paragraph,
    _replace_text_in_paragraph,
    _replace_variables_in_shape,
    _replace_all_variables,
    _build_variables_dict,
    _get_slide_index_for_slot,
    _calcular_hash_sha256,
)


class MockFont:
      def __init__(self):
                self.bold = None
                self.size = None
                self.name = None
                self.color = MagicMock()
                self.color.type = None


class MockRun:
      def __init__(self, text):
                self.text = text
                self.font = MockFont()


class MockParagraph:
      def __init__(self, runs_texts):
                self.runs = [MockRun(t) for t in runs_texts]


# ============================================================
# TESTS CRITICOS: Run Merging
# ============================================================

class TestRunMerging:
      """
          Tests para el problema critico de python-pptx donde
              {{Variable}} se divide en multiples runs: "{{", "Variable", "}}"
      """

    def test_merge_runs_simple(self):
              """Test basico: concatenacion de runs."""
              paragraph = MockParagraph(["Hola", " ", "mundo"])
              result = _merge_runs_in_paragraph(paragraph)
              assert result == "Hola mundo"

    def test_merge_runs_variable_dividida(self):
              """
                      CASO CRITICO: {{Cliente}} dividido en 3 runs por python-pptx.
                              """
              paragraph = MockParagraph(["{{", "Cliente", "}}"])
              result = _merge_runs_in_paragraph(paragraph)
              assert result == "{{Cliente}}"

    def test_merge_runs_multiple_variables(self):
              """Multiples variables en el mismo parrafo."""
              paragraph = MockParagraph(["{{", "Cliente", "}} - {{", "Nodo", "}}"])
              result = _merge_runs_in_paragraph(paragraph)
              assert result == "{{Cliente}} - {{Nodo}}"

    def test_merge_runs_empty(self):
              """Parrafo vacio."""
              paragraph = MockParagraph([])
              result = _merge_runs_in_paragraph(paragraph)
              assert result == ""

    def test_merge_runs_sin_variables(self):
              """Parrafo sin variables."""
              paragraph = MockParagraph(["Texto normal sin variables"])
              result = _merge_runs_in_paragraph(paragraph)
              assert result == "Texto normal sin variables"


class TestReplaceTextInParagraph:
      """Tests para el reemplazo de texto en parrafos."""

    def test_reemplaza_variable_simple(self):
              """Reemplaza {{Cliente}} en un solo run."""
              paragraph = MockParagraph(["Reporte de {{Cliente}} - {{Fecha}}"])
              variables = {"Cliente": "Empresa ABC", "Fecha": "2026-04-01"}
              _replace_text_in_paragraph(paragraph, variables)
              assert paragraph.runs[0].text == "Reporte de Empresa ABC - 2026-04-01"

    def test_reemplaza_variable_dividida_en_runs(self):
              """
                      CASO CRITICO: {{Cliente}} dividido en 3 runs.
                              Despues del replace, el primer run debe tener el texto completo
                                      y los demas runs deben quedar vacios.
                                              """
              paragraph = MockParagraph(["{{", "Cliente", "}}"])
              variables = {"Cliente": "Multitel S.A. de C.V."}
              _replace_text_in_paragraph(paragraph, variables)

        # El primer run debe tener el texto reemplazado
              assert paragraph.runs[0].text == "Multitel S.A. de C.V."
              # Los otros runs deben estar vacios
              assert paragraph.runs[1].text == ""
              assert paragraph.runs[2].text == ""

    def test_reemplaza_variable_dividida_compleja(self):
              """Variable con texto antes y despues."""
              paragraph = MockParagraph(["Cliente: {{", "ID del Servicio", "}} FIN"])
              variables = {"ID del Servicio": "SV-12345"}
              _replace_text_in_paragraph(paragraph, variables)
              assert paragraph.runs[0].text == "Cliente: SV-12345 FIN"

    def test_no_reemplaza_sin_variables(self):
              """No toca parrafos sin variables."""
              original = "Texto sin ninguna variable de reemplazo"
              paragraph = MockParagraph([original])
              variables = {"Cliente": "ABC"}
              _replace_text_in_paragraph(paragraph, variables)
              assert paragraph.runs[0].text == original

    def test_variable_vacia(self):
              """Variable con valor vacio."""
              paragraph = MockParagraph(["{{Coordinadora}}"])
              variables = {"Coordinadora": ""}
              _replace_text_in_paragraph(paragraph, variables)
              assert paragraph.runs[0].text == ""

    def test_variable_none_se_convierte_a_vacio(self):
              """Variable con valor None se convierte a string vacio."""
              paragraph = MockParagraph(["{{ADA}}"])
              variables = {"ADA": None}
              _replace_text_in_paragraph(paragraph, variables)
              assert paragraph.runs[0].text == ""

    def test_todos_los_patchcords(self):
              """Prueba reemplazo de patchcords PC01-PC28."""
              variables = {f"PC{i:02d}": f"2m SC/UPC SM" for i in range(1, 29)}
              paragraph = MockParagraph(["Patchcord: {{PC01}}"])
              _replace_text_in_paragraph(paragraph, variables)
              assert paragraph.runs[0].text == "Patchcord: 2m SC/UPC SM"

    def test_parrafo_sin_runs(self):
              """Parrafo sin runs no lanza excepcion."""
              paragraph = MockParagraph([])
              variables = {"Cliente": "ABC"}
              # No debe lanzar excepcion
              _replace_text_in_paragraph(paragraph, variables)


class TestBuildVariablesDict:
      """Tests para la construccion del diccionario de variables."""

    def test_planta_externa_completo(self):
              """Datos completos de reporte Planta Externa."""
              reporte_data = {
                  "tipo_reporte": "planta_externa",
                  "cliente": "Empresa XYZ",
                  "id_servicio": "SV-001",
                  "encargado_grupo": "Carlos Lopez",
                  "fecha": "2026-04-01",
                  "coordinadora": "Ana Martinez",
                  "supervisor_lider": "Pedro Gomez",
                  "gerente_operativo": "Luis Hernandez",
                  "datos_tecnicos": {
                      "nodo": "NODO-01",
                      "tipo_servicio": "Fibra FTTH",
                      "equipo_instalado": "OLT Huawei",
                      "potencia_caja_liu": -15.5,
                      "perdida_caja_liu": 0.5,
                      "fusion_caja_liu": 0.1,
                      "perdida_mufa_ultima": 0.3,
                      "ada": "ADA-001",
                      "odi": "ODI-001",
                  },
                  "patchcords": [
                      {"metraje": 2, "tipo": "SC/UPC", "modo": "SM"},
                      {"metraje": 5, "tipo": "LC/APC", "modo": "MM"},
                  ],
              }
              variables = _build_variables_dict(reporte_data)

        assert variables["Cliente"] == "Empresa XYZ"
        assert variables["ID del Servicio"] == "SV-001"
        assert variables["Encargado de grupo"] == "Carlos Lopez"
        assert variables["Fecha"] == "2026-04-01"
        assert variables["Coordinadora"] == "Ana Martinez"
        assert variables["Nodo"] == "NODO-01"
        assert variables["PotenciaCajaLiu"] == "-15.5"
        assert variables["PC01"] == "2m SC/UPC SM"
        assert variables["PC02"] == "5m LC/APC MM"
        assert variables["PC03"] == ""  # Patchcord vacio
        assert variables["PC28"] == ""  # Ultimo patchcord vacio

    def test_cpe_sin_patchcords(self):
              """Datos CPE sin patchcords."""
              reporte_data = {
                  "tipo_reporte": "cpe",
                  "cliente": "Cliente CPE",
                  "id_servicio": "CPE-001",
                  "encargado_grupo": "Tecnico 1",
                  "fecha": "2026-04-01",
                  "datos_tecnicos": {},
                  "patchcords": [],
              }
              variables = _build_variables_dict(reporte_data)

        # Todos los patchcords deben estar vacios
              for i in range(1, 29):
                            assert variables[f"PC{i:02d}"] == ""


class TestGetSlideIndexForSlot:
      """Tests para el mapeo de slots a diapositivas."""

    def test_planta_externa_portada(self):
              assert _get_slide_index_for_slot("foto_portada", "planta_externa") == 0

    def test_planta_externa_punta_inicial(self):
              assert _get_slide_index_for_slot("foto_punta_inicial", "planta_externa") == 2

    def test_planta_externa_materiales(self):
              assert _get_slide_index_for_slot("foto_materiales", "planta_externa") == 8

    def test_cpe_portada(self):
              assert _get_slide_index_for_slot("foto_portada", "cpe") == 9

    def test_cpe_rack_posterior(self):
              assert _get_slide_index_for_slot("foto_rack_posterior", "cpe") == 11

    def test_slot_desconocido_retorna_none(self):
              assert _get_slide_index_for_slot("slot_inexistente", "planta_externa") is None


class TestCalcularHashSHA256:
      """Tests para el calculo de hash SHA-256."""

    def test_hash_archivo_temporal(self, tmp_path):
              """Calcula hash de un archivo temporal."""
              test_file = tmp_path / "test.txt"
              test_file.write_bytes(b"Contenido de prueba Multitel")

        hash_result = _calcular_hash_sha256(str(test_file))

        assert len(hash_result) == 64  # SHA-256 hex = 64 chars
        assert all(c in "0123456789abcdef" for c in hash_result)

    def test_hash_consistente(self, tmp_path):
              """El hash del mismo archivo debe ser siempre igual."""
              test_file = tmp_path / "test.pptx"
              test_file.write_bytes(b"PK\x03\x04test pptx content")

        hash1 = _calcular_hash_sha256(str(test_file))
        hash2 = _calcular_hash_sha256(str(test_file))

        assert hash1 == hash2

    def test_hash_diferente_para_contenidos_distintos(self, tmp_path):
              """Archivos distintos deben tener hashes distintos."""
              file1 = tmp_path / "file1.txt"
              file2 = tmp_path / "file2.txt"
              file1.write_bytes(b"Contenido 1")
              file2.write_bytes(b"Contenido 2")

        hash1 = _calcular_hash_sha256(str(file1))
        hash2 = _calcular_hash_sha256(str(file2))

        assert hash1 != hash2
