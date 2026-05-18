// La regla de evitar Unicode (cp1252 en Windows) aplica a stdout de scripts Python, no a TSX servido al browser.
import type { ReactNode } from "react"

type HelpContentMap = Record<string, ReactNode>

export const helpContent: HelpContentMap = {
  home: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Panel de Administración</p>
      <p>
        Este panel centraliza la gestión de la estructura academica institucional: universidades,
        facultades, carreras, planes, materias, comisiones y periodos.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Universidades:</strong> Tenants raiz. Solo superadmin puede crear nuevas.
        </li>
        <li>
          <strong>Facultades:</strong> Divisiones dentro de una universidad. Requieren universidad
          creada.
        </li>
        <li>
          <strong>Carreras:</strong> Programas academicos. Requieren facultad creada.
        </li>
        <li>
          <strong>Planes:</strong> Versiones de plan por carrera (vigentes y derogados).
        </li>
        <li>
          <strong>Materias:</strong> Asignaturas asociadas a un plan de estudios.
        </li>
        <li>
          <strong>Comisiones:</strong> Secciones de cursado por materia y periodo.
        </li>
        <li>
          <strong>Periodos:</strong> Ciclos lectivos (ej. 2026-S1). Cada comision vive en un
          periodo.
        </li>
        <li>
          <strong>Importacion masiva:</strong> Carga CSV de entidades con dry-run preview.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Consejo:</p>
        <p className="text-sm mt-1">
          El orden de creacion es: Universidad → Facultad → Carrera → Plan → Materia → Periodo →
          Comision.
        </p>
      </div>
    </div>
  ),

  universidades: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Universidades</p>
      <p>
        Las universidades son los tenants raiz del sistema. Cada una tiene su propio realm de
        Keycloak y aislamiento de datos via Row-Level Security.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Crear:</strong> Requiere rol superadmin. Completa nombre, codigo, realm Keycloak y
          dominio email opcional.
        </li>
        <li>
          <strong>Codigo:</strong> Identificador corto unico (ej. unsl). Solo letras, numeros,
          guiones. Inmutable una vez creado.
        </li>
        <li>
          <strong>Realm Keycloak:</strong> Nombre del realm en Keycloak. Debe existir o ser creado
          via onboarding.
        </li>
        <li>
          <strong>Eliminar:</strong> Falla si la universidad tiene facultades u otras entidades
          asociadas.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Nota:</p>
        <p className="text-sm mt-1">
          El codigo y el realm Keycloak son inmutables. Definirlos con cuidado antes de crear la
          universidad.
        </p>
      </div>
      <div className="bg-danger/50 p-4 rounded-lg mt-2 border border-danger">
        <p className="text-[var(--danger-text)] font-medium">Advertencia:</p>
        <p className="text-sm mt-1">
          Eliminar una universidad con datos asociados fallara con error 422. Primero elimina todas
          las entidades dependientes.
        </p>
      </div>
    </div>
  ),

  facultades: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Facultades</p>
      <p>
        Las facultades son divisiones academicas dentro de una universidad. Cada carrera pertenece a
        una facultad.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Seleccionar universidad:</strong> El filtro de universidad carga las facultades
          correspondientes.
        </li>
        <li>
          <strong>Crear facultad:</strong> Haz clic en "Crear facultad" con una universidad
          seleccionada. Completa codigo y nombre.
        </li>
        <li>
          <strong>Codigo:</strong> Identificador corto unico dentro de la universidad (ej. FCFMyN).
        </li>
        <li>
          <strong>Eliminar:</strong> Soft-delete logico. La facultad desaparece de la lista pero sus
          datos historicos se preservan.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Nota:</p>
        <p className="text-sm mt-1">
          Si no hay universidades creadas, el boton "Crear facultad" estara deshabilitado. Primero
          crea una universidad.
        </p>
      </div>
    </div>
  ),

  carreras: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Carreras</p>
      <p>
        Las carreras son programas academicos del tenant actual. Cada carrera pertenece a una
        facultad y puede tener multiples planes de estudio.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Crear carrera:</strong> Requiere al menos una facultad existente. Selecciona
          facultad, completa codigo, nombre, duracion y modalidad.
        </li>
        <li>
          <strong>Codigo:</strong> Identificador corto (ej. LIS, ING-COMP). Solo letras, numeros,
          guiones.
        </li>
        <li>
          <strong>Duracion:</strong> En semestres. Tipicamente 8 o 10 para licenciaturas.
        </li>
        <li>
          <strong>Modalidad:</strong> Presencial, virtual o hibrida.
        </li>
        <li>
          <strong>Eliminar:</strong> Falla si la carrera tiene planes, materias o comisiones
          asociadas.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Nota:</p>
        <p className="text-sm mt-1">
          El boton "Nueva carrera" estara deshabilitado si no hay facultades creadas. Crea una
          facultad primero.
        </p>
      </div>
    </div>
  ),

  planes: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Planes de Estudio</p>
      <p>
        Los planes de estudio son versiones del curriculum de una carrera. Pueden estar vigentes o
        derogados. Usa los selectores en cascada para navegar Universidad → Carrera → Planes.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Crear plan:</strong> Selecciona universidad y carrera primero. Completa version,
          ano de inicio, ordenanza y vigencia.
        </li>
        <li>
          <strong>Version:</strong> Identificador del plan (ej. 2024, Plan-2020). Libre pero unico
          por carrera.
        </li>
        <li>
          <strong>Ordenanza:</strong> Opcional. Referencia a la resolucion de Consejo Superior (ej.
          Res. CS No 12/24).
        </li>
        <li>
          <strong>Vigente:</strong> Indica si el plan esta activo para nuevas inscripciones.
        </li>
        <li>
          <strong>Eliminar:</strong> Soft-delete logico. Falla si el plan tiene materias activas.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Nota:</p>
        <p className="text-sm mt-1">
          Selecciona universidad y carrera en los desplegables para habilitar el boton "Crear plan".
        </p>
      </div>
    </div>
  ),

  materias: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Materias</p>
      <p>
        Las materias son asignaturas asociadas a un plan de estudios. Usa los selectores en cascada
        para navegar Universidad → Carrera → Plan → Materias.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Crear materia:</strong> Selecciona universidad, carrera y plan primero. Completa
          codigo, nombre, horas y cuatrimestre sugerido.
        </li>
        <li>
          <strong>Codigo:</strong> Identificador unico dentro del plan (ej. PROG1, ALG-LIN).
        </li>
        <li>
          <strong>Horas totales:</strong> Carga horaria total. Minimo 16, maximo 500.
        </li>
        <li>
          <strong>Cuatrimestre sugerido:</strong> Numero de cuatrimestre recomendado en el plan (1,
          2, 3...).
        </li>
        <li>
          <strong>Objetivos:</strong> Opcional. Descripcion de objetivos pedagogicos de la materia.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Nota:</p>
        <p className="text-sm mt-1">
          El breadcrumb superior muestra el contexto completo (Universidad / Carrera / Plan) del
          plan seleccionado.
        </p>
      </div>
    </div>
  ),

  comisiones: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Comisiones</p>
      <p>
        Las comisiones son secciones de cursado de una materia en un periodo determinado. Usa los
        selectores en cascada: Universidad → Carrera → Plan → Materia + Periodo.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Crear comision:</strong> Selecciona materia y periodo primero. Completa codigo,
          cupo maximo y budget AI.
        </li>
        <li>
          <strong>Codigo:</strong> Identificador de la comision (ej. C1, ComA). Unico por materia y
          periodo.
        </li>
        <li>
          <strong>Cupo maximo:</strong> Cantidad maxima de estudiantes inscriptos. Default 50.
        </li>
        <li>
          <strong>Budget AI mensual (USD):</strong> Limite de gasto mensual en servicios AI por
          comision. Default 100.00.
        </li>
        <li>
          <strong>Eliminar:</strong> Soft-delete logico. Los datos historicos se preservan para
          auditoria.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Nota:</p>
        <p className="text-sm mt-1">
          Si no hay periodos creados, aparece una alerta. Ve a la pagina de Periodos para crear uno
          antes de gestionar comisiones.
        </p>
      </div>
    </div>
  ),

  clasificaciones: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Clasificaciones N4</p>
      <p>
        Vista de clasificaciones cognitivas N4 agregadas por comision. Muestra distribucion,
        promedios de coherencias y evolucion temporal de los episodios de aprendizaje.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Periodo:</strong> Filtra los episodios por los ultimos 7, 30 o 90 dias.
        </li>
        <li>
          <strong>Distribucion:</strong> Muestra cuantos episodios cayeron en cada categoria N4:
          Delegacion Pasiva, Apropiacion Superficial, Apropiacion Reflexiva.
        </li>
        <li>
          <strong>Coherencias:</strong> Promedios de las 3 coherencias: Temporal (CT), Codigo vs
          Discurso (CCD) e Inter-Iteracion (CII).
        </li>
        <li>
          <strong>Evolucion temporal:</strong> Grafico de barras apiladas por fecha con los 3 tipos
          de apropiacion.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Nota:</p>
        <p className="text-sm mt-1">
          Esta vista requiere que classifier-service este corriendo en el puerto 8008 y que haya
          clasificaciones persistidas para la comision demo.
        </p>
      </div>
    </div>
  ),

  periodos: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Periodos Lectivos</p>
      <p>
        Gestión de periodos academicos (ej. 2026-S1). Cada comision se crea dentro de un periodo.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Crear periodo:</strong> Haz clic en "Nuevo periodo" y completa codigo, nombre,
          fechas de inicio y fin.
        </li>
        <li>
          <strong>Editar:</strong> Modifica nombre y fechas de periodos abiertos. El codigo es
          inmutable.
        </li>
        <li>
          <strong>Cerrar:</strong> Accion irreversible. El periodo queda frozen y no se puede editar
          ni reabrir.
        </li>
        <li>
          <strong>Eliminar:</strong> Falla si el periodo tiene comisiones asociadas.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Nota:</p>
        <p className="text-sm mt-1">El codigo del periodo es inmutable una vez creado.</p>
      </div>
      <div className="bg-danger/50 p-4 rounded-lg mt-2 border border-danger">
        <p className="text-[var(--danger-text)] font-medium">Advertencia:</p>
        <p className="text-sm mt-1">
          Cerrar un periodo es irreversible. No se puede reabrir. Las comisiones del periodo quedan
          congeladas.
        </p>
      </div>
    </div>
  ),

  bulkImport: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Importacion Masiva</p>
      <p>
        Importa entidades academicas desde archivos CSV. El flujo tiene 4 pasos: seleccionar
        entidad, subir archivo, validar (dry-run) y confirmar.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Paso 1 - Entidad:</strong> Elige el tipo de entidad a importar. El panel muestra
          las columnas requeridas y opcionales del CSV.
        </li>
        <li>
          <strong>Paso 2 - Archivo CSV:</strong> Sube un archivo .csv con los datos. La primera fila
          debe ser el encabezado con los nombres de columna.
        </li>
        <li>
          <strong>Paso 3 - Validar:</strong> Ejecuta un dry-run que detecta errores sin escribir en
          la base. Muestra filas invalidas con mensaje de error.
        </li>
        <li>
          <strong>Paso 4 - Confirmar:</strong> Solo se habilita si el dry-run no mostro errores. La
          importacion es atomica: todas o ninguna.
        </li>
        <li>
          <strong>Reiniciar:</strong> Limpia el formulario para empezar una nueva importacion.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Consejo:</p>
        <p className="text-sm mt-1">
          Siempre ejecuta el dry-run primero. Si hay errores, corrige el CSV y vuelve a validar
          antes de confirmar.
        </p>
      </div>
      <div className="bg-danger/50 p-4 rounded-lg mt-2 border border-danger">
        <p className="text-[var(--danger-text)] font-medium">Advertencia:</p>
        <p className="text-sm mt-1">
          La importacion es irreversible. No hay rollback manual disponible una vez confirmada.
          Verifica bien el CSV antes de confirmar.
        </p>
      </div>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-2 border border-sidebar-bg-edge">
        <p className="text-accent-brand font-medium">Inscripciones (estudiantes):</p>
        <p className="text-sm mt-1">
          ADR-029. El CSV requiere comision_id, student_pseudonym (UUID derivado por federacion
          LDAP) y fecha_inscripcion. Rol y estado tienen defaults (regular, activa). Cada
          (comision_id, student_pseudonym) debe ser unico — re-inscripciones legitimas en periodos
          distintos van en filas separadas.
        </p>
      </div>
    </div>
  ),

  auditoria: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Auditoria de integridad CTR</p>
      <p>
        Verifica que la cadena criptografica SHA-256 de un episodio cerrado del piloto NO fue
        manipulada. ADR-031 (D.4) — los aliases publicos /api/v1/audit/* apuntan al ctr-service via
        el ROUTE_MAP del api-gateway.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Episode ID:</strong> UUID del episodio cerrado a verificar. Lo obtenes del
          dashboard de classifier-service o de los exports academicos.
        </li>
        <li>
          <strong>Verificar:</strong> Recomputa el self_hash y chain_hash de cada evento del
          episodio y los compara con los persistidos en ctr_store. Si coinciden TODOS, la cadena
          esta integra.
        </li>
        <li>
          <strong>Failing seq:</strong> Si la verificacion falla, este campo apunta al primer evento
          donde la integridad se rompio. Permite localizar el tampering exacto.
        </li>
        <li>
          <strong>integrity_compromised (flag persistente):</strong> Marcado por el
          integrity-checker en background (ADR-021) — si fue true en algun momento, el flag queda
          aunque la verificacion on-demand pase ahora.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Para que sirve:</p>
        <p className="text-sm mt-1">
          Util para: (a) demos al comite doctoral de la integridad CTR en vivo, (b) diagnostico ante
          sospecha de tampering, (c) reproduccion bit-a-bit en auditorias externas (combinable con
          el JSONL Ed25519 de attestations institucionales, RN-128).
        </p>
      </div>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-2 border border-sidebar-bg-edge">
        <p className="text-accent-brand font-medium">Append-only:</p>
        <p className="text-sm mt-1">
          ADR-010. El CTR NO permite UPDATE ni DELETE de eventos. Esta auditoria es la prueba
          empirica del invariante — si la cadena no verifica, hay tampering en la base.
        </p>
      </div>
    </div>
  ),

  byok: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">BYOK Keys</p>
      <p>
        Bring Your Own Key (BYOK) permite que cada universidad use su propia clave de proveedor LLM
        (Anthropic, OpenAI, Gemini, Mistral) en vez del presupuesto global del sistema. Las claves
        se encriptan con AES-256-GCM y nunca se devuelven en claro. (ADR-038, ADR-039)
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Scope tenant:</strong> La key aplica a toda la universidad. Es el fallback
          si no hay key de scope materia configurada.
        </li>
        <li>
          <strong>Scope materia:</strong> Sobrescribe el scope tenant para esa materia especifica.
          Util para materias con presupuesto propio.
        </li>
        <li>
          <strong>Rotar:</strong> Reemplaza el valor encriptado con una nueva API key del proveedor.
          El fingerprint se actualiza. Las keys en uso del ai-gateway pasan al nuevo valor
          automaticamente.
        </li>
        <li>
          <strong>Revocar:</strong> Marca la key como inactiva. Irreversible. El resolver BYOK
          cae al env_fallback si no hay otra key activa para ese scope.
        </li>
        <li>
          <strong>Uso:</strong> Muestra tokens consumidos y costo estimado por periodo mensual.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Resolver jerarquico:</p>
        <p className="text-sm mt-1">
          El ai-gateway resuelve keys en orden: materia =&gt; tenant =&gt; env_fallback. Si se
          revocan todas las keys de un scope, el resolver degrada al nivel siguiente.
        </p>
      </div>
      <div className="bg-danger/50 p-4 rounded-lg mt-2 border border-danger">
        <p className="text-[var(--danger-text)] font-medium">Seguridad:</p>
        <p className="text-sm mt-1">
          Las keys BYOK nunca se devuelven en claro por ningun endpoint. Solo se expone el
          fingerprint (ultimos 4 caracteres). Guardar el plaintext en un gestor de passwords antes
          de crear la key — una vez creada no hay forma de recuperarla, solo rotarla.
        </p>
      </div>
    </div>
  ),

  governanceEvents: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Eventos de gobernanza</p>
      <p>
        Vista institucional cross-cohort de los <strong>intentos adversos detectados</strong> por el
        guardrails Fase A del tutor (ADR-019, RN-129). El sistema matchea el prompt del estudiante
        contra un corpus regex ANTES de pegarle al LLM y emite un evento side-channel al CTR — NO
        bloquea el flow, el prompt llega al modelo igual.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Categorias:</strong> jailbreak_indirect, jailbreak_substitution,
          jailbreak_fiction, persuasion_urgency, prompt_injection. Cada una refleja una tactica
          distinta.
        </li>
        <li>
          <strong>Severidad 1-5:</strong> escala del corpus. Sev &gt;=3 dispara refuerzo pedagogico
          inyectado al prompt del tutor (Seccion 8.5.1 de la tesis).
        </li>
        <li>
          <strong>Filtros cascade:</strong> facultad =&gt; materia =&gt; periodo. La pagina permite
          slice institucional o granular hasta una comision especifica.
        </li>
        <li>
          <strong>Exportar CSV:</strong> conjunto filtrado actual con headers ASCII (cp1252-safe en
          Windows). Filename incluye timestamp ISO + filtros.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4 border border-sidebar-bg-edge">
        <p className="text-accent-brand font-medium">Solo lectura:</p>
        <p className="text-sm mt-1">
          ADR-037. La pagina NO permite mutaciones ni workflow "marcar revisado" — eso queda
          diferido a piloto-2 con tabla governance_event_reviews. El CTR es append-only por diseno.
        </p>
      </div>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-2 border border-sidebar-bg-edge">
        <p className="text-warning font-medium">Que NO es:</p>
        <p className="text-sm mt-1">
          NO es deteccion de plagio. NO es deteccion automatica de mala-conducta. Es un instrumento
          de visibilidad pedagogica: el docente/admin puede ver patrones agregados de presion sobre
          el tutor, no individuos a sancionar.
        </p>
      </div>
    </div>
  ),
}
