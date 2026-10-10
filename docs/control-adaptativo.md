# Diseño del seguimiento adaptativo

El catálogo versionado, lotes, densidades manuales y etapas supervisadas están integrados con Node-RED: ver [gestor de perfiles](../server/profiles/README.md). Las consignas remotas siguen bloqueadas. El control adaptativo, ML y el envío automático de perfiles siguen pendientes. Este documento describe también capacidades futuras; no todas se atribuyen al despliegue actual.

## Datos del proceso

- **Receta versionada:** nombre, estilo, levadura, perfil térmico, límites de temperatura y rampas, FG estimada o atenuación esperada, criterios de etapas y duración mínima/máxima. Guardar otra versión no modifica la que usa un lote.
- **Lote:** identificador, fermentador, receta y versión, fecha inicial, volumen, densidad inicial, temperatura inicial real, etapa, modo y confirmaciones.
- **Medición manual:** fecha con zona horaria, valor y unidad originales, instrumento, temperatura de muestra, calibración/corrección, SG corregida y observaciones. Una carga tardía conserva la fecha de medición.
- **Medición térmica:** mosto, interior de cámara y exterior cuando sean sensores distintos; compresor, tiempo desde la transición, consignas deseada/aplicada y calidad. Identificar simulación o dato real.

SQLite es la base inicial del catálogo. InfluxDB conserva series temporales. La integración deberá resolver también almacenamiento de lotes, mediciones manuales, permisos y recuperación.

## Métricas distintas

Estimación de atenuación aparente en puntos de SG:

`100 × (OG − SG actual) / (OG − 1)`

Avance hacia una FG estimada:

`100 × (OG − SG actual) / (OG − FG estimada)`

OG 1.050, SG 1.020 y FG estimada 1.010 producen aproximadamente 60 % de atenuación aparente y 75 % de avance. Ninguno mide directamente azúcares residuales ni diacetilo. OG y volumen, por sí solos, no determinan una duración exacta de fermentación.

Calcular tendencia y estabilidad con cobertura temporal, fechas distintas y mediciones recientes. Los parámetros iniciales de la biblioteca son ejemplos configurables, no criterios universales de cerveza terminada. La densidad debe estar corregida antes de calcular; no hay conversión automática de lecturas crudas de refractómetro.

## Etapas y decisiones

La primera integración propone transiciones para confirmación manual.

| Estado | Datos revisados | Acción |
|---|---|---|
| Preparación | Receta, OG, temperatura inicial, sensores | Confirmar inicio |
| Fermentación | Tendencia de densidad, temperaturas, límites de tiempo | Mantener perfil o proponer un ajuste limitado |
| Descanso | Criterio de avance para la levadura, duración | Proponer descanso y registrar inicio |
| Verificación | Estabilidad, FG esperada, comprobación de diacetilo | Solicitar confirmación de enfriado |
| Enfriado | Confirmación, rampa y límites del compresor | Seguir perfil autorizado |
| Finalizado | Cierre confirmado y medición final | Archivar lote |

Una lectura faltante, inválida o no corregida no habilita transiciones. Registrar diacetilo como pendiente, aprobado, no aprobado o no realizado, con fecha y observación. No deducir su eliminación de la temperatura o atenuación.

Registrar sugerencias, datos de entrada, motivo, aceptación/rechazo y consigna efectiva. No iniciar enfriado profundo únicamente porque terminó un calendario o un modelo predijo la finalización.

## Aprendizaje automático

Primero comparar contra histéresis y un modelo térmico sencillo. Un ensayo con agua caracteriza inercia y refrigeración, pero no reproduce el calor de la fermentación.

Un primer modelo puede predecir temperatura del mosto a corto plazo con interior/exterior, historial térmico, consigna, compresor, volumen y etapa. La densidad y su tendencia aportan contexto; no lo convierten en detector de diacetilo.

Usar datos reales identificados por lote y separar entrenamiento/evaluación por lote y tiempo. No entrenar ni demostrar rendimiento con las pruebas actuales, ni repartir al azar puntos vecinos de una misma fermentación.

Evaluar error, tiempo en banda, sobrepaso y ciclos del compresor. Tiempo encendido no equivale a energía medida: afirmar ahorro eléctrico requiere medición.

Comenzar en modo observación. Luego sugerir correcciones pequeñas dentro de límites aprobados. La autorización de consignas y protección del compresor quedan fuera del modelo. Ante variables ausentes, antiguas o fuera de distribución, volver al control de referencia y explicar por qué.

## Información pendiente

- Instrumento de densidad, unidad y correcciones utilizadas.
- Ubicación de sensores y disponibilidad de temperatura exterior independiente.
- Refrigeración, posible calefacción, volumen y características de cámara.
- Levaduras, estilos y comprobación manual de diacetilo.
- Interfaz para catálogo y mediciones: Node-RED Dashboard es la propuesta inicial coherente con la instalación.

## Referencias

- [Diacetilo, White Labs](https://go.whitelabs.com/forced-diacetyl-testing).
- [Ejemplo de levadura: Fermentis US-05](https://fermentis.com/es/producto/safale-us-05/). No usar las condiciones de una levadura como regla universal.
- [Contexto y persistencia, Node-RED](https://nodered.org/docs/user-guide/context).
