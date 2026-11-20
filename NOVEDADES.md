# CANCHA 2 · Guía de las nuevas funciones

## Abrir

En el Escritorio, abre CANCHA y ejecuta INICIAR.cmd. Si tenías la versión anterior abierta, cierra su ventana del servidor y vuelve a iniciarla. El navegador se abre automáticamente. Tus cuentas y torneos se conservan.

## Torneos

Al crear una competencia se muestran cuatro tarjetas de selección:

- **Liga:** todos contra todos, una vuelta o ida y vuelta. La tabla determina al campeón, que confirma el administrador al finalizar los partidos.
- **Fase liguera + eliminatorias:** todos contra todos y una tabla única; configura cuántos equipos clasifican. Al cerrar la liga se crean las llaves de eliminación directa.
- **Grupos:** grupos iguales, dos clasificados por grupo y después eliminatorias.
- **Eliminación directa:** cruces automáticos o elegidos por ti, con pases libres cuando hacen falta.

Configura la primera fecha y los días entre jornadas. Tras inscribir equipos y completar plantillas, genera el calendario. En Partidos puedes programar todas las fechas pendientes o cambiar la fecha de un encuentro individual. Las jornadas de liga/grupos pueden tener ida y vuelta; las llaves del torneo son a partido único. Para una serie independiente de ida y vuelta utiliza el Centro de partidos.

En Grupos y llaves confirma los resultados de la fase. Puedes marcar «Quiero elegir los cruces manualmente». Cada clasificado debe aparecer una sola vez. Un desempate exacto se resuelve introduciendo los IDs de todos los equipos en el orden que corresponda: se respetan primero puntos, diferencia y goles a favor. El servidor impide clasificar mientras haya partidos pendientes o repetir/eliminar indebidamente un participante.

## Plantillas y formaciones

Registra la plantilla completa con nombre, dorsal y posición. En cada acta elige primero los convocados y después los titulares. Un jugador no convocado no puede ser titular ni entrar como sustituto.

Las formaciones se ven en una cancha con círculos de jugador, nombre y dorsal. Elige, por ejemplo, 4-3-3, 4-4-2 o 4-3-1-2 en fútbol 11. Los indicadores de goles y tarjetas aparecen junto al jugador. Los círculos usan iniciales: no se incluyen fotografías ni plantillas oficiales de clubes. La distribución visual se realiza según la posición registrada; no incluye arrastrar jugadores.

## Actas y estadísticas

Cada evento registra autor, minuto, segundo y nota opcional. Incluye goles, remates, penales convertidos y fallados, autogoles, asistencias, faltas, entradas, ocasiones claras falladas, córners, fueras de juego, paradas, tarjetas, sustituciones y penales de tanda. Baloncesto dispone de puntos, intentos, asistencias, faltas, rebotes, robos y pérdidas.

Para evitar duplicados, **un gol, penal o una ocasión clara fallada ya cuenta como un remate**. Registra un Remate separado solo para otro intento. Indica Al arco, Fuera o Bloqueado. Los penales de tanda no suman al marcador ni a los remates del partido.

En Estadísticas puedes buscar jugadores y ordenar las tablas por cada métrica. Se muestran todos los jugadores, sus equipos, cobradores de penales, anotaciones, remates y disciplina. El resumen incluye el ranking de equipos con más tarjetas. Una segunda amarilla suma una expulsión; por eso el total contabiliza las amarillas mostradas y las expulsiones registradas.

Noticias muestra el minuto a minuto de cada partido. La última jugada aparece primero. Las estadísticas solo describen los eventos ingresados: un acta antigua que tiene marcador sin acciones no permite atribuir goles a jugadores.

## Centro de partidos independiente

En el menú lateral abre **Centro de partidos**. Este panel comparte los permisos de usuario, pero sus encuentros no alteran los torneos.

1. Crea una serie de ida y vuelta o un partido único con equipos, deporte, duración y fechas.
2. En Alineaciones, carga las plantillas completas de ambos equipos: `nombre; dorsal; posición`, una línea por jugador.
3. Elige convocados, titulares y formación para cada encuentro.
4. Inicia el partido. El reloj puede pausarse, reanudarse y ajustarse; su estado se guarda y continúa al recargar la página.
5. Usa los botones de eventos, selecciona el jugador y confirma el tiempo. El marcador, las estadísticas y las noticias se actualizan al guardar.
6. Si te equivocas, retira el último evento con un motivo y vuelve a ingresarlo. La corrección queda en el historial. Solo se permiten correcciones antes de finalizar.
7. Finaliza la ida antes de iniciar la vuelta. Se muestra el marcador de cada encuentro y el global. No existe regla de gol visitante.

Los expulsados no pueden participar en acciones posteriores. Fútbol 11 y 7 no permiten reingreso; futsal y baloncesto sí. En baloncesto se excluye al jugador que acumula cinco faltas. Los penales de tanda alternan equipos, guardan cobrador y resultado y no permiten repetir cobrador antes de que todos los habilitados hayan cobrado. El cierre comprueba que una tanda usada para resolver el global empatado tenga ganador.

