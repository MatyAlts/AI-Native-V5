"""Schemas Pydantic compartidos para entidades academicas.

ADR-047: los ejercicios pasaron a ser entidad de primera clase. Los
schemas correspondientes viven en `platform_contracts.academic.ejercicio`.
Este modulo queda intencionalmente vacio — se mantiene como punto de
extension para futuros schemas compartidos del plano academico que NO
sean eventos (los eventos viven en `.events`).
"""

from __future__ import annotations
