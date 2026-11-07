# AI Usage & Decision Note

**Herramientas:** Claude (Anthropic), usado como asistente de arquitectura y programación durante el examen.

**Para qué se usó**
- Diagnóstico del repositorio inicial: detectó una clasificación fija en el código, un fixture con una hora incorrecta (E-1012) y datos personales expuestos.
- Transcripción de las respuestas de ejemplo del examen a JSON.
- Propuesta de alternativas para cada decisión (D-001 a D-009) y redacción del registro de decisiones.
- Generación del código del motor, de los endpoints y de las pruebas.

**Resultados aceptados:** el pipeline determinista (D-002), la jerarquía de fuentes, la regla de conexión, el filtro de alternativas y la exposición mínima de datos personales.

**Resultados rechazados o modificados**
- Se descartó una arquitectura agéntica o con IA en tiempo de ejecución (D-002 C).
- En R5 se eligió la opción conservadora B frente a A (D-007).
- La propuesta inicial de eliminar `age` y `fare_family` del fixture se rechazó al comprobar en el examen que esos datos sí existen.

**Cómo se verificó**
- La transcripción JSON se comparó manualmente con las fotografías del examen.
- El caso base se resolvió a mano y se contrastó con la salida del motor.
- 27 pruebas automatizadas se ejecutaron en el equipo del estudiante.
- Cada cambio se aplicó como parche revisado sobre `feature/backend` (`git apply --check` antes de aplicar).

**Decisiones tomadas personalmente:** aprobación de D-001 a D-009, elección de B en el algoritmo y en R5, estrategia de ramas y momento de fusionar a `main`.

**Información que nunca entregaría a un modelo:** email, teléfono, `document_id` y `loyalty_tier` del pasajero, la edad del menor, credenciales y claves de idempotencia reales. Tampoco la decisión de reubicar o compensar: esa permanece determinista o humana.
