# ADR-061 — La corrección con Active-IA no pasa por el ai-gateway

- **Estado**: **Propuesto** — la decisión técnica está tomada y **la personería quedó resuelta el 2026-08-27** (§ Consentimiento): son la misma, así que el consentimiento vigente alcanza y el despliegue con datos reales deja de estar bloqueado por ahí. Sigue *Propuesto* por lo único que falta: el **borrado por alumno del lado de Active-IA** (tarea 5.5), que depende del §3.6 de ellos, todavía sin empezar.
- **Fecha**: 2026-08-19
- **Deciders**: Alberto Cortez (decisión de privacidad y su defensa académica). Juani Sarmiento (implementación).
- **Tags**: privacidad, integraciones, correccion, terceros, activeia
- **Relacionado**: [ADR-004](004-ai-gateway-propio.md) — nombra explícitamente "evaluation para sugerencia de notas" entre los consumidores del gateway. Este ADR documenta por qué ese caso quedó afuera.

## Contexto y problema

El ADR-004 estableció una regla que la plataforma cumple en todos lados:
**todo LLM y todo embedding pasa por el `ai-gateway`**, para tener budget por
tenant, caché, fallback entre proveedores y una sola superficie donde viven las
credenciales.

La corrección asistida con Active-IA **no la cumple**. El `evaluation-service`
habla directo con `https://api.active-ia.com`.

Eso es una excepción a una regla que sostiene tres propiedades del piloto, así
que necesita quedar escrita: si no, dentro de seis meses alguien la lee como un
descuido y "arregla" el ruteo.

## Por qué no pasa por el gateway

**1. Active-IA no es un proveedor de LLM: es un servicio de corrección.**

El gateway rutea `completions` y `embeddings` — pide texto, devuelve texto, y
puede cambiar de proveedor porque el contrato es el mismo. Active-IA recibe **el
código del alumno, el resultado de los tests que ya corrimos en nuestro sandbox,
y una referencia al ejercicio** que del otro lado resuelve a una rúbrica; y
devuelve una nota con desglose y un PDF. No hay otro proveedor al que rutear
eso, porque no es una capacidad genérica: es un producto con su propio modelo
de datos, sus cuentas y sus rúbricas cargadas del otro lado.

Meterlo en el gateway obligaría a que el gateway conozca rúbricas, comisiones y
entregas. Eso convierte un proxy de LLM en un segundo backend académico.

**2. El fallback no aplica, y ofrecerlo sería peor.**

El valor del gateway ante una caída es rutear a otro proveedor. Acá no hay a
dónde: la rúbrica vive en Active-IA. Si Active-IA no responde, la corrección
**no se hace** — y esa es la respuesta correcta, no una degradación.

La invariante del epic es exactamente ésa: **un fallo de infraestructura nunca
se convierte en nota.** Un fallback silencioso a otro motor sería la forma más
directa de romperla.

**3. Las credenciales son por docente, no por tenant.**

El gateway maneja claves de la institución (`BYOK`, ADR-038): una por tenant y
proveedor. Acá cada docente conecta **su propia cuenta de Active-IA**, con su
usuario y contraseña, porque las rúbricas que puede usar dependen de esa cuenta.

El modelo del gateway no tiene lugar para eso sin distorsionarlo.

## Consecuencias asumidas

Que esté fuera del gateway tiene un costo, y no se disimula:

| Lo que el gateway da | Cómo se resuelve acá |
|---|---|
| Budget por tenant | Cuota diaria por docente (`ACTIVEIA_CUOTA_DIARIA_POR_DOCENTE`), que **falla cerrada** |
| Observabilidad del gasto | Métricas propias (`activeia_correcciones_*`), ADR-tarea 6.2 |
| Credenciales en un solo lugar | `ACTIVEIA_MASTER_KEY` propia, AES-256-GCM, en `evaluation-service` |
| Kill switch central | `ACTIVEIA_ENABLED`, default `false` |

**La master key es propia y no la de BYOK, a propósito** (design D5). Compartirla
ampliaría el blast radius de una superficie a dos: si se filtra la del gateway,
las cuentas de los docentes siguen cifradas, y al revés.

## La parte de privacidad, que es la que importa para la tesis

Esto **manda código de estudiantes a un servidor de un tercero**. No es un
detalle de arquitectura: es un tratamiento de datos personales del piloto.

