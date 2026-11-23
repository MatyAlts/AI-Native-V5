// La regla de evitar Unicode (cp1252 en Windows) aplica a stdout de scripts Python, no a TSX servido al browser.
import type { ReactNode } from "react"

type HelpContentMap = Record<string, ReactNode>

export const helpContent: HelpContentMap = {
  episode: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">
        Tutor Socratico de Programacion
      </p>
      <p>
        Esta es tu estacion de trabajo para resolver trabajos prácticos (TPs) con asistencia de un
        tutor socratico. El tutor no te da la respuesta directa — te guia con preguntas para que
        construyas tu solucion.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Seleccionar comision:</strong> Arriba a la derecha elegis la comision en la que
          estas cursando.
        </li>
        <li>
          <strong>Elegir TP:</strong> Se listan las tareas disponibles de tu comision. Haz clic en
          una para abrir el episodio.
        </li>
        <li>
          <strong>Descargar:</strong> <em>Borrador</em> es lo que tenes ahora en el editor;{" "}
          <em>lo entregado</em> es lo que vio tu docente al corregir.
        </li>
        <li>
          <strong>Enunciado:</strong> Panel colapsable arriba del editor con la consigna de la TP.
        </li>
        <li>
          <strong>Editor de codigo:</strong> Escribis tu codigo Python, lo ejecutas con Pyodide en
          el navegador.
        </li>
        <li>
          <strong>Chat con el tutor:</strong> A la derecha. Enter envia. Shift+Enter agrega una
          linea.
        </li>
        <li>
          <strong>Cerrar episodio:</strong> Cuando termines, cerras el episodio y recibis una
          devolucion sobre como trabajaste.
        </li>
        <li>
          <strong>Pedir ayuda a tu docente:</strong> Si algo no anda o te trabaste, usa el boton
          &quot;Pedir ayuda a tu docente&quot;: le llega a tu docente con el ejercicio adjunto. No
          es una pista; el tutor sigue siendo tu ayuda para resolver.
        </li>
        <li>
          <strong>Cambiar TP:</strong> Cierra el episodio actual y volves al selector. No perdes lo
          hecho: queda registrado en el CTR.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-4">
        <p className="text-warning font-medium">Consejo:</p>
        <p className="text-sm mt-1">
          Si recargas la pestana (F5), tu episodio se recupera automáticamente. Si cerras la
          pestana, el episodio queda abierto pero volves al selector la proxima vez.
        </p>
      </div>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-2">
        <p className="text-warning font-medium">Que mira la devolucion:</p>
        <ul className="text-sm mt-2 space-y-1">
          <li>
            <strong>Constancia:</strong> si trabajaste de forma sostenida, sin tantas pausas.
          </li>
          <li>
            <strong>Codigo y charla:</strong> si lo que escribis en el codigo va de la mano con lo
            que le contas al tutor.
          </li>
          <li>
            <strong>Tus consultas:</strong> si tus preguntas al tutor siguen un hilo, en vez de
            saltar de un tema a otro.
          </li>
        </ul>
      </div>
    </div>
  ),
  reflexiones: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Mis reflexiones</p>
      <p>
        Despues de cerrar un episodio, podes dejar una reflexion metacognitiva de un minuto: lo que
        penso, lo que te trabo, lo que aprendiste. Aca podes releerlas cuando quieras.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Solo tuyas:</strong> el listado filtra por tu identidad — nadie mas ve tus
          reflexiones, ni el docente ni otros alumnos.
        </li>
        <li>
          <strong>No se califican:</strong> no hay nota ni feedback. Son para vos.
        </li>
        <li>
          <strong>Append-only:</strong> una vez enviada queda registrada en la cadena criptografica
          del episodio (ADR-035). No se editan ni se borran.
        </li>
        <li>
          <strong>No cambian tu devolucion:</strong> el sistema no las usa para mirar como
          trabajaste (ADR-027). Las podes dejar en blanco sin penalizacion.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-2">
        <p className="text-warning font-medium">Como volves a ver una?</p>
        <p className="text-sm mt-1">
          Aparecen ordenadas de mas reciente a mas antigua. Cada card muestra la TP, la fecha de
          cierre del episodio y las tres respuestas tal como las escribiste.
        </p>
      </div>
    </div>
  ),
  misNotas: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Mis notas</p>
      <p>
        Todas tus entregas calificadas de esta comision, en un solo lugar — aunque el docente haya
        archivado el trabajo practico despues de corregirlo.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Con nota:</strong> entregas ya calificadas. Hace click para ver la correccion
          completa del docente y el codigo que entregaste en cada ejercicio, que podes descargar.
        </li>
        <li>
          <strong>Sin corregir todavia:</strong> ya entregaste, el docente todavia no la reviso.
        </li>
        <li>
          <strong>Por comision:</strong> si cursas mas de una materia, elegis cual ver arriba.
        </li>
      </ul>
    </div>
  ),
}
