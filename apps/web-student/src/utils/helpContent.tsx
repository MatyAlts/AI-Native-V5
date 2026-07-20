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
          <strong>Cerrar episodio:</strong> Cuando termines, cerras el episodio y recibis tu
          clasificacion pedagogica (3 coherencias N4).
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
        <p className="text-warning font-medium">Las tres coherencias N4:</p>
        <ul className="text-sm mt-2 space-y-1">
          <li>
            <strong>Temporal (CT):</strong> Patron de trabajo sostenido en el tiempo.
          </li>
          <li>
            <strong>Codigo-Discurso (CCD):</strong> Alineacion entre lo que codeas y lo que
            verbalizas con el tutor.
          </li>
          <li>
            <strong>Inter-iteracion (CII):</strong> Estabilidad y evolucion de tu trabajo entre
            intentos.
          </li>
        </ul>
      </div>
    </div>
  ),
  reflexiones: (
    <div className="space-y-4 text-muted-soft">
      <p className="text-lg font-medium text-[var(--text-inverse)]">Mis reflexiones</p>
      <p>
        Despues de cerrar un episodio, podes dejar una reflexion metacognitiva de un
        minuto: lo que penso, lo que te trabo, lo que aprendiste. Aca podes releerlas
        cuando quieras.
      </p>
      <ul className="list-disc list-inside space-y-2 ml-4">
        <li>
          <strong>Solo tuyas:</strong> el listado filtra por tu identidad — nadie mas ve
          tus reflexiones, ni el docente ni otros alumnos.
        </li>
        <li>
          <strong>No se califican:</strong> no hay nota ni feedback. Son para vos.
        </li>
        <li>
          <strong>Append-only:</strong> una vez enviada queda registrada en la cadena
          criptografica del episodio (ADR-035). No se editan ni se borran.
        </li>
        <li>
          <strong>No afectan tu clasificacion N4:</strong> el clasificador ignora las
          reflexiones (ADR-027). Las podes dejar en blanco sin penalizacion.
        </li>
      </ul>
      <div className="bg-sidebar-bg-edge p-4 rounded-lg mt-2">
        <p className="text-warning font-medium">Como volves a ver una?</p>
        <p className="text-sm mt-1">
          Aparecen ordenadas de mas reciente a mas antigua. Cada card muestra la TP, la
          fecha de cierre del episodio y las tres respuestas tal como las escribiste.
        </p>
      </div>
    </div>
  ),
}
