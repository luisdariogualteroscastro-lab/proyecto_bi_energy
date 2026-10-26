# Seguridad de la solución

## 1. Clasificación de datos
Definido en `data_classification.yaml`. Cada columna se encuentra catalogada en `Público`, `Interno`, `Confidencial` o `Restringido-PII`. El pipeline batch valida metadatos y aplica restricciones acordes.

## 2. Cifrado
| Qué | Dónde | Mecanismo | Gestión de la llave |
|---|---|---|---|
| PII (NIT, email, celular, rep_legal) | `core.dim_cliente` | AES-256-GCM a nivel de aplicación con derivadas de `LLAVE_MAESTRA` | Inyectada por variable de entorno |

- **Joins sobre campos sensibles:** Se utiliza un hash SHA-256 (`nit_hash`) almacenado en columna separada para permitir búsquedas e índices sin descifrar el texto original.

## 3. Control de accesos (menor privilegio)
| Rol | Puede | NO puede | Dónde está el GRANT |
|---|---|---|---|
| `rol_ingesta` | Escribir en `core` y `cuarentena`, insertar en `audit` | Leer PII en claro sin descifrar | `sql/init.sql` |
| `rol_analista` | Consultar la vista `analytics.v_consumo_diario` | Tocar tablas base o ver PII | `sql/init.sql` |
| `rol_auditor` | Leer bitácoras en `audit` y cuarentena | Ver PII o modificar registros | `sql/init.sql` |

## 4. Enmascaramiento de PII
- Las observaciones en `clientes.csv` con correos, teléfonos o cédulas incrustadas se enmascaran automáticamente mediante expresiones regulares antes del cifrado y almacenamiento.

## 5. Gestión de secretos
- Cero credenciales en código. Scaffolding auditado para remover secretos expuestos (`S3cr3t_H3r3d4d0`), migrando a `.env` y variables de entorno dinámicas.

## 6. Trazabilidad y auditoría
- Bitácora append-only `audit.log_ejecuciones` protegida mediante un trigger de base de datos que aborta cualquier intento de `UPDATE` o `DELETE`.

## 7. Dependencias
- `requirements.txt` actualizado a versiones seguras y sin vulnerabilidades conocidas (`requests>=2.32.3`, `cryptography>=43.0.0`, etc.).

## 8. Cómo verificar todo lo anterior
```bash
make up
make run
make verificar
```
Adicionalmente, se puede ejecutar `pytest` para verificar los tests unitarios de seguridad y cifrado.
