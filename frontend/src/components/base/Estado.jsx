import React from "react";
import { cn } from "@/lib/utils";
import Boton from "./Boton";

/* Estado · cargando / vacío / error
   ─────────────────────────────────────────────────────────────────────────────
   El hallazgo que obliga a que esto exista: hoy un fallo de red es indistinguible
   de "no hay nada". En la Cartera, un error de carga se presenta literalmente como
   "Sin acciones todavía", que es una mentira con consecuencias: el usuario cree que
   su cartera está vacía cuando lo que pasa es que el servidor no contestó.

   Son tres estados DISTINTOS y tienen que verse distintos:

     Cargando → hay una petición en curso. Se dibuja con la FORMA del contenido que
                va a llegar, no con un spinner centrado: así la página no da un salto
                al rellenarse y se intuye qué está por venir.
     Vacío    → la petición fue bien y la respuesta no trae nada. Obligatorio decir
                POR QUÉ está vacío y, si se puede, qué hacer para que no lo esté.
     Error    → la petición falló. Obligatorio decir la causa y ofrecer reintentar.

   La regla que se deduce: un estado vacío sin motivo es un estado a medias. Por eso
   `motivo` no tiene valor por defecto — si no sabes qué escribir ahí, probablemente
   el bloque no debería estar vacío, sino no estar. */

/** Bloque gris con la forma del contenido. `filas` y `alto` para parecerse a lo que viene. */
export function Cargando({ filas = 3, alto = "h-4", className, etiqueta = "Cargando…" }) {
  return (
    <div className={cn("space-y-2", className)} role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{etiqueta}</span>
      {Array.from({ length: filas }).map((_, i) => (
        <div
          key={i}
          className={cn("rounded-iv-sm bg-linea/60 animate-pulse", alto)}
          // Anchos decrecientes: un bloque de barras idénticas parece una tabla rota;
          // así se lee como texto que todavía no ha llegado.
          style={{ width: `${100 - i * 12}%`, animationDelay: `${i * 90}ms` }}
        />
      ))}
    </div>
  );
}

/**
 * Vacío honesto.
 * @param titulo  Qué no hay. "Tus fuentes no han hablado de NVDA."
 * @param motivo  Por qué no hay. "En los últimos 30 días." — sin esto el bloque miente a medias.
 * @param accion  Opcional: { texto, onClick } para ampliar el criterio o crear el primer elemento.
 */
export function Vacio({ titulo, motivo, accion, icono = null, className }) {
  return (
    <div className={cn("text-center py-8 px-4", className)}>
      {icono && <div className="mb-2 flex justify-center text-tinta-3">{icono}</div>}
      <p className="text-cuerpo text-tinta font-medium">{titulo}</p>
      {motivo && <p className="text-apoyo text-tinta-3 mt-1 max-w-prose mx-auto">{motivo}</p>}
      {accion && (
        <Boton variante="contorno" tamano="sm" className="mt-3" onClick={accion.onClick}>
          {accion.texto}
        </Boton>
      )}
    </div>
  );
}

/**
 * Error con causa y salida.
 * @param error         El Error o la respuesta de axios. Se le saca el mensaje útil.
 * @param onReintentar  Si se pasa, sale el botón. Casi siempre debería pasarse.
 */
export function Error_({ error, onReintentar, titulo = "No se han podido cargar los datos", className }) {
  return (
    <div
      className={cn("text-center py-8 px-4 border border-baja/30 bg-baja/5 rounded-iv", className)}
      role="alert"
    >
      <p className="text-cuerpo text-tinta font-medium">{titulo}</p>
      <p className="text-apoyo text-tinta-2 mt-1 max-w-prose mx-auto">{mensajeDe(error)}</p>
      {onReintentar && (
        <Boton variante="contorno" tamano="sm" className="mt-3" onClick={onReintentar}>
          Reintentar
        </Boton>
      )}
    </div>
  );
}

/** Saca el mensaje más útil que haya, en lenguaje normal.
 *
 *  El orden importa: el `detail` del backend está escrito para leerse ("Sesión
 *  expirada o inválida"), y es mejor que el `message` de axios ("Request failed
 *  with status code 401"), que está escrito para un log. */
export function mensajeDe(error) {
  if (!error) return "Error desconocido.";
  const detalle = error?.response?.data?.detail;
  if (typeof detalle === "string" && detalle) return detalle;
  const status = error?.response?.status;
  if (status === 401) return "Tu sesión ha caducado. Vuelve a iniciar sesión.";
  if (status === 404) return "No se ha encontrado el dato que pedía esta pantalla.";
  if (status === 429) return "Se ha alcanzado el límite de peticiones del proveedor de datos. Prueba en un minuto.";
  if (status >= 500) return "El servidor ha fallado al preparar la respuesta.";
  if (error?.code === "ECONNABORTED") return "La petición ha tardado demasiado y se ha cancelado.";
  if (error?.message === "Network Error") return "No hay conexión con el servidor.";
  return error?.message || "Error desconocido.";
}

/**
 * Atajo para el caso corriente: envuelve el contenido y elige el estado.
 * Deja pasar `children` solo cuando de verdad hay algo que enseñar.
 */
export default function Estado({
  cargando, error, vacio, onReintentar,
  tituloVacio = "No hay nada que mostrar", motivoVacio, accionVacio,
  filasCargando = 3, children,
}) {
  if (cargando) return <Cargando filas={filasCargando} />;
  if (error) return <Error_ error={error} onReintentar={onReintentar} />;
  if (vacio) return <Vacio titulo={tituloVacio} motivo={motivoVacio} accion={accionVacio} />;
  return children;
}

export { Error_ as Error };
