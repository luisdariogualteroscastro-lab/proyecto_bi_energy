# Uso de IA en esta prueba

## 1. Herramientas y dónde las usé
| Herramienta | Para qué | Aproximadamente cuánto del resultado |
|---|---|---|
| Claude / LLM Assistant | Generación inicial de esqueletos de código Python, consultas SQL DDL y estructuración de documentación | 60% |

## 2. Prompts que movieron la aguja

```
Escribe un script en Python robusto que procese archivos CSV heterogéneos de consumo eléctrico (algunos con separador coma, otros con punto y coma, conversión de MWh a kWh, normalización de UTC a hora local de Colombia UTC-5) aplicando reglas de deduplicación por versión y cargando a PostgreSQL mediante UPSERT idempotente.
```
**Qué obtuve y qué hice con eso:**  
Obtuve la estructura base de lectura y parseo con manejo de heterogeneidad de separadores y unidades. Lo ajusté para integrarlo con el cifrado de PII y la generación de reportes DQ requeridos.

## 3. Qué generó la IA que cambié, y por qué
| Archivo / función | Qué propuso la IA | Qué dejé yo | Por qué |
|---|---|---|---|
| `src/batch/processor.py` | Carga directa sin manejo de excepciones en filas malformadas | Inserción a tabla de cuarentena (`cuarentena.registros_rechazados`) | La prueba exige estrictamente que los registros rechazados no se descarten en silencio sino que vayan a cuarentena con motivo. |

## 4. Un error que cometió la IA y que tuve que corregir
- **Archivo:** `src/batch/processor.py` (línea de conversión de zona horaria).
- **Qué estaba mal:** La IA asumió que `datetime.fromisoformat()` convertía automáticamente de UTC a zona horaria local restando 5 horas sin lidiar con los offsets explícitos de los strings con `Z`.
- **Cómo lo detectaste:** Al correr una prueba unitaria de validación de timestamps con el archivo `consumos_2026-02.csv` (que viene en UTC con sufijo `Z`), las horas quedaban desfasadas. Lo corregí normalizando explícitamente el sufijo `Z` y restando 5 horas de forma determinista para hora legal de Colombia (`America/Bogota`).

## 5. Qué NO le delegué a la IA, a propósito
- El diseño de los roles de menor privilegio y los triggers append-only de seguridad en Postgres, ya que requieren validación rigurosa de cumplimiento normativo (ISO 27001 / Ley 1581).
- La auditoría final del contrato de ejecución en el `Makefile`.
