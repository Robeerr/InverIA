import React from "react";
import { AlertTriangle } from "lucide-react";

// Red de seguridad: si cualquier componente lanza una excepción al renderizar, en vez de
// dejar la PANTALLA EN BLANCO (especialmente en el iPhone), mostramos un mensaje amable con
// un botón para reintentar. Los Error Boundaries de React deben ser componentes de clase.
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // Log en consola para depurar; no rompemos la app.
    // eslint-disable-next-line no-console
    console.error("ErrorBoundary capturó un error de render:", error, info);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="max-w-md mx-auto mt-20 mb-10 px-4">
          <div className="iv-panel p-7 text-center">
          <p className="mb-4 mx-auto grid place-items-center h-11 w-11 rounded-[12px] bg-baja/10 text-baja">
            <AlertTriangle size={20} strokeWidth={1.75} aria-hidden="true" />
          </p>
          <h2 className="text-titulo font-semibold text-tinta mb-2">Algo se ha roto en esta vista</h2>
          <p className="text-apoyo text-tinta-2 mb-6">
            No te preocupes, tus datos están a salvo. Prueba a recargar o volver a la pantalla principal.
          </p>
          <div className="flex gap-2 justify-center">
            <button
              onClick={() => window.location.reload()}
              className="h-10 px-4 rounded-[10px] iv-boton-brillo text-apoyo font-medium hover:brightness-[1.08]"
            >
              Recargar
            </button>
            <button
              onClick={() => { this.handleReset(); window.location.href = "/"; }}
              className="h-10 px-4 rounded-[10px] border border-medio text-tinta-2 text-apoyo font-medium hover:bg-tinta/[0.05] hover:text-tinta"
            >
              Ir al inicio
            </button>
          </div>
          {/* El detalle técnico, plegado. Esta pantalla salió varias veces sin decir NUNCA
              qué se había roto: había que pedir la consola del navegador para saberlo, y
              desde el móvil eso no es viable. El mensaje de una excepción suele señalar la
              línea culpable directamente. Va plegado para no asustar a quien solo quiere
              recargar, y seleccionable para poder copiarlo y pegarlo. */}
          {this.state.error && (
            <details className="mt-6 text-left">
              <summary className="text-apoyo text-tinta-3 cursor-pointer select-none">
                Detalle técnico
              </summary>
              <pre className="mt-2 p-3 rounded-[10px] bg-superficie-alt text-tinta text-etiqueta font-mono whitespace-pre-wrap break-words select-all max-h-48 overflow-auto">
                {String(this.state.error?.message || this.state.error)}
              </pre>
            </details>
          )}
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