Los visitantes pueden consultar; administrador y empleado pueden registrar. Se detectan conflictos si dos personas intentan guardar sobre la misma revisión. Los paneles abiertos consultan cambios cada cinco segundos.

## Próximo partido

La pestaña usa hasta diez partidos finalizados por equipo **registrados en este centro**, con el mismo deporte y nombre de equipo. Muestra goles esperados, porcentajes de victoria/empate/derrota, tres marcadores posibles y medias de remates, faltas y tarjetas.

Es un cálculo Poisson exploratorio, no una predicción entrenada o calibrada. Los parámetros de goles combinan el promedio anotado por cada equipo y el promedio recibido por su rival. Se informa la cantidad de partidos y se advierte cuando la muestra es pequeña. No incorpora noticias, lesiones, localía ni datos externos. Escribir «Barcelona» no descarga sus resultados reales. Baloncesto conserva el registro y las estadísticas, pero no utiliza este estimador de fútbol.

## Conservación de datos y límites

La actualización añade columnas y la tabla del centro en vivo al SQLite existente. No reemplaza cuentas ni torneos. La carpeta `instance` contiene la base de datos y la clave: conserva una copia de seguridad.

Continúan fuera del alcance: fuentes oficiales en vivo, fotos de jugadores, recuperación de contraseñas, publicación en Internet, suspensión entre partidos, exclusiones temporales de futsal, desglose de prórrogas y faltas técnicas/descalificantes de baloncesto. Las asistencias se registran como eventos independientes. Las imágenes de referencia se usaron como guía de estructura y presentación, sin añadir cuotas ni servicios de apuestas.

## Tablas compactas y edición de plantillas

Estadísticas abre con una clasificación compacta. Los botones de goleadores, asistencias, remates y tarjetas muestran solo las columnas de esa categoría. El selector permite consultar las demás métricas; puedes elegir jugadores o equipos, filtrar por equipo, buscar y alternar General/Local/Visitante. Se muestran 15 filas por página. Restablecer filtros vuelve a la vista general. La forma presenta los últimos cinco resultados (G/E/P). En eliminación directa se muestra el cuadro de llaves, sin tabla de puntos.

En Equipos → Ver plantilla puedes editar nombre, dorsal y posición y pulsar Guardar cambios, incluso después de generar el calendario. Cada jugador conserva su ID y sus eventos. Se permiten intercambios de dorsales siempre que no queden repetidos. Si otra pestaña ha modificado la misma plantilla, se pide recargarla antes de guardar. También puedes agregar jugadores después de generar la programación; debes convocarlos expresamente en los siguientes partidos.

## Correcciones de competición

- El acta muestra la tanda solo con marcador empatado en eliminatorias. Cada cobro requiere jugador y resultado (gol o fallado); los totales se calculan automáticamente. Los penales antiguos conservan sus totales, pero al editar una de esas actas hay que completar los cobradores.
- 26 formaciones para fútbol 11, 12 para fútbol 7 y 8 para futsal.
- Cuadro conectado completo hasta la final, incluidos 16 y 32 puestos. Sorteo inicial o puestos manuales; los ganadores siguen el camino fijado.
- La confirmación de ronda muestra nombres. Solo los empates exactos en clasificaciones requieren ordenar equipos para desempatar.
- En grupos se elige cuántos equipos clasifican por grupo. Primero se completan los grupos y después se generan las eliminatorias.
- La liga por puntos y la fase liguera con eliminatorias mantienen sus propias reglas. Eliminación directa no muestra clasificación por puntos.

Validación: 19 pruebas automáticas y comprobaciones de estructura del cuadro y número de jugadores de cada formación. Migración comprobada sobre una copia de los datos existentes.

## Ida y vuelta por cruce
En el cuadro, pulsa Elegir ida y vuelta antes de registrar la ida. Solo cambia ese cruce, incluida la final si lo eliges. La vuelta invierte localía y tiene fecha y acta independientes. Avanza el ganador global, sin ventaja por gol visitante. Los penales corresponden únicamente a la vuelta si el global queda empatado. Una vez registrada la vuelta, la ida queda protegida contra cambios.
## Configuración inicial y totales del partido
La modalidad de ida y vuelta se configura desde el cuadro antes del primer resultado del torneo, incluidas rondas futuras. Después queda bloqueada. Los totales manuales de remates, córneres y fueras de juego se conservan separadamente de los eventos y se muestran en la ficha; no se atribuyen a jugadores. Se pueden indicar pases completados sin conocer los totales. Si se completan ambos campos, los acertados no pueden superar el total del mismo equipo. Los IDs internos de equipos no aparecen en sus tarjetas.
## Noticias basadas en datos
Los resultados de remates ya no se muestran en tarjetas, goles ni sustituciones. Noticias destaca cifras registradas de posesión, remates, córneres, expulsiones y pases; no inventa datos ausentes ni atribuye causalidad a las comparaciones.