Lo que sí está resuelto:

- **Falla cerrado.** `ACTIVEIA_ENABLED=false` por default. Un doc no frena un
  deploy; un default sí.
- **La plataforma nunca escribe en calificaciones.** El resultado se muestra
  como sugerencia; "Usar como base" rellena el formulario y no guarda. La nota
  la pone el docente.
- **Derecho al olvido parcial.** El procedimiento borra de nuestro lado el
  artefacto, el snapshot de tests, el desglose y el PDF.

Los dos gates que mantenían este ADR en *Propuesto*. El primero se cerró el
2026-08-27; el segundo sigue abierto y es el único que falta:

### Consentimiento y personería (tarea 0.5, RESUELTA el 2026-08-27)

> **Son la misma personería.** Confirmado por Juani el 2026-08-27 y comunicado
> por escrito a Active-IA en `docs/research/activeia-respuesta-2026-08-27.md`
> §2.1, que era lo que ellos pedían como punto 2 de su documento del 24/08.
>
> Se aplica entonces la primera rama de las dos que este ADR planteaba: **el
> tratamiento es interno y el consentimiento vigente alcanza**. Mandarle el
> código de un alumno a Active-IA **no es una cesión a un tercero**, así que no
> hace falta tocar el texto del consentimiento del piloto.
>
> **Lo que esto NO cubre**, y conviene no leerlo de más: la limitación que el
> propio equipo de Active-IA declaró de frente — la anonimización va a cubrir la
> base viva pero **no los respaldos históricos**. Ser la misma personería no
> responde qué pasa con lo que quedó en un backup anterior a un borrado. Eso
> sigue abierto y va a la dirección del proyecto junto con la política de
> retención.

El razonamiento original, que se conserva porque es lo que fundamenta la
respuesta de arriba:

**Hay que determinar si AI-Native y Active-IA son la misma personería frente al
consentimiento firmado por los estudiantes del piloto.**

- Si **lo son**: el tratamiento es interno y el consentimiento vigente alcanza.
- Si **no lo son**: mandar código de un alumno a Active-IA es una **cesión a un
  tercero**, y el consentimiento del piloto tiene que decirlo explícitamente.
  Sin eso, el dato se cedió sin base legal — y para una tesis que se defiende
  sobre auditabilidad y privacidad, eso no es un detalle operativo.

**Esta pregunta bloquea el despliegue con datos reales.** No bloquea el
desarrollo, y por eso los epics 1–5 están implementados: el flag apagado hace
que el código exista sin que se ejecute sobre nadie.

### Borrado del lado de Active-IA (tarea 5.5, ABIERTA)

El derecho al olvido hoy es **parcial**: borra lo nuestro. Active-IA **no expone
un endpoint de borrado por alumno** — está pedido en
`docs/research/activeia-cambios-pedidos.md` (3.6).

Mientras eso no exista, la respuesta honesta a un alumno que pide el borrado es
"lo borramos de la plataforma, y el pedido a Active-IA se hace por fuera". El
procedimiento no puede decir que borró todo, porque no borró todo.

## Alternativas consideradas

**Rutear igual por el gateway, como un proveedor más.** Descartada: obligaría al
gateway a conocer rúbricas y comisiones, y el fallback —su razón de ser— no
tiene sentido acá.

**Un servicio propio de corrección.** Fuera de alcance del piloto y del ADR-004.
Además, la corrección de Active-IA es un producto con coautoría (Ana Garis) y
prompts que no se tocan.

**No integrar.** Era la posición hasta este epic: `FEATURES.md` decía "vive en
active-ia, fuera de scope". Se revisó porque la corrección manual del piloto no
escala a las tres comisiones.

## Pendiente antes de pasar a Aceptado

- [x] Resolver la personería (tarea 0.5) y escribir acá la respuesta — 2026-08-27: son la misma
- [x] Si son personerías distintas: revisar el texto del consentimiento del piloto — NO aplica, son la misma
- [ ] Borrado por alumno del lado de Active-IA (tarea 5.5) — **lo único que falta.** Depende del §3.6 de ellos, especificado y sin empezar
- [ ] Política de retención para los respaldos históricos, que la anonimización de ellos NO cubre (lo declararon el 24/08). Va a la dirección del proyecto
